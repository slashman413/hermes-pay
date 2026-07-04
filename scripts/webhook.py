#!/usr/bin/env python3
"""
webhook.py — Real payment event ingestion for Ko-fi and Gumroad.

Receives live webhook POST requests, verifies authenticity, maps each event
to a product/tier defined in payment.py's PRODUCTS dict, and appends a
normalized record to data/revenue.json. Transactions are deduplicated by txn_id
so re-deliveries are safe.

Deployment: run this as a small HTTP server on any host that can receive
inbound HTTPS requests (e.g. a $5 VPS, Railway, Render, or Fly.io free tier).
See PAYMENTS.md for the full setup guide.

Required env vars (never hardcode these):
    KOFI_VERIFICATION_TOKEN   — from Ko-fi Settings > Webhooks > Verification Token
    GUMROAD_SECRET            — arbitrary shared secret you set in Gumroad's
                                webhook settings ("secret" field) and here

Usage:
    python scripts/webhook.py          # listens on 0.0.0.0:8787
    PORT=9000 python scripts/webhook.py
"""

import os
import sys
import json
import hmac
import hashlib
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
REVENUE_FILE = DATA_DIR / "revenue.json"

# ---------------------------------------------------------------------------
# PRODUCTS map (canonical source is payment.py; duplicated here for
# standalone operation so this file can be deployed independently).
# Keys: Ko-fi shop item URL slug or Gumroad product permalink.
# ---------------------------------------------------------------------------
# Import PRODUCTS from payment.py when running from the same directory tree.
_payment_mod_path = Path(__file__).parent / "payment.py"
if _payment_mod_path.exists():
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("payment", _payment_mod_path)
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    PRODUCTS = _mod.PRODUCTS
else:
    # Fallback copy — keep in sync with payment.py manually.
    PRODUCTS = {
        "shortsgen": {
            "name": "ShortsGen Pro",
            "tiers": {
                "free": {"price": 0},
                "pro": {"price": 29, "kofi": "https://ko-fi.com/s/896aa3c229"},
                "business": {"price": 99, "kofi": "https://ko-fi.com/s/896aa3c229"},
                "enterprise": {"price": 499, "kofi": "https://ko-fi.com/s/896aa3c229"},
            },
        },
        "twse": {
            "name": "TWSE Premium",
            "tiers": {
                "monthly": {"price": 49, "kofi": "https://ko-fi.com/s/b99720d13d"},
                "quarterly": {"price": 99, "kofi": "https://ko-fi.com/s/b99720d13d"},
                "annual": {"price": 299, "kofi": "https://ko-fi.com/s/b99720d13d"},
            },
        },
        "dealfinder": {
            "name": "Deal Finder Pro",
            "tiers": {
                "free": {"price": 0},
                "pro": {"price": 9, "kofi": "https://ko-fi.com/s/5730f8f947"},
            },
        },
        "seofarm": {
            "name": "SEO Content Engine",
            "tiers": {
                "free": {"price": 0},
                "pro": {"price": 19, "kofi": "https://ko-fi.com/s/a03f0a8e3b"},
            },
        },
    }

# Build a reverse-lookup: Ko-fi shop URL slug → (product_key, tier_key)
_KOFI_SLUG_MAP: dict[str, tuple[str, str]] = {}
for _pk, _pv in PRODUCTS.items():
    for _tk, _tv in _pv.get("tiers", {}).items():
        _url = _tv.get("kofi", "")
        if _url:
            # slug is the last path component: ".../s/896aa3c229" → "896aa3c229"
            _slug = _url.rstrip("/").split("/")[-1]
            if _slug and _slug not in _KOFI_SLUG_MAP:
                _KOFI_SLUG_MAP[_slug] = (_pk, _tk)

# ---------------------------------------------------------------------------
# Env vars (set these in your hosting environment — never commit values)
# ---------------------------------------------------------------------------
KOFI_VERIFICATION_TOKEN: str = os.environ.get("KOFI_VERIFICATION_TOKEN", "")
GUMROAD_SECRET: str = os.environ.get("GUMROAD_SECRET", "")

_WARN_MISSING: list[str] = []
if not KOFI_VERIFICATION_TOKEN:
    _WARN_MISSING.append("KOFI_VERIFICATION_TOKEN")
if not GUMROAD_SECRET:
    _WARN_MISSING.append("GUMROAD_SECRET")
