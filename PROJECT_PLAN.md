# Verlumen Market Research - Project Plan

## Current State (Feb 2026)

### Phases 1-9 Complete

**8-page app**: Dashboard, Products, Product Detail (5 tabs), Export, Marketplace Gap, Recycle Bin, Settings

**27 services**: Amazon search (multi-marketplace, rate-limited), competition analysis, semantic ML scoring, trend tracking, profit calculation, Xray import, scheduled research, PDF export, Excel export with charts, fee calculator (2025-Q4), category hierarchy helpers, AI Go-to-Market brief, brand moat detector, review velocity monitor, review NLP pain map, seasonal forecasting, PPC keyword intelligence, LLM listing autopsy, listing quality predictor, cross-marketplace gap analyzer, DB backup/restore

**ML stack**: sentence-transformers semantic scorer, TF-IDF query optimizer, K-means price recommender, demand estimator, VVS viability scorer, GradientBoosting sales predictor

**LLM stack**: Claude API (Haiku) for AI briefs + listing autopsy via tool-use structured output

**Rich competitor table**: 19+ columns, inline editing, drag-and-drop column reorder, column visibility presets, trend arrows, NEW/GONE badges, persistent sort/layout

**Data safety**: Auto SQL dump on startup + git pre-commit hook, rolling backups, auto-restore on new machines

**Deployment**: Docker-ready with Dockerfile, docker-compose.yml, health endpoint

### Scores by Area
| Area | Score | Notes |
|------|-------|-------|
| Feature completeness | 10/10 | All planned intelligence features shipped |
| UI/UX | 9.5/10 | 8 pages, rich charts, inline editing, filter presets |
| ML/Intelligence | 9.5/10 | LLM autopsy, sales predictor, brand moat, review mining, seasonal, PPC |
| Code quality | 8/10 | Session helper, indexes, rate limiting; monolithic files remain |
| Testing | 0/10 | Zero tests — next priority |
| Production readiness | 9/10 | Rate limiting, backup system, Docker, health endpoint |
| Performance | 7/10 | DB indexes done, N+1 fixed; SQL pagination + VVS caching still TODO |

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

## Completed: Phase 5.5 - Hierarchical Categories

### Category Tree Model (DONE)
Self-referencing `Category` model with `parent_id`, `level`, `sort_order`, `amazon_department`. Sibling uniqueness via `UniqueConstraint("parent_id", "name")`. Helper methods: `get_ancestors()`, `get_path()`, `get_descendants()`, `get_all_ids()`, `resolve_department()`.

### Database Migration (DONE)
Safe SQLite migration (recreate table to drop UNIQUE constraint). Copies existing categories as root-level. Migrates department mappings from config into `amazon_department` column. Seeds Toys & Games tree with 20 Amazon subcategories + Baby Products root.

### Search Enhancement (DONE)
New `category_helpers.get_search_context()` returns department (inherited up tree) and query suffix (leaf category name stripped of special chars). Applied to all 4 search call sites: product detail, bulk research, scheduled research. Example: product in "Puzzles" searches as "Wooden Blocks Puzzles".

### Settings Tree UI (DONE)
Recursive tree management replacing flat category list + department mapping. Per-node: icon, name, count badge, department dropdown with "(inherit)" option, add subcategory, rename, move/re-parent, delete (cascade-aware). Department inheritance shown via tooltip.

### Move/Re-parent (DONE)
Dialog with hierarchical parent dropdown. Prevents circular moves (excludes self and descendants). Fixes descendant levels recursively after move.

### Sidebar Navigation (DONE)
Only shows categories with products (total_count > 0). Clean indented tree, no expansion panels. Links use `category_id` query param.

### Hierarchical Filters (DONE)
Products and Export pages: indented dropdown with product counts per category. Selecting a parent includes all descendant products. Backward-compatible with `?category=Name` URLs.

---

## Phase 6: Next-Gen Intelligence (DONE)

The leap from "research tool" to "AI-powered competitive intelligence platform." Every feature below was selected because no existing Amazon tool (Helium 10, Jungle Scout, SmartScout, DataDive) does it well — or at all.

### Sprint 1: Quick Wins (DONE)

#### 6.1 - AI Go-to-Market Brief (DONE)
LLM synthesis layer that turns all existing scored data into a 1-page actionable brief per product.

