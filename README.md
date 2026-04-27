# CV Tailor

**A desktop app that uses Claude AI to tailor your CV to any job description in seconds.**

---

## Overview

Job applications require a unique CV for every role, but rewriting one from scratch for each application is slow and error-prone. CV Tailor solves this by maintaining a single master profile extracted from your existing CV documents, then using Claude to intelligently select and rewrite the most relevant experience, projects, and skills for each target job description — without ever inventing content.

The intended user is a job seeker who applies to many roles and wants professional, consistently formatted, role-specific CVs without manual editing.

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| Language | Python 3 |
| GUI framework | PyQt5 5.15.10 |
| AI / LLM | Anthropic Claude (`claude-sonnet-4-5`) via `anthropic >= 0.40.0` SDK |
| Document generation | `python-docx 1.1.2` |
| PDF parsing | `pdfplumber 0.11.0` |
| Credential storage | `keyring 25.2.1` (OS-native keychain) |
| Document format | `.docx` (A4, Calibri, 2 cm margins) |

---

## Key Features

- **Master profile builder** — upload one or more PDF, DOCX, or TXT CV files; Claude extracts your experience, education, projects, skills, and achievements into a structured JSON master profile. Subsequent uploads can be merged, not replaced.
- **Single-job tailoring** — paste a job description with a company name and title; the app runs a single Claude call that simultaneously assesses your fit and produces a tailored CV JSON.
- **Bulk processing** — paste multiple job descriptions separated by `---` delimiters; the app queues and processes them sequentially, writing a `.docx` for each.
- **Traffic-light fit scoring** — every generation returns a `green / yellow / red` fit rating (0–100 score), a one-sentence summary, strengths, gaps, and hard-gap flags. Red fit pauses the run and prompts a "Generate Anyway / Skip" decision.
- **Hallucination guard** — a post-generation validation step strips any skills or achievements from the output that are not present verbatim in the master profile, preventing Claude from inventing credentials.
- **Prompt caching** — the static system prompt and compressed profile payload are marked with Anthropic's `cache_control: ephemeral`, separating them from the per-job-description content. On a cache hit, input costs drop to 10% of the normal rate.
- **Profile compression** — empty fields are stripped and common JSON keys are abbreviated before being sent to Claude, reducing input token count.
- **Formatted DOCX output** — generates a polished A4 CV with Calibri font, right-aligned date tabs, bottom-bordered section headers, a borderless two-column skills table, and clickable hyperlinks for LinkedIn/GitHub/portfolio URLs.
- **Secure key storage** — the Anthropic API key is stored in the OS-native keyring (Windows Credential Manager / macOS Keychain), never written to disk. Legacy plaintext keys found in `config.json` are migrated and scrubbed on first load.
- **CSV export** — bulk runs can be exported to a structured CSV with fit scores, summaries, strengths, gaps, and output filenames for each job.

---

## Architecture / How It Works

CV Tailor is structured as a Python package (`cv_tailor/`) with a thin `main.py` entry point that re-exports the public API. There is no separate frontend/backend split or server.

```text
cv_tailor/
├── claude_client.py   # Anthropic API wrapper, session stats, prompt caching
├── config.py          # Config + keyring I/O
├── constants.py       # App-wide constants (model, page geometry, schema)
├── docx_builder.py    # OOXML / .docx rendering pipeline
├── extract.py         # PDF/DOCX/TXT text extraction
├── profile.py         # Master profile CRUD, compression, validation
├── prompts.py         # Claude system prompts
├── utils.py           # Filename sanitization, JSON parsing, path helpers
├── workers.py         # QThread subclasses for non-blocking API calls
└── gui/
    ├── main_window.py     # Application shell + tab container
    ├── single_job_tab.py  # Single-job CV generation UI
    ├── bulk_tab.py        # Bulk job processing UI
    ├── profile_tab.py     # Profile upload & extraction UI
    ├── profile_editor.py  # Profile editing widgets
    ├── settings_tab.py    # API key + output folder settings
    ├── styles.py          # Light/dark theme stylesheets
    └── widgets.py         # Custom Qt widgets
```

**Data flow:**

