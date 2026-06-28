# 🚀 Gumroad 設定懶人包

## Step 1: 註冊 Gumroad（3 分鐘）
1. 去 https://gumroad.com
2. 用你的 Google 一鍵登入（最快）
3. 設定 Payoneer 收款（台灣可以提領）
   - 如果還沒有 Payoneer，可以先跳過，之後再補

## Step 2: 建立產品（每個 2 分鐘 × 4 = 8 分鐘）

### 🎬 ShortsGen Pro（$29/$99/$499）
打開：https://gumroad.com/products/new
```
產品名稱：ShortsGen Pro — AI 自動生成 YouTube Shorts
價格設定：Subscription（訂閱）
  - Pro: $29/月
  - Business: $99/月
  - Enterprise: $499/月
描述：複製貼上 → hermes-pay/gumroad/shortsgen-product.txt
封面：打開 hermes-pay/gumroad/cover-images.html → 截圖上傳
```

### 📈 TWSE Premium（$49/$99/$299）
```
產品名稱：TWSE Premium — 台股量化交易信號
價格設定：Subscription
  - Monthly: $49/月
  - Quarterly: $99/季
  - Annual: $299/年
描述：複製貼上 → hermes-pay/gumroad/twse-product.txt
封面：同上
```

### 🏷️ Deal Finder Pro（$9）
```
產品名稱：Deal Finder Pro — Amazon 優惠追蹤器
價格設定：Subscription $9/月
描述：複製貼上 → hermes-pay/gumroad/dealfinder-product.txt
```

### 📝 SEO Content Engine（$19）
```
產品名稱：SEO Content Engine — AI SEO 文章產出
價格設定：Subscription $19/月
描述：複製貼上 → hermes-pay/gumroad/seoengine-product.txt
```

## Step 3: 把連結給我（1 分鐘）
建立完每個產品後，Gumroad 會給你一個連結：
```
https://slashman413.gumroad.com/l/shortsgen-pro
https://slashman413.gumroad.com/l/shortsgen-business
...
```

把這些連結貼給我，我會：
- ✅ 更新 hermes-pay/scripts/payment.py 的 PRODUCTS
- ✅ 更新 Shorts 影片說明的結帳按鈕
- ✅ 推上 GitHub Pages 付款中心
- ✅ 記錄到收入追蹤系統

## Step 4: 開賣！🎉
產品上線後：
1. Shorts 影片說明自動顯示購買連結
2. YouTube 觀眾直接點擊結帳
3. 收入自動進入你的 Gumroad 帳戶

---

## 你的角色 vs 我的角色

| 你做 | 我做 |
|-----|------|
| gumroad.com 註冊帳號 | 準備所有產品文案 |
| 填寫 Email/密碼/收款資訊 | 截圖封面模板 |
| 按「建立產品」 | 事後更新 payment.py |
| 把連結貼給我 | 推送到 GitHub Pages |
| | 計入收入儀表板 |
