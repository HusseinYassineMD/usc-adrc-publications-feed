#!/usr/bin/env python3
"""Flask app for USC ADRC PubMed publications live feed."""

from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from fetch_pubmed import CACHE_PATH, fetch_publications, load_config

BASE_DIR = Path(__file__).resolve().parent

app = Flask(__name__)

ENABLE_PUBMED_REFRESH = os.environ.get("ENABLE_PUBMED_REFRESH", "").lower() in (
    "1",
    "true",
    "yes",
)


def load_cached_or_fetch(refresh: bool = False) -> dict:
    if refresh or not CACHE_PATH.exists():
        return fetch_publications()
    with open(CACHE_PATH, encoding="utf-8") as f:
        return json.load(f)


@app.route("/")
def index():
    config = load_config()
    return render_template(
        "index.html",
        author_count=len(config["authors"]),
        keyword_count=len(config["keywords"]),
        enable_refresh=ENABLE_PUBMED_REFRESH,
    )


@app.route("/api/publications")
def api_publications():
    refresh = request.args.get("refresh", "").lower() in ("1", "true", "yes")
    if refresh and not ENABLE_PUBMED_REFRESH:
        return jsonify(
            {
                "error": "Live refresh is disabled on hosted deploy. Data is updated via scheduled rebuild."
            }
        ), 503
    try:
        data = load_cached_or_fetch(refresh=refresh)
        return jsonify(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/config")
def api_config():
    return jsonify(load_config())


if __name__ == "__main__":
    if not CACHE_PATH.exists():
        print("No cache found — fetching publications from PubMed (may take several minutes)...")
        load_cached_or_fetch(refresh=True)
    else:
        print(f"Using cached publications from {CACHE_PATH.name}")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    print(f"Starting server at http://127.0.0.1:{port}")
    app.run(debug=debug, port=port, host="0.0.0.0")
