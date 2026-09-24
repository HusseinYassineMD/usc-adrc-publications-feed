#!/usr/bin/env python3
"""Flask app for USC ADRC PubMed publications live feed."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from fetch_pubmed import CACHE_PATH, fetch_publications, load_config

BASE_DIR = Path(__file__).resolve().parent

app = Flask(__name__)

_refresh_lock = threading.Lock()
_refresh_state = {
    "status": "idle",
    "message": "",
    "error": None,
    "started_at": None,
    "finished_at": None,
}


def _read_cache() -> dict:
    with open(CACHE_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_cached_or_fetch(refresh: bool = False) -> dict:
    if refresh or not CACHE_PATH.exists():
        return fetch_publications()
    return _read_cache()


def _run_pubmed_refresh() -> None:
    global _refresh_state
    try:
        _refresh_state["message"] = "Searching PubMed for all ADRC authors and keywords…"
        fetch_publications()
        _refresh_state.update(
            {
                "status": "complete",
                "message": "PubMed refresh finished.",
                "error": None,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception as exc:
        _refresh_state.update(
            {
                "status": "error",
                "message": "Refresh failed.",
                "error": str(exc),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    finally:
        _refresh_lock.release()


@app.route("/")
def index():
    config = load_config()
    return render_template(
        "index.html",
        author_count=len(config["authors"]),
        keyword_count=len(config["keywords"]),
    )


@app.route("/api/publications")
def api_publications():
    try:
        if not CACHE_PATH.exists():
            return jsonify({"error": "No data yet. Click Refresh from PubMed."}), 404
        return jsonify(_read_cache())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/publications/refresh", methods=["POST"])
def api_publications_refresh_start():
    if not _refresh_lock.acquire(blocking=False):
        return jsonify(
            {
                "status": _refresh_state["status"],
                "message": "A PubMed refresh is already running.",
            }
        ), 409

    _refresh_state.update(
        {
            "status": "running",
            "message": "Starting PubMed refresh…",
            "error": None,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
        }
    )
    thread = threading.Thread(target=_run_pubmed_refresh, daemon=True)
    thread.start()
    return jsonify(_refresh_state)


@app.route("/api/publications/refresh/status")
def api_publications_refresh_status():
    return jsonify(_refresh_state)


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
