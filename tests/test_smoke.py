"""Smoke tests for CV Tailor — pure functions + DOCX build."""
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Prevent Qt from needing a display during import
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import main  # noqa

PASS = []
FAIL = []


def check(name, cond, detail=""):
    """Record a test result."""
    (PASS if cond else FAIL).append(f"{name} {detail}")
    print(("[PASS] " if cond else "[FAIL] ") + name + (f"  [{detail}]" if detail else ""))


# ─── sanitize_filename_part ──────────────────────────────────────────────
check("sanitize ASCII spaces",
      main.sanitize_filename_part("Google Inc", 25) == "Google_Inc")
check("sanitize non-ASCII transliterates",
      main.sanitize_filename_part("Société Générale", 25)
      == "Societe_Generale")
check("sanitize strips special chars",
      main.sanitize_filename_part("Ernst & Young!", 25) == "Ernst_Young")
check("sanitize collapses underscores",
      main.sanitize_filename_part("A   B   C", 25) == "A_B_C")
check("sanitize truncates",
      main.sanitize_filename_part("a" * 50, 10) == "a" * 10)
check("sanitize empty -> Unknown",
      main.sanitize_filename_part("", 25) == "Unknown")
check("sanitize only-specials -> Unknown",
      main.sanitize_filename_part("!!!@@@", 25) == "Unknown")


# ─── build_output_path collision ────────────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    p1 = main.build_output_path(td, "Google", "SWE")
    open(p1, "w").close()
    p2 = main.build_output_path(td, "Google", "SWE")
    p3 = main.build_output_path(td, "Google", "SWE")
    # p2 and p3 are both candidate next paths (files not yet created) so
    # both compute the first free suffix _2. That's fine — call site
    # writes before asking again. Verify p2 != p1.
    check("collision adds _2", p2.endswith("_2.docx"))
    open(p2, "w").close()
    p3 = main.build_output_path(td, "Google", "SWE")
    check("collision adds _3", p3.endswith("_3.docx"))


# ─── parse_json_response ────────────────────────────────────────────────
check("JSON bare", main.parse_json_response('{"a":1}') == {"a": 1})
check("JSON with fences",
      main.parse_json_response('```json\n{"a":2}\n```') == {"a": 2})
check("JSON with leading chatter",
      main.parse_json_response('Sure! Here you go:\n{"a":3}\nDone.')
      == {"a": 3})
check("JSON with embedded braces in strings",
      main.parse_json_response('{"x":"a{b}c","y":{"z":1}}')
      == {"x": "a{b}c", "y": {"z": 1}})
check("JSON nested",
      main.parse_json_response('{"a":{"b":{"c":[1,2,3]}}}')
      == {"a": {"b": {"c": [1, 2, 3]}}})
try:
    main.parse_json_response("no json here")
    check("JSON missing -> raises", False, "did not raise")
except ValueError:
    check("JSON missing -> raises", True)


# ─── strip_hard_gap ─────────────────────────────────────────────────────
body, hg = main.strip_hard_gap('{"a":1}\nHARD_GAP: missing Kubernetes')
check("strip HARD_GAP extracts", hg == "missing Kubernetes")
check("strip HARD_GAP leaves body", body.strip() == '{"a":1}')
body, hg = main.strip_hard_gap('{"a":1}')
check("strip HARD_GAP absent -> empty", hg == "")


# ─── trim_profile ───────────────────────────────────────────────────────
p = {"name": "Alice", "summary": "", "experience": [],
     "skills": {"languages": ["Py"], "frontend": []},
     "projects": [{"name": "X"}], "interests": [],
     "contact": {"email": "a@b.com", "phone": ""}}
t = main.trim_profile(p)
check("trim removes empty top-level", "experience" not in t)
check("trim removes empty arrays", "interests" not in t)
check("trim removes empty sub-keys", "frontend" not in t["skills"])
check("trim keeps populated", t["projects"] == [{"name": "X"}])
check("trim cleans contact blanks", t["contact"] == {"email": "a@b.com"})


# ─── safe_merge_profiles ────────────────────────────────────────────────
old = {"name": "Alice", "experience": [{"title": "Dev", "company": "A"}],
       "skills": {"languages": ["Py", "Go"]},
       "contact": {"email": "a@b.com", "phone": "123"}}
new = {"name": "", "experience": [{"title": "Lead", "company": "B"}],
       "skills": {"languages": ["Py", "Rust"]},
       "contact": {"email": "a@b.com"}}
m = main.safe_merge_profiles(old, new)
titles = [r["title"] for r in m["experience"]]
check("merge keeps old role", "Dev" in titles and "Lead" in titles)
check("merge unions skills",
      set(m["skills"]["languages"]) == {"Py", "Go", "Rust"})
check("merge restores name", m["name"] == "Alice")
check("merge restores phone", m["contact"].get("phone") == "123")


