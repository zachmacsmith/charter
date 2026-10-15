"""Serve the site locally with caching turned off, so every reload picks up edited files (python -m http.server lets the browser
keep stale copies of the ES modules, and a page mixing old and new modules breaks):

    python site/serve.py [PORT]        # default 8790; serves site/ (and site/_data, the local dataset copy)
"""
import functools
import http.server
import sys
from pathlib import Path


class NoCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_head(self):                                                # never answer 304 from If-Modified-Since
        del self.headers["If-Modified-Since"]
        return super().send_head()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8790
    handler = functools.partial(NoCache, directory=str(Path(__file__).resolve().parent))
    with http.server.ThreadingHTTPServer(("", port), handler) as httpd:
        print(f"serving site/ at http://localhost:{port} (no caching)")
        httpd.serve_forever()
