# Sharing This Project With Your Team

This document explains what is safe to share, what to exclude, and how teammates should run the ADRC publications feed.

## Purpose

Internal tool that builds a **live PubMed feed** from:

- **22 ADRC authors** — `ADRC Publications Authors + Key words.docx`
- **67 research keywords** — same document (core + additional lists)
- **Quality filters** — strong AD/ADRD keywords, no broad-only matches, USC affiliation when PubMed lists it

Source data is **public PubMed metadata only** (titles, authors, abstracts, PMIDs). There is **no patient/clinical PHI** and **no API keys or passwords** in this repo.

## What to share

| Include | Why |
|---------|-----|
| `app.py`, `fetch_pubmed.py` | Application logic |
| `templates/index.html` | UI |
| `data/config.json` | Author + keyword parameters (matches manager docs) |
| `requirements.txt` | Python dependencies |
| `README.md`, `SHARING.md` | Setup and policy |
| `.gitignore` | Keeps venv out of git |
| Optional: the two `.docx` files | Traceability to original requirements |

## What NOT to share / commit

| Exclude | Why |
|---------|-----|
| `.venv/` | Recreate locally per machine |
| `__pycache__/`, `*.pyc` | Generated files |
| Public GitHub with docx | Use **private** USC/team storage unless manager approves public release |

`data/publications.json` is optional: large cached output; teammates can run `python fetch_pubmed.py` to regenerate (~4–5 minutes).

## How teammates set up

```bash
cd ADRC_Research
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python fetch_pubmed.py      # first-time PubMed pull (optional if cache provided)
python app.py
```

**Live link:** https://husseinyassinemd.github.io/usc-adrc-publications-feed/

Local dev: **http://127.0.0.1:5000** (`python app.py`)

## Security notes for internal use

1. **Development server** — `python app.py` uses Flask `debug=True`. Fine for **local or trusted internal** use only.
2. **Do not expose debug mode to the internet** without IT (use gunicorn/waitress, HTTPS, auth).
3. **Refresh from PubMed** — `/api/publications?refresh=true` triggers a long NCBI fetch; avoid exposing that on a public server without rate limiting or auth.
4. **NCBI etiquette** — The fetcher uses a descriptive User-Agent and delays between requests; do not run many parallel refreshes.

## Manager / compliance checklist

Before wider distribution, confirm with your manager or CPBH lead:

- [ ] OK to share the tool **inside the team** (code + config)
- [ ] OK to include the two requirement `.docx` files in the shared package/repo
- [ ] If hosting on a USC server, route through **IT** (no debug, access control)

## Support

- Edit authors/keywords in `data/config.json`, then run `python fetch_pubmed.py` and refresh the UI.
- PubMed API docs: https://www.ncbi.nlm.nih.gov/home/develop/api/
