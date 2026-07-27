# 📥 Manual Data Slot — Sensor Tower snapshots

> Thư mục này dành cho việc **paste/drop data** mà bạn lấy thủ công (save web →
> strip ra bằng tay) từ các nguồn không thể craw tự động (như Sensor Tower).

## Cách sử dụng

1. **Mở trang Sensor Tower** report public (vd: `sensortower.com/blog/...`)
2. **Copy bảng dữ liệu** → paste vào Excel/CSV
3. **Save** vào thư mục này với convention tên:
   ```
   sensortower_<topic>_<YYYYMMDD>.csv
   ```
   Ví dụ: `sensortower_state_of_mobile_2026Q2.csv`

4. **Cite nguồn** trong cột cuối cùng của CSV:
   ```
   source_url: https://sensortower.com/blog/...
   fetched_date: 2026-07-27
   ```

## Lý do tồn tại slot này

- JD nhắc tới Sensor Tower nhiều lần — interviewer sẽ hỏi về nó
- Có thể không craw tự động (ToS cấm), nhưng **report public** là data họ tự publish
- Paste manual = "human-in-the-loop" workflow, hợp pháp hơn auto-scrap

## Sau khi có file CSV ở đây

Pipeline có thể đọc các file này để enrich dim tables (Roadmap feature).
Hiện tại MVP chỉ tự động Tier 1 sources.

## Ví dụ data đã có (sau khi paste)

```
sensortower_state_of_mobile_2026Q2.csv
sensortower_top_publishers_VN_2026Q2.csv
appannie_market_report_2026.csv
```

→ Ghi rõ metadata ở dòng đầu tiên (header comment).
