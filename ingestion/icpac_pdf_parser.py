"""HazardGraph — ICPAC PDF text extraction using pdfplumber.

Stub for future implementation. Will extract structured data
from ICPAC PDF bulletins.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def extract_pdf_text(pdf_path: str) -> Optional[str]:
    """Extract text from a PDF file using pdfplumber.

    Args:
        pdf_path: Local path or URL to the PDF file.

    Returns:
        Extracted text as a string, or None on failure.
    """
    # TODO: Implement in FEAT-03
    logger.warning("PDF parsing not yet implemented (stub)")
    return None