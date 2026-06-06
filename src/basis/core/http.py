"""HTTP helpers — public, no-key REST calls with a browser User-Agent.

Several exchange endpoints (OKX, Coinbase, Bybit) 403 the default urllib
User-Agent, so we always send a browser-like one. All requests RETRY with backoff on
transient failures (DNS hiccups, timeouts, 429, 5xx) so a momentary network blip on a
home server doesn't kill a cycle. Definitive client errors (4xx except 408/429, e.g.
geo-block 451/403) raise immediately — retrying them is pointless.
"""

import json
import socket
import time
import urllib.error
import urllib.request

TIMEOUT = 12
RETRIES = 3            # total attempts on transient errors
BACKOFF = 1.5          # seconds, multiplied by the attempt number
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def _request(req):
    last = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, socket.timeout, ConnectionError,
                json.JSONDecodeError) as e:
            code = getattr(e, "code", None)
            # 4xx are definitive (bad request / geo-block) — don't waste retries,
            # except 408 (timeout) and 429 (rate limit) which are worth retrying.
            if code is not None and 400 <= code < 500 and code not in (408, 429):
                raise
            last = e
            if attempt < RETRIES - 1:
                time.sleep(BACKOFF * (attempt + 1))
    raise last


def http_get(url):
    return _request(urllib.request.Request(url, headers=UA))


def http_post(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, headers={**UA, "Content-Type": "application/json"},
                                 data=data, method="POST")
    return _request(req)


def safe(label, fn):
    """Run a source fn; never let one dead endpoint kill the whole run."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        print(f"  ! {label} failed: {str(e)[:90]}")
        return None
