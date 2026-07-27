# 🤖 AGENTS.md — Hướng dẫn cho AI Code Agent

> File này được tự động đọc bởi ZCode/Claude/Cursor/Codeium khi mở project.
> Khi bạn mở Mac lên và nói "tiếp tục đi" hoặc "setup project này", agent sẽ
> đọc file này đầu tiên để hiểu context mà không cần bạn giải thích lại.

---

## 🎯 Project là gì?

**Game Publishing BI Pipeline** — thu thập data game thật từ các nguồn công khai
(Steam, iTunes, IGDB) → lưu SQLite → visualize bằng Power BI.

**Mục đích:** Portfolio project mô phỏng công việc BI Analyst trong ngành
mobile/PC game publishing (match JD: Game Publishing BI Lead).

**Tech stack:**
- Python 3.10+ (test trên 3.14)
- SQLite (stdlib `sqlite3`, không cần cài riêng)
- requests, pandas, loguru, tenacity, click
- Power BI Desktop (separate)

---

## ⚙️ Setup lần đầu (trên máy mới)

Khi user nói *"setup project này"*, chạy tuần tự:

```bash
# 1. Clone repo (nếu chưa có)
git clone git@github.com:hieubqdsm/sensortower.git
cd sensortower

# 2. Tạo virtualenv + install deps
python -m venv .venv
source .venv/bin/activate          # Mac/Linux
# .venv\Scripts\activate           # Windows
pip install -r requirements.txt

# 3. Cấu hình credentials
cp .env.example .env
# Edit .env với các key thật (xem phần "API Keys" bên dưới)

# 4. Init database (tạo schema + dim_date)
python scripts/init_db.py

# 5. Verify setup (dry-run, không crawl)
python scripts/run_daily.py --dry-run
```

---

## 🔑 API Keys — hướng dẫn user đăng ký

Nếu `.env` chưa có key thật, **hỏi user** để họ tự đăng ký:

| Key | Đăng ký ở đâu | Cần gì |
|-----|---------------|--------|
| `STEAM_API_KEY` | https://steamcommunity.com/dev/apikey | Login Steam account → có key ngay |
| `TWITCH_CLIENT_ID` | https://dev.twitch.tv/console | Tạo app → copy Client ID |
| `TWITCH_CLIENT_SECRET` | (cùng chỗ Twitch) | Copy Client Secret |
| iTunes | KHÔNG cần key | Free public API |

**Quy tắc:** Agent KHÔNG tự đăng ký giúp (cần account cá nhân của user).
Agent chỉ hướng dẫn + verify sau khi user điền key.

---

## 🚀 Lệnh thường dùng

### Chạy pipeline
```bash
python scripts/run_daily.py                      # Full run (tất cả nguồn)
python scripts/run_daily.py --source steam        # Chỉ Steam
python scripts/run_daily.py --source itunes       # Chỉ iTunes
python scripts/run_daily.py --source igdb         # Chỉ IGDB
python scripts/run_daily.py --max 50              # Giới hạn 50 game/source
python scripts/run_daily.py --dry-run             # Check credentials, không crawl
python scripts/run_daily.py --skip-init           # Bỏ qua init schema
```

### Chạy news crawler (morning briefing)
```bash
python scripts/run_news.py                        # 24h mặc định
python scripts/run_news.py --hours 6              # 6h gần nhất
python scripts/run_news.py --hours 48             # 2 ngày
python scripts/run_news.py --source rss           # Chỉ RSS (Verge/IGN/Eurogamer/PCGamer/RPS)
python scripts/run_news.py --source hackernews    # Chỉ Hacker News
python scripts/run_news.py --source steam         # Chỉ Steam News (cần game Steam trong DB)
python scripts/run_news.py --source ai            # Chỉ AI News (TechCrunch/VentureBeat/...)
```
Nguồn: RSS gaming (5 outlets) + **AI News (5 outlets)** + Hacker News + Steam News. Reddit skip (cần OAuth từ 2023).

