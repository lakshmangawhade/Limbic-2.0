"""
CNSVS Cognitive Report Parse Backend
FastAPI server exposing /parse-cnsvs to accept multi-file PDF uploads
and return structured JSON consumed by index.html's CNSVS dashboard.
"""

import os
import re
import uuid
import traceback
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_THIS_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

DOMAIN_NAMES = [
    "Neurocognition Index (NCI)", "Composite Memory", "Verbal Memory", "Visual Memory",
    "Psychomotor Speed", "Reaction Time", "Complex Attention", "Cognitive Flexibility",
    "Processing Speed", "Executive Function", "Social Acuity", "Reasoning",
    "Working Memory", "Sustained Attention", "Simple Attention", "Motor Speed",
]

SPECIFIC_TEST_NAMES = [
    "Verbal Memory Test (VBM)", "Visual Memory Test (VSM)", "Finger Tapping Test (FTT)",
    "Symbol Digit Coding (SDC)", "Stroop Test (ST)", "Shifting Attention Test (SAT)",
    "Continuous Performance Test (CPT)", "Perception Of Emotions Test (POET)",
    "Positive Emotions", "Negative Emotions", "Reasoning Test (RT)",
]
FOUR_PART_NAMES = ["Part 1", "Part 2", "Part 3", "Part 4"]
CANONICAL_TESTS = SPECIFIC_TEST_NAMES + ["Four Part Continuous Performance Test"] + FOUR_PART_NAMES
FLAG_THRESHOLD = 30


def _find_index_html() -> Optional[Path]:
    for p in [_THIS_DIR / "index.html", _THIS_DIR.parent / "index.html", Path.cwd() / "index.html", Path.cwd().parent / "index.html"]:
        if p.exists():
            logger.info("Serving index.html from: %s", p)
            return p
    return None


app = FastAPI(title="CNSVS Cognitive Report Parse Service", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


def clean_text(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "").replace("\n", " ")).strip()


def num(v: Any) -> Optional[float]:
    if v is None:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", str(v).replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean_text(s).lower())


def canonical_domain(name: str) -> Optional[str]:
    n = norm(name)
    if not n:
        return None
    for d in DOMAIN_NAMES:
        dn = norm(d)
        if n == dn or n in dn or dn in n:
            return d
    return None


def canonical_test(name: str) -> Optional[str]:
    n = norm(name)
    if not n:
        return None
    for t in CANONICAL_TESTS:
        tn = norm(t)
        if n == tn or n in tn or tn in n:
            return t
    return None


def make_entry(metric: str, ss: Any, perc: Any) -> Optional[Dict[str, Any]]:
    standard_score = num(ss)
    percentile = num(perc)
    metric = clean_text(metric).strip("·•-* :")
    if not metric or standard_score is None or percentile is None:
        return None
    if not (0 <= percentile <= 100) or not (0 <= standard_score <= 300):
        return None
    return {
        "metric": metric,
        "standard_score": standard_score,
        "percentile": percentile,
        "flagged": percentile < FLAG_THRESHOLD,
    }


def add_unique_domain(domain_scores: List[Dict], entry: Dict, domain_name: str) -> None:
    item = {**entry, "domain": domain_name, "metric": domain_name}
    key = norm(domain_name)
    if not any(norm(x.get("domain", "")) == key for x in domain_scores):
        domain_scores.append(item)


def add_unique_test(tests: Dict[str, List[Dict]], test_name: str, entry: Dict) -> None:
    tests.setdefault(test_name, [])
    key = (norm(entry.get("metric", "")), entry.get("standard_score"), entry.get("percentile"))
    existing = {(norm(x.get("metric", "")), x.get("standard_score"), x.get("percentile")) for x in tests[test_name]}
    if key not in existing:
        tests[test_name].append(entry)


def extract_text_from_pdf(pdf_path: str) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join(page.extract_text(x_tolerance=1, y_tolerance=3) or "" for page in pdf.pages)
    except Exception as exc:
        logger.warning("pdfplumber text extraction failed: %s", exc)
    try:
        import PyPDF2
        with open(pdf_path, "rb") as f:
            return "\n".join(page.extract_text() or "" for page in PyPDF2.PdfReader(f).pages)
    except Exception as exc:
        logger.error("PDF text extraction failed: %s", exc)
        return ""


def extract_tables_from_pdf(pdf_path: str) -> List[List[List[Any]]]:
    try:
        import pdfplumber
        tables: List[List[List[Any]]] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables.extend(page.extract_tables() or [])
        return tables
    except Exception as exc:
        logger.warning("pdfplumber table extraction failed: %s", exc)
        return []


def parse_tables(tables: List[List[List[Any]]]) -> Tuple[List[Dict], Dict[str, List[Dict]]]:
    domain_scores: List[Dict] = []
    tests: Dict[str, List[Dict]] = {}
    current_test: Optional[str] = None

    for table in tables:
        if not table:
            continue
        for row in table:
            cells = [clean_text(c) for c in row if clean_text(c)]
            if not cells:
                continue
            row_text = " ".join(cells)

            # Update current section/test whenever a row contains a canonical test header.
            found_test = canonical_test(row_text)
            if found_test:
                current_test = None if found_test == "Four Part Continuous Performance Test" else found_test
                if current_test:
                    tests.setdefault(current_test, [])
                continue

            # Domain rows usually contain Domain Name + T score/standard score + percentile.
            dname = canonical_domain(cells[0])
            numeric_cells = [num(c) for c in cells[1:] if num(c) is not None]
            if dname and len(numeric_cells) >= 2:
                entry = make_entry(dname, numeric_cells[-2], numeric_cells[-1])
                if entry:
                    add_unique_domain(domain_scores, entry, dname)
                continue

            # Test metric rows inside current test. Use the last two numeric values as standard score and percentile.
            if current_test and len(numeric_cells) >= 2:
                metric = cells[0]
                if canonical_test(metric) or canonical_domain(metric) or norm(metric) in {"standard", "percentile", "score", "rawscore"}:
                    continue
                entry = make_entry(metric, numeric_cells[-2], numeric_cells[-1])
                if entry:
                    add_unique_test(tests, current_test, entry)

    return domain_scores, tests