# ─── parse_bulk_input ───────────────────────────────────────────────────
bulk = """COMPANY: Google
TITLE: SWE
JD:
Build cool things.
---
COMPANY: Meta
TITLE: Full Stack
JD:
React and Node.
---"""
jobs = main.parse_bulk_input(bulk)
check("bulk parses 2 jobs", len(jobs) == 2)
check("bulk first company", jobs[0][0] == "Google")
check("bulk second title", jobs[1][1] == "Full Stack")
check("bulk JD multi-line", "React" in jobs[1][2])


# ─── DocxBuilder: full build ────────────────────────────────────────────
profile = {"name": "Alice Smith",
           "contact": {"email": "alice@x.com", "phone": "+44 123",
                       "linkedin": "linkedin.com/in/alice",
                       "github": "github.com/alice"},
           "summary": "Senior engineer.",
           "education": [{"degree": "BSc CS", "institution": "Imperial",
                          "year": "2018"}],
           "skills": {"languages": ["Python", "Go"],
                      "frontend": ["React"], "backend": ["FastAPI"]}}
cv = {"summary": "Backend specialist tailored to this role.",
      "experience": [{"title": "Senior Engineer", "company": "Acme",
                      "location": "London", "start": "2020", "end": "2024",
                      "current": False,
                      "achievements": ["Built X handling 1M rps",
                                       "Mentored 4 juniors"]}],
      "projects": [{"name": "SideProj", "year": "2023",
                    "tech": ["Rust", "Postgres"],
                    "bullets": ["CLI tool with 500 stars"]}],
      "skills": {"languages": ["Python", "Go"], "backend": ["FastAPI"]},
      "volunteering": [{"role": "Mentor", "org": "CodeFirst",
                        "period": "2022-2024",
                        "bullets": ["Ran weekly sessions"]}],
      "achievements": ["Top 1% Stack Overflow"],
      "education": [{"degree": "BSc CS", "institution": "Imperial",
                     "year": "2018"}]}

with tempfile.TemporaryDirectory() as td:
    out = os.path.join(td, "test.docx")
    main.DocxBuilder.build(profile, cv, out)
    check("docx file created", os.path.exists(out))
    check("docx non-empty", os.path.getsize(out) > 2000,
          f"{os.path.getsize(out)} bytes")
    # Verify it's a valid zip (docx is zip)
    try:
        with zipfile.ZipFile(out) as z:
            names = z.namelist()
            check("docx has document.xml",
                  "word/document.xml" in names)
            xml = z.read("word/document.xml").decode("utf-8")
            check("docx contains name", "Alice Smith" in xml)
            check("docx contains tailored summary",
                  "Backend specialist" in xml)
            check("docx contains role", "Senior Engineer" in xml)
            check("docx contains bullet content", "1M rps" in xml)
            check("docx has bottom border XML", "w:bottom" in xml)
            check("docx has tblBorders nil",
                  'w:val="nil"' in xml)
            check("docx has right tab stop",
                  "w:tabs" in xml)
            check("docx uses Calibri",
                  'w:ascii="Calibri"' in xml)
    except zipfile.BadZipFile:
        check("docx is valid zip", False)

# ─── DocxBuilder with minimal data (edge cases) ─────────────────────────
min_profile = {"name": "Bob", "contact": {"email": "b@x.com"}}
min_cv = {"summary": "Short."}
with tempfile.TemporaryDirectory() as td:
    out = os.path.join(td, "min.docx")
    try:
        main.DocxBuilder.build(min_profile, min_cv, out)
        check("docx minimal build", os.path.exists(out))
    except Exception as e:
        check("docx minimal build", False, str(e))


# ─── Config I/O ─────────────────────────────────────────────────────────
# Patch keyring to an in-memory backend so tests never touch the OS store.
import keyring.backend


class _MemKeyring(keyring.backend.KeyringBackend):
    priority = 999
    _store = {}

    def get_password(self, service, user):
        return self._store.get((service, user))

    def set_password(self, service, user, pwd):
        self._store[(service, user)] = pwd

    def delete_password(self, service, user):
        self._store.pop((service, user), None)


keyring.set_keyring(_MemKeyring())

_cwd = os.getcwd()
with tempfile.TemporaryDirectory() as td:
    os.chdir(td)
    try:
        main.save_config({"api_key": "sk-ant-test", "output_folder": "out"})
        cfg = main.load_config()
        check("config roundtrip", cfg["api_key"] == "sk-ant-test")
        main.save_profile({"name": "Test"})
        p = main.load_profile()
        check("profile roundtrip", p["name"] == "Test")
    finally:
        os.chdir(_cwd)

print()
print(f"PASSED: {len(PASS)}   FAILED: {len(FAIL)}")
if FAIL:
    print("Failures:")
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