```text
CV documents (PDF/DOCX/TXT)
        │
        ▼
  pdfplumber / python-docx
  (text extraction)
        │
        ▼
  ProfileManager  ──► Claude API (profile extraction / merge)
        │
        ▼
  master_profile.json  (local JSON, git-ignored)
        │
        ▼
  UnifiedWorker / BulkRunner  ──► Claude API
  (fit assessment + CV generation, one call per job,
   with prompt caching on system + profile blocks)
        │
        ▼
  validate_cv_output()
  (strips hallucinated skills/achievements)
        │
        ▼
  DocxBuilder
  (renders tailored JSON → formatted .docx)
        │
        ▼
  output/<Company>_<Title>.docx
```

**Threading model**: Claude API calls run in `QThread` subclasses (`UnifiedWorker`, `ProfileBuildWorker`, `BulkRunner`) with Qt signals/slots for progress and result delivery, keeping the GUI responsive.

**Bulk RED gating**: When the bulk runner encounters a poor-fit job, it blocks on a `threading.Event` and emits a Qt signal. The GUI renders inline "Generate Anyway / Skip" buttons in the table row; the user's choice unblocks the thread.

**Data flow for a single job**:

1. Profile is compressed — empty fields stripped, common keys abbreviated.
2. A single `messages.create` call sends: system prompt (cached) + profile block (cached) + fresh job description.
3. Claude returns a JSON blob containing both `fit` (assessment) and `cv` (tailored content).
4. `validate_cv_output` cross-checks skills and achievements against the master profile.
5. `DocxBuilder.build` renders the validated JSON to a `.docx` file.

No deployment configuration is present in this repository; the app runs locally.

---

## Setup & Installation

**Requirements**: Python 3.9+ and pip.

```bash
# 1. Clone the repository
git clone <repo-url>
cd CV-builder

# 2. (Recommended) Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
python main.py
```

On first launch, go to the **Settings** tab and enter your Anthropic API key (must start with `sk-ant-`). The key is stored in your OS keychain and never written to disk.

**Running tests:**

```bash
# Unit + DOCX build tests — no API key required
python tests/test_smoke.py

# DOCX render test against the real master profile — requires master_profile.json
python tests/test_real_profile.py

# End-to-end live API test — requires a configured API key
python tests/test_live.py
```

**Usage workflow:**

1. **Settings tab** — paste your Anthropic API key and click Save.
2. **Profile tab** — upload your existing CV(s) (PDF/DOCX/TXT) and click **Build New Profile**. Use **Merge Into Profile** to add further documents without losing existing data.
3. **Single Job tab** — fill Company, Title, paste a JD, click **Assess & Generate CV**. Green/yellow proceeds automatically; red pauses for your decision.
4. **Bulk Jobs tab** — paste many JDs at once using the format below and run them sequentially.

**Bulk input format** — separate jobs with `---` on its own line:

```text
COMPANY: Google
TITLE: Software Engineer
JD:
[full job description]
---
COMPANY: Meta
TITLE: Full Stack Developer
JD:
[full job description]
---
```

Generated `.docx` files are saved to `./output/` by default (configurable in Settings) with filenames following `Company_JobTitle.docx`.

---

## Environment Variables

This project does not use a `.env` file. Configuration is split across two locations:

| Setting | Storage | Description |
| --- | --- | --- |
| Anthropic API key | OS keyring (`cv-tailor` / `anthropic-api-key`) | **[REQUIRED — keep private]** Your `sk-ant-*` key for Claude API access. Set via the Settings tab in the app. |
| `output_folder` | `config.json` (git-ignored) | Directory where generated `.docx` files are written. Defaults to `output/`. |

`master_profile.json` — the extracted candidate profile — is also git-ignored as it contains personal information.

---

## Project Status

**Functional MVP — in active personal use.**

The core loop (profile extraction → fit assessment → CV generation → DOCX output) is complete and working, as evidenced by 15+ generated CVs in the `output/` directory across multiple real companies and roles. The codebase includes unit tests, a live API integration test, and a real-profile render test.

**Incomplete or absent areas:**

- No standalone installer — `pyproject.toml` and `cv_tailor.spec` (PyInstaller) are present but a packaged executable has not been published.
- No deployment configuration (no Docker, no CI/CD pipeline).
- No profile editing UI — the master profile JSON must be edited manually if corrections are needed.

---

## What I Built / My Role

This is a solo personal project I built to automate my own job application process. I designed and implemented the full application — the PyQt5 GUI, the Claude prompting strategy (including prompt caching for cost efficiency), the DOCX rendering pipeline with raw OOXML manipulation, and the post-generation hallucination-prevention validation layer.
