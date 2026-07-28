# 🗓️ Daily Schedule — Một ngày làm việc của Game Publishing BI Analyst

> Lịch trình tham khảo dựa trên JD (`docs/job_description.md`) + workflow thật.
> Mỗi khung giờ gắn với 1 lệnh cụ thể trong repo.
> Bạn có thể copy paste lệnh để chạy.

---

## 🌅 Buổi sáng (9:00 – 12:00)

### 09:00 — ☕ Daily Portfolio Health Check

> *"Mở mắt ra, mở dashboard, check overnight có gì sập không"*

```bash
# Mac đã chạy cron lúc 2h sáng → data đã sẵn sàng
# Trên PC: mở report briefing (đã generate sẵn)
cat reports/$(date +%F)-briefing.md

# Hoặc mở dashboard (nếu muốn interactive)
streamlit run dashboard/app.py
# → Mở trang "📊 Portfolio Overview"
```

**Kiểm tra:**
- 🟢/🔴 Top games có tụt rank/CCU không?
- 🟢/🔴 News 24h qua có gì ảnh hưởng portfolio không? (layoffs, shutdown, leak)
- 🟢/🔴 Data quality có alert không?

```bash
# Nếu cron fail hôm qua — chạy tay
python scripts/data_quality.py            # xem có warning gì không
python scripts/run_daily.py               # re-craw nếu thiếu
python scripts/run_news.py                # re-fetch news
python scripts/generate_report.py         # re-generate briefing
```

---

### 09:30 — 📰 Morning News Briefing

> *"Đọc tin game 24h qua — có deal机会 gì không?"*

**Mở:** Dashboard → trang **"📰 Daily News"**

**Focus vào:**
- Tin tag `acquisition`, `funding` → có studio nào vừa raise tiền → cơ hội deal
- Tin tag `layoffs`, `shutdown` → game nào dying → tránh publishing
- Tin tag `launch`, `dlc` → game nào vừa update → UA window

```bash
# Nếu muốn xem tin 6h gần nhất (sáng nay thôi)
python scripts/run_news.py --hours 6
```

---

### 10:00 — 🎯 Deal Assessment (ưu tiên cao nhất)

> *"Có dev submit game, xem có đáng mua không"*

**Mở:** Dashboard → trang **"💼 Deal Evaluation"**

**Workflow:**
1. Nhập thông tin game submission (name, genre, deal cost, CPI estimate, LTV estimate)
2. Xem scorecard 6 chiều:
   - Market Fit
   - Monetization
   - ROI / ROAS
   - Retention
   - Quality (reviews)
   - Scalability
3. Xem recommendation: 🟢 **PURSUE** / 🟡 **WATCH** / 🔴 **PASS**
4. Xem ROAS projection + sensitivity analysis

**Cross-reference:**
- Dashboard → trang **"📈 Genre Trends"** → genre game này có trending không?
- Dashboard → trang **"🎭 Genre & Publisher"** → publisher có uy tín không?

**Output:** Note recommendation vào deal tracker (Excel/Notion)

---

### 11:00 — 🤝 Meeting prep (Cross-functional)

> *"Chuẩn bị data cho meeting với Marketing/Finance"*

**Với Marketing team:**
- Dashboard → trang **"🏆 Rankings & Trends"** → in rank trajectory
- Check genre trends → tư vấn UA direction

**Với Finance team:**
- Dashboard → trang **"💼 Deal Evaluation"** → share ROAS projection
- Print deal scorecard

**Với Dev (external):**
- Dashboard → trang **"🔍 Game Detail"** → show benchmark retention/reviews
- Compare với industry standard

---

## 🌞 Buổi chiều (13:00 – 18:00)

### 13:00 — 🔧 Power BI Development

> *"Build / maintain dashboard cho stakeholder"*

**3 dashboard phải maintain (theo JD):**

#### Dashboard 1: Portfolio Overview (cho Leadership)
- KPIs: Total DAU proxy, MTD revenue proxy, YoY growth
- Top 5 games by revenue
- Game health matrix

#### Dashboard 2: UA Performance (cho Marketing)
- Spend today, Installs, Blended CPI
- ROAS D7/D30 by game
- Cohort retention curves (cần MMP data — Roadmap)

#### Dashboard 3: Game Performance (cho Product)
- Funnel: Install → Tutorial → D1 → D7
- Crash rate / ANR
- Monetization breakdown

**Công việc thực tế:**
- Connect Power BI → SQLite (xem `powerbi/data_sources.md`)
- Viết DAX measures phức tạp
- Power Query transform
- Tối ưu refresh performance

```bash
# Data đã crawl sẵn — chỉ cần refresh Power BI
# Power BI Desktop → Home → Refresh
```

---

### 14:30 — 📚 Market Research (Ad hoc)

> *"Leadership hỏi: Genre nào đang trend ở VN?"*

```bash
# Mở dashboard
streamlit run dashboard/app.py
# → Trang "📈 Genre Trends"
```

