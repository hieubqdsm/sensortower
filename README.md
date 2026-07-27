# 🎮 Game Publishing BI Pipeline

> Pipeline thu thập data thật từ các nguồn công khai (Steam, iTunes, IGDB) → SQLite → Power BI dashboard. Phục vụ mục đích **Game Publishing BI Analyst** (đánh giá portfolio, market trend, deal assessment).

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> 🤖 **Mở project bằng AI agent (ZCode/Claude/Cursor)?** Đọc [`AGENTS.md`](AGENTS.md) trước — file đó chứa đầy đủ context để agent tự hiểu project và tiếp tục làm mà không cần giải thích lại.

## 🎯 Mục tiêu dự án

Đây là project cá nhân mô phỏng công việc thực tế của vị trí **BI Analyst trong ngành mobile/PC game publishing**. Pipeline thu thập các loại dữ liệu:

| Loại data | Nguồn | Tần suất |
|-----------|-------|----------|
| Game catalog (metadata, genre, platform) | IGDB API | Daily |
| Player counts, reviews, prices (PC) | Steam Web API | Daily |
| App info, top charts (iOS) | iTunes Search API | Daily |
| Ad creatives (UA spying) | Meta/TikTok Ad Library | *(sau MVP)* |
| Community sentiment | Reddit, YouTube | *(sau MVP)* |

## ⚖️ Tuyên bố pháp lý & Đạo đức

Dự án **CHỈ** sử dụng:
- API chính thức của các nền tảng (theo ToS)
- Public RSS feeds
- Báo cáo đã được publish công khai

**KHÔNG** sử dụng: scrap Sensor Tower, data.ai, AppMagic, SteamDB (login-gated / ToS cấm). Chi tiết tại [`docs/tos_compliance.md`](docs/tos_compliance.md).

## 🚀 Quick Start

### 1. Cài đặt dependencies

```bash
git clone <repo-url> sensortower
cd sensortower
python -m venv .venv
.venv\Scripts\activate         # Windows
# source .venv/bin/activate    # Mac/Linux
pip install -r requirements.txt
```

### 2. Đăng ký API keys (tất cả FREE)

| Service | Link đăng ký | Cần gì |
|---------|-------------|--------|
| Steam Web API | https://steamcommunity.com/dev/apikey | Login Steam |
| Twitch / IGDB | https://dev.twitch.tv/console | Tạo app → Client ID + Secret |
| iTunes Search | *(không cần)* | Free public API |

### 3. Cấu hình env

```bash
cp .env.example .env
# Edit .env, điền key thật
```

### 4. Khởi tạo database & chạy pipeline

```bash
# Tạo schema SQLite
python scripts/init_db.py

# Chạy full pipeline (lấy top 100 mỗi nguồn)
python scripts/run_daily.py
```

### 5. Crawl news (morning briefing)

```bash
python scripts/run_news.py                    # 24h gần nhất (RSS + HN + Steam News)
python scripts/run_news.py --hours 6          # 6h gần nhất
```

### 6. Xem data đã crawl (Streamlit inspector)

```bash
streamlit run dashboard/app.py
# → mở http://localhost:8501
```

5 trang dashboard: Portfolio Overview · **Daily News** · Rankings & Trends · Genre & Publisher · Game Detail

### 7. Mở Power BI

1. Mở `powerbi/sensortower.pbix` bằng Power BI Desktop
2. Connection details: [`powerbi/data_sources.md`](powerbi/data_sources.md)

## 📁 Cấu trúc dự án

```
sensortower/
├── config/          # Settings, env, source config
├── src/
│   ├── crawlers/    # Steam, iTunes, IGDB crawlers
│   ├── transforms/  # Raw → dim/fact tables
│   ├── storage/     # SQLite helpers
│   └── pipeline.py  # Orchestrator
├── data/
│   ├── raw/         # JSON responses (audit)
│   └── *.db         # SQLite database
├── scripts/         # Entry points (init, run_daily)
├── powerbi/         # .pbix dashboard files
└── docs/            # Data dictionary, ToS, methodology
```

## 📊 Data Model (Star Schema)

Xem chi tiết tại [`docs/data_dictionary.md`](docs/data_dictionary.md).

```
   dim_game ◄─────── fact_steam_playercounts
       ▲            ── fact_itunes_rankings
   dim_date         ── fact_engagement_metrics
       ▲
   dim_publisher
```

## 🔁 Chạy hàng ngày (Mac 24/7)

```bash
# Cron entry (Mac/Linux)
0 2 * * * cd ~/sensortower && .venv/bin/python scripts/run_daily.py >> logs/$(date +\%F).log 2>&1
```

Đồng bộ SQLite về PC qua iCloud/Dropbox để Power BI đọc.

## 🛣️ Roadmap

- [x] **MVP**: Steam + iTunes + IGDB → SQLite → Power BI
- [ ] Mở rộng: Meta Ad Library, Reddit, YouTube
- [ ] Deal evaluation model (ROAS/LTV)
- [ ] Cohort retention dashboard
- [ ] Scheduler nâng cao (APScheduler)

## 📝 License

MIT — see [LICENSE](LICENSE).
