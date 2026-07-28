"""
Streamlit dashboard — inspect data đã crawl.

Chạy:  streamlit run dashboard/app.py

Không phải Power BI dashboard (user sẽ tự build .pbix).
Dashboard này dùng để:
  - Verify hàng ngày "hôm nay crawler gom được gì"
  - Quick inspection trên Mac mà không cần mở Power BI
  - Debug data quality issues
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Ensure project root on sys.path (khi chạy từ dashboard/ folder)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.db import get_connection


# ---- Page config ---------------------------------------------------------
st.set_page_config(
    page_title="Game BI — Crawler Inspector",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---- Cached DB loaders ---------------------------------------------------
@st.cache_data(ttl=60)  # cache 60s — đủ để refresh sau khi crawl mới
def load_dim_game() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql("SELECT * FROM dim_game ORDER BY name", conn)


@st.cache_data(ttl=60)
def load_fact_rankings() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql("SELECT * FROM fact_itunes_rankings", conn)


@st.cache_data(ttl=60)
def load_fact_steam() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql("SELECT * FROM fact_steam_playercounts", conn)


@st.cache_data(ttl=60)
def load_dim_publisher() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql("SELECT * FROM dim_publisher ORDER BY name", conn)


@st.cache_data(ttl=60)
def load_fact_news(hours: int = 24) -> pd.DataFrame:
    """Load news items trong N giờ gần nhất."""
    with get_connection() as conn:
        return pd.read_sql(
            """
            SELECT n.*, s.source_type, s.source_name,
                   g.name as game_name
            FROM fact_news n
            JOIN dim_news_source s ON n.source_id = s.source_id
            LEFT JOIN dim_game g ON n.game_id = g.game_id
            WHERE n.published_at >= datetime('now', ?)
            ORDER BY n.published_at DESC
            """,
            conn,
            params=(f"-{hours} hours",),
        )


@st.cache_data(ttl=60)
def load_table_rowcounts() -> dict[str, int]:
    from src.storage.db import get_table_rowcounts
    return get_table_rowcounts()


# ---- Sidebar: navigation + global state ---------------------------------
st.sidebar.title("🎮 Game BI")
st.sidebar.caption("Crawler data inspector")

# Refresh button — clear cache
if st.sidebar.button("🔄 Refresh data", help="Clear cache, đọc lại từ DB"):
    st.cache_data.clear()
    st.rerun()

# Show DB path
from config import SQLITE_PATH
st.sidebar.divider()
st.sidebar.write("**DB:**")
st.sidebar.code(str(SQLITE_PATH.relative_to(PROJECT_ROOT)))

# Row counts
counts = load_table_rowcounts()
st.sidebar.write("**Rows per table:**")
for t, n in counts.items():
    st.sidebar.write(f"`{t}`: **{n:,}**")

# ---- CSV Downloads (Power BI / Excel) ----
st.sidebar.divider()
st.sidebar.write("**📥 CSV Downloads (Power BI):**")
try:
    import socket
    # Get LAN IP
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    lan_ip = s.getsockname()[0]
    s.close()
except Exception:
    lan_ip = "localhost"

api_base = f"http://{lan_ip}:8000"
st.sidebar.markdown(f"API: [`{api_base}/downloads`]({api_base}/downloads)")
csv_files = ["gacha_flat", "steam_flat", "itunes_flat", "news_flat", "dim_date"]
for f in csv_files:
    st.sidebar.markdown(f"&nbsp;&nbsp;[`{f}.csv`]({api_base}/downloads/{f}.csv)")
st.sidebar.caption("Mở trên máy khác (cùng WiFi) để tải. API server phải đang chạy.")

# ---- Page routing via radio (đơn giản, không cần multipage app) ---------
PAGES = [
    "📊 Portfolio Overview",
    "📰 Daily News",
    "🏆 Rankings & Trends",
    "🎮 Steam CCU",
    "🎭 Genre & Publisher",
    "📈 Genre Trends",
    "🔍 Game Detail",
    "💼 Deal Evaluation",
    "💰 Gacha Revenue",
]
page = st.sidebar.radio("Navigate", PAGES, label_visibility="collapsed")
st.sidebar.divider()
st.sidebar.caption("Power BI dashboard build riêng — đây chỉ là inspector.")


# =========================================================================
# PAGE 1: PORTFOLIO OVERVIEW
# =========================================================================
if page == PAGES[0]:
    st.title("📊 Portfolio Overview")
    st.caption("Tổng quan data đã crawl từ các nguồn")

    games = load_dim_game()
    rankings = load_fact_rankings()
    steam = load_fact_steam()
    pubs = load_dim_publisher()

    # KPI cards
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Games", len(games))
    col2.metric("iTunes Games", len(games[games["source"] == "itunes"]))
    col3.metric("Steam Games", len(games[games["source"] == "steam"]))
    col4.metric("IGDB Games", len(games[games["source"] == "igdb"]))
    col5.metric("Publishers", len(pubs))

    st.divider()

    # Games by source
    st.subheader("Games by source")
    source_counts = games["source"].value_counts().reset_index()
    source_counts.columns = ["Source", "Count"]
    st.dataframe(source_counts, use_container_width=True, hide_index=True)

    # Recent crawl activity
    st.subheader("📅 Recent crawl activity")
    if not rankings.empty:
        recent = (
            rankings.groupby("snapshot_date")
            .agg(rankings=("ranking_id", "count"),
                 unique_games=("game_id", "nunique"),
                 countries=("country", "nunique"))
            .reset_index()
            .sort_values("snapshot_date", ascending=False)
            .head(14)
        )
        st.dataframe(recent, use_container_width=True, hide_index=True)
    else:
        st.info("No iTunes ranking data yet.")

    if not steam.empty:
        st.write("**Steam snapshots:**")
        recent_steam = (
            steam.groupby("snapshot_date")
            .agg(games=("game_id", "nunique"),
                 total_peak_ccu=("peak_ccu", "sum"))
            .reset_index()
            .sort_values("snapshot_date", ascending=False)
            .head(14)
        )
        st.dataframe(recent_steam, use_container_width=True, hide_index=True)
    else:
        st.info("No Steam data yet (cần STEAM_API_KEY).")

    # Last crawl timestamp
    st.divider()
    st.subheader("🕐 Last update")
    if not games.empty:
        last = games["updated_at"].max()
        st.write(f"Last game update: **{last}**")


# =========================================================================
# PAGE 2: DAILY NEWS (morning briefing)
# =========================================================================
elif page == PAGES[1]:
    st.title("📰 Daily News")
    st.caption("Morning game news briefing — RSS + Hacker News + Steam News")

    # Hours selector
    col_h1, col_h2 = st.columns([1, 3])
    with col_h1:
        hours = st.selectbox("Lookback", [6, 12, 24, 48, 72], index=2)

    news = load_fact_news(hours)

    if news.empty:
        st.warning(
            f"❌ Chưa có news trong {hours}h qua. "
            f"Chạy: `python scripts/run_news.py --hours {hours}` rồi refresh."
        )
        st.stop()

    # KPI cards
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(f"News (last {hours}h)", len(news))
    col2.metric("Sources", news["source_name"].nunique())
    col3.metric("Matched games", news["game_id"].notna().sum())
    col4.metric("With keywords", news["keywords"].notna().sum() - (news["keywords"] == "").sum())

    st.divider()

    # Filters
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        sources = ["All"] + sorted(news["source_name"].unique())
        sel_source = st.selectbox("Filter by source", sources)
    with col_f2:
        # Parse keywords thành list unique
        all_keywords = set()
        for kws in news["keywords"].dropna():
            if kws:
                all_keywords.update(kws.split(","))
        kw_options = ["All"] + sorted(all_keywords)
        sel_keyword = st.selectbox("Filter by keyword", kw_options)
    with col_f3:
        search = st.text_input("🔍 Search title", "")

    # Apply filters
    filtered = news.copy()
    if sel_source != "All":
        filtered = filtered[filtered["source_name"] == sel_source]
    if sel_keyword != "All":
        filtered = filtered[filtered["keywords"].str.contains(sel_keyword, na=False)]
    if search:
        filtered = filtered[filtered["title"].str.contains(search, case=False, na=False)]

    st.write(f"**Showing {len(filtered)} of {len(news)} news items**")

    # Display news as cards (cherry-picked style, không phải raw table)
    import plotly.express as px

    # Keyword distribution chart
    st.subheader("🏷️ News by keyword")
    kw_series = (
        news["keywords"].dropna()
        .str.split(",")
        .explode()
        .value_counts()
        .head(10)
        .reset_index()
    )
    kw_series.columns = ["Keyword", "Count"]
    if not kw_series.empty:
        fig = px.bar(kw_series, x="Count", y="Keyword", orientation="h",
                     title=f"Top keywords (last {hours}h)")
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=350)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No keywords detected.")

    # News by source breakdown
    st.divider()
    col_s1, col_s2 = st.columns([2, 3])
    with col_s1:
        st.subheader("📡 By source")
        src_counts = news["source_name"].value_counts().reset_index()
        src_counts.columns = ["Source", "Count"]
        st.dataframe(src_counts, use_container_width=True, hide_index=True)

    with col_s2:
        st.subheader("📅 Timeline")
        news_dt = news.copy()
        news_dt["hour"] = pd.to_datetime(news_dt["published_at"]).dt.floor("H")
        timeline = news_dt.groupby("hour").size().reset_index(name="count")
        if not timeline.empty:
            fig = px.bar(timeline, x="hour", y="count",
                         title=f"News per hour (last {hours}h)")
            fig.update_layout(height=300, xaxis_title="", yaxis_title="items")
            st.plotly_chart(fig, use_container_width=True)

    # News list (cherry-picked display)
    st.divider()
    st.subheader(f"📋 News feed ({len(filtered)} items)")

    # Sort by date (newest first) then by score
    display_cols = ["published_at", "source_name", "title", "keywords", "score", "url"]
    display_df = filtered[display_cols].copy() if not filtered.empty else filtered
    display_df["published_at"] = pd.to_datetime(display_df["published_at"]).dt.strftime("%H:%M")

    # Render as clickable links
    for _, row in display_df.head(50).iterrows():
        title = row["title"]
        url = row["url"]
        src = row["source_name"]
        time_str = row["published_at"]
        kw = row["keywords"]
        score = row["score"]

        kw_html = f" `<span style='color:#888'>[{kw}]</span>`" if kw else ""
        score_html = f" ⬆{score}" if pd.notna(score) and score else ""

        st.markdown(
            f"**[{time_str}]** `[{src}]` [{title}]({url}){kw_html}{score_html}",
            unsafe_allow_html=True,
        )


# =========================================================================
# PAGE 3: RANKINGS & TRENDS
# =========================================================================
elif page == PAGES[2]:
    st.title("🏆 Rankings & Trends")
    st.caption("iTunes top chart rankings theo country & chart type")

    rankings = load_fact_rankings()
    games = load_dim_game()

    if rankings.empty:
        st.warning("No ranking data yet. Chạy `python scripts/run_daily.py --source itunes`")
        st.stop()

    # Join with game names
    df = rankings.merge(
        games[["game_id", "name", "genre", "publisher_name"]],
        on="game_id", how="left"
    )

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        countries = sorted(df["country"].unique())
        sel_countries = st.multiselect("Country", countries, default=countries)
    with col2:
        charts = sorted(df["chart_name"].unique())
        sel_charts = st.multiselect("Chart", charts, default=charts)
    with col3:
        dates = sorted(df["snapshot_date"].unique(), reverse=True)
        sel_date = st.selectbox("Snapshot date", dates, index=0)

    mask = (
        df["country"].isin(sel_countries)
        & df["chart_name"].isin(sel_charts)
        & (df["snapshot_date"] == sel_date)
    )
    filtered = df[mask].sort_values(["country", "chart_name", "rank"])

    st.subheader(f"Top games — {sel_date}")
    if filtered.empty:
        st.info("No data cho filter này.")
    else:
        # Display as grouped table
        display_cols = ["rank", "name", "genre", "publisher_name", "country", "chart_name"]
        st.dataframe(
            filtered[display_cols],
            use_container_width=True,
            hide_index=True,
            height=500,
        )

    # Rank trajectory chart (if multiple snapshots)
    st.divider()
    st.subheader("📈 Rank trajectory")
    if len(dates) > 1:
        sel_games_traj = st.multiselect(
            "Chọn games để xem trajectory",
            sorted(df["name"].dropna().unique()),
            max_selections=10,
        )
        if sel_games_traj:
            traj = df[df["name"].isin(sel_games_traj)].copy()
            traj = traj.sort_values("snapshot_date")
            fig = px.line(
                traj, x="snapshot_date", y="rank", color="name",
                markers=True, title="Rank over time (lower = better)",
            )
            fig.update_yaxes(autorange="reversed")  # rank 1 on top
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Chọn ít nhất 1 game để xem trajectory.")
    else:
        st.info("Cần ít nhất 2 snapshot dates để vẽ trajectory. Chạy crawler thêm vài ngày.")


# =========================================================================
# PAGE 3.5: 🎮 STEAM CCU RANKINGS
# =========================================================================
elif page == PAGES[3]:
    st.title("🎮 Steam CCU Rankings")
    st.caption("Top 100 Steam games by concurrent players — hourly snapshot via Steam Web API")

    steam_df = load_fact_steam()
    games_df = load_dim_game()

    if steam_df.empty:
        st.warning(
            "❌ Chưa có Steam data. Cần:\n"
            "1. `STEAM_API_KEY` trong `.env` (đăng ký: steamcommunity.com/dev/apikey)\n"
            "2. Chạy: `python scripts/run_daily.py --source steam`\n"
            "3. Cron đã setup hourly — đợi vài giờ để có history"
        )
        st.stop()

    # Join game metadata
    df = steam_df.merge(
        games_df[["game_id", "name", "genre", "publisher_name", "developer_name", "price_usd"]],
        on="game_id", how="left",
    )

    # Latest snapshot
    latest_date = df["snapshot_date"].max()
    latest = df[df["snapshot_date"] == latest_date].copy()
    n_dates = df["snapshot_date"].nunique()

    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Games tracked", latest["game_id"].nunique())
    col2.metric("Total CCU (now)", f"{latest['peak_ccu'].sum():,}")
    col3.metric("Snapshots", n_dates)
    col4.metric("Latest snapshot", str(latest_date))

    st.divider()

    # Filter by publisher (optional)
    colf1, colf2 = st.columns(2)
    with colf1:
        top_n = st.slider("Top N games", 10, 100, 25, step=5)
    with colf2:
        publishers = ["All"] + sorted(
            p for p in latest["publisher_name"].dropna().unique() if p
        )
        sel_pub = st.selectbox("Filter by publisher", publishers)

    filtered = latest.copy()
    if sel_pub != "All":
        filtered = filtered[filtered["publisher_name"] == sel_pub]
    filtered = filtered.nlargest(top_n, "peak_ccu")

    # === Top N leaderboard ===
    st.subheader(f"🏆 Top {len(filtered)} by CCU — {latest_date}")
    display = filtered.copy()
    # Sentiment %
    display["sentiment_%"] = (
        display["positive_reviews"] /
        (display["positive_reviews"] + display["negative_reviews"]) * 100
    ).round(1)
    display["sentiment"] = display["sentiment_%"].apply(
        lambda x: f"{x:.0f}%" if x == x else "—"
    )
    display = display[[
        "name", "peak_ccu", "publisher_name", "genre", "price_usd",
        "positive_reviews", "negative_reviews", "sentiment",
    ]].copy()
    display.columns = [
        "Game", "Peak CCU", "Publisher", "Genre", "Price ($)",
        "Reviews +", "Reviews −", "Sentiment",
    ]
    st.dataframe(display, use_container_width=True, hide_index=True, height=450)

    st.divider()

    # === CCU trajectory (line chart — cần ≥2 snapshots) ===
    st.subheader("📈 CCU Trajectory")
    if n_dates >= 2:
        sel_traj = st.multiselect(
            "🎮 Games so sánh trajectory",
            sorted(latest.nlargest(15, "peak_ccu")["name"].dropna().unique()),
            max_selections=10,
        )
        if sel_traj:
            traj = df[df["name"].isin(sel_traj)].copy()
            traj = traj.sort_values(["name", "snapshot_date"])
            fig = px.line(
                traj, x="snapshot_date", y="peak_ccu", color="name",
                markers=True, title="CCU over time (hourly snapshots)",
                labels={"peak_ccu": "Peak Concurrent Players", "snapshot_date": "Date"},
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Chọn ít nhất 1 game để xem trajectory.")
    else:
        st.info(
            f"⏳ Hiện chỉ có {n_dates} snapshot. Cron hourly sẽ tự thêm data — "
            f"vài giờ nữa quay lại sẽ có line chart CCU trajectory."
        )
        st.caption(
            "Pipeline: cron `0 * * * *` chạy Steam crawler mỗi giờ → "
            "`fact_steam_playercounts` thêm 1 row/game/hour → line chart tự render."
        )

    st.divider()

    # === Publisher market share (CCU) ===
    st.subheader("📊 Publisher Market Share (by CCU)")
    pub_share = (
        latest.groupby("publisher_name")["peak_ccu"].sum()
        .reset_index()
        .sort_values("peak_ccu", ascending=False)
    )
    # Top 10 + Other
    top10 = pub_share.head(10).copy()
    other_ccu = pub_share.iloc[10:]["peak_ccu"].sum()
    if other_ccu > 0:
        top10 = pd.concat([top10, pd.DataFrame([{"publisher_name": "Other", "peak_ccu": other_ccu}])])
    fig_pie = px.pie(
        top10, values="peak_ccu", names="publisher_name",
        title=f"CCU share by publisher — {latest_date}",
    )
    st.plotly_chart(fig_pie, use_container_width=True)


# =========================================================================
# PAGE 4: GENRE & PUBLISHER
# =========================================================================
elif page == PAGES[4]:
    st.title("🎭 Genre & Publisher Analysis")
    st.caption("Phân tích market share theo thể loại và publisher")

    games = load_dim_game()
    rankings = load_fact_rankings()

    if games.empty:
        st.warning("No data yet.")
        st.stop()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Games by genre")
        genre_counts = games["genre"].fillna("(unknown)").value_counts().reset_index()
        genre_counts.columns = ["Genre", "Count"]
        import plotly.express as px
        fig = px.bar(
            genre_counts.head(15), x="Count", y="Genre", orientation="h",
            title=f"Top {min(15, len(genre_counts))} genres",
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Games by publisher")
        pub_counts = games["publisher_name"].fillna("(unknown)").value_counts().reset_index()
        pub_counts.columns = ["Publisher", "Count"]
        fig = px.bar(
            pub_counts.head(15), x="Count", y="Publisher", orientation="h",
            title=f"Top {min(15, len(pub_counts))} publishers",
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Cross-source analysis
    st.subheader("🔀 Cross-source distribution")
    cross = (
        games.groupby(["source", "genre"])
        .size()
        .reset_index(name="count")
        .sort_values(["source", "count"], ascending=[True, False])
    )
    st.dataframe(cross, use_container_width=True, hide_index=True)

    # Publisher detail table
    st.divider()
    st.subheader("📋 Publisher detail")
    pub_detail = (
        games.groupby("publisher_name")
        .agg(
            total_games=("game_id", "count"),
            genres=("genre", lambda x: ", ".join(sorted(set(x.dropna()))) or "—"),
            sources=("source", lambda x: ", ".join(sorted(set(x))) or "—"),
        )
        .reset_index()
        .sort_values("total_games", ascending=False)
    )
    st.dataframe(pub_detail, use_container_width=True, hide_index=True)


# =========================================================================
# PAGE 5: GAME DETAIL
# =========================================================================
elif page == PAGES[6]:
    st.title("🔍 Game Detail")
    st.caption("Deep dive vào 1 game cụ thể")

    games = load_dim_game()
    rankings = load_fact_rankings()
    steam = load_fact_steam()

    if games.empty:
        st.warning("No games in DB yet.")
        st.stop()

    # Game selector
    sel_game_name = st.selectbox(
        "Chọn game", sorted(games["name"].dropna().unique())
    )

    game_rows = games[games["name"] == sel_game_name]
    if game_rows.empty:
        st.error("Game not found.")
        st.stop()

    # If multiple rows (cross-source), let user pick
    if len(game_rows) > 1:
        options = game_rows.apply(
            lambda r: f"{r['source']} ({r['source_app_id']})", axis=1
        ).tolist()
        sel_idx = st.radio("Có nhiều row (cross-source)", options)
        sel_row = game_rows.iloc[options.index(sel_idx)]
    else:
        sel_row = game_rows.iloc[0]

    game_id = sel_row["game_id"]

    # Metadata
    st.subheader(f"🎮 {sel_row['name']}")
    meta_col1, meta_col2, meta_col3 = st.columns(3)
    meta_col1.write(f"**Source:** {sel_row['source']}")
    meta_col1.write(f"**App ID:** `{sel_row['source_app_id']}`")
    meta_col2.write(f"**Genre:** {sel_row['genre'] or '—'}")
    meta_col2.write(f"**Platform:** {sel_row['platform'] or '—'}")
    meta_col3.write(f"**Release:** {sel_row['release_date'] or '—'}")
    meta_col3.write(f"**Price:** ${sel_row['price_usd']:.2f}" if pd.notna(sel_row['price_usd']) else "**Price:** —")

    st.write(f"**Publisher:** {sel_row['publisher_name'] or '—'}")
    st.write(f"**Developer:** {sel_row['developer_name'] or '—'}")
    if sel_row['description']:
        st.write(f"**Description:**")
        st.caption(sel_row['description'])

    # Ranking history
    st.divider()
    st.subheader("🏆 iTunes ranking history")
    game_rankings = rankings[rankings["game_id"] == game_id].sort_values("snapshot_date")
    if game_rankings.empty:
        st.info("No iTunes ranking data cho game này.")
    else:
        st.dataframe(game_rankings, use_container_width=True, hide_index=True)

    # Steam stats
    st.divider()
    st.subheader("🎮 Steam player counts")
    game_steam = steam[steam["game_id"] == game_id].sort_values("snapshot_date")
    if game_steam.empty:
        st.info("No Steam data cho game này.")
    else:
        st.dataframe(game_steam, use_container_width=True, hide_index=True)

    # Raw payload link
    st.divider()
    if sel_row['raw_payload_path']:
        st.subheader("📂 Raw payload")
        raw_path = PROJECT_ROOT / sel_row['raw_payload_path']
        st.code(str(raw_path))
        if raw_path.exists():
            with st.expander("View raw JSON"):
                import json
                st.json(json.loads(raw_path.read_text(encoding="utf-8")))
        else:
            st.warning(f"Raw file không tồn tại: {raw_path}")


# =========================================================================
# PAGE 6: GENRE TRENDS (emerging / declining genres)
# =========================================================================
elif page == PAGES[5]:
    st.title("📈 Genre Trends")
    st.caption("Emerging vs declining genres — recommend deal sourcing direction")

    games = load_dim_game()
    rankings = load_fact_rankings()
    steam = load_fact_steam()

    if games.empty:
        st.warning("No data yet.")
        st.stop()

    import plotly.express as px

    # ---- Section 1: Current genre distribution --------------------------
    st.subheader("🎯 Current genre distribution")
    genre_counts = (
        games["genre"].fillna("(unknown)").value_counts().reset_index()
    )
    genre_counts.columns = ["Genre", "Count"]
    fig = px.pie(
        genre_counts.head(10), values="Count", names="Genre",
        title=f"Distribution of {len(games)} tracked games by genre",
    )
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)

    # ---- Section 2: Genre momentum (Steam CCU proxy) -------------------
    st.divider()
    st.subheader("🚀 Genre momentum (Steam CCU proxy)")
    if not steam.empty:
        steam_with_genre = steam.merge(
            games[["game_id", "genre", "name"]], on="game_id", how="left"
        )
        genre_momentum = (
            steam_with_genre.groupby("genre")
            .agg(
                games=("game_id", "nunique"),
                total_peak_ccu=("peak_ccu", "sum"),
                avg_peak_ccu=("peak_ccu", "mean"),
            )
            .reset_index()
            .sort_values("total_peak_ccu", ascending=False)
        )
        st.dataframe(genre_momentum, use_container_width=True, hide_index=True)

        fig = px.bar(
            genre_momentum.head(15), x="total_peak_ccu", y="genre", orientation="h",
            title="Total peak CCU by genre (Steam)",
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=450)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Steam data chưa có (chạy `--source steam`). Hiện không tính được momentum.")

    # ---- Section 3: Genre by source (cross-platform) -------------------
    st.divider()
    st.subheader("🔀 Cross-platform genre comparison")
    cross = (
        games.groupby(["genre", "source"])
        .size()
        .reset_index(name="count")
        .pivot(index="genre", columns="source", values="count")
        .fillna(0)
        .astype(int)
    )
    cross["total"] = cross.sum(axis=1)
    cross = cross.sort_values("total", ascending=False).head(15)
    st.dataframe(cross, use_container_width=True)

    # ---- Section 4: iTunes ranking movement (genre-level) --------------
    st.divider()
    st.subheader("🏆 iTunes ranking presence by genre")
    if not rankings.empty:
        rank_genre = rankings.merge(
            games[["game_id", "genre"]], on="game_id", how="left"
        )
        genre_rank = (
            rank_genre.groupby("genre")
            .agg(
                top10_appearances=("rank", lambda x: (x <= 10).sum()),
                avg_rank=("rank", "mean"),
                total_appearances=("rank", "count"),
            )
            .reset_index()
            .sort_values("top10_appearances", ascending=False)
        )
        st.dataframe(genre_rank, use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có iTunes ranking data.")

    # ---- Section 5: Emerging genres (insight heuristic) ---------------
    st.divider()
    st.subheader("💡 Emerging genre signals")
    st.caption("Heuristic: genres có >3 games + publisher đa dạng (không độc quyền)")
    emerging = (
        games.groupby("genre")
        .agg(
            games=("game_id", "count"),
            publishers=("publisher_name", "nunique"),
        )
        .reset_index()
    )
    emerging["competition_ratio"] = emerging["publishers"] / emerging["games"]
    # Genre "healthy" = nhiều games + nhiều publishers (không bị 1 pub độc quyền)
    healthy = emerging[(emerging["games"] >= 2) & (emerging["publishers"] >= 2)]
    if not healthy.empty:
        st.write("**Genres có competition lành mạnh (đáng sourcing):**")
        st.dataframe(
            healthy.sort_values("games", ascending=False),
            use_container_width=True, hide_index=True
        )
    else:
        st.info("Cần thêm data để detect emerging genres (hiện chỉ có 1 genre dominant).")


# =========================================================================
# PAGE 7: DEAL EVALUATION (game scorecard + ROAS calculator)
# =========================================================================
elif page == PAGES[7]:
    st.title("💼 Deal Evaluation")
    st.caption("Scorecard + ROAS calculator cho game publishing deals")

    st.divider()
    st.subheader("📊 Deal Scorecard")
    st.caption("Nhập thông tin game submission → đánh giá PURSUE/WATCH/PASS")

    col1, col2 = st.columns(2)
    with col1:
        # Game selection: either pick from DB or manual input
        input_mode = st.radio(
            "Game source",
            ["📋 Chọn từ DB", "✍️ Nhập manual"],
            horizontal=True,
            label_visibility="collapsed",
        )

        if input_mode == "📋 Chọn từ DB":
            with get_connection() as conn:
                db_games = pd.read_sql_query(
                    """SELECT DISTINCT name, genre, source FROM dim_game
                       WHERE name IS NOT NULL ORDER BY name""", conn)
                # Also include gacha games
                gacha_games = pd.read_sql_query(
                    """SELECT DISTINCT name, NULL as genre, 'gacha' as source
                       FROM dim_gacha_game ORDER BY name""", conn)
            all_games = pd.concat([db_games, gacha_games], ignore_index=True)
            sel_idx = st.selectbox(
                "Chọn game để evaluate",
                range(len(all_games)),
                format_func=lambda i: f"{all_games.iloc[i]['name']} ({all_games.iloc[i]['source']})",
            )
            game_name = all_games.iloc[sel_idx]["name"]
            db_genre = all_games.iloc[sel_idx]["genre"]
            genre = db_genre if db_genre else "Action"
        else:
            game_name = st.text_input("Game name", value="", placeholder="vd: Pixel Dungeon 3")
            genre = st.selectbox(
                "Genre",
                ["Action", "RPG", "Strategy", "Casual", "Puzzle", "Simulation",
                 "Racing", "Sports", "Adventure", "MMO", "Roleplaying", "Other"]
            )
        platform = st.selectbox("Platform", ["Mobile (iOS)", "Mobile (Android)",
                                              "PC (Steam)", "Cross-platform"])
        monetization = st.selectbox(
            "Monetization model",
            ["F2P + IAP", "F2P + Ads", "F2P + Hybrid", "Premium (paid)",
             "Subscription", "Paid + DLC"]
        )

    with col2:
        deal_cost = st.number_input("Deal cost (USD)", min_value=0, value=50000, step=5000)
        target_cpi = st.number_input("Target CPI (USD)", min_value=0.0, value=0.50, step=0.05)
        est_ltv = st.number_input("Estimated LTV (USD)", min_value=0.0, value=0.80, step=0.05)
        target_d30_retention = st.slider("Target D30 retention %", 0, 50, 15)
        review_score = st.slider("Current review score (0-100)", 0, 100, 75)

    # ---- Compute scores -------------------------------------------------
    st.divider()
    st.subheader("🎯 Scorecard Result")

    # Simple scoring logic (heuristic, can be refined)
    scores = {}

    # Market fit (genre popularity in current DB)
    with get_connection() as conn:
        genre_count = conn.execute(
            "SELECT COUNT(*) FROM dim_game WHERE genre LIKE ?", (f"%{genre}%",)
        ).fetchone()[0]
    # Benchmark: nếu genre có nhiều game tracked → market có demand
    market_fit_score = min(10, 5 + genre_count // 3)
    scores["Market Fit"] = market_fit_score

    # Monetization potential
    mono_scores = {"F2P + Hybrid": 9, "F2P + IAP": 8, "Subscription": 7,
                   "Paid + DLC": 6, "F2P + Ads": 5, "Premium (paid)": 4}
    scores["Monetization"] = mono_scores.get(monetization, 5)

    # ROI / ROAS
    if est_ltv > 0 and target_cpi > 0:
        roas = est_ltv / target_cpi
        # ROAS > 1.5 = good, > 2.0 = great
        roi_score = min(10, int(roas * 4))
    else:
        roas = 0
        roi_score = 0
    scores["ROI / ROAS"] = roi_score

    # Retention potential
    scores["Retention"] = min(10, target_d30_retention // 5)

    # Quality signal (reviews)
    scores["Quality (reviews)"] = review_score // 10

    # Scalability (platform)
    scale_scores = {"Cross-platform": 10, "Mobile (iOS)": 7, "Mobile (Android)": 7,
                    "PC (Steam)": 6}
    scores["Scalability"] = scale_scores.get(platform, 5)

    # Display scores as table
    score_df = pd.DataFrame([
        {"Dimension": dim, "Score": f"{sc}/10", "Raw": sc}
        for dim, sc in scores.items()
    ])
    total_score = sum(scores.values())
    max_score = len(scores) * 10
    pct = total_score / max_score * 100

    col_s1, col_s2, col_s3 = st.columns(3)
    col_s1.metric("Total Score", f"{total_score}/{max_score}")
    col_s2.metric("Percentage", f"{pct:.0f}%")
    # Recommendation
    if pct >= 75:
        rec, rec_color = "🟢 PURSUE", "green"
    elif pct >= 50:
        rec, rec_color = "🟡 WATCH", "orange"
    else:
        rec, rec_color = "🔴 PASS", "red"
    col_s3.markdown(
        f"<h3 style='color:{rec_color}; margin:0;'>{rec}</h3>",
        unsafe_allow_html=True,
    )

    # Bar chart of scores
    fig = px.bar(
        score_df, x="Raw", y="Dimension", orientation="h",
        range_x=[0, 10], title="Score by dimension",
        color="Raw",
        color_continuous_scale=["red", "yellow", "green"],
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=350)
    st.plotly_chart(fig, use_container_width=True)

    # ---- Competitor benchmark (từ DB thật) -----------------------------
    st.divider()
    st.subheader("📊 Competitor Benchmark (từ DB)")
    st.caption("So sánh game submission với competitors trong cùng genre — data thật từ Steam/iTunes/Gacha")

    with get_connection() as conn:
        # Find games in same genre across sources
        bench_games = pd.read_sql_query(
            """
            SELECT g.name, g.genre, g.publisher_name, g.source, g.price_usd,
                   f.peak_ccu, f.positive_reviews, f.negative_reviews
            FROM dim_game g
            LEFT JOIN fact_steam_playercounts f ON g.game_id = f.game_id
            WHERE g.genre LIKE ? AND g.source IN ('steam', 'itunes')
            GROUP BY g.game_id
            ORDER BY f.peak_ccu DESC NULLS LAST
            LIMIT 10
            """,
            conn,
            params=(f"%{genre}%",),
        )
        # Gacha competitors (revenue-based)
        gacha_bench = pd.read_sql_query(
            """
            SELECT g.name, g.publisher, r.revenue_usd, r.snapshot_month, r.rank
            FROM fact_gacha_revenue r
            JOIN dim_gacha_game g ON r.game_id = g.game_id
            WHERE r.snapshot_month = (SELECT MAX(snapshot_month) FROM fact_gacha_revenue)
            ORDER BY r.revenue_usd DESC LIMIT 10
            """,
            conn,
        )

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        st.write(f"**🎮 Steam/iTunes: '{genre}' competitors**")
        if not bench_games.empty:
            display = bench_games[["name", "source", "publisher_name", "peak_ccu"]].copy()
            display["peak_ccu"] = display["peak_ccu"].apply(
                lambda x: f"{x:,.0f}" if pd.notna(x) else "—"
            )
            display.columns = ["Game", "Platform", "Publisher", "Peak CCU"]
            st.dataframe(display, use_container_width=True, hide_index=True)
        else:
            st.info(f"Không có game '{genre}' trong DB.")

    with col_b2:
        st.write("**💰 Top gacha revenue (latest month)**")
        if not gacha_bench.empty:
            display = gacha_bench[["name", "publisher", "revenue_usd", "rank"]].copy()
            display["revenue"] = display["revenue_usd"].apply(lambda x: f"${x/1e6:.1f}M")
            display = display[["rank", "name", "publisher", "revenue"]]
            display.columns = ["Rank", "Game", "Publisher", "Revenue"]
            st.dataframe(display, use_container_width=True, hide_index=True)
        else:
            st.info("Chưa có gacha data.")

    # Genre insights
    if not bench_games.empty:
        avg_ccu = bench_games["peak_ccu"].mean()
        n_competitors = len(bench_games)
        st.info(
            f"📈 **Genre insight:** {n_competitors} games '{genre}' tracked. "
            f"Avg peak CCU: {avg_ccu:,.0f}. "
            f"{'Bão hòa — cần differentiation mạnh.' if n_competitors > 8 else 'Còn room — cơ hội tốt.'}"
        )

    # ---- ROAS projection ----------------------------------------------
    st.divider()
    st.subheader("💰 ROAS Projection")
    if roas > 0:
        # Payback period (số user cần acquire để cover deal cost)
        users_needed = int(deal_cost / max(est_ltv - target_cpi, 0.01))
        # Simple projection: assume X users/month
        col_r1, col_r2, col_r3 = st.columns(3)
        col_r1.metric("ROAS ratio (LTV/CPI)", f"{roas:.2f}x",
                      delta="✅ profitable" if roas > 1 else "❌ loss")
        col_r2.metric("Users needed to break even", f"{users_needed:,}")
        col_r3.metric("Margin per user", f"${est_ltv - target_cpi:.2f}")

        # Sensitivity: vary CPI
        st.write("**Sensitivity analysis (varying CPI):**")
        cpi_range = [target_cpi * f for f in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]]
        sens_data = []
        for cpi in cpi_range:
            roas_sens = est_ltv / cpi if cpi > 0 else 0
            sens_data.append({
                "CPI": f"${cpi:.2f}",
                "ROAS": f"{roas_sens:.2f}x",
                "Profitable": "✅" if roas_sens > 1 else "❌",
            })
        st.dataframe(pd.DataFrame(sens_data), use_container_width=True, hide_index=True)
    else:
        st.warning("Cần nhập LTV và CPI để tính ROAS.")


# =========================================================================
# PAGE 8: 💰 Gacha Revenue
# =========================================================================
elif page == PAGES[8]:
    st.title("💰 Gacha Revenue Tracker")
    st.caption(
        "Top 50 mobile gacha revenue hàng tháng — OCR từ r/gachagaming monthly reports. "
        "Source gốc: Sensor Tower mobile estimates (PC/console excluded)."
    )

    @st.cache_data(ttl=300)
    def load_gacha_revenue() -> pd.DataFrame:
        with get_connection() as conn:
            df = pd.read_sql_query(
                """
                SELECT g.name as game, g.game_id, g.icon_url, g.first_seen_month,
                       r.snapshot_month, r.rank, r.revenue_usd, r.scope, r.source
                FROM fact_gacha_revenue r
                JOIN dim_gacha_game g ON r.game_id = g.game_id
                ORDER BY r.snapshot_month DESC, r.rank ASC
                """,
                conn,
            )
        return df

    gacha = load_gacha_revenue()

    if gacha.empty:
        st.warning(
            "❌ Chưa có gacha revenue data. "
            "Mở revenue.ennead.cc → copy HTML table → save file → "
            "`python scripts/manual/parse_gacha_html.py data/manual/gacha_2026-06.html`"
        )
    else:
        # KPIs
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Months tracked", gacha["snapshot_month"].nunique())
        col2.metric("Games tracked", gacha["game_id"].nunique())
        col3.metric("Total facts", len(gacha))
        latest_month = gacha["snapshot_month"].max()
        n_months = gacha["snapshot_month"].nunique()
        latest_total = gacha[gacha["snapshot_month"] == latest_month]["revenue_usd"].sum()
        col4.metric(f"Revenue ({latest_month})",
                    f"${latest_total/1e6:.1f}M")

        st.divider()

        # Filters
        colf1, colf2 = st.columns(2)
        with colf1:
            all_games = sorted(gacha["game"].unique())
            selected_games = st.multiselect(
                "🎮 Games so sánh (trend lines)",
                all_games,
                default=[g for g in ["Genshin Impact", "Honkai: Star Rail",
                                     "Love and Deepspace", "Wuthering Waves"]
                         if g in all_games] or all_games[:5],
            )
        with colf2:
            top_n = st.slider("Top N games (market share)", 5, 30, 10)

        st.subheader("📈 Revenue Trend")
        st.caption("Monthly revenue (USD) cho games đã chọn — xem momentum qua thời gian")
        if selected_games:
            trend_df = (
                gacha[gacha["game"].isin(selected_games)]
                .pivot_table(index="snapshot_month", columns="game",
                             values="revenue_usd", aggfunc="sum")
                .fillna(0)
                .sort_index()
            )
            st.plotly_chart(
                px.line(trend_df, x=trend_df.index, y=trend_df.columns,
                        labels={"value": "Revenue (USD)", "snapshot_month": "Month"},
                        title="Monthly Revenue Trend"),
                use_container_width=True,
            )
        else:
            st.info("Chọn ít nhất 1 game ở filter trên.")

        st.divider()
        st.subheader("📊 Market Share (latest month)")
        latest_data = gacha[gacha["snapshot_month"] == latest_month].nlargest(top_n, "revenue_usd")
        fig_bar = px.bar(
            latest_data, x="revenue_usd", y="game", orientation="h",
            labels={"revenue_usd": "Revenue (USD)", "game": ""},
            title=f"Top {top_n} Gacha Games — {latest_month}",
        )
        fig_bar.update_yaxes(autorange="reversed")
        st.plotly_chart(fig_bar, use_container_width=True)

        st.divider()
        st.subheader("🏆 Latest Month — Full Ranking")
        latest_full = gacha[gacha["snapshot_month"] == latest_month][
            ["rank", "game", "scope", "revenue_usd"]
        ].sort_values("rank")
        display = latest_full.copy()
        display["revenue"] = display["revenue_usd"].apply(lambda x: f"${x/1e6:.2f}M")
        display = display[["rank", "game", "scope", "revenue"]]
        display.columns = ["Rank", "Game", "Scope", "Revenue (est)"]
        st.dataframe(display, use_container_width=True, hide_index=True)
        st.caption(
            f"💡 Data parsed từ HTML table (source: {gacha['source'].iloc[0]}). "
            f"Revenue = mobile estimates (PC/console excluded)."
        )

        st.divider()
        # === Total Revenue by Game (all months tracked) ===
        st.subheader("💰 Total Revenue by Game (all months)")
        st.caption(
            f"Tổng revenue mỗi game từ {gacha['snapshot_month'].min()} → "
            f"{gacha['snapshot_month'].max()} ({n_months} tháng)"
        )
        totals = (
            gacha.groupby(["game", "scope"], as_index=False)
            .agg(
                total_revenue_usd=("revenue_usd", "sum"),
                months_tracked=("snapshot_month", "nunique"),
                avg_monthly=("revenue_usd", "mean"),
                best_month_revenue=("revenue_usd", "max"),
            )
            .sort_values("total_revenue_usd", ascending=False)
        )
        # Filter scope (optional)
        scopes = ["All"] + sorted(totals["scope"].dropna().unique())
        sel_scope_total = st.selectbox(
            "Filter by scope", scopes, key="gacha_total_scope"
        )
        totals_view = totals.copy()
        if sel_scope_total != "All":
            totals_view = totals_view[totals_view["scope"] == sel_scope_total]

        # Top N slider
        top_total = st.slider(
            "Top N games (total revenue)", 10, 100, 25, step=5, key="gacha_total_top"
        )
        totals_view = totals_view.head(top_total)

        # Bar chart
        fig_total = px.bar(
            totals_view, x="total_revenue_usd", y="game", orientation="h",
            labels={"total_revenue_usd": "Total Revenue (USD)", "game": ""},
            title=f"Top {len(totals_view)} Games — Cumulative Revenue ({n_months} months)",
        )
        fig_total.update_yaxes(autorange="reversed")
        st.plotly_chart(fig_total, use_container_width=True)

        # Table with full detail
        table = totals_view.copy()
        table["Total Rev"] = table["total_revenue_usd"].apply(lambda x: f"${x/1e6:.1f}M")
        table["Avg Monthly"] = table["avg_monthly"].apply(lambda x: f"${x/1e6:.1f}M")
        table["Best Month"] = table["best_month_revenue"].apply(lambda x: f"${x/1e6:.1f}M")
        table = table[["game", "scope", "Total Rev", "months_tracked", "Avg Monthly", "Best Month"]]
        table.columns = ["Game", "Scope", "Total Revenue", "Months", "Avg/Month", "Best Month"]
        st.dataframe(table, use_container_width=True, hide_index=True)
        st.caption(
            f"💡 Tổng revenue {n_months} tháng: ${totals_view['total_revenue_usd'].sum()/1e6:.0f}M. "
            f"Avg/Month = tổng chia số tháng track được (games mới ra sẽ ít tháng hơn)."
        )


# ---- Footer --------------------------------------------------------------
st.sidebar.divider()
st.sidebar.caption(
    "💡 **Tip:** Chạy `python scripts/run_daily.py` rồi nhấn 🔄 Refresh"
)
