"""Member benefits (perks) from OfficeRnD, shaped for the TV board. Standard library only,
so scripts/dev.py can use the same shaping locally.

Each benefit becomes {id, name, category, offer, image}. The offer is a short line
(at most ~100 characters, readable across a lobby) taken from the benefit's own text: the lines that name the deal (percent off,
free, save, code, ...) come first, else its opening sentence. Phone numbers, emails, URLs and "click here"
instructions are left out. To change what a tile says, edit the benefit in OfficeRnD.
"""
import html, re

_DEAL = re.compile(r"\d+\s*%|\bfree\b|\boff\b|\bsave|\bcode\b|\bcomp(ed|limentary)\b|\bon us\b", re.I)
_SKIP = re.compile(r"@|https?://|www\.|\d{3}[-.\s)]+\d{3}[-.\s]\d{4}|\bclick\b|\bvisit website\b", re.I)


def _plain(text):
    text = html.unescape(re.sub(r"<(br|/p|/div|/li)[^>]*>", "\n", text or "", flags=re.I))
    return re.sub(r"<[^>]+>", " ", text).replace("​", "").replace("﻿", "").replace("\xa0", " ")


def _pieces(text):
    """Lines, then sentences, cleaned of bullets and stray spacing."""
    for line in _plain(text).split("\n"):
        line = re.sub(r"\s+", " ", line).strip(" ✓•-–—*")
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9$])", line):
            s = s.strip()
            if len(s) > 3 and not _SKIP.search(s):
                yield s


def _trim(s, limit):
    """Cut at the last clause break that fits (", " or " · "), else at a word, with an ellipsis."""
    if len(s) <= limit:
        return s
    cut = s[:limit]
    for sep in (" · ", ", "):
        at = cut.rfind(sep)
        if at >= 45:
            return cut[:at].rstrip(".")
    return cut.rsplit(" ", 1)[0].rstrip(",;:—–- ") + "…"


def offer(b, limit=100):
    seen, pieces = set(), []
    for p in list(_pieces(b.get("description"))) + list(_pieces(b.get("content"))):
        if p.lower() not in seen:
            seen.add(p.lower())
            pieces.append(p)
    deals = [p for p in pieces if _DEAL.search(p)]
    if not deals:
        return _trim(pieces[0], limit) if pieces else ""
    out = deals[0]
    if len(deals) > 1 and len(out) + 3 + len(deals[1]) <= limit:
        out += (" " if out[-1] in ".!?" else " · ") + deals[1]
    return _trim(out, limit)


def shape_benefits(raw, office=None):
    out = []
    for b in raw:
        locs = b.get("locations") or []
        if office and locs and office not in locs:
            continue
        name = (b.get("name") or "").strip()
        if not name:
            continue
        image = b.get("image") or b.get("coverImage") or ""
        out.append({
            "id": b.get("_id", ""),
            "name": name,
            "category": (b.get("category") or "").strip(),
            "offer": offer(b),
            "image": "https:" + image if image.startswith("//") else image,
        })
    return out