- **Input**: VVS dimensions, pricing strategies, demand estimates, trend data, competitor stats (all already computed)
- **Output** (structured JSON via Claude tool-use):
  - Recommended launch price with rationale
  - Top 3 listing headline angles
  - Risk flags ("2 of top 5 are Amazon 1P — avoid" or "all sellers are unbranded — your brand is a moat")
  - 90-day launch milestones with concrete actions
- New service: `src/services/gtm_brief_generator.py`
- Rendered as collapsible "AI Brief" section in product detail + included in PDF export
- Cost: ~$0.002/product with Claude Haiku, ~$0.02 with Sonnet
- **Why it matters**: Reduces cognitive load to near-zero. A non-expert can hand the brief to a factory rep or PPC agency the same day.

#### 6.2 - Brand Moat Detector (DONE)
Classify competitors by seller type and compute a Brand Concentration Risk Score per subcategory.

- **Seller classification**: Amazon 1P, private label (unbranded), established brand (has trademark/website), Chinese commodity seller
- **Data**: `seller_country`, `brand`, `manufacturer` already exist in `AmazonCompetitor` model from Xray import — currently unused in scoring
- **Metrics**:
  - Herfindahl-Hirschman Index (HHI) for revenue concentration
  - Amazon-as-competitor flag (red flag)
  - Brand vs. commodity seller ratio
- **Integration**: Add as 6th VVS dimension (weight ~0.10, reduce differentiation from 0.10 to 0.05)
- **UI**: Brand concentration pie chart on product detail Analysis tab
- **Why it matters**: A market of 20 unbranded Chinese sellers = STRONG GO. Same market with 3 established US toy brands = CONDITIONAL at best. This single insight flips decisions.

#### 6.3 - Review Velocity Anomaly Detector (DONE)
Track weekly review count deltas across all monitored competitors. Flag market events.

- **Signals**: New entrant surge (50+ reviews in 30 days), established player decline (velocity drop), aggressive relaunch
- **Implementation**: Diff review counts per ASIN between scheduled research runs (data already collected)
- **UI**: "Market Events" feed on dashboard, alert badges on competitor table
- **Why it matters**: Earliest public signal of competitive threats. No tool alerts you to competitor launches in your niche.

### Sprint 2: Intelligence Layer (DONE)

#### 6.4 - Review NLP Pain Map (DONE)
Mine competitor reviews to extract actionable product improvement opportunities.

- **Pipeline**: Fetch 50-200 reviews per top-5 competitors → aspect-based sentiment analysis → cluster complaints by topic (size, material, assembly, durability, packaging) → frequency × intensity heat map
- **Tech**: `pyabsa` (open-source ABSA) or Claude batch calls with structured output
- **Data source**: SerpAPI reviews endpoint (~$0.005/review page) or SP-API `getReviews` (gated)
- **Output**: "42% of negatives mention loose joints → emphasize mortise & tenon joinery and offer 30-day structural guarantee"
- New service: `src/services/review_miner.py`, new `review_analysis` DB table, "Review Map" tab in product detail
- **Why it matters**: The highest-value feature for a niche toy brand. A "paint chips" cluster in reviews means Verlumen can invest $0.30/unit in better finish and own 4.8+ stars within 6 months.

#### 6.5 - Seasonal Demand Forecasting (DONE)
Predict optimal launch windows using Google Trends + accumulated BSR history.

- **Data**: `pytrends` (free, no API key) for 5-year weekly interest data + own BSR time-series from scheduled research sessions
- **Model**: Prophet or ARIMA fit on combined signals → monthly demand index, peak week prediction
- **Output**: "Wooden building blocks peak week 47 (late Nov). Ship FBA by mid-October to capture Q4. Launching after Dec 1 costs you an entire season of review accumulation."
- New service: `src/services/season_forecaster.py`, "Best Launch Window" card on product detail
- **Why it matters**: For kids toys, Q4 is 3-4x baseline. Getting timing wrong by 6 weeks costs an entire season.

#### 6.6 - PPC Keyword Intelligence (DONE)
Reverse-ASIN keyword lookup on top competitors → auto-generated campaign seeds.

