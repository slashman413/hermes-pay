# Deploy the payment webhook (≈15 min → real payments show on the dashboard)

`scripts/webhook.py` receives Ko-fi + Gumroad payment events, verifies them, and
appends to `data/revenue.json`. With `GITHUB_TOKEN` set it also **commits that file
back to this repo**, so the `hermes-pro` dashboard (which syncs `data/revenue.json`)
shows real revenue automatically. Dependency-free (stdlib only).

## Option A — Render (free, one-click)
1. Push this repo to GitHub (already done).
2. Render → **New → Blueprint** → select `slashman413/hermes-pay`. It reads `render.yaml`.
3. Set the four env vars when prompted:
   - `KOFI_VERIFICATION_TOKEN` — Ko-fi → Settings → Webhooks → Verification Token
   - `GUMROAD_SECRET` — any random string (you'll reuse it below)
   - `GITHUB_TOKEN` — a fine-grained PAT with **contents:write** on `slashman413/hermes-pay`
   - `GITHUB_REPO` — already `slashman413/hermes-pay`
4. Deploy → you get a URL like `https://hermes-pay-webhook.onrender.com`.

## Option B — Docker anywhere
```bash
docker build -t hermes-pay-webhook .
docker run -p 8787:8787 \
  -e KOFI_VERIFICATION_TOKEN=... -e GUMROAD_SECRET=... \
  -e GITHUB_TOKEN=... -e GITHUB_REPO=slashman413/hermes-pay \
  hermes-pay-webhook
```

## Wire the payment providers to it
- **Ko-fi:** Settings → Webhooks → set **`https://<your-url>/webhook/kofi`**.
- **Gumroad:** product → Settings → Ping → **`https://<your-url>/webhook/gumroad?secret=<GUMROAD_SECRET>`**.

## Verify end-to-end (do this once)
1. `curl https://<your-url>/health` → `ok — N revenue records`.
2. Make a real $1 test purchase → refund. Confirm:
   - webhook logs `recorded txn_id=...` then `persisted revenue.json ...`
   - a `chore: record payment` commit appears on this repo
   - the [hermes-pro dashboard](https://slashman413.github.io/hermes-pro/) shows the payment on its next run
3. If step 2 works, your revenue is now measured end-to-end. **This is the Experiment-0 gate.**

> Free-tier hosts sleep when idle; the first webhook after a nap may take a few seconds.
> Because events are deduped by `txn_id` and providers retry, no payment is lost.
