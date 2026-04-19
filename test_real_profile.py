"""Render the real master profile directly (no Claude call) to verify
the DocxBuilder handles the on-disk schema without dropping data."""
import json
import os
import sys
import tempfile
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import main  # noqa

with open("master_profile.json", "r", encoding="utf-8") as f:
    profile = json.load(f)

cv = {k: profile.get(k) for k in
      ("summary", "experience", "projects", "skills",
       "volunteering", "achievements", "education")}

with tempfile.TemporaryDirectory() as td:
    out = os.path.join(td, "real.docx")
    main.DocxBuilder.build(profile, cv, out)
    with zipfile.ZipFile(out) as z:
        xml = z.read("word/document.xml").decode("utf-8")

checks = [
    ("Experience bullet from responsibilities",
     "process mapping" in xml.lower()),
    ("Experience date Nov 2025", "Nov 2025" in xml),
    ("Ernst &amp; Young rendered",
     "Ernst" in xml and "Young" in xml),
    ("Volunteering org AIESEC", "AIESEC" in xml),
    ("Volunteering date 2022", "2022" in xml and "2024" in xml),
    ("Volunteering Vice Captain", "Vice Captain" in xml),
    ("Project highlight bullet (Brux)", "Brux Waffles" in xml),
    ("Project highlight bullet content", "PayHere" in xml),
    ("Skills: languages", "TypeScript" in xml),
    ("Skills: frontend", "Next.js" in xml or "Next" in xml),
    ("Skills: backend", "FastAPI" in xml),
    ("Skills: databases", "Firebase Firestore" in xml),
    ("Skills: cloud", "Vercel" in xml),
    ("Skills: ai_integrations", "Gemini" in xml),
    ("Skills: third_party_apis", "Microsoft Graph" in xml),
    ("Skills: erp", "SAP" in xml),
    ("Education date range", "2022" in xml and "2026" in xml),
    ("Education institution", "University of Colombo" in xml),
    ("Achievements count >=3",
     xml.count("Boxing") >= 2),
]
fail = 0
for name, ok in checks:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    if not ok:
        fail += 1
print(f"\n{len(checks) - fail}/{len(checks)} passed")
sys.exit(1 if fail else 0)
