# Verlumen Market Research - Project Plan

## Current State (Feb 2026)

### Phases 1-5 Complete

**5-page app**: Dashboard, Products, Product Detail (4 tabs), Export, Settings

**22 services**: Amazon search (multi-marketplace), competition analysis, semantic ML scoring, trend tracking, profit calculation, Xray import, scheduled research, PDF export, Excel export with charts, fee calculator (2025-Q4)

**ML stack**: sentence-transformers semantic scorer, TF-IDF query optimizer, K-means price recommender, demand estimator, VVS viability scorer

**Rich competitor table**: 19+ columns, inline editing, drag-and-drop column reorder, column visibility presets, trend arrows, NEW/GONE badges, persistent sort/layout

**Deployment**: Docker-ready with Dockerfile, docker-compose.yml, health endpoint

### Scores by Area
| Area | Score | Notes |
|------|-------|-------|
| Feature completeness | 9/10 | Core + temporal + scheduling + multi-market |
| UI/UX | 9/10 | Tabbed detail, global search, filter presets, trend charts |
| ML/Intelligence | 8/10 | Semantic scoring, VVS, K-means pricing, demand estimation |
| Code quality | 7/10 | Clean architecture, some large files remain |
| Testing | 0/10 | Zero tests |
| Production readiness | 8/10 | Docker-ready, health endpoint, scheduled jobs |
| Performance | 5/10 | N+1 queries in some areas, loads everything in memory |

---

## Completed: Phase 4 - Next Level

### 4.1 - Tabbed Product Detail (DONE)
Split 1,560-line page into 4 focused tabs: Overview, Competitors, Analysis, History.

### 4.2 - Competitor Trend Tracking (DONE)
New `trend_tracker.py` service compares research snapshots. Trend arrows on competitor table, NEW/GONE badges, delta badges on stats cards, ECharts timeline chart in History tab.

### 4.3 - Smart Dashboard (DONE)
Action widgets (Need Research / Awaiting Review / Approved), VVS-enriched top opportunities table, category performance with VVS badges, clickable navigation, activity feed.

### 4.4 - Column Visibility & Groups (DONE)
Eye icon toggle with Core/Revenue/Seller/Full group presets, per-column checkboxes, persisted to localStorage.

### 4.5 - Semantic Match Scoring (DONE)
Replaced TF-IDF with sentence-transformers (all-MiniLM-L6-v2). Brand name boost (10-15%). Graceful TF-IDF fallback if library not installed.

### 4.6 - Excel Charts (DONE)
Executive Summary sheet with KPI table, Price Distribution chart, Top 10 Opportunity chart. Category Analysis sheet with grouped bar chart.

### 4.7 - Saved Filter Presets (DONE)
4 built-in presets (All Products, High Opportunity, Needs Research, Approved Winners) + custom user presets. localStorage persistence.

### 4.8 - Fee Calculator Update (DONE)
Updated to 2025-Q4 rates. 30 category referral fees, tiered FBA fees by weight, storage fees, aged inventory surcharges.

### 4.9 - Decision Log (DONE)
Timestamped entries per product. Auto-logs status changes. "Add Note" dialog. Timeline UI on product detail. DB migration included.

---

## Completed: Phase 5 - Professional Grade

### 5.0 - Global Search (DONE)
Search bar in header. Type product name and hit Enter to search from any page. Routes search query to Products page.

### 5.1 - Multi-Marketplace (DONE)
8 Amazon marketplaces: US, UK, DE, CA, JP, ES, FR, IT. Marketplace selector on both single-product and bulk research. `amazon_search.py` already supported domain parameter.

### 5.2 - Scheduled Research (DONE)
APScheduler BackgroundScheduler with daily/weekly/monthly options. Config stored in `data/schedule_config.json`. Settings page UI: enable/disable, frequency, hour, day-of-week, Run Now button, status display.

### 5.3 - PDF Reports (DONE)
Branded Verlumen PDF using fpdf2. Cover page with KPI table, product summary table (color-coded by VVS), per-product detail pages with top 5 competitors. Export button alongside Excel on Export page.

### 5.7 - Docker Deployment (DONE)
Dockerfile (python:3.11-slim), docker-compose.yml with volumes and env vars, .dockerignore, `/_health` endpoint, configurable APP_HOST.

---

## Phase 6: Next Frontier (Future)

### 6.1 - Review Sentiment Analysis
- Fetch top competitor reviews via SP-API
- NLP sentiment analysis (positive/negative/neutral)
- Extract common complaints (opportunities for differentiation)
- "Customers want X but competitors don't offer it" insights

### 6.2 - Keepa / CamelCamelCamel Integration
- Historical price charts (90-day, 1-year trends)
- BSR history tracking
- Seasonal pattern detection
- "Best time to launch" recommendation

### 6.3 - Testing & CI/CD
- pytest test suite (target 60%+ coverage)
- GitHub Actions CI pipeline
- Automated lint (black, flake8, mypy)
- Pre-commit hooks

### 6.4 - Multi-User Support
- User authentication (login/registration)
- Per-user filter presets and decision logs
- Role-based access (admin, researcher, viewer)
- Audit trail for all actions

### 6.5 - Notification System
- Price drop alerts ("Competitor X dropped price 20%")
- New competitor alerts
- Scheduled report emails (weekly digest)
- In-app notification center

### 6.6 - Product Comparison View
- Side-by-side comparison of 2-3 products
- Shared competitor overlap analysis
- Category-level aggregation charts
- Decision matrix for sourcing choices

### 6.7 - Performance Optimization
- Eager loading / batch queries to eliminate N+1
- Pagination with server-side filtering
- Background data loading
- Database indexing audit

---

## Architecture (Current)

```
┌──────────────────────────────────────────────────────┐
│               UI Layer (NiceGUI 3.x)                 │
│                                                       │
│  Dashboard    Products     Product Detail     Export   │
│  (action      (presets,    (4 tabs: Overview, (Excel, │
│   widgets,    global       Competitors,        PDF)   │
│   VVS,        search,      Analysis,                  │
│   activity)   bulk ops)    History)                    │
│                                                       │
│  Settings     Layout (global search bar, sidebar)     │
│  (schedule,                                           │
│   API keys,                                           │
│   departments)                                        │
└────────────────────────┬─────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────┐
│              Service Layer (22 services)              │
│                                                       │
│  Search*     SP-API    Xray      TrendTracker         │
│  Analyzer    Scorer*   Price     Demand    VVS        │
│  Profit      Fees*     Export*   PDF*      Scheduler* │
│  ImageFetch  Cache     QueryOpt                       │
│                                                       │
│  * = upgraded in Phase 4-5                            │
└────────────────────────┬─────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────┐
│               Data Layer (SQLAlchemy 2.0)             │
│                                                       │
│  Product (+ decision_log, status)                     │
│  AmazonCompetitor (19+ columns, trend support)        │
│  SearchSession (+ amazon_domain for marketplace)      │
│  Category   SearchCache                               │
└──────────────────────────────────────────────────────┘

Deployment: Docker (Dockerfile + docker-compose.yml)
Scheduling: APScheduler (background research)
ML: sentence-transformers + scikit-learn
```

---

*Last updated: February 2026*
*Project: Verlumen Market Research Tool*
*Team: Verlumen Kids - Internal Tools*
