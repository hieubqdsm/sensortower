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

# ---- Page routing via radio (đơn giản, không cần multipage app) ---------
PAGES = [
    "📊 Portfolio Overview",
    "🏆 Rankings & Trends",
    "🎭 Genre & Publisher",
    "🔍 Game Detail",
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
# PAGE 2: RANKINGS & TRENDS
# =========================================================================
elif page == PAGES[1]:
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
            import plotly.express as px
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
# PAGE 3: GENRE & PUBLISHER
# =========================================================================
elif page == PAGES[2]:
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
# PAGE 4: GAME DETAIL
# =========================================================================
elif page == PAGES[3]:
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


# ---- Footer --------------------------------------------------------------
st.sidebar.divider()
st.sidebar.caption(
    "💡 **Tip:** Chạy `python scripts/run_daily.py` rồi nhấn 🔄 Refresh"
)
