# 🔌 Power BI Data Sources

> Hướng dẫn kết nối Power BI Desktop với Game BI data. 3 methods — chọn theo use case.

## Quick comparison

| Method | Best for | Real-time | Cloud/LAN | Setup effort |
|--------|----------|-----------|-----------|--------------|
| **1. REST API** (recommended) | Cloudflare tunnel, always-fresh data | ✅ | ✅ | Medium |
| **2. CSV export** | LAN folder sync, offline, Excel | ❌ (batch) | ✅ | Low |
| **3. SQLite ODBC** | Local Power BI on same machine | ✅ | ❌ (file access) | High |

---

## Method 1: REST API (recommended)

Pipeline có FastAPI server serve JSON/CSV endpoints. Power BI dùng **Web connector** pull data.

### Bước 1: Start API server
```bash
# Localhost (Power BI cùng máy)
python scripts/serve_api.py

# LAN accessible (Power BI máy khác trong network)
python scripts/serve_api.py --host 0.0.0.0

# Expose ra internet qua cloudflare tunnel (terminal khác):
cloudflared tunnel --url http://localhost:8000
```

Lấy API key từ `.env` (biến `API_KEY=`).

### Bước 2: Power BI Desktop → Get Data

1. **Get Data** → **Web** → **Advanced**
2. Điền:
   - **URL parts**: `http://localhost:8000/api/gacha/revenue?format=csv`
     (đổi `localhost` → LAN IP hoặc cloudflare URL nếu remote)
   - **HTTP request header parameters**:
     - Header: `X-API-Key`
     - Value: `<API_KEY từ .env>`
3. **OK** → Power BI load CSV → **Transform Data** nếu cần

### Endpoints available

| Endpoint | Output | Purpose |
|----------|--------|---------|
| `/api/gacha/revenue?format=csv` | Flat table (game+month+rank+revenue+scope+icon) | Main gacha dashboard |
| `/api/gacha/latest?format=csv&top_n=50` | Top 50 tháng mới nhất | Latest snapshot view |
| `/api/news?hours=24&format=csv` | News + source_type | News dashboard |
| `/api/stats/summary` | KPIs JSON | Overview cards (Total Revenue, Top games) |
| `/api/tables/{name}?format=csv` | Raw table | Load individual tables |
| `/api/health` | DB status + row counts | Monitoring/alerting |

💡 **Tips:**
- `?format=csv` = load như file CSV (đơn giản nhất cho Power BI)
- `?format=json` (default) = Power BI expand record (linh hoạt hơn)
- Filter: `?month=2026-06`, `?game=Genshin`, `?scope=combined`
- Test endpoints tại `http://localhost:8000/docs` (Swagger UI)

### Refresh schedule
- **Power BI Desktop**: Home → **Refresh** manual sau khi input data mới
- **Power BI Service** (cloud): cần On-premises Data Gateway trỏ tới API endpoint
- **Scheduled refresh**: set trong Power BI Service (Pro license)

---

## Method 2: CSV export (LAN / cloud sync)

Export tất cả tables ra CSV files, share qua LAN folder hoặc cloud (rclone/GDrive/Dropbox).

### Bước 1: Export CSV
```bash
# Export pre-joined BI-ready flat tables (recommended)
python scripts/export_csv.py --flat

# Export tất cả raw tables + flat views
python scripts/export_csv.py --all

# Export 1 table cụ thể
python scripts/export_csv.py --table fact_gacha_revenue
```

Output: `data/processed/*.csv` + `_manifest.json` (metadata: tables, row counts, export time)

**Files:**
| File | Content | Rows (current) |
|------|---------|----------------|
| `gacha_flat.csv` | Pre-joined gacha (game+month+rank+revenue+scope) | 362 |
| `news_flat.csv` | News + source joined | 89 |
| `dim_date.csv` | Date dimension (4 năm) | 1,460 |
| `dim_gacha_game.csv` | Gacha game dimension | 184 |
| `fact_gacha_revenue.csv` | Raw fact (no join) | 362 |

### Bước 2: Share folder

**Option A — LAN (SMB/AFP):**
- macOS: System Settings → General → Sharing → File Sharing → add `data/processed/`
- Power BI máy khác: `\\<mac-ip>\data\processed\gacha_flat.csv`

**Option B — Cloud sync:**
```bash
# rclone lên S3/GDrive/Dropbox
rclone copy data/processed/ remote:game-bi/

# Hoặc symlink vào Dropbox/iCloud folder
ln -s "$(pwd)/data/processed" ~/Dropbox/game-bi
```

