"""Canonical figure/table numbers and grouped prose references."""

import re
import unicodedata

SEP = r"[.·\-_—–－]"
NUMBER = rf"\d+(?:{SEP}\d+)?"
PREFIX = r"(图|表|Figures?\.?|Fig\.|Tables?\.?)"


def number_key(number):
    number = re.sub(r"\s+", "", unicodedata.normalize("NFKC", number))
    return re.sub(SEP, ".", number)


def references(text):
    text = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))
    found = {"figure": set(), "table": set()}
    pattern = re.compile(rf"{PREFIX}({NUMBER})(?!\d|[.·]\d)", re.I)
    for match in pattern.finditer(text):
        kind = (
            "table" if match.group(1).lower().startswith(("表", "table")) else "figure"
        )
        first = number_key(match.group(2))
        found[kind].add(first)
        cursor, previous = match.end(), first
        while True:
            tail = re.match(
                rf"([、,，和及与至到~～–—-])(?:{PREFIX})?({NUMBER})(?!\d|[.·]\d)",
                text[cursor:],
                re.I,
            )
            if not tail:
                break
            if tail.group(2):
                tail_kind = (
                    "table"
                    if tail.group(2).lower().startswith(("表", "table"))
                    else "figure"
                )
                if tail_kind != kind:
                    break
            last = number_key(tail.group(3))
            found[kind].add(last)
            if tail.group(1) in "至到~～–—-":
                a, b = previous.split("."), last.split(".")
                if (
                    len(a) == len(b) == 2
                    and a[0] == b[0]
                    and 0 < int(b[1]) - int(a[1]) < 100
                ):
                    found[kind].update(
                        f"{a[0]}.{i}" for i in range(int(a[1]), int(b[1]) + 1)
                    )
            previous = last
            cursor += tail.end()
    return found
