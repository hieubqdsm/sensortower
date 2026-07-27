# ⚖️ Terms of Service Compliance Log

> Tài liệu này ghi lại tình trạng ToS của từng nguồn data mà pipeline sử dụng.
> Cập nhật mỗi khi thêm nguồn mới hoặc khi platform thay đổi policy.
>
> **Nguyên tắc:** Chỉ sử dụng data qua (1) API chính thức, (2) public RSS, hoặc
> (3) báo cáo đã publish công khai. **KHÔNG** scrap trang login-gated.

---

## ✅ Đang sử dụng (Tier 1 — xanh)

### Steam Web API
- **Endpoint:** `https://api.steampowered.com`, `https://store.steampowered.com/api`
- **ToS:** https://steamcommunity.com/dev/apiterms
- **Auth:** API key (free, https://steamcommunity.com/dev/apikey)
- **Rate limit:** ~200 req / 5 phút (chính sách không công bố chính thức)
- **Bản quyền:** Steam Subscriber Agreement — data dùng cho mục đích cá nhân/research OK
- **Cách dùng:** GetAppList, GetSchemaForGame, store appdetails endpoint
- **Cập nhật:** 2026-07-27

### iTunes Search API
- **Endpoint:** `https://itunes.apple.com/search`, `https://rss.applemarketingtools.com`
- **ToS:** https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/
- **Auth:** KHÔNG cần key (public)
- **Rate limit:** ~20 req/phút (khuyến nghị)
- **Cách dùng:** App metadata, top charts RSS (JSON)
- **Cập nhật:** 2026-07-27

### IGDB (Twitch)
- **Endpoint:** `https://api.igdb.com/v4`
- **ToS:** https://www.twitch.tv/p/legal/developer-agreement/
- **Auth:** Twitch OAuth (Client Credentials)
- **Rate limit:** 4 req/s concurrent, 10k req/tháng (free tier)
- **Giới hạn:** Chỉ non-commercial use. Commercial cần partnership.
- **Cách dùng:** Game catalog enrichment (genres, platforms, screenshots)
- **Cập nhật:** 2026-07-27

---

## ⚠️ Tier 2 — Grey zone (chưa dùng, có thể thêm sau)

### Google Play Store
- **Tình trạng:** ToS cấm automated access, không có API public general-purpose
- **Giải pháp thay thế:** Chỉ dùng `google-play-scraper` library với số lượng nhỏ
  cho mục đích demo, document rõ ràng rủi ro
- **Quyết định:** Chưa thêm vào MVP

### Google Trends
- **Tình trạng:** Không có API chính thức, PyTrends dùng internal endpoint
- **Rủi ro:** Dễ bị 429 (rate limit)
- **Quyết định:** Có thể thêm với sample nhỏ nếu cần trend signal

---

## ❌ Tier 3 — Tránh (login-gated, ToS cấm scrap)

| Source | Lý do tránh | Thay thế |
|--------|-------------|----------|
| **Sensor Tower** | Enterprise SaaS, login-gated, ToS cấm automated access. Giá $30k-150k/năm. | Build pipeline thay thế từ Tier 1 |
| **data.ai (ex-App Annie)** | Login-gated, premium API. Đã thuộc Sensor Tower. | (như trên) |
| **AppMagic** | Login-gated, ToS-conditioned, không có free tier | (như trên) |
| **SteamDB** | ToS cấm scrap rõ ràng, Cloudflare bot detection | Dùng upstream Steam Web API |

**Về Sensor Tower:** JD nhắc tới nhưng thực tế không thể craw hợp pháp.
Tham khảo các báo cáo công khai họ publish tại `sensortower.com/blog` —
đây là data họ tự release cho báo chí, có thể download + cite.

---

## 🔄 Quy trình khi thêm nguồn mới

Trước khi tích hợp bất kỳ nguồn data mới nào, phải trả lời được:

1. [ ] Có API chính thức không? Link tài liệu?
2. [ ] ToS có cho phép automated access không? (trích đoạn cụ thể)
3. [ ] Cần auth gì? (API key, OAuth, cookie?)
4. [ ] Rate limit là bao nhiêu?
5. [ ] Có giới hạn commercial use không?
6. [ ] Nếu scrap HTML — robots.txt có disallow không?

Nếu câu trả lời không rõ ràng → **không thêm**. Ưu tiên ethics over convenience.

---

## 📝 Maintenance log

| Date | Source | Action | Note |
|------|--------|--------|------|
| 2026-07-27 | Steam, iTunes, IGDB | Initial ToS check | Tất cả Tier 1, hợp pháp |
