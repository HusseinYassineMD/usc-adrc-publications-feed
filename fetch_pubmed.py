#!/usr/bin/env python3
"""Fetch USC ADRC publications from PubMed — exact author + keyword params only."""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "data" / "config.json"
CACHE_PATH = BASE_DIR / "data" / "publications.json"
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
REQUEST_DELAY = 0.5
PAGE_SIZE = 500
EFETCH_BATCH = 50


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("\u2019", "'").replace("\u03b5", "e").replace("\u03b2", "beta")
    text = text.replace("‐", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def keyword_variants(keyword: str) -> list[str]:
    """Generate normalized search variants for a manager keyword."""
    base = normalize_text(keyword)
    variants = {base, base.replace("'", ""), base.replace("alzheimer's", "alzheimer")}

    if "apoe" in base:
        variants.update({"apoe e4", "apoe ε4", "apolipoprotein e", "apoe4"})
    if "amyloid beta" in base:
        variants.update({"amyloid-beta", "amyloid β", "aβ", "abeta", "amyloid beta"})
    if "phosphorylated tau" in base:
        variants.update({"p-tau", "ptau", "phospho-tau"})
    if "plasma p-tau217" in base:
        variants.update({"p-tau217", "ptau217", "p-tau 217"})
    if "mild cognitive impairment" in base:
        variants.update({"mci"})
    if "magnetic resonance imaging" in base:
        variants.update({"mri"})
    if "genome-wide association" in base:
        variants.update({"gwas"})
    if "autosomal dominant" in base:
        variants.update({"adad", "autosomal dominant alzheimer"})
    if "neurofilament light" in base:
        variants.update({"nfl", "neurofilament light chain", "nfl chain"})

    return [v for v in variants if len(v) >= 2]


def keyword_in_haystack(keyword: str, haystack: str) -> bool:
    h = normalize_text(haystack)
    for variant in keyword_variants(keyword):
        if len(variant) <= 3:
            if re.search(rf"\b{re.escape(variant)}\b", h):
                return True
        elif variant in h:
            return True
    return False


def pubmed_keyword_term(keyword: str) -> str:
    cleaned = keyword.replace("\u2019", "'")
    if " " in cleaned:
        return f'"{cleaned}"[Title/Abstract]'
    return f"{cleaned}[Title/Abstract]"


def build_keyword_clause(config: dict) -> str:
    terms = [pubmed_keyword_term(kw) for kw in config["keywords"]]
    return " OR ".join(terms)


def build_author_keyword_query(author: dict, keyword_clause: str) -> str:
    author_q = author.get("pubmed_query") or author.get("pubmed", "")
    return f"({author_q}) AND ({keyword_clause})"


def http_get(url: str, params: dict, retries: int = 3) -> str:
    query = urllib.parse.urlencode(params)
    full_url = f"{url}?{query}"
    req = urllib.request.Request(
        full_url,
        headers={"User-Agent": "USC-ADRC-Publications-Feed/1.0 (research@usc.edu)"},
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 400) and attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            raise
    raise RuntimeError("PubMed request failed")


def search_pubmed_page(query: str, retstart: int = 0) -> tuple[list[str], int]:
    params = {
        "db": "pubmed",
        "term": query,
        "retstart": retstart,
        "retmax": PAGE_SIZE,
        "retmode": "json",
        "sort": "pub+date",
    }
    raw = http_get(ESEARCH_URL, params)
    result = json.loads(raw).get("esearchresult", {})
    return result.get("idlist", []), int(result.get("count", 0))


def search_pubmed_all(query: str, label: str = "") -> list[str]:
    _, total = search_pubmed_page(query, 0)
    if label:
        print(f"  {label}: {total} matches")

    pmids: list[str] = []
    retstart = 0
    while retstart < total:
        batch, _ = search_pubmed_page(query, retstart)
        if not batch:
            break
        pmids.extend(batch)
        retstart += PAGE_SIZE
        time.sleep(REQUEST_DELAY)
    return pmids


def keyword_batches(config: dict, batch_size: int = 12) -> list[str]:
    keywords = config["keywords"]
    batches = []
    for i in range(0, len(keywords), batch_size):
        chunk = keywords[i : i + batch_size]
        batches.append(" OR ".join(pubmed_keyword_term(kw) for kw in chunk))
    return batches


def search_per_author(config: dict) -> list[str]:
    """PubMed search per ADRC author × keyword batches — exact to your params."""
    batches = keyword_batches(config)
    all_pmids: list[str] = []

    for author in config["authors"]:
        name = author["name"].split(",")[0]
        author_pmids: list[str] = []
        author_q = author.get("pubmed_query") or author.get("pubmed", "")

        for batch in batches:
            query = f"({author_q}) AND ({batch})"
            author_pmids.extend(search_pubmed_all(query))
            time.sleep(REQUEST_DELAY)

        author_pmids = list(dict.fromkeys(author_pmids))
        print(f"  {name}: {len(author_pmids)} papers")
        all_pmids.extend(author_pmids)

    return list(dict.fromkeys(all_pmids))


def fetch_article_details(pmids: list[str]) -> list[dict]:
    if not pmids:
        return []

    articles: list[dict] = []
    for i in range(0, len(pmids), EFETCH_BATCH):
        batch = pmids[i : i + EFETCH_BATCH]
        params = {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"}
        xml_text = http_get(EFETCH_URL, params)
        articles.extend(parse_pubmed_xml(xml_text))
        if (i // EFETCH_BATCH) % 10 == 0:
            print(f"  Parsed {min(i + EFETCH_BATCH, len(pmids))}/{len(pmids)}")
        time.sleep(REQUEST_DELAY)
    return articles


def parse_pubmed_xml(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    articles = []
    for article_el in root.findall(".//PubmedArticle"):
        medline = article_el.find("MedlineCitation")
        if medline is None:
            continue
        pmid = _text(medline.find("PMID"))
        article = medline.find("Article")
        if article is None:
            continue

        title = _text(article.find("ArticleTitle"))
        abstract_parts = []
        for abs_el in article.findall(".//AbstractText"):
            label = abs_el.get("Label")
            text = "".join(abs_el.itertext()).strip()
            if label:
                abstract_parts.append(f"{label}: {text}")
            elif text:
                abstract_parts.append(text)
        abstract = " ".join(abstract_parts)

        journal_el = article.find("Journal")
        journal = _text(journal_el.find("Title")) if journal_el is not None else ""
        pub_date = extract_pub_date(article_el)

        authors = []
        author_records = []
        author_list = article.find("AuthorList")
        if author_list is not None:
            for author in author_list.findall("Author"):
                last = _text(author.find("LastName"))
                fore = _text(author.find("ForeName"))
                initials = _text(author.find("Initials"))
                if not last:
                    continue
                display = f"{fore} {last}".strip() if fore else f"{last} {initials}".strip()
                affiliations = [
                    _text(info.find("Affiliation"))
                    for info in author.findall("AffiliationInfo")
                    if _text(info.find("Affiliation"))
                ]
                authors.append(display)
                author_records.append({"display": display, "affiliations": affiliations})

        doi = None
        pmc_id = None
        pubmed_data = article_el.find("PubmedData")
        id_sources = list(article.findall(".//ArticleId"))
        if pubmed_data is not None:
            id_list = pubmed_data.find("ArticleIdList")
            if id_list is not None:
                id_sources.extend(id_list.findall("ArticleId"))
        for id_el in id_sources:
            id_type = id_el.get("IdType")
            if id_type == "doi" and not doi:
                doi = _text(id_el)
            elif id_type == "pmc" and not pmc_id:
                pmc_id = _text(id_el)

        keywords = []
        keyword_list = medline.find("KeywordList")
        if keyword_list is not None:
            for kw in keyword_list.findall("Keyword"):
                text = _text(kw)
                if text:
                    keywords.append(text)

        mesh_terms = []
        mesh_list = medline.find("MeshHeadingList")
        if mesh_list is not None:
            for mesh in mesh_list.findall("MeshHeading"):
                descriptor = _text(mesh.find("DescriptorName"))
                if descriptor:
                    mesh_terms.append(descriptor)

        pmc_num = pmc_id.replace("PMC", "") if pmc_id else ""
        pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
        pmc_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_num}/" if pmc_num else ""

        articles.append(
            {
                "pmid": pmid,
                "title": title,
                "abstract": abstract,
                "journal": journal,
                "pub_date": pub_date,
                "authors": authors,
                "author_records": author_records,
                "doi": doi,
                "pmc_id": pmc_id,
                "keywords": keywords,
                "mesh_terms": mesh_terms,
                "pubmed_url": pubmed_url,
                "pmc_url": pmc_url,
                "title_url": pmc_url or pubmed_url,
            }
        )
    return articles


def extract_pub_date(article_el: ET.Element) -> str:
    pub_date = article_el.find(".//PubDate")
    if pub_date is None:
        return ""
    year = _text(pub_date.find("Year"))
    month = _text(pub_date.find("Month"))
    day = _text(pub_date.find("Day"))
    medline = _text(pub_date.find("MedlineDate"))

    month_map = {
        "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
        "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
        "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
    }
    if month in month_map:
        month = month_map[month]
    elif month and month.isalpha():
        month = month_map.get(month[:3], "01")

    if year and month and day:
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    if year and month:
        return f"{year}-{str(month).zfill(2)}-01"
    if year:
        return f"{year}-01-01"
    if medline:
        year_match = re.search(r"\b(19|20)\d{2}\b", medline)
        if year_match:
            return f"{year_match.group()}-01-01"
    return ""


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _author_tokens_match(pattern: str, author: str) -> bool:
    p_tokens = pattern.split()
    a_tokens = author.split()
    if len(p_tokens) < 2 or len(a_tokens) < 2:
        return False

    pairs = [
        (p_tokens[0], p_tokens[-1], a_tokens[0], a_tokens[-1]),
        (p_tokens[-1], p_tokens[0], a_tokens[0], a_tokens[-1]),
        (p_tokens[0], p_tokens[-1], a_tokens[-1], a_tokens[0]),
    ]
    for p_first, p_last, a_first, a_last in pairs:
        if len(p_last) < 2 or len(a_last) < 2:
            continue
        if p_last != a_last:
            continue
        if p_first == a_first:
            return True
        if len(p_first) == 1 and a_first.startswith(p_first):
            return True
        if len(a_first) == 1 and p_first.startswith(a_first):
            return True
    return False


def author_record_verified(author_cfg: dict, record: dict) -> bool:
    verify_names = author_cfg.get("verify_names", [])
    ambiguous = author_cfg.get("ambiguous", False)
    if not verify_names:
        return False

    norm = normalize_text(record.get("display", ""))
    for pattern in verify_names:
        pat = normalize_text(pattern)
        if ambiguous:
            if pat in norm or norm in pat:
                return True
            continue
        if pat in norm:
            return True
        if _author_tokens_match(pat, norm):
            return True
    return False


def author_verified(author_cfg: dict, article_authors: list[str]) -> bool:
    for display in article_authors:
        if author_record_verified(author_cfg, {"display": display, "affiliations": []}):
            return True
    return False


def has_usc_affiliation(affiliations: list[str], config: dict) -> bool:
    markers = [normalize_text(m) for m in config.get("usc_affiliation_markers", [])]
    text = normalize_text(" ".join(affiliations))
    return any(marker in text for marker in markers)


def match_adrc_authors(article: dict, config: dict) -> list[str]:
    records = article.get("author_records") or [
        {"display": name, "affiliations": []} for name in article.get("authors", [])
    ]
    matched = []
    for author_cfg in config["authors"]:
        for record in records:
            if author_record_verified(author_cfg, record):
                matched.append(author_cfg["name"])
                break
    return list(dict.fromkeys(matched))


def verified_adrc_author_records(article: dict, config: dict) -> list[dict]:
    """Return author records that match an ADRC investigator."""
    records = article.get("author_records") or [
        {"display": name, "affiliations": []} for name in article.get("authors", [])
    ]
    hits = []
    for author_cfg in config["authors"]:
        for record in records:
            if author_record_verified(author_cfg, record):
                hits.append(
                    {
                        "name": author_cfg["name"],
                        "display": record["display"],
                        "affiliations": record.get("affiliations", []),
                    }
                )
                break
    return hits


def passes_affiliation(article: dict, config: dict) -> bool:
    """Keep if a verified ADRC author has USC affiliation or affiliation is unknown."""
    hits = verified_adrc_author_records(article, config)
    if not hits:
        return False

    for hit in hits:
        affs = hit.get("affiliations", [])
        if not affs:
            return True
        if has_usc_affiliation(affs, config):
            return True
    return False


def build_haystack(article: dict) -> str:
    return " ".join(
        [
            article.get("title", ""),
            article.get("abstract", ""),
            " ".join(article.get("keywords", [])),
            " ".join(article.get("mesh_terms", [])),
        ]
    )


def match_keywords(article: dict, config: dict) -> list[str]:
    haystack = build_haystack(article)
    return [kw for kw in config["keywords"] if keyword_in_haystack(kw, haystack)]


def match_strong_keywords(article: dict, config: dict) -> list[str]:
    haystack = build_haystack(article)
    strong = config.get("strong_keywords") or config["keywords"]
    return [kw for kw in strong if keyword_in_haystack(kw, haystack)]


def passes_best_list(article: dict, config: dict) -> bool:
    """
    Best-quality ADRC list:
    - Verified ADRC author on the paper
    - At least one AD/ADRD-specific (strong) keyword match
    - Not qualified by broad keywords alone
    - USC affiliation when PubMed lists one for the ADRC author
    """
    if not article.get("adrc_authors"):
        return False
    if not article.get("strong_keywords"):
        return False

    broad = {normalize_text(k) for k in config.get("broad_keywords", [])}
    matched_norm = {normalize_text(k) for k in article.get("matched_keywords", [])}
    if matched_norm and matched_norm.issubset(broad):
        return False

    return passes_affiliation(article, config)


def filter_publications(articles: list[dict], config: dict) -> list[dict]:
    filtered = []
    for article in articles:
        article["adrc_authors"] = match_adrc_authors(article, config)
        article["matched_keywords"] = match_keywords(article, config)
        article["strong_keywords"] = match_strong_keywords(article, config)
        if passes_best_list(article, config):
            filtered.append(article)

    filtered.sort(key=lambda a: a.get("pub_date", ""), reverse=True)
    return filtered


def fetch_publications(use_cache_only: bool = False) -> dict:
    if use_cache_only and CACHE_PATH.exists():
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)

    config = load_config()
    print(f"Searching PubMed: {len(config['authors'])} authors × {len(config['keywords'])} keywords\n")

    pmids = search_per_author(config)
    print(f"\nUnique PMIDs from PubMed: {len(pmids)}")
    time.sleep(REQUEST_DELAY)

    articles = fetch_article_details(pmids)
    print(f"Parsed {len(articles)} articles")

    before = len(articles)
    articles = filter_publications(articles, config)
    print(f"Best list (author + strong keyword + USC): {len(articles)} (removed {before - len(articles)})")

    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "pubmed_raw_count": len(pmids),
        "author_count": len(config["authors"]),
        "keyword_count": len(config["keywords"]),
        "total": len(articles),
        "authors": config["authors"],
        "keywords": config["keywords"],
        "publications": articles,
    }

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return result


if __name__ == "__main__":
    data = fetch_publications()
    print(f"Saved {data['total']} publications to {CACHE_PATH}")
