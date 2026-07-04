# PAYMENTS.md — Webhook Setup Guide

This guide explains how to wire Ko-fi and Gumroad into the live revenue log
(`data/revenue.json`) so the hermes-pro dashboard shows real booked numbers.

---

## Architecture

```
Ko-fi / Gumroad sale
        │
        ▼  HTTPS POST
scripts/webhook.py  (your deployed server)
        │
        ▼  append + deduplicate
data/revenue.json  (canonical revenue log)
        │
        ▼  git push / sync
hermes-pro/data/revenue.json
        │
        ▼
docs/index.html  (GitHub Pages dashboard)
```

---

## Required Environment Variables

Set these on whatever host runs `webhook.py`. **Never commit their values.**

| Variable | Where to find it | Purpose |
|---|---|---|
| `KOFI_VERIFICATION_TOKEN` | Ko-fi Dashboard > Settings > Webhooks > Verification Token | Authenticates Ko-fi events |
| `GUMROAD_SECRET` | You choose this value; paste it into Gumroad and here | Authenticates Gumroad events |
| `PORT` | Optional, default `8787` | Port the server listens on |

Export them before starting the server:

```bash
export KOFI_VERIFICATION_TOKEN="paste-your-token-here"
export GUMROAD_SECRET="choose-any-long-random-string"
export PORT=8787
python scripts/webhook.py
```

---

## Deploying the Webhook Server

The server is a zero-dependency Python stdlib HTTP server. Any host that can
receive inbound HTTPS is fine. Recommended free/cheap options:

| Platform | Command |
|---|---|
| Railway | `railway up` (set env vars in dashboard) |
| Render | Free web service, set env vars in UI |
| Fly.io | `fly launch` + `fly secrets set` |
| VPS | `python scripts/webhook.py` behind nginx + certbot |

The server exposes:
- `POST /webhook/kofi` — Ko-fi events
- `POST /webhook/gumroad?secret=<GUMROAD_SECRET>` — Gumroad events
- `GET  /health` — liveness check (returns record count)

---

## Ko-fi Configuration

### Verification

Ko-fi includes a `verification_token` field **inside** the JSON payload. The
webhook handler compares it to your `KOFI_VERIFICATION_TOKEN` using
constant-time comparison (`hmac.compare_digest`). A mismatch returns HTTP 403.

### Steps

1. Go to: https://ko-fi.com/manage/webhooks
2. Set webhook URL: `https://your-server.com/webhook/kofi`
3. Copy the "Verification Token" shown on that page.
4. Set `KOFI_VERIFICATION_TOKEN=<that token>` in your server environment.
5. Click "Test" — the server should log `kofi ok`.

### Product Mapping

The handler maps Ko-fi shop item URLs to product/tier using the slugs already
in `scripts/payment.py`'s `PRODUCTS` dict (e.g. `896aa3c229` → shortsgen/pro).
No extra config needed as long as PRODUCTS stays up to date.

---

## Gumroad Configuration

### Verification

Gumroad does not sign request bodies with HMAC. Instead, you append a
`?secret=<GUMROAD_SECRET>` query parameter to your webhook URL. The handler
compares it against `GUMROAD_SECRET` using constant-time comparison. A
mismatch returns HTTP 403.

### Steps

1. Go to: https://app.gumroad.com/settings/advanced → Webhooks
2. Add webhook URL: `https://your-server.com/webhook/gumroad?secret=<GUMROAD_SECRET>`
   (replace `<GUMROAD_SECRET>` with the actual value of your env var)
3. Set `GUMROAD_SECRET=<same value>` in your server environment.
4. Gumroad will send a ping — verify the server responds 200.

### Product Permalink Mapping

After you create Gumroad product listings, edit `GUMROAD_PERMALINK_MAP` in
`scripts/webhook.py` to map each permalink to the correct product/tier:

```python
GUMROAD_PERMALINK_MAP = {
    "shortsgen-pro":     ("shortsgen", "pro"),
    "shortsgen-business":("shortsgen", "business"),
    "twse-monthly":      ("twse", "monthly"),
    "dealfinder-pro":    ("dealfinder", "pro"),
    "seoengine-pro":     ("seofarm", "pro"),
}
```

Until this is populated the handler falls back to matching by amount, which
works as long as your prices are distinct.

---

## Revenue Log Format

Each record appended to `data/revenue.json`:

```json
{
  "date":       "2026-07-04T12:00:00+00:00",
  "product":    "shortsgen",
  "tier":       "pro",
  "amount":     29.0,
  "currency":   "USD",
  "customer":   "buyer@example.com",
  "source":     "kofi",
  "txn_id":     "abc123",
  "event_type": "Shop Order"
}
```

`txn_id` is the deduplication key — re-delivered webhooks are silently ignored.

---

## Syncing to hermes-pro

After the webhook server appends to `data/revenue.json`, copy it to
hermes-pro so the dashboard picks it up. Two options:

**Option A — GitHub Actions (recommended)**
Add a workflow in hermes-pro that runs on a schedule, fetches the latest
`data/revenue.json` from hermes-pay (via the GitHub API or a direct curl),
and commits it to `hermes-pro/data/revenue.json`, then regenerates the dashboard.

**Option B — Manual sync**
```bash
cp path/to/hermes-pay/data/revenue.json path/to/hermes-pro/data/revenue.json
cd path/to/hermes-pro && python scripts/dashboard.py && git commit -am "sync revenue"
```

---

## Verifying End-to-End

```bash
# 1. Start the server locally
export KOFI_VERIFICATION_TOKEN="test-token-abc"
export GUMROAD_SECRET="test-secret-xyz"
python scripts/webhook.py &

# 2. Send a synthetic Ko-fi event
python scripts/webhook.py --self-test-kofi   # (see test section below)

# 3. Check the log
cat data/revenue.json
```

A basic self-test is included — run `python scripts/webhook.py --self-test`
to send a fake Ko-fi payload and verify a record lands in revenue.json.
