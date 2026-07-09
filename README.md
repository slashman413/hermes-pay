# hermes-pay 💳

付款中心 — 所有 hermes 產品的 Stripe/Gumroad 金流串接。

## 產品與定價

| 產品 | 方案 | 價格 | 付款方式 |
|------|------|------|---------|
| 🎬 ShortsGen Pro | Pro/Business/Enterprise | $29/$99/$499 | Gumroad/Stripe |
| 📊 TWSE Premium | Monthly/Quarterly/Annual | $49/$99/$299 | Gumroad/Stripe |
| 🛒 Deal Finder Pro | Pro | $9 | Gumroad |
| 📝 SEO Engine | Pro | $19 | Gumroad |

## 快速啟動（Gumroad — 5 分鐘上線）

```bash
# 1. 去 gumroad.com 註冊帳號
# 2. 建立產品 listing
# 3. 複製產品連結
# 4. 更新 scripts/payment.py 的 PRODUCTS 字典
# 5. 執行生成付款按鈕頁面
python scripts/payment.py buttons
```

## 當前狀態

- [x] Gumroad 帳號註冊（slashmaster6.gumroad.com，已驗證：slashmaster6.gumroad.com/l/kuvajr 已上線）
- [ ] ShortsGen Pro listing 建立
- [x] TWSE Premium listing 建立（Ko-fi：ko-fi.com/s/b99720d13d 已上線）
- [ ] Deal Finder Pro listing 建立
- [ ] SEO Engine listing 建立
- [ ] 第一筆交易記錄
