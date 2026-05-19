"""
Extract CNSVS Scales (GAD-7, NPQ SF-45, PHQ-9, PSQI, PCL-5) using Groq Llama models.
Falls back to regex parsing when Groq is unavailable or fails.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

CANONICAL_SCALE_NAMES = [
    "Generalized Anxiety Disorder 7-item (GAD-7) Scale",
    "NeuroPsych Questionnaire (NPQ) SF-45",
    "Patient Health Questionnaire (PHQ-9)",
    "Pittsburgh Sleep Quality Index (PSQI) SF-10",
    "The PTSD Checklist (PCL-5) SF-20",
]

# One-line extraction hint prepended to each section in the user message
_SECTION_HINTS: Dict[str, str] = {
    "Generalized Anxiety Disorder 7-item (GAD-7) Scale": (
        "Expect: 7 lines 'N <question> <0-3> - <response>' + total 'GAD-7 Anxiety Severity <n>'."
    ),
    "NeuroPsych Questionnaire (NPQ) SF-45": (
        "Expect: 12 domain rows (name + score 0-300 + severity) + blocks '<Domain> Questions' with numbered items."
    ),
    "Patient Health Questionnaire (PHQ-9)": (
        "Expect: items 1-9 (0-3), item 10 functional impairment, total 'PHQ-9 Score <n>'."
    ),
    "Pittsburgh Sleep Quality Index (PSQI) SF-10": (
        "Expect: domain score table (two columns per line possible) + 'PSQI Total Score <n>' + optional items 1-10."
    ),
    "The PTSD Checklist (PCL-5) SF-20": (
        "Expect: 4 cluster subtotals + 'Total Score (Items 1 - 20)' + items 1-20 with scores 1-5."
    ),
}

SYSTEM_PROMPT = """You extract structured numeric results from CNS Vital Signs (CNSVS) PDF text for exactly five clinical scales.

Your job is to read messy, line-broken plain text (not tables) and output ONLY patient-reported scores that appear in the report. Be precise: copy question wording from the text; never guess or compute totals yourself.

=== CANONICAL JSON KEYS (use exactly, spelling and punctuation) ===
1. "Generalized Anxiety Disorder 7-item (GAD-7) Scale"
2. "NeuroPsych Questionnaire (NPQ) SF-45"
3. "Patient Health Questionnaire (PHQ-9)"
4. "Pittsburgh Sleep Quality Index (PSQI) SF-10"
5. "The PTSD Checklist (PCL-5) SF-20"

=== OUTPUT FORMAT ===
Return a single JSON object (no markdown fences, no explanation):
{
  "scales": {
    "<canonical scale name>": [
      {
        "metric": "<label>",
        "score": <number>,
        "severity": "<string or empty>",
        "response": "<string or empty>",
        "row_type": "item" | "domain" | "total"
      }
    ]
  }
}

Field rules:
- score: numeric only (integer or float). Must match a number printed in the source line for that row.
- response: text after " - " or " – " on the same item line (e.g. "Nearly every day", "A severe problem", "Extremely"). Empty string if none.
- severity: NPQ domain rows only (e.g. "Severe", "Moderate", "Mild", "Not a problem"). Empty for items and other scales unless explicitly labeled.
- row_type: "item" = single question; "domain" = NPQ domain summary or PSQI domain; "total" = instrument total / cluster subtotal line.

=== IGNORE (do not output rows for these) ===
- Patient ID, test date, age, administrator, duration, version headers
- Scoring instructions, interpretation bands (e.g. "0-4 None-Minimal anxiety", "5-9 Mild")
- Copyright / developer footnotes
- Narrative paragraphs (NPQ description text mixed into the domain table)
- Column headers alone ("Domain Score Severity Description")
- Item numbers alone — always pair the question text with its score

=== SCALE-SPECIFIC PATTERNS ===

--- GAD-7 ---
Section title contains "GAD-7".
Items look like:
  "1 Feeling nervous, anxious or on edge 3 - Nearly every day"
  (leading number = item index, trailing number before dash = score 0-3)
Also accept bullet/colon form: "• text: 3 - Nearly every day"
metric for numbered items: "Item <n>: <question text>" (include item number in metric).
Total line (row_type "total"):
  "GAD-7 Anxiety Severity 21"  → metric "GAD-7 Anxiety Severity (Total)", score 21

--- PHQ-9 ---
Same item pattern as GAD-7 for items 1-9 (score 0-3).
Total (row_type "total"):
  "PHQ-9 Score 23" → metric "PHQ-9 Score (Total)", score 23
Item 10 (functional impairment) may appear as:
  "10. How difficult have the problems..." or continuation on next lines with "4 - Extremely difficult"
→ metric "Item 10: How difficult have the problems you reported made it for you to do your work, take care of things at home, or get along with other people?", score 0-4, row_type "item"; response must end before the word "Developed"
Item 8 may wrap across two lines; still extract one row if score/response are present.

--- NPQ SF-45 ---
Two layers — extract BOTH:

(A) Domain summaries (row_type "domain") — exactly these 12 names as metric:
Attention, Impulsive, Memory, Anxiety, Panic, Depression, Mood Stability, Aggression, Fatigue, Sleep, Suicide, Pain
Table rows look like: "Attention 300 Severe" or "Suicide 0 Not a problem"
(score is 0-300; severity is the word after the score)
Ignore descriptive text glued on the same line (long sentences after severity).

(B) Question items under "<Domain> Questions" headers (row_type "item"):
  "Attention Questions" then lines like "1 Difficulty concentrating 3 - A severe problem"
metric MUST be "<Domain> · <question text>" — e.g. "Attention · Difficulty concentrating"
(Do not use "Item 1:" prefix for NPQ questions; use Domain · question.)
Score is the number before " - " (typically 0-3). Response is after the dash.

--- PSQI SF-10 ---
(A) Domain scores from the compact table (row_type "domain"):
  Two columns per line are common, e.g. "Duration Of Sleep 1 Sleep Disturbance 2"
  Extract each domain name with its score separately.
  Domains include: Duration Of Sleep, Sleep Latency, Sleep Efficiency, Need Meds To Sleep,
  Sleep Disturbance, Day Dysfunction Due To Sleepiness, Overall Sleep Quality, etc.
(B) Total (row_type "total"):
  "PSQI Total Score 17" → metric "PSQI Total Score", score 17
(C) Optional detailed items 1-10 and sub-items a-j if they have "N - response" or time answers:
  metric = full question text; score = numeric part if present (some answers are times/text — use numeric score only when a clear 0-3 style number appears before the dash)

--- PCL-5 SF-20 ---
(A) Cluster subtotals (row_type "domain" unless label says Total):
  "Intrusion (Items 1 - 5) 25"
  "Persistent Avoidance (Items 6 - 7) 10"
  "Negative Alterations in Cognitions and Mood (Items 8 - 14) 30"
  "Alterations in Arousal and Reactivity (Items 15 - 20) 24"
  metric = cluster name without "(Items ...)" suffix; score = trailing number.
(B) Grand total (row_type "total"):
  "Total Score (Items 1 - 20) 89" → metric "Total Score (Items 1 - 20)", score 89
(C) Items 1-20 (row_type "item"):
  "1 Repeated, disturbing, and unwanted memories...? 5 - Extremely"
  metric = "Item <n>: <question text>" (question may end with ?)
  score = 1-5 before the dash; response = text after dash

=== VALIDATION CHECKLIST (before responding) ===
- Every scale section present in the input should appear in output (empty array only if that scale truly has no scores).
- GAD-7: 7 items + 1 total (8 rows minimum when complete).
- PHQ-9: 9 items + item 10 + 1 total when present.
- NPQ: 12 domain rows + all question rows under each "* Questions" block.
- PSQI: all domain scores + PSQI Total Score.
- PCL-5: 4 clusters + total + up to 20 items when listed.
- No duplicate metrics within a scale.
- Do not invent scores; if a line is ambiguous, skip it rather than guess.

