"""Live API smoke test — verifies Anthropic key + end-to-end CV generation."""
import os
import sys
import tempfile
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
import anthropic
import main  # noqa

cfg = main.load_config()
key = cfg.get("api_key", "").strip()
if not key:
    print("[FAIL] no api_key in config.json")
    sys.exit(1)
print(f"[INFO] key loaded, len={len(key)}")

profile = {
    "name": "Alice Smith",
    "contact": {"email": "alice@example.com", "phone": "+44 7000 000000",
                "linkedin": "linkedin.com/in/alice"},
    "summary": "Backend engineer with 5 years building Python services.",
    "experience": [{
        "title": "Senior Backend Engineer", "company": "Acme",
        "location": "London", "start": "2021", "end": "2025",
        "current": False,
        "achievements": [
            "Designed a FastAPI service handling 50k rps with p99 < 40ms",
            "Migrated billing from monolith to microservices, cut deploy time 6x",
            "Mentored 3 junior engineers through structured pairing",
        ],
    }],
    "education": [{"degree": "BSc Computer Science",
                   "institution": "Imperial College London", "year": "2020"}],
    "skills": {"languages": ["Python", "Go", "SQL"],
               "backend": ["FastAPI", "PostgreSQL", "Redis", "Kafka"],
               "devops": ["Docker", "Kubernetes", "AWS"]},
    "projects": [],
}

jd = """We're hiring a Senior Python Backend Engineer to build high-throughput
APIs on AWS. You'll own services written in FastAPI, work with Postgres and
Kafka, and help scale to millions of daily users. Must have 4+ years Python,
strong SQL, and cloud experience (AWS or GCP). Kubernetes nice to have."""

client = anthropic.Anthropic(api_key=key)
compact = json.dumps(main.trim_profile(profile), separators=(",", ":"))
user_msg = (f"COMPANY: Stripe\nTITLE: Senior Backend Engineer\n"
            f"JD:\n{jd}\n\nMASTER_PROFILE:{compact}")

print("[INFO] calling Claude (unified fit + CV)...")
try:
    raw = main.claude_call(client, main.UNIFIED_SYSTEM, user_msg,
                           main.MAX_TOKENS_UNIFIED)
except Exception as e:
    print(f"[FAIL] API call errored: {type(e).__name__}: {e}")
    sys.exit(1)

print(f"[INFO] response received, {len(raw)} chars")

try:
    body, hard_gap = main.strip_hard_gap(raw)
    data = main.parse_json_response(body)
except Exception as e:
    print(f"[FAIL] could not parse response: {e}")
    print("--- raw ---")
    print(raw[:2000])
    sys.exit(1)

fit = data.get("fit", {})
cv = data.get("cv", {})
print(f"[DEBUG] fit keys: {list(fit.keys())}")
print(f"[DEBUG] fit dict: {json.dumps(fit)[:400]}")
print(f"[PASS] fit colour: {fit.get('colour')}")
print(f"[INFO] fit score:  {fit.get('score')}")
print(f"[INFO] fit reason: {(fit.get('reason') or '')[:120]}")
print(f"[INFO] hard_gap:   {hard_gap or '(none)'}")

if not cv.get("experience"):
    print("[FAIL] CV has no experience section")
    sys.exit(1)
print(f"[PASS] CV experience count: {len(cv['experience'])}")
print(f"[PASS] CV summary: {(cv.get('summary') or '')[:120]}")

with tempfile.TemporaryDirectory() as td:
    out = os.path.join(td, "live.docx")
    main.DocxBuilder.build(profile, cv, out)
    size = os.path.getsize(out)
    print(f"[PASS] docx built, {size} bytes")
    with zipfile.ZipFile(out) as z:
        xml = z.read("word/document.xml").decode("utf-8")
        for needle in ["Alice Smith", "Stripe" if "Stripe" in xml else "Acme",
                       "FastAPI"]:
            ok = needle in xml
            print(f"[{'PASS' if ok else 'FAIL'}] docx contains '{needle}'")

print("\n[DONE] live test passed")
