# CV Tailor

Desktop app that tailors your CV to job descriptions using Claude.

## Prerequisites

- Python 3.10+
- An Anthropic API key: https://console.anthropic.com/keys

## Install

```
pip install -r requirements.txt
```

## Run

```
python main.py
```

On first launch:
1. **Settings tab** — paste your Anthropic API key and click Save.
2. **Profile tab** — upload your existing CV(s) (PDF/DOCX/TXT) and click
   **Build New Profile**. Later you can add more docs and use
   **Merge Into Profile** to grow your master profile without losing data.
3. **Single Job tab** — fill Company, Title, paste a JD, click
   **Assess & Generate CV**. The app assesses fit first; green/yellow
   proceeds automatically, red pauses for your decision.
4. **Bulk Jobs tab** — paste many JDs at once (format below) and run
   them all sequentially.

## Bulk input format

Separate jobs with `---` on its own line:

```
COMPANY: Google
TITLE: Software Engineer
JD:
[paste full job description here]
---
COMPANY: Meta
TITLE: Full Stack Developer
JD:
[paste full job description here]
---
```

## Output

Generated `.docx` files are saved to `./output/` by default (configurable
in Settings). Filenames follow the pattern
`YYYY-MM-DD_Company_JobTitle.docx`.

## Files

- `config.json` — API key and output folder.
- `master_profile.json` — persistent master profile.
- `output/` — generated CVs.