=== EXAMPLE (truncated) ===
Input snippet:
"1 Feeling nervous, anxious or on edge 3 - Nearly every day
GAD-7 Anxiety Severity 21"
Output row:
{"metric": "Item 1: Feeling nervous, anxious or on edge", "score": 3, "severity": "", "response": "Nearly every day", "row_type": "item"}
{"metric": "GAD-7 Anxiety Severity (Total)", "score": 21, "severity": "", "response": "", "row_type": "total"}
"""


def _groq_enabled() -> bool:
    key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not key:
        return False
    mode = (os.getenv("SCALES_EXTRACTION_MODE") or "llm").strip().lower()
    return mode in ("llm", "hybrid", "groq", "auto", "")


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    m = re.search(r"-?\d+(?:\.\d+)?", str(v).replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _normalize_row(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    metric = re.sub(r"\s+", " ", str(raw.get("metric") or "")).strip()
    if not metric:
        return None
    score = _num(raw.get("score", raw.get("standard_score")))
    if score is None:
        return None
    row_type = str(raw.get("row_type") or "item").strip().lower()
    if row_type not in ("item", "domain", "total"):
        if "total" in metric.lower():
            row_type = "total"
        elif any(metric == d for d in (
            "Attention", "Impulsive", "Memory", "Anxiety", "Panic", "Depression",
            "Mood Stability", "Aggression", "Fatigue", "Sleep", "Suicide", "Pain",
        )):
            row_type = "domain"
        else:
            row_type = "item"
    return {
        "metric": metric,
        "score": score,
        "standard_score": score,
        "percentile": None,
        "severity": str(raw.get("severity") or "").strip(),
        "response": str(raw.get("response") or "").strip(),
        "row_type": row_type,
        "flagged": False,
    }


def _normalize_scales_payload(data: Any) -> Dict[str, List[Dict[str, Any]]]:
    if not isinstance(data, dict):
        return {}
    scales_raw = data.get("scales") if "scales" in data else data
    if not isinstance(scales_raw, dict):
        return {}
    out: Dict[str, List[Dict[str, Any]]] = {}
    for scale_name, rows in scales_raw.items():
        if scale_name not in CANONICAL_SCALE_NAMES:
            continue
        if not isinstance(rows, list):
            continue
        clean: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for raw in rows:
            row = _normalize_row(raw)
            if not row:
                continue
            key = re.sub(r"[^a-z0-9]+", "", row["metric"].lower())
            if key in seen:
                continue
            seen.add(key)
            clean.append(row)
        if clean:
            out[scale_name] = clean
    return out


def _extract_json_object(text: str) -> Any:
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty LLM response")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence:
        return json.loads(fence.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("No JSON object in LLM response")


def _build_scales_prompt_text(full_text: str, max_chars: int = 48000) -> str:
    from scales_parser import _scale_section_ranges

    sections = _scale_section_ranges(full_text)
    if not sections:
        chunk = full_text
        for marker in ("Generalized Anxiety Disorder", "GAD-7", "SCALES"):
            idx = full_text.find(marker)
            if idx >= 0:
                chunk = full_text[idx:]
                break
        return chunk[:max_chars]

    parts: List[str] = []
    used = 0
    for name in CANONICAL_SCALE_NAMES:
        body = sections.get(name, "")
        if not body:
            continue
        hint = _SECTION_HINTS.get(name, "")
        piece = f"\n\n===== {name} =====\n{hint}\n\n{body}" if hint else f"\n\n===== {name} =====\n{body}"
        if used + len(piece) > max_chars:
            piece = piece[: max_chars - used]
        parts.append(piece)
        used += len(piece)
        if used >= max_chars:
            break
    return "".join(parts) if parts else full_text[:max_chars]


def _call_groq(prompt_text: str) -> Dict[str, List[Dict[str, Any]]]:
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured")

    model = (os.getenv("GROQ_MODEL") or DEFAULT_GROQ_MODEL).strip()
    timeout = float(os.getenv("GROQ_TIMEOUT_SECONDS", "120"))

    user_content = (
        "Extract every patient score from the CNSVS scale sections below.\n"
        "Each section is delimited by ===== headers. Process all five scales if present.\n"
        "Follow the system instructions for line patterns, metric naming, and row_type.\n"
        "Return complete JSON only.\n\n"
        f"{prompt_text}"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
        "max_tokens": int(os.getenv("GROQ_MAX_TOKENS", "8192")),
        "response_format": {"type": "json_object"},
    }

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            GROQ_CHAT_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    if resp.status_code >= 400:
        detail = resp.text[:500]
        raise RuntimeError(f"Groq API error HTTP {resp.status_code}: {detail}")

    body = resp.json()
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError("Groq API returned no choices")
    content = choices[0].get("message", {}).get("content", "")
    parsed = _extract_json_object(content)
    scales = _normalize_scales_payload(parsed)
    if not scales:
        raise ValueError("Groq returned no usable scale rows")
    logger.info(
        "Groq scales extraction (%s): %d scales, %d total rows",
        model,
        len(scales),
        sum(len(v) for v in scales.values()),
    )
    return scales


def _merge_scales(
    primary: Dict[str, List[Dict[str, Any]]],
    fallback: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Prefer primary (LLM); fill missing scales or metrics from fallback."""
    merged: Dict[str, List[Dict[str, Any]]] = {}
    for name in CANONICAL_SCALE_NAMES:
        llm_rows = primary.get(name) or []
        regex_rows = fallback.get(name) or []
        if not llm_rows:
            merged[name] = regex_rows
            continue
        if not regex_rows:
            merged[name] = llm_rows
            continue
        by_key = {re.sub(r"[^a-z0-9]+", "", r["metric"].lower()): r for r in llm_rows}
        for r in regex_rows:
            k = re.sub(r"[^a-z0-9]+", "", r["metric"].lower())
            if k not in by_key:
                by_key[k] = r
        merged[name] = list(by_key.values())
    return {k: v for k, v in merged.items() if v}


def parse_scales_from_text(full_text: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extract scales using Groq Llama when configured; otherwise regex-only.
    Mode SCALES_EXTRACTION_MODE: llm (default), hybrid, regex.
    """
    from scales_parser import parse_scales_from_text as parse_scales_regex

    regex_scales = parse_scales_regex(full_text)
    mode = (os.getenv("SCALES_EXTRACTION_MODE") or "llm").strip().lower()

    if mode == "regex" or not _groq_enabled():
        logger.info("Scales extraction: regex (%d scales)", len(regex_scales))
        return regex_scales

    try:
        prompt_text = _build_scales_prompt_text(full_text)
        llm_scales = _call_groq(prompt_text)
        if mode == "hybrid":
            return _merge_scales(llm_scales, regex_scales)
        return llm_scales
    except Exception as exc:
        logger.warning("Groq scales extraction failed, using regex fallback: %s", exc)
        return regex_scales