### Daily tasks (sáng dậy chạy 1 lệnh)
```bash
# 1. Generate daily briefing markdown
python scripts/generate_report.py                 # → reports/<date>-briefing.md

# 2. Check data quality
python scripts/data_quality.py                    # alerts ra terminal
python scripts/data_quality.py --json             # output JSON (cho monitoring)
python scripts/data_quality.py --strict           # exit 1 nếu có warning
```

### Chạy dashboard inspector (xem data đã crawl)
```bash
streamlit run dashboard/app.py
# → mở http://localhost:8501
```
Dashboard này KHÔNG phải Power BI — chỉ để inspect/verify data sau khi crawl.
Power BI dashboard user sẽ tự build (xem `powerbi/data_sources.md`).

7 trang:
- 📊 Portfolio Overview — KPIs + crawl activity
- 📰 Daily News — morning briefing with filters
- 🏆 Rankings & Trends — iTunes rankings + trajectory
- 🎭 Genre & Publisher — market share analysis
- 📈 Genre Trends — emerging genres + momentum
- 🔍 Game Detail — deep dive 1 game + raw payload
- 💼 Deal Evaluation — scorecard + ROAS calculator

### Init database
```bash
python scripts/init_db.py                         # Tạo schema + dim_date (idempotent)
```

### Query DB kiểm tra data
```python
from src.storage.db import get_connection
with get_connection() as conn:
    rows = conn.execute("SELECT COUNT(*) FROM dim_game").fetchone()
    print(rows[0])
```

---

## 📂 Cấu trúc project (đọc để hiểu code)

| File/Folder | Mục đích |
|-------------|----------|
| `README.md` | Quickstart cho user |
| `AGENTS.md` | File này — context cho AI agent |
| `docs/data_dictionary.md` | Schema SQLite + business meaning |
| `docs/tos_compliance.md` | **QUAN TRỌNG** — log ethics mỗi nguồn data |
| `docs/methodology.md` | Cách tính proxy metrics + deal evaluation |
| `config/settings.py` | Load env, paths, flags enable crawler |
| `config/sources.yaml` | Rate limit + ToS URL từng nguồn |
| `src/crawlers/base.py` | BaseCrawler: retry, rate limit, UPSERT helper |
| `src/crawlers/steam_crawler.py` | Steam Web API |
| `src/crawlers/itunes_crawler.py` | iTunes Search + RSS (games-only) |
| `src/crawlers/igdb_crawler.py` | IGDB (Twitch OAuth) |
| `src/crawlers/news_crawler.py` | News: RSS (gaming+AI) + Hacker News + Steam News |
| `src/storage/db.py` | Schema DDL + connection helpers |
| `src/transforms/build_models.py` | Post-crawl: extract dim_publisher |
| `src/pipeline.py` | Orchestrator (cô lập failure từng source) |
| `scripts/run_daily.py` | CLI entry point (games pipeline) |
| `scripts/run_news.py` | CLI entry point (news briefing) |
| `scripts/generate_report.py` | Daily briefing markdown generator |
| `scripts/data_quality.py` | Data quality alerts (freshness/anomaly/integrity) |
| `scripts/init_db.py` | Tạo schema + populate dim_date |
| `scripts/manual/` | Slot cho Sensor Tower data save-tay (xem README) |
| `dashboard/app.py` | Streamlit inspector — xem data đã crawl (4 pages) |
| `powerbi/data_sources.md` | Hướng dẫn connect Power BI |

---

## ⚠️ Quy tắc CỐT LÕI (KHÔNG được phá)

### 1. ToS Compliance — KHÔNG bao giờ craw trang login-gated
- ❌ **KHÔNG** scrap Sensor Tower, data.ai, AppMagic, SteamDB
- ✅ Chỉ dùng: Steam Web API, iTunes Search, IGDB, Meta/TikTok Ad Library API
- Xem chi tiết: `docs/tos_compliance.md`

> Nếu user yêu cầu craw Sensor Tower, agent phải GIẢI THÍCH rủi ro ToS/ethics
> trước khi làm. Đây là điểm quan trọng cho portfolio — interviewer sẽ đánh giá
> ethics của candidate.

