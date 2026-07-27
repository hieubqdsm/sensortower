# 🔬 Methodology — How metrics are computed

> Tài liệu này giải thích cách pipeline ước tính các KPI quan trọng khi không
> có quyền truy cập dữ liệu enterprise (Sensor Tower, data.ai).
>
> **Mục đích:** Minh bạch về cách số liệu được tạo ra, để bất kỳ ai đọc
> dashboard cũng hiểu giới hạn của data.

---

## 🎯 Vấn đề cốt lõi

JD yêu cầu phân tích các KPI: downloads, revenue, retention, ROAS. Tuy nhiên:

| KPI | Có sẵn miễn phí + hợp pháp? | Thay thế |
|-----|---------------------------|----------|
| Downloads (mobile) | ❌ Chỉ Sensor Tower/data.ai (paid) | Xem ranking changes trên iTunes top charts |
| Revenue (mobile) | ❌ Paid | Top grossing chart position |
| DAU/MAU (mobile) | ❌ Paid | Ranking trajectory |
| Player count (PC) | ✅ Steam API (`peak_ccu`) | Trực tiếp |
| Reviews / sentiment | ✅ Steam/iTunes public | Trực tiếp |
| Ad creatives | ✅ Meta/TikTok Ad Library | Trực tiếp |

---

## 📐 Proxy metrics (ước tính)

### 1. Game popularity proxy (PC)

```
popularity_index = peak_ccu_today / max(peak_ccu_30d)
```

- Index > 0.8 → đang hot
- Index < 0.3 → declining
- Dùng cho dashboard "Game Health Matrix"

### 2. iOS market share estimation

iTunes không cho downloads số thực, nhưng cho **rank position**. Logic:

```
downloads_estimate(country, app) = country_volume_curve(rank)
```

Trong đó `country_volume_curve` là hàm suy giảm exponential được calibrate từ
benchmarks industry-public (Apple偶尔 publish tổng downloads / Sensor Tower reports):

- Rank #1: ~500k downloads/ngày (US, top genre)
- Rank #10: ~50k downloads/ngày
- Rank #100: ~5k downloads/ngày

**⚠️ Đây là ước tính rough**, dùng cho relative comparison KHÔNG dùng cho absolute claims.

### 3. Review sentiment score

```
sentiment_score = positive / (positive + negative)
```

- `> 0.85` → excellent
- `0.7-0.85` → good
- `< 0.7` → warning (có thể có issue user-facing)

### 4. Genre momentum (QoQ)

```sql
SELECT genre,
       SUM(peak_ccu) AS q_revenue_proxy,
       (SUM(peak_ccu) - LAG(SUM(peak_ccu)) OVER (ORDER BY quarter))
       / LAG(SUM(peak_ccu)) OVER (ORDER BY quarter) AS qoq_growth
FROM fact_steam_playercounts f
JOIN dim_game d USING (game_id)
JOIN dim_date dt USING (snapshot_date)
GROUP BY genre, quarter
```

Dùng cho "Genre Trends" dashboard — recommend deal sourcing cho các genre đang growth.

---

## 🎮 Deal Evaluation Framework

Đây là **core business value** của pipeline. Khi đánh giá 1 game để publish:

### Scorecard (5 chiều, mỗi chiều 0-10)

| Dimension | Câu hỏi | Nguồn data |
|-----------|---------|------------|
| **Market fit** | Genre này đang trend không? Bão hòa chưa? | Genre momentum + IGDB catalog count |
| **Scalability** | Có port được sang platform khác? Localize được? | dim_game.platform + description analysis |
| **Monetization** | ARPU benchmark của genre = bao nhiêu? | Industry reports + Sentiment |
| **ROI / ROAS** | CPI ước tính × LTV có dương không? | (cần UA spend data — Roadmap) |
| **Strategic fit** | Có lấp gap trong portfolio không? | Cross-ref dim_publisher |

**Output:** Recommendation = `PURSUE` / `WATCH` / `PASS` + justification.

---

## 🚫 Giới hạn đã biết (transparency)

1. **Không có actual revenue numbers** — chỉ có chart position proxy
2. **Không có retention curves** — cần MMP (AppsFlyer/Adjust), future work
3. **Player count chỉ cho Steam** — mobile metrics đều là proxy
4. **Sample bias** — chỉ crawl top 100 mỗi nguồn, không đại diện long tail

→ Đây là **rào cản thực tế** mà bất kỳ BI Analyst không có enterprise license
cũng gặp. Document rõ ràng để stakeholder hiểu.

---

## 🔗 Industry benchmarks reference

Sẽ enrich dần từ các nguồn public:

- Sensor Tower quarterly reports (public blog)
- Newzoo Global Games Market Report (free summary)
- App Annie annual reports
- SteamDB insights (read-only public posts, không scrap)

→ Store trong `data/manual/benchmarks.csv` (không commit nếu có copyright).
