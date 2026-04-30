"""Filename, JSON parse, file-open, output-path helpers."""
import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import datetime

from .constants import COMPANY_MAX, TITLE_MAX

JD_HEADER_RULE = "─────────────────────────────────────────"
JD_SUBFOLDER = "jds"


def sanitize_filename_part(text, maxlen):
    """Turn text into safe filename segment, transliterating non-ASCII."""
    if not text:
        return "Unknown"
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.strip().replace(" ", "_")
    text = re.sub(r"[^A-Za-z0-9_\-]", "", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:maxlen] or "Unknown"


def build_output_path(output_folder, company, title):
    """Return non-colliding output path for today's CV."""
    os.makedirs(output_folder, exist_ok=True)
    base = (f"{sanitize_filename_part(company, COMPANY_MAX)}_"
            f"{sanitize_filename_part(title, TITLE_MAX)}")
    path = os.path.join(output_folder, base + ".docx")
    i = 2
    while os.path.exists(path):
        path = os.path.join(output_folder, f"{base}_{i}.docx")
        i += 1
    return path


def jds_folder(output_folder):
    """Return absolute path to the JDs subfolder inside output_folder."""
    return os.path.join(output_folder, JD_SUBFOLDER)


def jd_path_for_docx(docx_path):
    """Return the JD .txt path that pairs with a given docx path.

    JDs live in the `jds/` subfolder beside the docx output folder.
    """
    folder = os.path.dirname(docx_path)
    name, _ = os.path.splitext(os.path.basename(docx_path))
    return os.path.join(folder, JD_SUBFOLDER, f"{name}_JD.txt")


def _normalize_fit_label(fit):
    """Map free-form fit indicator to canonical Green/Yellow/Red."""
    if not fit:
        return ""
    s = str(fit).lower()
    if "green" in s or "strong" in s:
        return "Green"
    if "yellow" in s or "partial" in s:
        return "Yellow"
    if "red" in s or "poor" in s:
        return "Red"
    return ""


def save_jd_file(docx_path, company, role, jd_text,
                 fit_label="", fit_score="", date_str=None):
    """Write the JD text file beside the docx with header. Returns path."""
    jd_path = jd_path_for_docx(docx_path)
    os.makedirs(os.path.dirname(jd_path) or ".", exist_ok=True)
    canonical = _normalize_fit_label(fit_label)
    score_part = f" (Score: {fit_score}/100)" if fit_score not in ("", None) else ""
    fit_line = f"{canonical or '-'}{score_part}"
    date_line = date_str or datetime.now().strftime("%Y-%m-%d")
    header = (
        f"{JD_HEADER_RULE}\n"
        f"Company:  {company or ''}\n"
        f"Role:     {role or ''}\n"
        f"Date:     {date_line}\n"
        f"Fit:      {fit_line}\n"
        f"{JD_HEADER_RULE}\n"
    )
    with open(jd_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(jd_text or "")
    return jd_path


def strip_hard_gap(text):
    """Split a response into (body_without_hard_gap, hard_gap_string)."""
    m = re.search(r"(?im)^\s*HARD_GAP\s*:\s*(.+?)\s*$", text)
    if not m:
        return text, ""
    return text[:m.start()] + text[m.end():], m.group(1).strip()


def parse_json_response(raw_text):
    """Extract a JSON object from Claude output robustly."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    text = re.sub(r"```[a-zA-Z]*\n?", "", text).replace("```", "")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    print(f"[ERROR] Failed to parse Claude response")
    print(f"[ERROR] Response length: {len(raw_text)} chars")
    print(f"[ERROR] First 500 chars: {raw_text[:500]}")
    print(f"[ERROR] Last 200 chars: {raw_text[-200:]}")
    raise ValueError(
        f"Could not parse Claude response as JSON. "
        f"Response length: {len(raw_text)} chars."
    )


def open_file_native(path):
    """Open a file or folder with the OS default app (cross-platform)."""
    abs_path = os.path.abspath(path)
    # Prefer Qt's portable opener when a QApplication is alive.
    try:
        from PyQt5.QtCore import QUrl
        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtWidgets import QApplication
        if QApplication.instance() is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(abs_path))
            return
    except Exception:
        pass
    try:
        if sys.platform.startswith("win"):
            os.startfile(abs_path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", abs_path])
        else:
            subprocess.Popen(["xdg-open", abs_path])
    except Exception:
        pass
