"""
Input validators for CNSVS FastAPI endpoints.
"""
from __future__ import annotations

import os
from typing import Tuple


def validate_pdf_file(
    file_content: bytes,
    filename: str | None,
    file_size: int,
    max_size_bytes: int = 50 * 1024 * 1024,
) -> Tuple[bool, str]:
    """
    Validate uploaded PDF content with lightweight security checks.

    Returns:
        (is_valid, error_message)
    """
    if not file_content:
        return False, "File is empty."

    if file_size <= 0:
        return False, "File size is invalid."

    if file_size > max_size_bytes:
        return False, f"File exceeds maximum allowed size ({max_size_bytes // (1024 * 1024)} MB)."

    safe_name = os.path.basename(filename or "")
    if not safe_name:
        return False, "Filename is missing."

    if len(safe_name) > 255:
        return False, "Filename is too long."

    if not safe_name.lower().endswith(".pdf"):
        return False, "Only PDF files are allowed."

    # Basic PDF signature check.
    if not file_content.startswith(b"%PDF-"):
        return False, "Invalid PDF signature."

    # Basic trailer check to reject obvious malformed uploads.
    trailer_tail = file_content[-2048:]
    if b"%%EOF" not in trailer_tail:
        return False, "Invalid PDF trailer."

    return True, ""