### 2. Idempotency — pipeline chạy lại không duplicate
- Mọi INSERT dùng `ON CONFLICT DO UPDATE` (UPSERT)
- Re-run `run_daily.py` an toàn
- Schema tạo bằng `CREATE TABLE IF NOT EXISTS`

### 3. Failure isolation
- 1 crawler fail không làm pipeline dừng
- Logic ở `src/pipeline.py::_run_one()`
- Luôn chạy transforms ở cuối dù crawler fail

### 4. `.env` KHÔNG bao giờ commit
- `.gitignore` đã handle
- Chỉ `.env.example` (template) được commit

---

## 🛣️ Trạng thái hiện tại & Next steps

### ✅ Đã hoàn thành (MVP)
- [x] Project structure + .gitignore + requirements
- [x] SQLite star schema (dim_game, dim_date, dim_publisher + 3 facts)
- [x] 3 crawlers: Steam, iTunes (games-only filter), IGDB
- [x] BaseCrawler: retry + rate limit + raw audit
- [x] Pipeline orchestrator + CLI
- [x] Docs: data dictionary, ToS, methodology
- [x] **Smoke test iTunes**: 16 games thật crawled (US + VN)

### 🚧 Chưa test (cần API key)
- [ ] Steam crawler (cần STEAM_API_KEY)
- [ ] IGDB crawler (cần Twitch Client ID/Secret)

### ⏭️ Roadmap tiếp theo (ưu tiên giảm dần)
1. **Power BI dashboard** (3 dashboards: Portfolio, Genre Trends, Game Comparison)
   - Xem `powerbi/data_sources.md` cho connection info
   - Sample DAX measures có ở cuối file đó
2. **Thêm nguồn Tier 1**: Meta Ad Library, Reddit, YouTube
3. **Scheduler**: APScheduler hoặc cron trên Mac (chạy daily tự động)
4. **Deal evaluation model**: ROAS/LTV calculator (Python script)
5. **Cohort retention dashboard** (cần MMP data — harder)

---

## 💬 Cách user thường giao tiếp với agent

Khi bạn mở Mac lên, có thể nói các kiểu:

| User nói | Agent nên làm |
|----------|---------------|
| "setup project này" | Chạy theo phần **Setup lần đầu** ở trên |
| "tiếp tục đi" | Đọc phần **Next steps**, hỏi user muốn làm cái nào |
| "chạy pipeline" | `python scripts/run_daily.py` |
| "chỉ chạy Steam thôi" | `python scripts/run_daily.py --source steam` |
| "lấy tin" / "morning briefing" | `python scripts/run_news.py` (gaming+AI+HN) rồi `python scripts/generate_report.py` |
| "lấy tin AI" | `python scripts/run_news.py --source ai` |
| "check data" | `python scripts/data_quality.py` hoặc query DB trực tiếp |
| "đánh giá game X" | Mở dashboard trang 💼 Deal Evaluation, hoặc viết script scorecard |
| "làm Power BI" | Hướng dẫn theo `powerbi/data_sources.md` |
| "thêm nguồn X" | Check ToS trước (`docs/tos_compliance.md`), rồi code |
| "craw Sensor Tower" | ⚠️ DỪNG. Giải thích ToS/ethics trước. Đề xuất `scripts/manual/` |

---

## 🧪 Test nhanh sau setup

```bash
# Verify Python + deps OK
python -c "from src.storage.db import init_schema; init_schema(); print('OK')"

# Verify DB có data
python -c "
from src.storage.db import get_connection
with get_connection() as c:
    print('dim_date rows:', c.execute('SELECT COUNT(*) FROM dim_date').fetchone()[0])
"
```

Expected: `dim_date rows: 1460` (4 năm data: 2 năm trước → 1 năm sau).

---

## 📝 Cập nhật file này khi...

- Thêm source data mới → cập nhật phần **API Keys** và **ToS compliance**
- Hoàn thành roadmap item → đánh dấu ✅
- Thay đổi schema → cập nhật `docs/data_dictionary.md`
- Deploy cron/scheduler → thêm phần scheduling
