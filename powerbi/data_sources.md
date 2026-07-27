# 🔌 Power BI Data Sources

> Hướng dẫn kết nối Power BI Desktop với SQLite database.

## Cách 1: SQLite ODBC (Recommended)

### Bước 1: Cài SQLite ODBC Driver
- Download: http://www.ch-werner.de/sqliteodbc/
- Cài bản 64-bit (phải khớp với bitness Power BI Desktop)

### Bước 2: Trong Power BI Desktop
1. **Get Data** → **Other** → **ODBC**
2. DSN name: `SQLite3 Datasource` (hoặc build connection string)
3. Database path: `<project>\data\sensortower.db`
4. Click **OK** → chọn tables → **Transform Data**

### Bước 3: Setup relationship trong Model view
```
dim_game.game_id  ◄──── fact_steam_playercounts.game_id
dim_game.game_id  ◄──── fact_itunes_rankings.game_id
dim_date.date     ◄──── fact_steam_playercounts.snapshot_date
```

---

## Cách 2: Import CSV (đơn giản hơn, không cần ODBC)

Pipeline có thể export staging tables ra CSV (xem `scripts/export_csv.py` — Roadmap).

```
data/processed/
├── dim_game.csv
├── dim_date.csv
├── fact_steam_playercounts.csv
└── ...
```

Trong Power BI: **Get Data** → **CSV** → trỏ tới từng file.

---

## Cách 3: Python connector (nâng cao)

Dùng `pyodbc` hoặc `pandas.read_sql` trong **Power Query (Python script)**:

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect(r"C:\path\to\sensortower.db")
df = pd.read_sql("SELECT * FROM dim_game", conn)
```

→ Cài Python trong Power BI options, enable Python scripting.

---

## Refresh schedule

- **Local:** Power BI Desktop → **Refresh** manual sau khi `run_daily.py` xong
- **Mac deployment:** Sync `sensortower.db` về PC qua iCloud/Dropbox trước khi refresh

## Recommended DAX measures

Sau khi data loaded, tạo các measures sau (xem `docs/methodology.md`):

```dax
Total Peak CCU = SUM(fact_steam_playercounts[peak_ccu])

Review Sentiment Score =
DIVIDE(
    SUM(fact_steam_playercounts[positive_reviews]),
    SUM(fact_steam_playercounts[positive_reviews])
        + SUM(fact_steam_playercounts[negative_reviews])
)

Avg Rank by Country =
AVERAGEX(
    VALUES(fact_itunes_rankings[country]),
    MIN(fact_itunes_rankings[rank])
)
```
