#!/usr/bin/env python3
"""
Payment Gateway — Stripe/Gumroad checkout integration.
Generates payment links and handles webhooks for all products.

Usage:
  python payment.py create-link --product shortsgen --tier pro
  python payment.py create-link --product twse --tier monthly
  python payment.py webhook --event payment.succeeded
  python payment.py status
"""
import os, sys, json, hmac, hashlib
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
TRANSACTIONS_FILE = DATA_DIR / "transactions.json"
CUSTOMERS_FILE = DATA_DIR / "customers.json"

PRODUCTS = {
    "shortsgen": {
        "name": "ShortsGen Pro",
        "repo": "hermes-shortsgen",
        "tiers": {
            "free": {"price": 0, "kofi": ""},
            "pro": {"price": 29, "kofi": "https://ko-fi.com/s/896aa3c229"},
            "business": {"price": 99, "kofi": "https://ko-fi.com/s/896aa3c229"},
            "enterprise": {"price": 499, "kofi": "https://ko-fi.com/s/896aa3c229"},
        }
    },
    "twse": {
        "name": "TWSE Premium",
        "repo": "hermes-twse-premium",
        "tiers": {
            "monthly": {"price": 49, "kofi": "https://ko-fi.com/s/b99720d13d"},
            "quarterly": {"price": 99, "kofi": "https://ko-fi.com/s/b99720d13d"},
            "annual": {"price": 299, "kofi": "https://ko-fi.com/s/b99720d13d"},
        }
    },
    "dealfinder": {
        "name": "Deal Finder Pro",
        "repo": "hermes-deal-finder",
        "tiers": {
            "free": {"price": 0},
            "pro": {"price": 9, "stripe_link": "https://buy.stripe.com/test_...",
                   "gumroad": "https://slashman413.gumroad.com/l/dealfinder-pro"},
        }
    },
    "seofarm": {
        "name": "SEO Content Engine",
        "repo": "hermes-seo-farm",
        "tiers": {
            "free": {"price": 0},
            "pro": {"price": 19, "stripe_link": "https://buy.stripe.com/test_...",
                   "gumroad": "https://slashman413.gumroad.com/l/seo-engine"},
        }
    },
}


def ensure_data():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for f in [TRANSACTIONS_FILE, CUSTOMERS_FILE]:
        if not f.exists():
            f.write_text("[]")


def create_checkout_link(product: str, tier: str) -> dict:
    """Generate a checkout link (Stripe/Gumroad) for a product+tier."""
    prod = PRODUCTS.get(product)
    if not prod:
        return {"error": f"Product '{product}' not found"}
    
    tier_info = prod["tiers"].get(tier)
    if not tier_info:
        return {"error": f"Tier '{tier}' not found for {product}"}
    
    # For Gumroad (instant setup, no approval needed)
    gumroad_url = tier_info.get("gumroad", "")
    stripe_url = tier_info.get("stripe_link", "")
    
    return {
        "product": product,
        "product_name": prod["name"],
        "tier": tier,
        "price": tier_info["price"],
        "gumroad_url": gumroad_url or "🚧 待設定 — 先到 gumroad.com 建立產品",
        "stripe_url": stripe_url or "🚧 待設定 — 先到 Stripe Dashboard 建立價格",
        "recommended": "Gumroad" if gumroad_url else "Stripe" if stripe_url else "Gumroad（最快上線）",
    }


def record_transaction(transaction: dict) -> dict:
    """Record a completed transaction."""
    ensure_data()
    transactions = json.loads(TRANSACTIONS_FILE.read_text())
    transaction["recorded_at"] = datetime.now().isoformat()
    transactions.append(transaction)
    TRANSACTIONS_FILE.write_text(json.dumps(transactions, indent=2, ensure_ascii=False))
    
    # Also add to customer list
    if "email" in transaction:
        customers = json.loads(CUSTOMERS_FILE.read_text()) if CUSTOMERS_FILE.exists() else []
        existing = [c for c in customers if c.get("email") == transaction["email"]]
        if not existing:
            customers.append({
                "email": transaction["email"],
                "product": transaction.get("product"),
                "tier": transaction.get("tier"),
                "created_at": datetime.now().isoformat(),
                "lifetime_value": transaction.get("amount", 0),
            })
            CUSTOMERS_FILE.write_text(json.dumps(customers, indent=2, ensure_ascii=False))
    
    return transaction


