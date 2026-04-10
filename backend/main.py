"""
VNG PDF table extraction API.

Returns JSON aligned with the frontend contract:
{ "sessions": [ { "pdf_name", "ocr_tables": [ { "test_name", "data": [ ... ] } ] } ] }
"""
import os
import tempfile
import traceback
from datetime import datetime
from typing import Any, Dict, List

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from ocr import PDFTableExtractor

# Optional: legacy OCR pipeline helpers (kept for reference / CLI)
from page_utils import get_total_pages

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_FILES_PER_REQUEST = 10

app = FastAPI(title="VNG Parser", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/parse-vng")
async def parse_vng(files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    """
    Accept multipart field name `files` (one or more PDFs).
    Response: { "sessions": [ { "pdf_name", "ocr_tables", "processing_timestamp" }, ... ] }
    Each ocr_tables entry matches: { "test_name", "data": [ { "field_name", "value", ... } ] }.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_FILES_PER_REQUEST} PDFs per request.",
        )

    extractor = PDFTableExtractor()
    sessions: List[Dict[str, Any]] = []

    for uf in files:
        pdf_name = (uf.filename or "upload.pdf").strip() or "upload.pdf"
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            raw = await uf.read()
            if len(raw) > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="File too large (max 25MB).")
            with open(path, "wb") as f:
                f.write(raw)

            tables = extractor.process_pdf(path)
            if not isinstance(tables, list):
                tables = []

            sessions.append(
                {
                    "pdf_name": pdf_name,
                    "ocr_tables": tables,
                    "processing_timestamp": datetime.now().isoformat(),
                    "total_pages": get_total_pages(path),
                }
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("parse_vng error: %s\n%s", e, traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"VNG parse failed: {e!s}") from e
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    return {"sessions": sessions}


def process_pdf_with_ocr_extraction(pdf_path: str, pdf_name: str) -> Dict[str, Any]:
    """Legacy helper: run extractor and return summary paths (optional tooling)."""
    logger.info("Starting OCR extraction for %s", pdf_name)
    try:
        extractor = PDFTableExtractor()
        initial_tables = extractor.process_pdf(pdf_path) or []
        return {
            "success": True,
            "ocr_tables_count": len(initial_tables),
            "pdf_name": pdf_name,
            "total_pages": get_total_pages(pdf_path),
        }
    except Exception as e:
        logger.error("OCR extraction error: %s", e)
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), reload=False)