def parse_text(text: str) -> Tuple[List[Dict], Dict[str, List[Dict]]]:
    domain_scores: List[Dict] = []
    tests: Dict[str, List[Dict]] = {}
    section: Optional[str] = None
    current_test: Optional[str] = None

    bullet_re = re.compile(r"[·•\-*]?\s*(.+?):\s*Standard\s+Score:\s*(-?\d+(?:\.\d+)?)\s*\|?\s*Percentile:\s*(-?\d+(?:\.\d+)?)(.*)", re.I)
    raw_row_re = re.compile(r"^([A-Za-z][A-Za-z\s()*/'\-]+?)\s+((?:-?\d{1,3}(?:\.\d+)?\s+)*-?\d{1,3}(?:\.\d+)?)\s*$")

    for raw in text.splitlines():
        line = clean_text(raw)
        if not line:
            continue
        if re.search(r"Cognitive\s+Domain\s+Scores", line, re.I):
            section, current_test = "domain", None
            continue
        if re.search(r"Specific\s+Test\s+Scores", line, re.I):
            section, current_test = "specific", None
            continue
        if re.fullmatch(r"Four\s+Part\s+Continuous\s+Performance\s+Test:?,?", line, re.I):
            section, current_test = "fourpart", None
            continue

        found_test = canonical_test(line)
        if found_test:
            if found_test == "Four Part Continuous Performance Test":
                section, current_test = "fourpart", None
            else:
                current_test = found_test
                tests.setdefault(current_test, [])
            continue

        m = bullet_re.match(line)
        if m:
            entry = make_entry(m.group(1), m.group(2), m.group(3))
        else:
            m2 = raw_row_re.match(line)
            entry = None
            if m2:
                values = [float(x) for x in m2.group(2).split()]
                if len(values) >= 2:
                    entry = make_entry(m2.group(1), values[-2], values[-1])

        if not entry:
            continue
        dname = canonical_domain(entry["metric"])
        if section == "domain" or (dname and current_test is None):
            add_unique_domain(domain_scores, entry, dname or entry["metric"])
        elif current_test:
            add_unique_test(tests, current_test, entry)

    return domain_scores, tests


def parse_cnsvs_pdf(pdf_path: str, pdf_name: str) -> Dict[str, Any]:
    table_domains, table_tests = parse_tables(extract_tables_from_pdf(pdf_path))
    text_domains, text_tests = parse_text(extract_text_from_pdf(pdf_path))

    domain_scores = table_domains[:]
    for d in text_domains:
        add_unique_domain(domain_scores, d, d.get("domain") or d.get("metric"))

    tests = {k: v[:] for k, v in table_tests.items()}
    for t, rows in text_tests.items():
        for r in rows:
            add_unique_test(tests, t, r)

    return {
        "pdf_name": pdf_name,
        "processing_timestamp": datetime.now(timezone.utc).isoformat(),
        "domain_scores": domain_scores,
        "tests": tests,
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(status_code=500, content={"error": {"message": f"Internal server error: {str(exc)}"}})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": {"message": str(exc)}})


@app.get("/health")
async def health():
    return {"status": "ok", "service": "cnsvs-parse"}


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    html_path = _find_index_html()
    if html_path is None:
        raise HTTPException(status_code=404, detail="index.html not found. Place it next to main.py or at the project root.")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.post("/parse-cnsvs")
async def parse_cnsvs(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    sessions, errors = [], []
    for upload in files:
        filename = upload.filename or "uploaded.pdf"
        if not filename.lower().endswith(".pdf"):
            errors.append({"file": filename, "error": "Not a PDF file."})
            continue

        pdf_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}.pdf")
        try:
            with open(pdf_path, "wb") as f:
                f.write(await upload.read())
            session = parse_cnsvs_pdf(pdf_path, filename)
            sessions.append(session)
            logger.info("Parsed %s: %d domains, %d tests", filename, len(session["domain_scores"]), len(session["tests"]))
        except Exception as exc:
            logger.error("Failed to parse %s: %s\n%s", filename, exc, traceback.format_exc())
            errors.append({"file": filename, "error": str(exc)})
        finally:
            try:
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
            except Exception:
                pass

    if not sessions and errors:
        raise HTTPException(status_code=422, detail=f"All files failed to parse. Errors: {errors}")
    return JSONResponse(content=sessions)


@app.post("/api/messages")
async def proxy_messages(request: Request):
    import httpx
    body = await request.json()
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return JSONResponse(status_code=503, content={"error": {"message": "ANTHROPIC_API_KEY not configured"}})
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            json={**body, "model": body.get("model", "claude-sonnet-4-20250514")},
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        )
    return JSONResponse(status_code=resp.status_code, content=resp.json())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
