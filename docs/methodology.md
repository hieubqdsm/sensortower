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
| Revenue (mobile) | ✅ Gacha revenue (community-compiled, ennead.cc) | Trực tiếp — fact_gacha_revenue |
| Revenue (Steam) | ❌ Paid | Review count × ~$15 (industry avg ARPU proxy) |
| DAU/MAU (mobile) | ❌ Paid | Ranking trajectory + review velocity |
| Player count (PC) | ✅ Steam API (`peak_ccu`) | Trực tiếp — fact_steam_playercounts |
| Retention D1/D7/D30 | ❌ Cần MMP (internal data) | Industry benchmark by genre (see §6) |
| CPI / UA Spend | ❌ Cần Meta/TikTok Ad API (token required) | Ad creative count proxy (manual count) |
| Reviews / sentiment | ✅ Steam/iTunes public | Trực tiếp — positive/negative ratio |
| Ad creatives | 🟡 Meta/TikTok Ad Library (cần access token) | Manual browse (no API) |
| Crash rate / ANR | ❌ Internal only (Firebase Crashlytics) | N/A — không có proxy |
| ARPU/ARPPU | 🟡 Tính được nếu có DAU estimate | Revenue ÷ estimated DAU |
| LTV | 🟡 Tính được nếu có retention curve | ARPU × avg_lifespan (genre benchmark) |

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

1. **Không có actual revenue numbers** — chỉ có chart position proxy (trừ gacha data từ ennead.cc)
2. **Không có retention curves** — cần MMP (AppsFlyer/Adjust), future work
3. **Player count chỉ cho Steam** — mobile metrics đều là proxy
4. **Sample bias** — chỉ crawl top 100 mỗi nguồn, không đại diện long tail
5. **No UA spend data** — Meta/TikTok Ad Library cần access token (Facebook App review)
6. **No internal KPIs** — DAU/MAU/crash rate/IAP conversion là internal data, không có public source

→ Đây là **rào cản thực tế** mà bất kỳ BI Analyst không có enterprise license
cũng gặp. Document rõ ràng để stakeholder hiểu.

---

## 📊 JD KPI Coverage Matrix

| JD KPI Category | Metric | Data source | Status | Proxy available? |
|----------------|--------|-------------|--------|-----------------|
| **Game Performance** | CCU (Steam) | Steam Web API | ✅ Have | Direct |
| | Rankings (iTunes) | iTunes Search API | ✅ Have | Direct |
| | Reviews/Sentiment | Steam API | ✅ Have | Direct |
| | Revenue (gacha) | ennead.cc HTML parse | ✅ Have | Direct |
| | DAU/MAU | MMP (internal) | ❌ Missing | Ranking trajectory |
| | Retention D1/D7/D30 | MMP (internal) | ❌ Missing | Genre benchmark |
| | Crash rate/ANR | Firebase (internal) | ❌ Missing | N/A |
| **User Acquisition** | CPI/Spend | Meta/TikTok Ad API | ❌ Missing | Ad count (manual) |
| | Installs | MMP (internal) | ❌ Missing | Rank-based estimate |
| | Creative performance | Ad Library | 🟡 Needs token | Manual browse |
| **Monetization** | Revenue | ennead.cc + Steam proxy | ✅ Partial | Direct + proxy |
| | ARPU/ARPPU | Revenue ÷ DAU | 🟡 Calculable | If DAU estimated |
| | LTV | ARPU × lifespan | 🟡 Calculable | Genre benchmark |
| | IAP conversion % | Internal analytics | ❌ Missing | N/A |
| **Deal Assessment** | ROI/ROAS | CPI × LTV | ✅ Calculator | Dashboard ready |
| | Market fit | Genre trends | ✅ Have | Direct |
| | Competitor benchmark | Cross-game compare | ✅ Have | Direct |
| **Market Intelligence** | Genre trends | Aggregated data | ✅ Have | Direct |
| | Publisher share | dim_publisher | ✅ Have | Direct |
| | News/sentiment | RSS + keywords | ✅ Have | Direct |

### KPIs marked ❌ (cần internal data — không có public source)
- **DAU/MAU**: cần MMP integration (AppsFlyer/Adjust/Firebase)
- **Retention D1/D7/D30**: cần MMP cohort data
- **Crash rate/ANR**: cần Firebase Crashlytics
- **CPI/Spend**: cần Ad Network API access (Meta/TikTok business account)
- **IAP conversion %**: cần internal analytics SDK

→ **Portfolio note:** Đây là data thật sự chỉ có khi làm việc tại công ty game publishing.
Trong portfolio, chúng ta simulate được analysis framework nhưng không có actual numbers.
Interviewer hiểu limitation này — focus vào **analytical thinking**, không phải data completeness.

---

## 🔗 Industry benchmarks reference

Sẽ enrich dần từ các nguồn public:

- Sensor Tower quarterly reports (public blog)
- Newzoo Global Games Market Report (free summary)
- App Annie annual reports
- SteamDB insights (read-only public posts, không scrap)

→ Store trong `data/manual/benchmarks.csv` (không commit nếu có copyright).

---

## 6. Industry Benchmarks (cho proxy calculations)

### Retention benchmarks (mobile games, by genre)

Source: GameAnalytics, AppsFlyer industry reports (public summaries).

| Genre | D1 Retention | D7 Retention | D30 Retention | Avg session (min) |
|-------|-------------|-------------|--------------|-------------------|
| Casual (Puzzle/Match) | 35-40% | 12-15% | 4-6% | 8-12 |
| Hyper-casual | 30-35% | 8-10% | 2-3% | 4-6 |
| Action/Shooter | 25-30% | 10-12% | 3-5% | 15-25 |
| RPG / Gacha | 40-50% | 18-25% | 8-12% | 20-40 |
| Strategy | 35-45% | 15-20% | 6-10% | 15-30 |
| Simulation | 30-40% | 12-18% | 5-8% | 12-20 |

### ARPU benchmarks (mobile, monthly)

| Genre | ARPU (USD/month) | ARPPU (USD/month) | IAP conversion |
|-------|------------------|-------------------|----------------|
| Casual | $0.15-0.40 | $5-15 | 2-5% |
| RPG / Gacha | $1.50-5.00 | $20-80 | 5-15% |
| Strategy | $0.80-2.50 | $15-50 | 3-8% |
| Action/Shooter | $0.30-1.00 | $8-25 | 2-6% |
| Hyper-casual | $0.02-0.08 | N/A (ad-driven) | <1% IAP |

### CPI benchmarks (by region, mobile)

| Region | Casual CPI | RPG CPI | Action CPI |
|--------|-----------|---------|------------|
| US | $2-5 | $8-20 | $4-10 |
| VN/SEA | $0.20-0.80 | $1.50-5 | $0.50-2 |
| JP | $3-8 | $10-30 | $5-15 |

### LTV formula (simplified)

```
LTV = ARPU × (avg_lifespan_in_days)
avg_lifespan ≈ 1 / (1 - D1_retention)  [geometric series approximation]

Example (RPG gacha):
  ARPU = $2.50/month, D1 = 45%
  avg_lifespan ≈ 1/(1-0.45) = 1.8 days (rough)
  → Better: use D30 retention curve integral
  LTV_30 = ARPU_daily × Σ(retention_curve, day 1..30)
```

⚠️ Đây là **benchmarks công khai**, dùng cho **ước tính sơ bộ** trong Deal Assessment.
Khi có dữ liệu nội bộ thực tế, thay thế benchmarks bằng dữ liệu thực.