- **Pipeline**: Top 5 competitor ASINs (already stored) → DataForSEO Amazon keywords API (~$0.025/product) → keyword dedup + tiering
- **Output tiers**:
  - Auto campaign seeds: all gap keywords with high volume
  - Manual exact match: keywords where competitors rank #1-3 (intercept)
  - Negative keyword list: irrelevant high-volume terms
- Exportable CSV + rendered table in product detail, wire into `excel_exporter.py`
- **Why it matters**: PPC keyword research is 3-5 hours per product launch. This automates it entirely. Competitors charge $99+/month for standalone versions (Helium 10 Cerebro).

### Sprint 3: Advanced ML (DONE)

#### 6.7 - LLM Listing Autopsy (DONE)
Feed top competitor listings into Claude for structured competitive analysis.

- **Input**: Bullet points, A+ content, titles from SP-API `getListingsItem` or SerpAPI product scrape
- **Output**: `{gaps: [], winning_angles: [], missing_claims: [], messaging_framework: ""}`
- "All top sellers mention ASTM certification and age 3+ but none mention sensory play — that is your opening"
- New service: `src/services/listing_analyzer.py`, on-demand from product detail
- **Why it matters**: Directly actionable — seller can draft their listing using the winning framework the same day.

#### 6.8 - Listing Quality Regression Model (DONE)
Train a predictive model on accumulated competitor data to forecast sales from listing attributes.

- **Model**: GradientBoosting (scikit-learn) trained on `AmazonCompetitor` rows: title length, price, rating, review count, position, match score, badge → predict `bought_last_month`
- **Data flywheel**: Model improves with every research session. After 200+ competitors with sales data, predictions become niche-specific.
- **Use case**: "Your listing attributes predict 340 units/month. Adding ASTM certification mention increases prediction to 480 units/month."
- New service: `src/services/listing_predictor.py`, model serialized to `data/listing_model.joblib`
- **Why it matters**: Converts from "measure the market" to "optimize my listing." The data flywheel is a moat competitors can't replicate.

### Sprint 4: Experimental

#### 6.9 - Product Image Differentiation Scorer (DEFERRED)
CLIP-based visual analysis of competitor thumbnails.

- **Pipeline**: Download competitor thumbnails (URLs already in DB) → CLIP embeddings → cluster into visual styles (lifestyle, white-background, infographic, bundle) → score visual diversity
- "All competitors use white-background shots — be the only lifestyle photo for 15-30% CTR lift"
- New service: `src/services/image_analyzer.py`, visual grid in product detail
- **Why it matters**: Visual differentiation is top-3 factor in Amazon CTR. Genuinely novel — no tool does this.

#### 6.10 - Cross-Marketplace Gap Analyzer (DONE)
Compare products and competitors across all 8 supported marketplaces.

- **Pipeline**: Multi-marketplace data already exists → diff-view across marketplace tables
- Flag ASINs high-performing in US but absent in DE/UK (white-space expansion)
- Flag pricing arbitrage: product at €32 in DE, $22 in US (>30% differential alerts)
- New page at `/marketplace-gap` with sidebar nav link
- Opportunity scores per marketplace, ECharts price comparison, overlap matrix
- **Why it matters**: Lowest effort of all features — just a new view over existing data.

---

### Parallel Track: Codebase Health

Performance and architecture improvements to run alongside feature sprints.

#### P0 - Critical (DONE)
| Issue | File | Fix | Status |
|-------|------|-----|--------|
| N+1 queries in category tree | `layout.py` | `selectinload(Category.children, recursion_depth=-1)` | DONE |
| Missing DB indexes | `database.py` | `ix_products_status_created_at`, `ix_amazon_competitors_position` | DONE |
| No SerpAPI rate limiting | `amazon_search.py` | `Semaphore(2)` + 1s min spacing via `_wait_for_rate_limit()` | DONE |
| Session management helper | `database.py` | `with_db()` context manager (available for new code) | DONE |
| In-memory pagination | `products.py` | Move search/status/count filters to SQL | TODO |
| VVS never cached | `dashboard.py` | Store VVS score in DB, recompute on new research | TODO |

