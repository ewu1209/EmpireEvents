#!/usr/bin/env python3
"""Local design preview for docs/: live events, live reload, no deploys.

  python3 scripts/dev.py            # then open http://localhost:8770/  (add #3 for slide 3)

- Serves docs/ as-is, except config.js, which points the page at /__events and
  adds a tiny watcher that reloads the page whenever a file in docs/ changes.
- /__events fetches the deployed function server-side (so its CORS rule doesn't
  apply) and caches the answer for a minute to keep OfficeRnD calls low.
Standard library only.
"""
import http.server, json, os, sys, time, urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs")
LIVE = "https://us-west1-empire-events-2610.cloudfunctions.net/empire-events"
PORT = int(os.environ.get("PORT", "8770"))
_cache = {"body": None, "at": 0}

CONFIG = """window.EMPIRE_EVENTS_API = "/__events";
(() => {  // dev only: reload when docs/ changes
  let v;
  setInterval(async () => {
    try {
      const n = await (await fetch("/__version", { cache: "no-store" })).text();
      if (v && n !== v) location.reload();
      v = n;
    } catch (_) {}
  }, 800);
})();
"""


def version():
    return str(max(os.path.getmtime(os.path.join(d, f)) for d, _, fs in os.walk(ROOT) for f in fs))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def send(self, body, ctype, status=200):
        body = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0].split("#")[0]
        if path == "/config.js":
            return self.send(CONFIG, "text/javascript")
        if path == "/__version":
            return self.send(version(), "text/plain")
        if path == "/__events":
            if not _cache["body"] or time.time() - _cache["at"] > 60:
                try:
                    with urllib.request.urlopen(LIVE, timeout=20) as r:
                        _cache.update(body=r.read(), at=time.time())
                except Exception as e:
                    if not _cache["body"]:
                        return self.send(json.dumps({"error": str(e)}), "application/json", 502)
            return self.send(_cache["body"], "application/json")
        return super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        if "/__version" not in (args[0] if args else ""):
            sys.stderr.write("%s\n" % (fmt % args))


if __name__ == "__main__":
    print(f"EmpireEvents preview: http://localhost:{PORT}/")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
