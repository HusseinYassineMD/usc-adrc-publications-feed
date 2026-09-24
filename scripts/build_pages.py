#!/usr/bin/env python3
"""Build static GitHub Pages site from template + cached publications."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
TEMPLATE = ROOT / "templates" / "index.html"
CACHE = ROOT / "data" / "publications.json"
CONFIG = ROOT / "data" / "config.json"


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CACHE, DOCS / "publications.json")

    with open(CONFIG, encoding="utf-8") as f:
        config = json.load(f)
    author_count = len(config["authors"])
    keyword_count = len(config["keywords"])

    html = TEMPLATE.read_text(encoding="utf-8")
    html = re.sub(r"\{% if enable_refresh %}.*?{% endif %\}\s*", "", html, flags=re.DOTALL)
    html = html.replace("{{ author_count }}", str(author_count))
    html = html.replace("{{ keyword_count }}", str(keyword_count))
    html = html.replace(
        "<p>Fetching publications from PubMed…</p>",
        "<p>Loading publications…</p>",
    )
    html = html.replace(
        'const url = refresh ? "/api/publications?refresh=true" : "/api/publications";',
        'const url = "publications.json";',
    )
    html = html.replace(
        'content.innerHTML = \'<div class="loading"><div class="spinner"></div><p>Fetching publications from PubMed…</p></div>\';',
        'content.innerHTML = \'<div class="loading"><div class="spinner"></div><p>Loading publications…</p></div>\';',
    )
    html = re.sub(r"\s*if \(refreshBtn\) refreshBtn\.disabled = true;\n", "\n", html)
    html = re.sub(r"\s*if \(refreshBtn\) refreshBtn\.disabled = false;\n", "\n", html)
    html = re.sub(r"\s*if \(refreshBtn\) refreshBtn\.addEventListener.*\n", "\n", html)
    html = re.sub(r"async function loadPublications\(refresh = false\)", "async function loadPublications()", html)
    html = re.sub(r"loadPublications\(true\)", "loadPublications()", html)

    (DOCS / "index.html").write_text(html, encoding="utf-8")
    print(f"Built {DOCS / 'index.html'} and {DOCS / 'publications.json'}")


if __name__ == "__main__":
    main()
