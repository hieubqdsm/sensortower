# 📋 Job Description — Game Publishing BI Lead

> Vị trí dự án này nhắm tới. Tất cả feature trong repo đều map ngược về 1 nhiệm
> vụ cụ thể trong JD này (xem `docs/daily_schedule.md`).

---

## 🏢 Thông tin chung

- **Vị trí:** Game Publishing BI Analyst / Lead
- **Reports to:** Head of Operations (Vietnam)
- **Location:** Ho Chi Minh City
- **Collaborators:** Marketing, Finance, Product, Development teams

---

## 🎯 Key Responsibilities

### 1. BI Systems & Data Strategy

**Architect BI Solutions:**
- Lead the design and implementation of a centralized Business Intelligence system
- Collaborate with Data Engineers to ensure data pipelines accurately capture KPIs across:
  - Game performance
  - User acquisition
  - Monetization

**Power BI Ecosystem:**
- Build, maintain, and optimize a suite of **automated Power BI dashboards**
- Provide real-time visibility into portfolio health for:
  - Technical teams
  - Marketing teams
  - Product teams

**Data Governance:**
- Work with technical team to define data schemas
- Ensure **"one version of the truth"** across all cross-functional reports

### 2. Game Evaluation & Deal Assessment

- Evaluate submitted or scouted game proposals based on:
  - **Market fit**
  - **Scalability**
  - **Monetization potential**
  - **Alignment with company objectives**
- Collaborate with **operations** and **finance** teams to assess:
  - Feasibility of potential deals
  - **ROI** of potential game publishing deals
- Provide detailed reports and recommendations to leadership on **which games to pursue**

### 3. Cross-Functional Collaboration

- Work closely with **marketing, product, and development** teams
- Ensure sourced games align with:
  - Promotional capabilities
  - Technical requirements
- Share insights and updates to foster a **data-driven approach** to game publishing

### 4. Reporting Structure

- Reports directly to the **Head of Operations in Vietnam**
- Collaborates with marketing, finance, and product teams

---

## ✅ Yêu cầu công việc (Requirements)

### Must-have

| # | Requirement |
|---|-------------|
| 1 | **Hardcore gamer** who plays a lot of mobile genres |
| 2 | **3-5+ years** in the mobile gaming industry (market analysis, game publishing, or related) |
| 3 | **Strong analytical skills** — interpret complex data → actionable strategies |
| 4 | **Deep knowledge** of mobile game trends, genres, monetization models (IAP, ads, subscriptions) |
| 5 | **Communication & negotiation skills** — liaise with developers and internal stakeholders |
| 6 | **Advanced Analytics:** expert SQL + Python for data extraction |
| 7 | **Power BI** (DAX / Power Query) for complex data modeling & visualization |
| 8 | Familiar with **3rd-party mobile game analytics platforms**: App Annie, Sensor Tower, Firebase, MMP (Adjust / AppsFlyer) |
| 9 | **English proficiency** |

### Nice-to-have

- Familiarity with **Vietnamese gaming market** and its unique characteristics
- Knowledge of gaming metrics: **ROI / ROAS / Retention**

---

## 🎁 Benefits

- Salary matches skills and experience
- Working hours: Monday to Friday
- **Full salary during probation**
- **13th-month salary** guaranteed
- Full social insurance based on gross salary
- Premium health insurance
- Annual leave from 14 days
- Lunch allowance
- In-house pantry (coffee, tea, snacks)
- Company activities and events

---

## 🗺️ Mapping JD → Project Features

Mỗi yêu cầu của JD được hiện thực hóa bằng 1 feature cụ thể trong project:

| JD Requirement | Feature trong repo |
|----------------|---------------------|
| BI Systems / Data pipelines | `src/pipeline.py` + `src/crawlers/` (Steam/iTunes/IGDB/News) |
| Power BI dashboards | `powerbi/data_sources.md` (user tự build) + `dashboard/app.py` (Streamlit inspector) |
| Data schemas / "one version of truth" | `docs/data_dictionary.md` + SQLite star schema |
| Game evaluation / Deal assessment | Dashboard page **💼 Deal Evaluation** (scorecard + ROAS) |
| ROI / ROAS / Retention | ROAS projection trong Deal Evaluation page |
| Genre trends / market fit | Dashboard page **📈 Genre Trends** |
| 3rd-party platforms (Sensor Tower etc) | `docs/tos_compliance.md` — giải thích ethics + alternative sources |
| SQL + Python | Toàn bộ codebase |
| Cross-functional reporting | `scripts/generate_report.py` (markdown briefing share được) |

---

*JD lưu trữ ngày 2026-07-28 cho mục đích portfolio documentation.*