**Câu trả lời dựa trên data:**
- Genre nào có nhiều games tracked → market active
- Genre nào có publisher đa dạng → competition healthy
- Genre nào Steam CCU đang tăng → demand đang grow

**Bổ sung từ news:**
```bash
python scripts/run_news.py --source hackernews  # industry signals
```

---

### 16:00 — 📊 Deep Analysis

> *"Investigate anomaly từ sáng"*

```bash
# Query trực tiếp SQLite để trả lời câu hỏi ad hoc
python -c "
from src.storage.db import get_connection
with get_connection() as c:
    # VD: Top 10 publisher theo số games tracked
    for r in c.execute('''
        SELECT publisher_name, COUNT(*) as n
        FROM dim_game
        GROUP BY publisher_name ORDER BY n DESC LIMIT 10
    '''):
        print(dict(r))
"
```

---

### 17:30 — 📋 Wrap-up & Day-end Crawl

> *"Đảm bảo mai sáng có data"*

**Trên Mac (cron tự chạy 2h sáng), nhưng có thể verify:**

```bash
# Check cron setup
crontab -l | grep sensortower

# Manual run nếu cần (trên Mac)
python scripts/run_daily.py --max 100       # craw games
python scripts/run_news.py                  # craw news
python scripts/generate_report.py           # gen briefing cho mai sáng
```

**Cập nhật deal tracker:**
- Game nào đã PURSUE/WATCH/PASS hôm nay
- Note follow-up actions

---

## 🔁 Cron Schedule (Mac 24/7)

> Mac chạy tự động, PC chỉ dùng để xem/traitement.

```bash
# Setup trên Mac
crontab -e
```

```cron
# === CRAWL PIPELINE ===
# 02:00 — Crawl games (Steam + iTunes + IGDB)
0 2 * * * cd ~/sensortower && .venv/bin/python scripts/run_daily.py >> logs/$(date +\%F)-crawl.log 2>&1

# 04:00 — Crawl news (RSS + HN + Steam News)
0 4 * * * cd ~/sensortower && .venv/bin/python scripts/run_news.py >> logs/$(date +\%F)-news.log 2>&1

# === QUALITY CHECK ===
# 05:00 — Data quality alerts (gửi email nếu critical — Roadmap)
0 5 * * * cd ~/sensortower && .venv/bin/python scripts/data_quality.py --strict >> logs/$(date +\%F)-quality.log 2>&1

# === REPORTING ===
# 05:30 — Generate daily briefing markdown (sẵn sàng cho 9h sáng)
30 5 * * * cd ~/sensortower && .venv/bin/python scripts/generate_report.py >> logs/$(date +\%F)-report.log 2>&1
```

---

## 📊 Phân bổ thời gian trong ngày ( theo JD)

| Khối | % | Việc |
|------|---|------|
| ☕ Portfolio monitoring | 30% | Dashboard, KPIs, DAU/revenue check |
| 🎯 Deal assessment | 25% | Scorecard, ROAS, market research |
| 🔧 Power BI development | 20% | Build/maintain dashboard, DAX |
| 🤝 Meetings cross-func | 15% | Marketing, Finance, Dev |
| 📚 Ad hoc analysis | 10% | Market research, deep dives |

---

## 🎯 Tóm tắt "Sáng dậy 1 lệnh"

```bash
# === TRÊN MAC (chạy tự động qua cron) ===
# 02:00 — python scripts/run_daily.py        # craw games
# 04:00 — python scripts/run_news.py         # craw news
# 05:00 — python scripts/data_quality.py     # check quality
# 05:30 — python scripts/generate_report.py  # gen briefing

# === TRÊN PC (sáng dậy làm) ===
cat reports/$(date +%F)-briefing.md           # đọc briefing
streamlit run dashboard/app.py               # mở dashboard
# → vào trang "📰 Daily News" đọc tin
# → vào trang "💼 Deal Evaluation" đánh giá game mới
```

---

## 📅 Tuần lễ (Weekly)

| Ngày | Task |
|------|------|
| **Monday** | Review weekend news + portfolio health |
| **Tuesday** | Deal pipeline review với leadership |
| **Wednesday** | Genre trend deep-dive (emerging genres) |
| **Thursday** | Power BI dashboard iteration |
| **Friday** | Wrap-up weekly insights, plan tuần sau |

---

## 🚨 Khi có anomaly

Pipeline detect anomaly → bạn phải investigate:

```bash
# Xem alerts chi tiết
python scripts/data_quality.py

# Query DB để debug
python -c "
from src.storage.db import get_connection
with get_connection() as c:
    # VD: tìm games có CCU tụt bất thường
    rows = c.execute('''
        SELECT g.name, f.peak_ccu, f.snapshot_date
        FROM fact_steam_playercounts f
        JOIN dim_game g ON f.game_id = g.game_id
        WHERE f.peak_ccu < 100
        ORDER BY f.snapshot_date DESC LIMIT 20
    ''').fetchall()
    for r in rows:
        print(dict(r))
"
```

---

*Schedule tham khảo — điều chỉnh theo phong cách cá nhân và timezone.*
