"""Cloud Run function: upcoming Empire Scottsdale events from OfficeRnD, shaped for the TV board.

Every request is answered from a 5-minute in-memory cache; on a miss it calls the
OfficeRnD public API. Credentials come only from environment variables (mapped
from Secret Manager at deploy time) and are never logged or returned.
"""
import html, json, logging, os, re, time, urllib.parse, urllib.request
from datetime import datetime, timezone

import functions_framework
import qrcode

ORG = os.environ.get("OFFICERND_ORG", "empire")
API = f"https://app.officernd.com/api/v2/organizations/{ORG}/events"
# The auth guide and the OpenAPI spec name different token paths; try both.
TOKEN_URLS = ["https://identity.officernd.com/oauth/token", "https://identity.officernd.com/auth/token"]
SCOPE = "flex.collaboration.events.read"
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
CACHE_SECONDS = int(os.environ.get("CACHE_SECONDS", "300"))
UA = {"User-Agent": "EmpireEvents/1.0"}

_token = {"value": None, "expires": 0}
_cache = {"body": None, "expires": 0}


def _http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _access_token():
    if _token["value"] and time.time() < _token["expires"]:
        return _token["value"]
    body = urllib.parse.urlencode({
        "client_id": os.environ["OFFICERND_CLIENT_ID"],
        "client_secret": os.environ["OFFICERND_CLIENT_SECRET"],
        "grant_type": "client_credentials",
        "scope": SCOPE,
    }).encode()
    for url in TOKEN_URLS:
        try:
            tok = _http(url, body, {"Content-Type": "application/x-www-form-urlencoded"})
        except Exception as e:  # message holds the URL and status only, never the form body
            logging.warning("token request to %s failed: %s", url, e)
            continue
        _token.update(value=tok["access_token"], expires=time.time() + int(tok.get("expires_in", 3600)) - 120)
        return _token["value"]
    raise RuntimeError("could not obtain an OfficeRnD access token")


def fetch_events():
    """All events starting from now. Public API v2: bracket operators, pages of at most 50."""
    auth = {"Authorization": f"Bearer {_access_token()}"}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # computed per call, never fixed
    params, out = {"start[$gte]": now, "$limit": 50}, []
    while True:
        page = _http(f"{API}?{urllib.parse.urlencode(params)}", headers=auth)
        out += page.get("results", [])
        if not page.get("cursorNext"):
            return out
        params["$cursorNext"] = page["cursorNext"]


# --- blurbs -----------------------------------------------------------------

_STOP = re.compile(r"^(disclaimer|release of liability|use of likeness|dress code|thank you to our sponsors|explore the lineup)", re.I)
_MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_DATE_LINE = re.compile(rf"^(\w+day,?\s+)?{_MONTH}\s+\d|^\d{{1,2}}(:\d\d)?\s*(am|pm)|^\d{{1,2}}\+\s*event", re.I)
_PRIVATE = re.compile(r"@|https?://|www\.|\d{3}[-.\s]\d{3}[-.\s]\d{4}|referr", re.I)
_PROMO = re.compile(r"\bcode\b", re.I)


def _lines(desc):
    text = html.unescape(re.sub(r"<(br|/p|/div|/li)[^>]*>", "\n", desc or "", flags=re.I))
    text = re.sub(r"<[^>]+>", " ", text).replace("​", "").replace("\xa0", " ")
    for raw in text.split("\n"):
        line = re.sub(r"\s+", " ", raw).strip()
        if _STOP.match(line):
            return
        if line and not line.endswith(":") and not _PRIVATE.search(line) and not _DATE_LINE.match(line):
            yield re.sub(r"\s+([:,.])", r"\1", line)


def _join(parts):
    # Lines from the description often lack end punctuation. Never add a period after
    # a promo code (it would read as part of it): separate those lines with a dot leader.
    text = ""
    for p in parts:
        if text:
            text += " " if text[-1] in ".!?…" else (". " if text[-1].islower() else " · ")
        text += p
    return text


def blurb(desc, limit=190):
    """A short blurb from the event description. Promo-code lines come first, verbatim and never trimmed."""
    lines = list(_lines(desc))
    promo = [l for l in lines if _PROMO.search(l)]
    out = list(promo)
    for l in (l for l in lines if l not in promo):
        room = limit - len(_join(out)) - 2
        if len(l) <= room:
            out.append(l)
            continue
        if room > 60:
            cut = l[:room]
            end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
            out.append(cut[:end + 1] if end > 40 else cut.rsplit(" ", 1)[0].rstrip(",;:—–- ") + "…")
        break
    text = _join(out)
    return text + "." if text and text[-1].islower() else text


# --- shaping ----------------------------------------------------------------

def _first_link(links):
    for l in links or []:
        url = l if isinstance(l, str) else (l.get("url") or l.get("link") or l.get("href"))
        if url:
            return url.strip()
    return ""


def _qr(url):
    q = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(url); q.make(fit=True)
    m = q.get_matrix(); n = len(m)
    d = "".join(f"M{x} {y}h1v1h-1z" for y, r in enumerate(m) for x, v in enumerate(r) if v)
    return f'<svg viewBox="0 0 {n} {n}" shape-rendering="crispEdges" aria-hidden="true"><path d="{d}"/></svg>'


def shape(raw):
    now = datetime.now(timezone.utc)
    events = []
    for e in sorted(raw, key=lambda e: e["start"]):
        if datetime.fromisoformat(e["start"].replace("Z", "+00:00")) <= now:
            continue
        if str(e.get("status", "")).lower() in ("cancelled", "canceled"):
            continue
        link, image = _first_link(e.get("links")), e.get("image") or ""
        events.append({
            "id": e.get("_id", ""),
            "title": (e.get("title") or "").strip(),
            "start": e["start"],
            "end": e.get("end") or e["start"],
            "where": (e.get("where") or "Empire Scottsdale").strip(),
            "link": link,
            "blurb": blurb(e.get("description")),
            "image": "https:" + image if image.startswith("//") else image,
            "qr": _qr(link) if link else "",
        })
    return events


# --- HTTP -------------------------------------------------------------------

@functions_framework.http
def events(request):
    cors = {"Access-Control-Allow-Origin": ALLOWED_ORIGIN, "Vary": "Origin"}
    if request.method == "OPTIONS":
        return ("", 204, {**cors, "Access-Control-Allow-Methods": "GET", "Access-Control-Max-Age": "3600"})
    headers = {**cors, "Content-Type": "application/json", "Cache-Control": f"public, max-age={CACHE_SECONDS}"}
    if _cache["body"] and time.time() < _cache["expires"]:
        return (_cache["body"], 200, headers)
    try:
        body = json.dumps({"generated": datetime.now(timezone.utc).isoformat(), "events": shape(fetch_events())})
    except Exception:
        logging.exception("refreshing events failed")
        if _cache["body"]:  # stale beats blank on a lobby screen
            return (_cache["body"], 200, {**headers, "Cache-Control": "no-store"})
        return (json.dumps({"error": "events unavailable"}), 502, {**headers, "Cache-Control": "no-store"})
    _cache.update(body=body, expires=time.time() + CACHE_SECONDS)
    return (body, 200, headers)