if _WARN_MISSING:
    print(
        f"[webhook] WARNING: env vars not set: {', '.join(_WARN_MISSING)}. "
        "Webhook verification will REJECT all events until these are configured."
    )


# ---------------------------------------------------------------------------
# Revenue log helpers
# ---------------------------------------------------------------------------

def _load_revenue() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if REVENUE_FILE.exists():
        try:
            data = json.loads(REVENUE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def _save_revenue(records: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REVENUE_FILE.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def append_revenue(record: dict) -> tuple[bool, str]:
    """
    Append record to revenue.json, deduplicating on txn_id.
    Returns (was_new, message).
    """
    txn_id = record.get("txn_id", "")
    records = _load_revenue()
    if txn_id:
        existing_ids = {r.get("txn_id") for r in records}
        if txn_id in existing_ids:
            return False, f"duplicate txn_id={txn_id}, skipped"
    records.append(record)
    _save_revenue(records)
    return True, f"recorded txn_id={txn_id}"


# ---------------------------------------------------------------------------
# Ko-fi webhook
# ---------------------------------------------------------------------------
# Ko-fi sends a form-encoded POST with a single field: data=<URL-encoded JSON>
# The JSON payload includes a "verification_token" field that must match
# the token shown in your Ko-fi account Settings > Webhooks.
#
# Reference: https://ko-fi.com/manage/webhooks

def _verify_kofi(payload: dict) -> bool:
    """
    Ko-fi verification: compare the token embedded in the payload against
    KOFI_VERIFICATION_TOKEN.  Constant-time compare prevents timing attacks.
    """
    if not KOFI_VERIFICATION_TOKEN:
        return False
    received = payload.get("verification_token", "")
    return hmac.compare_digest(
        KOFI_VERIFICATION_TOKEN.encode("utf-8"),
        received.encode("utf-8"),
    )


def _map_kofi_product(payload: dict) -> tuple[str, str]:
    """
    Map a Ko-fi payload to (product_key, tier_key).
    Ko-fi shop items carry the item URL in payload["url"] or the shop item
    path in payload["shop_items"][0]["direct_link_code"].
    Falls back to matching on amount if no slug is recognised.
    """
    # Try shop item direct link code first (most reliable)
    shop_items = payload.get("shop_items") or []
    for item in shop_items:
        slug = item.get("direct_link_code", "")
        if slug and slug in _KOFI_SLUG_MAP:
            return _KOFI_SLUG_MAP[slug]

    # Try the top-level url field
    url = payload.get("url", "")
    if url:
        slug = url.rstrip("/").split("/")[-1]
        if slug in _KOFI_SLUG_MAP:
            return _KOFI_SLUG_MAP[slug]

    # Amount-based fallback: find closest price match
    try:
        amount = float(payload.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0.0
    best_product, best_tier = "unknown", "unknown"
    best_delta = float("inf")
    for pk, pv in PRODUCTS.items():
        for tk, tv in pv.get("tiers", {}).items():
            price = tv.get("price", 0)
            if price > 0 and abs(amount - price) < best_delta:
                best_delta = abs(amount - price)
                best_product, best_tier = pk, tk
    return best_product, best_tier


def handle_kofi(body: bytes) -> tuple[int, str]:
    """Parse and ingest a Ko-fi webhook POST body."""
    # Body is application/x-www-form-urlencoded: data=<json>
    try:
        fields = urllib.parse.parse_qs(body.decode("utf-8"))
        raw_json = fields.get("data", [""])[0]
        payload = json.loads(raw_json)
    except Exception as exc:
        return 400, f"malformed Ko-fi payload: {exc}"

    if not _verify_kofi(payload):
        return 403, "Ko-fi verification_token mismatch — check KOFI_VERIFICATION_TOKEN"

    # Only ingest completed payments (type = "Shop Order" or "Subscription")
    event_type = payload.get("type", "")
    if event_type not in ("Shop Order", "Subscription", "Donation"):
        return 200, f"ignored event type={event_type}"

    # For subscriptions, only record the first payment (is_first_subscription_payment)
    # and each renewal (both carry real money).
    product_key, tier_key = _map_kofi_product(payload)

    try:
        amount = float(payload.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0.0

    record = {
        "date": payload.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "product": product_key,
        "tier": tier_key,
        "amount": amount,
        "currency": payload.get("currency", "USD"),
        "customer": payload.get("email", ""),
        "source": "kofi",
        "txn_id": payload.get("kofi_transaction_id", ""),
        "event_type": event_type,
    }

    new, msg = append_revenue(record)
    status_code = 200
    return status_code, ("kofi ok: " + msg)


# ---------------------------------------------------------------------------
# Gumroad webhook
# ---------------------------------------------------------------------------
# Gumroad sends a form-encoded POST (application/x-www-form-urlencoded).
# Each sale event includes fields like: seller_id, product_permalink,
# price, currency, purchaser_id, sale_id, email, etc.
#
# Gumroad does NOT sign individual requests with HMAC; instead it supports
# an optional "secret" parameter you include in the webhook URL query string:
#   https://your-server.com/webhook/gumroad?secret=YOUR_SECRET
# We compare that query-string secret against GUMROAD_SECRET.
#
# Reference: https://help.gumroad.com/article/180-integrate-gumroad-with-your-website

# Map Gumroad product permalink → (product_key, tier_key)
# Populate this once you create Gumroad listings and know their permalinks.
# Format:  "gumroad-permalink": ("product_key", "tier_key")
GUMROAD_PERMALINK_MAP: dict[str, tuple[str, str]] = {
    # Examples — update when you create Gumroad products:
    # "shortsgen-pro": ("shortsgen", "pro"),
    # "shortsgen-business": ("shortsgen", "business"),
    # "twse-monthly": ("twse", "monthly"),
    # "dealfinder-pro": ("dealfinder", "pro"),
    # "seoengine-pro": ("seofarm", "pro"),
}


def _verify_gumroad(query_string: str) -> bool:
    """
    Verify the shared secret passed as ?secret=... in the webhook URL.
    Constant-time compare prevents timing attacks.
    """
    if not GUMROAD_SECRET:
        return False
    params = urllib.parse.parse_qs(query_string)
    received = params.get("secret", [""])[0]
    return hmac.compare_digest(
        GUMROAD_SECRET.encode("utf-8"),
        received.encode("utf-8"),
    )


def handle_gumroad(body: bytes, query_string: str) -> tuple[int, str]:
    """Parse and ingest a Gumroad sale webhook POST body."""
    if not _verify_gumroad(query_string):
        return 403, "Gumroad secret mismatch — check GUMROAD_SECRET and webhook URL"

    try:
        fields = urllib.parse.parse_qs(body.decode("utf-8"))
        # parse_qs returns lists; take first value for each key
        payload = {k: v[0] for k, v in fields.items()}
    except Exception as exc:
        return 400, f"malformed Gumroad payload: {exc}"

    # Only ingest sale events (Gumroad also sends refund/dispute events)
    # The "sale" event has a "sale_id" field.
    sale_id = payload.get("sale_id", "")
    if not sale_id:
        return 200, "ignored: no sale_id (not a sale event)"

    permalink = payload.get("product_permalink", "")
    if permalink in GUMROAD_PERMALINK_MAP:
        product_key, tier_key = GUMROAD_PERMALINK_MAP[permalink]
    else:
        # Amount-based fallback
        try:
            # Gumroad sends price in cents
            amount_cents = int(payload.get("price", 0))
            amount = amount_cents / 100.0
        except (TypeError, ValueError):
            amount = 0.0
        product_key, tier_key = "unknown", "unknown"
        best_delta = float("inf")
        for pk, pv in PRODUCTS.items():
            for tk, tv in pv.get("tiers", {}).items():
                price = tv.get("price", 0)
                if price > 0 and abs(amount - price) < best_delta:
                    best_delta = abs(amount - price)
                    product_key, tier_key = pk, tk

    try:
        amount_cents = int(payload.get("price", 0))
        amount = amount_cents / 100.0
    except (TypeError, ValueError):
        amount = 0.0

    record = {
        "date": payload.get("sale_timestamp", datetime.now(timezone.utc).isoformat()),
        "product": product_key,
        "tier": tier_key,
        "amount": amount,
        "currency": payload.get("currency", "USD").upper(),
        "customer": payload.get("email", ""),
        "source": "gumroad",
        "txn_id": sale_id,
        "permalink": permalink,
    }

    new, msg = append_revenue(record)
    return 200, ("gumroad ok: " + msg)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class WebhookHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler. Routes:
        POST /webhook/kofi      — Ko-fi events
        POST /webhook/gumroad   — Gumroad sale events
        GET  /health            — liveness check
    """

    def log_message(self, fmt: str, *args) -> None:  # noqa: ANN001
        # Prefix all access logs with [webhook] for easy grepping
        print(f"[webhook] {self.address_string()} - {fmt % args}")

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def _respond(self, code: int, message: str) -> None:
        body = message.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/health":
            records = _load_revenue()
            self._respond(200, f"ok — {len(records)} revenue records")
        else:
            self._respond(404, "not found")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = parsed.query
        body = self._read_body()

        if path == "/webhook/kofi":
            code, msg = handle_kofi(body)
        elif path == "/webhook/gumroad":
            code, msg = handle_gumroad(body, query)
        else:
            code, msg = 404, "unknown webhook path"

        print(f"[webhook] {path} → {code} {msg}")
        self._respond(code, msg)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def self_test() -> None:
    """
    Inject a synthetic Ko-fi and Gumroad event directly (no HTTP) to verify
    the parse → verify → map → write pipeline.  Useful for CI smoke tests.

    Run: python scripts/webhook.py --self-test
    """
    import tempfile, shutil

    # Redirect revenue file to a temp location so we don't pollute real data
    global REVENUE_FILE
    tmp_dir = Path(tempfile.mkdtemp())
    REVENUE_FILE = tmp_dir / "revenue.json"

    # ---- Ko-fi synthetic event ----
    # Use real KOFI_VERIFICATION_TOKEN env var if set, otherwise patch it.
    global KOFI_VERIFICATION_TOKEN
    original_token = KOFI_VERIFICATION_TOKEN
    if not KOFI_VERIFICATION_TOKEN:
        KOFI_VERIFICATION_TOKEN = "test-token"

    kofi_payload = {
        "verification_token": KOFI_VERIFICATION_TOKEN,
        "kofi_transaction_id": "SELF-TEST-KOFI-001",
        "type": "Shop Order",
        "amount": "29.00",
        "currency": "USD",
        "email": "test@example.com",
        "timestamp": "2026-07-04T00:00:00Z",
        "shop_items": [{"direct_link_code": list(_KOFI_SLUG_MAP.keys())[0]}]
        if _KOFI_SLUG_MAP else [],
    }
    body = ("data=" + urllib.parse.quote(json.dumps(kofi_payload))).encode()
    code, msg = handle_kofi(body)
    assert code == 200, f"Ko-fi self-test failed: {code} {msg}"
    print(f"[self-test] Ko-fi: {msg}")

    # Duplicate should be skipped
    code2, msg2 = handle_kofi(body)
    assert "duplicate" in msg2, f"Ko-fi dedup failed: {msg2}"
    print(f"[self-test] Ko-fi dedup: {msg2}")

    # ---- Gumroad synthetic event ----
    global GUMROAD_SECRET
    original_secret = GUMROAD_SECRET
    if not GUMROAD_SECRET:
        GUMROAD_SECRET = "test-secret"

    gumroad_fields = {
        "sale_id": "SELF-TEST-GUMROAD-001",
        "product_permalink": "shortsgen-pro",
        "price": "2900",  # cents
        "currency": "usd",
        "email": "buyer@example.com",
        "sale_timestamp": "2026-07-04T01:00:00Z",
    }
    g_body = urllib.parse.urlencode(gumroad_fields).encode()
    g_query = f"secret={GUMROAD_SECRET}"
    code, msg = handle_gumroad(g_body, g_query)
    assert code == 200, f"Gumroad self-test failed: {code} {msg}"
    print(f"[self-test] Gumroad: {msg}")

    records = _load_revenue()
    assert len(records) == 2, f"Expected 2 records, got {len(records)}"
    print(f"[self-test] PASSED — {len(records)} records written to {REVENUE_FILE}")
    print(json.dumps(records, indent=2))

    # Restore
    KOFI_VERIFICATION_TOKEN = original_token
    GUMROAD_SECRET = original_secret
    shutil.rmtree(tmp_dir)


def main() -> None:
    if "--self-test" in sys.argv:
        self_test()
        return

    port = int(os.environ.get("PORT", 8787))
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    print(f"[webhook] listening on port {port}")
    print(f"[webhook] Ko-fi endpoint:   POST /webhook/kofi")
    print(f"[webhook] Gumroad endpoint: POST /webhook/gumroad?secret=<GUMROAD_SECRET>")
    print(f"[webhook] Revenue log:      {REVENUE_FILE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[webhook] shutting down")


if __name__ == "__main__":
    main()
