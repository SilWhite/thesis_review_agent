"""Explicit user-approved public metadata lookup; never receives a document."""

import json
from urllib.parse import urlencode
from urllib.request import urlopen


def search_public(query):
    url = "https://api.crossref.org/works?" + urlencode(
        {"query.bibliographic": query, "rows": 5}
    )
    with urlopen(url, timeout=20) as response:
        items = json.load(response)["message"]["items"]
    return [
        dict(
            title=item.get("title", ["无标题"])[0],
            doi=item.get("DOI"),
            url=item.get("URL"),
            scope="metadata_only",
        )
        for item in items
    ]
