"""HTTP helpers — public, no-key REST calls with a browser User-Agent.

Several exchange endpoints (OKX, Coinbase, Bybit) 403 the default urllib
User-Agent, so we always send a browser-like one.
"""

import json
import urllib.request

TIMEOUT = 12
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def http_get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def http_post(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, headers={**UA, "Content-Type": "application/json"},
                                 data=data, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def safe(label, fn):
    """Run a source fn; never let one dead endpoint kill the whole run."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        print(f"  ! {label} failed: {str(e)[:90]}")
        return None
