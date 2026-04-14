"""
Paper search sources - arXiv, Semantic Scholar, Papers With Code.
Each function returns a list of paper dicts with a consistent schema.
"""

import time
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from config import LOOKBACK_DAYS

# arXiv requires >= 3s between requests
_last_arxiv_ts: float = 0.0

# Standard paper schema
PAPER_KEYS = ("title", "abstract", "link", "authors", "published",
              "source", "citations", "code_url", "trending")


def _paper(title, abstract, link, authors=None, published="",
           source="", citations=None, code_url=None, trending=False):
    return {
        "title": title.strip().replace("\n", " "),
        "abstract": abstract.strip().replace("\n", " "),
        "link": link.strip(),
        "authors": (authors or [])[:4],
        "published": published,
        "source": source,
        "citations": citations,
        "code_url": code_url,
        "trending": trending,
    }


def search_arxiv(categories: list, keywords: list, max_results: int = 5) -> list:
    """Search arXiv API for recent papers."""
    global _last_arxiv_ts
    wait = 3.5 - (time.time() - _last_arxiv_ts)
    if wait > 0:
        time.sleep(wait)

    cat_q = " OR ".join(f"cat:{c}" for c in categories)
    kw_q = " OR ".join(f'all:"{k}"' for k in keywords[:4])
    end = datetime.utcnow()
    start = end - timedelta(days=LOOKBACK_DAYS)
    date_q = (f"submittedDate:[{start.strftime('%Y%m%d')}0000"
              f" TO {end.strftime('%Y%m%d')}2359]")

    params = {
        "search_query": f"({cat_q}) AND ({kw_q}) AND {date_q}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    for attempt in range(4):
        try:
            _last_arxiv_ts = time.time()
            resp = requests.get("https://export.arxiv.org/api/query",
                                params=params, timeout=30)
            if resp.status_code == 429:
                time.sleep(5 * (2 ** attempt))
                continue
            resp.raise_for_status()
            break
        except requests.exceptions.Timeout:
            if attempt < 3:
                time.sleep(5 * (2 ** attempt))
                continue
            raise
    else:
        return []

    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(resp.text)
    papers = []
    for entry in root.findall("a:entry", ns):
        title = entry.find("a:title", ns).text or ""
        abstract = entry.find("a:summary", ns).text or ""
        link = entry.find("a:id", ns).text or ""
        authors = [a.find("a:name", ns).text
                   for a in entry.findall("a:author", ns)]
        published = (entry.find("a:published", ns).text or "")[:10]
        papers.append(_paper(title, abstract, link, authors, published, "arXiv"))
    return papers


def search_semantic_scholar(keywords: list, max_results: int = 5) -> list:
    """Search Semantic Scholar for recent high-citation papers."""
    query = " ".join(keywords[:4])
    date_from = (datetime.utcnow() - timedelta(days=max(LOOKBACK_DAYS * 15, 30))
                 ).strftime("%Y-%m-%d")
    date_to = datetime.utcnow().strftime("%Y-%m-%d")

    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,abstract,url,authors,year,citationCount,externalIds",
        "publicationDateOrYear": f"{date_from}:{date_to}",
        "sort": "citationCount:desc",
    }

    time.sleep(3)
    for attempt in range(4):
        try:
            resp = requests.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params=params, timeout=30)
            if resp.status_code == 429:
                wait = max(int(resp.headers.get("retry-after", 15)), 10 * (attempt + 1))
                time.sleep(wait)
                continue
            resp.raise_for_status()
            break
        except requests.exceptions.Timeout:
            if attempt < 3:
                time.sleep(10)
                continue
            raise
    else:
        return []

    papers = []
    for item in resp.json().get("data", []):
        if not item.get("abstract"):
            continue
        arxiv_id = (item.get("externalIds") or {}).get("ArXiv")
        link = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else (item.get("url") or "")
        authors = [a["name"] for a in (item.get("authors") or [])[:4]]
        cites = item.get("citationCount") or 0
        year = item.get("year") or 0
        trending = (cites >= 50 and year >= datetime.utcnow().year - 1)
        papers.append(_paper(
            item.get("title", ""), item.get("abstract", ""), link,
            authors, str(year), "Semantic Scholar", cites, None, trending))
    return papers


def search_papers_with_code(keywords: list, max_results: int = 5) -> list:
    """Search Papers With Code for papers that have implementations."""
    params = {"q": " ".join(keywords[:3]), "page": 1, "items_per_page": max_results}
    headers = {"User-Agent": "research-digest/1.0", "Accept": "application/json"}

    for attempt in range(3):
        try:
            resp = requests.get("https://paperswithcode.com/api/v1/papers/",
                                params=params, headers=headers, timeout=20)
            if resp.status_code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            resp.raise_for_status()
            if "json" not in resp.headers.get("Content-Type", ""):
                return []
            break
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < 2:
                time.sleep(5)
                continue
            raise
        except json.JSONDecodeError:
            return []
    else:
        return []

    data = resp.json()
    results = data.get("results", []) if isinstance(data, dict) else data
    papers = []
    for item in results[:max_results]:
        title = (item.get("title") or "").strip()
        abstract = (item.get("abstract") or "").strip()
        if not title or not abstract:
            continue
        arxiv_id = item.get("arxiv_id")
        link = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else (item.get("url_abs") or "")
        code_url = item.get("repository") or item.get("url_pdf")
        if not (isinstance(code_url, str) and code_url.startswith("http")):
            code_url = None
        authors = item.get("authors") or []
        if authors and isinstance(authors[0], dict):
            authors = [a.get("name", "") for a in authors]
        papers.append(_paper(
            title, abstract, link, authors[:4],
            item.get("published", ""), "Papers With Code",
            None, code_url, bool(code_url)))
    return papers
