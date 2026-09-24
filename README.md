# USC ADRC Publications Live Feed

Internal web UI (styled like [ADRC publications](https://adrc.usc.edu/research/publications/)) that pulls **public PubMed** records for ADRC investigators and research themes defined in your manager’s documents.

## Requirements (source documents)

- `ADRC Publications Authors + Key words.docx` — 22 authors, 67 keywords  
- `B2_Publications_ADRC Y6_1.28.26.docx` — reference / validation (not used to drive the feed logic)

Parameters live in `data/config.json`.

## What the feed includes

Each publication must pass:

1. **Verified ADRC author** — name on the paper matches your author list  
2. **Strong AD/ADRD keyword** — from the manager keyword set (not broad-only, e.g. “Aging” or “MRI” alone)  
3. **USC affiliation** — when PubMed lists affiliations for that author, at least one must match USC/Keck/ADRC-related markers  

Data source: [PubMed E-utilities](https://www.ncbi.nlm.nih.gov/home/develop/api/) (no API key required).

## Quick start

```bash
cd ADRC_Research
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python fetch_pubmed.py    # optional first run; ~4–5 min
python app.py
```

Open **http://127.0.0.1:5000**

Use **Refresh from PubMed** in the UI to update the cache.

## Project layout

| Path | Purpose |
|------|---------|
| `data/config.json` | Authors, keywords, filter rules |
| `fetch_pubmed.py` | PubMed search, verify, cache |
| `app.py` | Flask server + API |
| `templates/index.html` | Publications table UI |
| `data/publications.json` | Generated cache (git-optional) |

## API

- `GET /` — UI  
- `GET /api/publications` — cached JSON  
- `GET /api/publications?refresh=true` — re-fetch from PubMed (slow)  
- `GET /api/config` — current author/keyword config  

## Sharing with your team

See **[SHARING.md](./SHARING.md)** for what to include, security notes, and manager checklist.

## Refresh data only (no UI)

```bash
source .venv/bin/activate
python fetch_pubmed.py
```
