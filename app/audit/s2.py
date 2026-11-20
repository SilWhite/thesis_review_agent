"""Semantic Scholar Graph API integration for scholarly literature retrieval.

Supports academic paper search, abstract extraction, citation metrics,
and rate-limited requests using S2 API keys.
"""

from html import unescape
import json
import logging
import os
import re
import threading
import time

log = logging.getLogger(__name__)

_S2_LOCK = threading.Lock()
_LAST_REQUEST_TIME = 0.0
_MIN_INTERVAL = 1.15  # Minimum seconds between calls to respect S2 rate limit (1 QPS)
_S2_SESSION = None


def _get_s2_session():
    global _S2_SESSION
    with _S2_LOCK:
        if _S2_SESSION is None:
            import requests

            s = requests.Session()
            s.trust_env = False
            _S2_SESSION = s
        return _S2_SESSION


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return " ".join(text.split()).strip()


def search_semantic_scholar(
    query: str,
    api_key: str = "",
    limit: int = 10,
    timeout: int = 15,
    year: str = "2020-",
) -> list[dict]:
    """Search papers on Semantic Scholar Graph API.
    
    Returns a list of normalized paper dictionaries with title, abstract,
    authors, year, venue, citationCount, tldr, and DOI.
    """
    global _LAST_REQUEST_TIME
    q = clean_text(query)
    if not q:
        return []

    fields = "paperId,title,abstract,authors,year,publicationDate,venue,citationCount,openAccessPdf,externalIds,tldr"
    params = {
        "query": q,
        "limit": min(limit, 30),
        "fields": fields,
    }
    if year:
        params["year"] = year
    url = "https://api.semanticscholar.org/graph/v1/paper/search"

    headers = {
        "User-Agent": "curl/8.21.0",
        "Accept": "application/json",
    }
    if api_key:
        headers["x-api-key"] = api_key.strip()

    proxy_url = (
        os.getenv("https_proxy")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("http_proxy")
        or os.getenv("HTTP_PROXY")
        or ""
    )
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

    for attempt in range(2):
        with _S2_LOCK:
            current = time.monotonic()
            delay = _MIN_INTERVAL - (current - _LAST_REQUEST_TIME)
            if delay > 0:
                time.sleep(delay)
            _LAST_REQUEST_TIME = time.monotonic()

        try:
            s = _get_s2_session()
            res = s.get(
                url,
                params=params,
                headers=headers,
                proxies=proxies,
                timeout=timeout,
            )
            if res.status_code == 429:
                if attempt == 0:
                    time.sleep(2.0)
                    continue
                log.warning("Semantic Scholar 429 Too Many Requests for query %r", q)
                break
            if res.status_code != 200:
                log.warning(
                    "Semantic Scholar status %d for query %r: %s",
                    res.status_code,
                    q,
                    res.text[:200],
                )
                break

            data = res.json()
            raw_items = data.get("data") or []
            results = []
            for item in raw_items:
                title = clean_text(item.get("title", ""))
                if not title:
                    continue
                paper_id = item.get("paperId", "")
                ext_ids = item.get("externalIds") or {}
                doi = ext_ids.get("DOI", "")
                arxiv_id = ext_ids.get("ArXiv", "")
                abstract = clean_text(item.get("abstract", ""))
                tldr_obj = item.get("tldr") or {}
                tldr = (
                    clean_text(tldr_obj.get("text", ""))
                    if isinstance(tldr_obj, dict)
                    else ""
                )
                authors = [
                    clean_text(a.get("name", ""))
                    for a in (item.get("authors") or [])
                    if a.get("name")
                ]
                year = str(item.get("year")) if item.get("year") else ""
                venue = clean_text(item.get("venue", ""))
                citations = item.get("citationCount", 0)

                url_link = ""
                if doi:
                    url_link = f"https://doi.org/{doi}"
                elif arxiv_id:
                    url_link = f"https://arxiv.org/abs/{arxiv_id}"
                elif paper_id:
                    url_link = f"https://www.semanticscholar.org/paper/{paper_id}"

                results.append(
                    {
                        "paper_id": paper_id,
                        "doi": doi,
                        "arxiv_id": arxiv_id,
                        "title": title,
                        "authors": authors,
                        "year": year,
                        "published": item.get("publicationDate") or "",
                        "venue": venue,
                        "citation_count": citations,
                        "tldr": tldr,
                        "abstract": abstract[:3000],
                        "url": url_link,
                        "scope": "abstract" if abstract else "metadata_only",
                        "source": "semantic_scholar",
                    }
                )
            return results
        except Exception as e:
            log.warning("Semantic Scholar error for query %r: %s", q, e)
            if attempt == 0:
                time.sleep(1.0)
                continue
            break

    return []
