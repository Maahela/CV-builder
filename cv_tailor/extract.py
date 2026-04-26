"""Extract raw text from PDF, DOCX, or TXT."""
from pathlib import Path

import pdfplumber
from docx import Document


def extract_text_from_file(path):
    """Extract raw text from PDF, DOCX, or TXT."""
    ext = Path(path).suffix.lower()
    try:
        if ext == ".pdf":
            with pdfplumber.open(path) as pdf:
                return "\n".join((p.extract_text() or "") for p in pdf.pages)
        if ext == ".docx":
            doc = Document(path)
            return "\n".join(p.text for p in doc.paragraphs)
        if ext == ".txt":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
    except Exception as e:
        return f"[parse error: {e}]"
    return ""