#### P1 - Important
| Issue | File | Fix |
|-------|------|-----|
| Products page monolithic (1,700+ lines) | `products.py` | Split into filters, render, bulk_actions modules |
| Product detail monolithic (2,400+ lines) | `product_detail.py` | Extract research dialog, Xray UI to components |
| Async operations not cancelled on page leave | `products.py` | Use `asyncio.Task` with timeout |
| Dashboard subquery complexity | `dashboard.py` | Use window functions, batch VVS computation |

#### P2 - Nice to Have
| Issue | Fix |
|-------|-----|
| Filter presets browser-only (localStorage) | Persist to DB |
| Bulk selection lost on refresh | Restore by product IDs |
| Trend data underutilized | Add trending badges to dashboard |
| No decision log viewer | Add timeline in product detail |

---

### Scores (Post Phase 9)
| Area | Score | Notes |
|------|-------|-------|
| Feature completeness | 10/10 | All planned intelligence features shipped |
| UI/UX | 9.5/10 | 8 pages, rich charts, inline editing, filter presets |
| ML/Intelligence | 9.5/10 | LLM autopsy, sales predictor, brand moat, review mining, seasonal forecasting, PPC |
| Code quality | 8/10 | Session helper, indexes, rate limiting; monolithic files remain |
| Testing | 0/10 | Still zero tests — next priority |
| Production readiness | 9/10 | Rate limiting, backup system, Docker, health endpoint |
| Performance | 7/10 | DB indexes done, N+1 fixed; SQL pagination + VVS caching still TODO |

### Dependencies Added in Phase 6-9
| Library | Purpose | License |
|---------|---------|---------|
| `anthropic` | Claude API for AI briefs, listing autopsy | MIT |
| `pytrends` | Google Trends seasonal forecasting (free) | MIT |
| `scikit-learn` | GradientBoosting sales predictor, K-means pricing | BSD |
| `joblib` | Model serialization | BSD |

---

## Architecture (Current)

```
┌───────────────────────────────────────────────────────────┐
│                  UI Layer (NiceGUI 3.x)                    │
│                                                            │
│  Dashboard    Products       Product Detail       Export   │
│  (widgets,    (presets,      (5 tabs: Overview,   (Excel,  │
│   VVS,        global search,  Competitors,         PDF,    │
│   activity)   bulk ops,       Analysis, History,   Brief)  │
│               hierarchy)      Review Map)                  │
│                                                            │
│  Marketplace Gap   Recycle Bin   Settings                  │
│  (arbitrage,       (restore,     (categories,              │
│   whitespace,       delete)       API keys, sched)         │
│   overlap)                                                 │
│                                                            │
│  Layout (global search bar, sidebar with categories)       │
└────────────────────────┬──────────────────────────────────┘
                         │
┌────────────────────────▼──────────────────────────────────┐
│              Service Layer (27 services)                    │
│                                                            │
│  Search       SP-API     Xray         TrendTracker         │
│  Analyzer     Scorer     Price        Demand       VVS     │
│  Profit       Fees       Export       PDF          Sched   │
│  ImageFetch   Cache      QueryOpt    CatHelpers            │
│  GTMBrief     ReviewMiner  SeasonForecaster                │
│  ListingAnalyzer  ListingPredictor  MarketplaceGap         │
│  KeywordIntel  BrandMoat  DBBackup                         │
└────────────────────────┬──────────────────────────────────┘
                         │
┌────────────────────────▼──────────────────────────────────┐
│              Data Layer (SQLAlchemy 2.0)                    │
│                                                            │
│  Product (decision_log, status, profitability_data)        │
│  AmazonCompetitor (19+ columns, trend support)             │
│  SearchSession (amazon_domain for marketplace)             │
│  Category (hierarchical tree)   SearchCache                │
│  ReviewAnalysis                                            │
│                                                            │
│  Backup: data/backup.sql (git-tracked, auto on startup)    │
└───────────────────────────────────────────────────────────┘

Deployment: Docker (Dockerfile + docker-compose.yml)
Scheduling: APScheduler (background research)
ML: sentence-transformers + scikit-learn (GradientBoosting, K-means, TF-IDF)
LLM: Claude API (Haiku/Sonnet) for AI briefs + listing autopsy
Backup: Auto SQL dump on startup + pre-commit hook + rolling .db copies
```

---

*Last updated: February 2026*
*Project: Verlumen Market Research Tool*
*Team: Verlumen Kids - Internal Tools*