def verify_webhook(payload: dict, signature: str, secret: str) -> bool:
    """Verify Stripe webhook signature."""
    expected = hmac.new(secret.encode(), json.dumps(payload).encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def generate_payment_buttons() -> str:
    """Generate HTML payment buttons for all products."""
    buttons = ""
    for prod_key, prod in PRODUCTS.items():
        buttons += f"""
        <div class="product-group">
            <h3>{prod['name']}</h3>
            <div class="tier-buttons">
        """
        for tier_key, tier_info in prod["tiers"].items():
            if tier_info["price"] == 0:
                continue
            kofi = tier_info.get('kofi', '')
            btn_url = kofi or '#'
            btn_label = 'Ko-fi 🚀' if kofi else '🔧 Pending setup'
            buttons += f"""
                <div class="tier-card">
                    <h4>{tier_key.title()}</h4>
                    <p class="price">${tier_info['price']}/月</p>
                    <a href="{btn_url}" class="pay-btn" target="_blank">{btn_label}</a>
                </div>
            """
        buttons += "</div></div>"
    
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>付款中心 — hermes-pay</title>
<style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ font-family:-apple-system,sans-serif; background:#0a0a1a; color:#e2e8f0; }}
    .container {{ max-width:800px; margin:auto; padding:20px; }}
    h1 {{ text-align:center; padding:30px 0; }}
    .product-group {{ background:#1e293b; border-radius:16px; padding:20px; margin:15px 0; }}
    .tier-buttons {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:10px; }}
    .tier-card {{ background:#0f172a; border-radius:12px; padding:15px; flex:1; min-width:140px; text-align:center; }}
    .tier-card .price {{ font-size:1.5rem; font-weight:bold; color:#22c55e; margin:5px 0; }}
    .pay-btn {{ display:inline-block; padding:10px 20px; background:linear-gradient(135deg,#3b82f6,#2563eb); color:white; border-radius:8px; text-decoration:none; font-weight:bold; font-size:0.9rem; }}
    footer {{ text-align:center; padding:30px; color:#475569; }}
</style>
</head>
<body>
    <div class="container">
        <h1>💳 付款中心</h1>
        <p style="text-align:center;color:#64748b;">選擇產品與方案，點擊按鈕前往結帳</p>
        {buttons}
        <footer>hermes-pay · 安全支付由 Stripe/Gumroad 處理</footer>
    </div>
</body>
</html>"""


def generate_gumroad_setup_guide() -> str:
    """Generate setup guide for Gumroad products."""
    return """# Gumroad 快速上手指南

## 為什麼選 Gumroad？
- ✅ 5分鐘完成設定，無需審核
- ✅ 支援台灣創作者提領（Payoneer）
- ✅ 免費方案即可使用
- ✅ 自動處理稅務和發票

## 設定步驟

### 1. 註冊 Gumroad
1. 前往 https://gumroad.com 註冊
2. 連結 Payoneer 帳戶（台灣可收款）

### 2. 建立產品
每個產品建立一個 listing：

| 產品 | 價格 | 類型 |
|------|------|------|
| ShortsGen Pro | $29/月 | 訂閱 |
| ShortsGen Business | $99/月 | 訂閱 |
| ShortsGen Enterprise | $499/月 | 訂閱 |
| TWSE Premium Monthly | $49/月 | 訂閱 |
| TWSE Premium Quarterly | $99/季 | 訂閱 |
| TWSE Premium Annual | $299/年 | 訂閱 |
| Deal Finder Pro | $9/月 | 訂閱 |
| SEO Content Engine | $19/月 | 訂閱 |

### 3. 設定 License Key（可選）
用 License Key 控制誰能使用你的服務。

### 4. 更新本 repo
建立產品後，把 Gumroad 連結填入 scripts/payment.py 的 PRODUCTS 字典。

## Stripe（進階，需要公司登記）

台灣創者可以用 Stripe Atlas 或 Stripe 台灣合作夥伴開通。
建議先用 Gumroad 快速啟動，月收入 > $1000 再開 Stripe。
"""


def main():
    ensure_data()
    
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    
    if cmd == "create-link":
        product = sys.argv[sys.argv.index("--product") + 1] if "--product" in sys.argv else ""
        tier = sys.argv[sys.argv.index("--tier") + 1] if "--tier" in sys.argv else ""
        result = create_checkout_link(product, tier)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif cmd == "record":
        transaction = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        result = record_transaction(transaction)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif cmd == "buttons":
        html = generate_payment_buttons()
        docs_dir = BASE_DIR / "docs"
        docs_dir.mkdir(exist_ok=True)
        (docs_dir / "index.html").write_text(html, encoding="utf-8")
        print("✅ Payment buttons page generated")
    
    elif cmd == "guide":
        print(generate_gumroad_setup_guide())
    
    elif cmd == "status":
        transactions = json.loads(TRANSACTIONS_FILE.read_text()) if TRANSACTIONS_FILE.exists() else []
        customers = json.loads(CUSTOMERS_FILE.read_text()) if CUSTOMERS_FILE.exists() else []
        total = sum(t.get("amount", 0) for t in transactions)
        print(f"💳 Payment Status:")
        print(f"  Products: {len(PRODUCTS)}")
        print(f"  Transactions: {len(transactions)}")
        print(f"  Customers: {len(customers)}")
        print(f"  Total Revenue: ${total:.2f}")
        print(f"\n🚀 Next Step: Go to gumroad.com to create products")
        print(f"   Then update PRODUCTS dict in scripts/payment.py")


if __name__ == "__main__":
    main()
