"""Explicit user-approved public metadata lookup; never receives a document."""

from html import unescape
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import os
import requests

USER_AGENT = "ThesisReviewAgent/1.0 (mailto:agent@thesis-review.org)"
_SESSION = None


def get_search_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        s.trust_env = False
        proxy = (
            os.getenv("https_proxy")
            or os.getenv("HTTPS_PROXY")
            or os.getenv("http_proxy")
            or os.getenv("HTTP_PROXY")
            or ""
        )
        if proxy:
            s.proxies = {"http": proxy, "https": proxy}
        _SESSION = s
    return _SESSION


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return " ".join(text.split()).strip()


def search_items(query: str, rows: int = 5, cutoff: str | None = None):
    """Retrieve raw items from Crossref API with polite headers and fallback."""
    url = "https://api.crossref.org/works"
    params = {"query.bibliographic": query, "rows": rows}
    if cutoff:
        params["filter"] = f"until-pub-date:{cutoff}"
    headers = {"User-Agent": USER_AGENT}
    try:
        session = get_search_session()
        resp = session.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("message", {}).get("items", [])
    except Exception:
        pass

    # Fallback to urllib if requests fails
    try:
        url_full = url + "?" + urlencode(params)
        req = Request(url_full, headers=headers)
        with urlopen(req, timeout=10) as response:
            return json.load(response).get("message", {}).get("items", [])
    except Exception:
        return []


def search_works(query: str, limit: int = 5, cutoff: str | None = None):
    """Retrieve normalized academic literature entries."""
    raw_items = search_items(query, rows=limit * 2)
    works = []
    seen = set()
    for item in raw_items:
        doi = item.get("DOI")
        title_list = item.get("title") or []
        title = clean_text(title_list[0]) if title_list else ""
        if not doi or not title or doi.lower() in seen:
            continue
        parts = item.get("published", {}).get("date-parts", [[]])[0]
        published = "-".join(str(p).zfill(2) for p in parts) if parts else None
        if cutoff and (len(parts) != 3 or published > cutoff):
            continue
        seen.add(doi.lower())
        abstract = clean_text(item.get("abstract", ""))
        authors = [
            f"{a.get('given', '')} {a.get('family', '')}".strip()
            for a in item.get("author", [])
            if a.get("family")
        ]
        year = str(parts[0]) if parts else None
        works.append(
            dict(
                id=f"lit_{len(works)+1}",
                title=title,
                doi=doi,
                url="https://doi.org/" + doi,
                authors=authors,
                year=year,
                published=published,
                abstract=abstract[:2500],
                scope="abstract" if abstract else "metadata_only",
                source="crossref",
            )
        )
        if len(works) >= limit:
            break
    return works


def search_public(query: str):
    items = search_items(query)
    return [
        dict(
            title=clean_text(item.get("title", ["无标题"])[0]),
            doi=item.get("DOI"),
            url=item.get("URL") or (f"https://doi.org/{item.get('DOI')}" if item.get("DOI") else None),
            scope="metadata_only",
        )
        for item in items
    ]