### Bước 3: Power BI → Get Data → CSV → trỏ tới file

---

## Method 3: SQLite ODBC (local only)

Power BI trên **cùng máy Mac/PC** truy cập trực tiếp `.db` file qua ODBC driver.

### Setup
1. Cài SQLite ODBC Driver: http://www.ch-werner.de/sqliteodbc/
   - macOS: `brew install sqliteodbc` (cần unixodbc: `brew install unixodbc`)
   - Windows: download installer 64-bit
2. Cấu hình DSN trỏ tới `data/sensortower.db`
3. Power BI: **Get Data** → **ODBC** → chọn DSN

⚠️ **Hạn chế:** Không work qua network (SQLite = serverless, file-based). Chỉ dùng nếu Power BI cùng máy.

---

## Power BI Data Model

Sau khi load data (Method 1 hoặc 2), build model trong **Model view**:

### Relationships (nếu dùng raw tables)
```
dim_gacha_game.game_id  ◄──── fact_gacha_revenue.game_id     (many-to-one)
dim_date.date           ◄──── fact_gacha_revenue.snapshot_month  (note: convert YYYY-MM → date)
```

💡 **Tip:** Dùng `gacha_flat.csv` (Method 2) hoặc `/api/gacha/revenue` (Method 1) — đã pre-join sẵn, không cần setup relationships.

### Recommended DAX measures

```dax
// === Gacha Revenue ===
Total Revenue = SUM(fact_gacha_revenue[revenue_usd])

Avg Monthly Revenue per Game =
AVERAGEX(
    VALUES(fact_gacha_revenue[snapshot_month]),
    CALCULATE(SUM(fact_gacha_revenue[revenue_usd]))
)

// Market Share (%) — per game trong 1 tháng
Market Share % =
VAR currentGame = SUM(fact_gacha_revenue[revenue_usd])
VAR totalMonth =
    CALCULATE(
        SUM(fact_gacha_revenue[revenue_usd]),
        REMOVEFILTERS(dim_gacha_game),
        VALUES(fact_gacha_revenue[snapshot_month])
    )
RETURN DIVIDE(currentGame, totalMonth)

// Month-over-Month Growth (%)
MoM Growth % =
VAR currentMonth = SUM(fact_gacha_revenue[revenue_usd])
VAR prevMonth =
    CALCULATE(
        SUM(fact_gacha_revenue[revenue_usd]),
        DATEADD(fact_gacha_revenue[snapshot_month], -1, MONTH)
    )
RETURN DIVIDE(currentMonth - prevMonth, prevMonth)

// Rank Momentum (rank improvement vs prev month — số âm = tốt hơn)
Rank Change =
VAR currentRank = MIN(fact_gacha_revenue[rank])
VAR prevRank =
    CALCULATE(
        MIN(fact_gacha_revenue[rank]),
        DATEADD(fact_gacha_revenue[snapshot_month], -1, MONTH)
    )
RETURN prevRank - currentRank
```

### Calculated columns

```dax
// Revenue in $M (dễ hiển thị)
Revenue $M = DIVIDE(fact_gacha_revenue[revenue_usd], 1000000, 0)

// Snapshot month as proper date (for time intelligence)
MonthDate = DATEVALUE(dim_gacha_game[snapshot_month] & "-01")
```

---

## Sample visuals

| Visual | Type | Fields |
|--------|------|--------|
| Revenue Trend | Line chart | X: snapshot_month, Y: revenue_usd, Legend: name |
| Market Share | Treemap | Category: name, Value: revenue_usd |
| Top 50 Latest | Table | rank, name, scope, Revenue $M |
| Scope breakdown | Pie/Donut | Legend: scope, Value: revenue_usd |
| Rank Momentum | Bar chart | X: name, Y: Rank Change (filter latest month) |

---

## Troubleshooting

**Power BI "Web" connector error 401:**
→ Thiếu header `X-API-Key`. Dùng "Advanced" mode, thêm HTTP header parameter.

**CSV shows weird characters:**
→ Đảm bảo Power BI detect UTF-8 encoding (File Origin → UTF-8).

**Refresh fails khi API offline:**
→ API server phải chạy. Cho Method 2 (CSV) để có offline fallback.

**`DATEADD` DAX fails:**
→ `snapshot_month` là text 'YYYY-MM', cần cast sang date. Tạo calculated column `MonthDate = DATEVALUE([snapshot_month] & "-01")`.
