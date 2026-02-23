# Verlumen Market Research - Project Plan

## Current State (Feb 2026)

### Phases 1-5 Complete

**5-page app**: Dashboard, Products, Product Detail (4 tabs), Export, Settings

**23 services**: Amazon search (multi-marketplace), competition analysis, semantic ML scoring, trend tracking, profit calculation, Xray import, scheduled research, PDF export, Excel export with charts, fee calculator (2025-Q4), category hierarchy helpers

**ML stack**: sentence-transformers semantic scorer, TF-IDF query optimizer, K-means price recommender, demand estimator, VVS viability scorer

**Rich competitor table**: 19+ columns, inline editing, drag-and-drop column reorder, column visibility presets, trend arrows, NEW/GONE badges, persistent sort/layout

**Deployment**: Docker-ready with Dockerfile, docker-compose.yml, health endpoint

### Scores by Area
| Area | Score | Notes |
|------|-------|-------|
| Feature completeness | 9/10 | Core + temporal + scheduling + multi-market + hierarchical categories |
| UI/UX | 9/10 | Tabbed detail, global search, filter presets, trend charts, category tree |
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

## Phase 6: Next-Gen Intelligence

The leap from "research tool" to "AI-powered competitive intelligence platform." Every feature below was selected because no existing Amazon tool (Helium 10, Jungle Scout, SmartScout, DataDive) does it well — or at all.

### Sprint 1: Quick Wins (1-2 days each, zero new data sources)

#### 6.1 - AI Go-to-Market Brief
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

#### 6.2 - Brand Moat Detector
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

#### 6.3 - Review Velocity Anomaly Detector
Track weekly review count deltas across all monitored competitors. Flag market events.

- **Signals**: New entrant surge (50+ reviews in 30 days), established player decline (velocity drop), aggressive relaunch
- **Implementation**: Diff review counts per ASIN between scheduled research runs (data already collected)
- **UI**: "Market Events" feed on dashboard, alert badges on competitor table
- **Why it matters**: Earliest public signal of competitive threats. No tool alerts you to competitor launches in your niche.

### Sprint 2: Intelligence Layer (3-5 days each, one new API each)

#### 6.4 - Review NLP Pain Map
Mine competitor reviews to extract actionable product improvement opportunities.

- **Pipeline**: Fetch 50-200 reviews per top-5 competitors → aspect-based sentiment analysis → cluster complaints by topic (size, material, assembly, durability, packaging) → frequency × intensity heat map
- **Tech**: `pyabsa` (open-source ABSA) or Claude batch calls with structured output
- **Data source**: SerpAPI reviews endpoint (~$0.005/review page) or SP-API `getReviews` (gated)
- **Output**: "42% of negatives mention loose joints → emphasize mortise & tenon joinery and offer 30-day structural guarantee"
- New service: `src/services/review_miner.py`, new `review_analysis` DB table, "Review Map" tab in product detail
- **Why it matters**: The highest-value feature for a niche toy brand. A "paint chips" cluster in reviews means Verlumen can invest $0.30/unit in better finish and own 4.8+ stars within 6 months.

#### 6.5 - Seasonal Demand Forecasting
Predict optimal launch windows using Google Trends + accumulated BSR history.

- **Data**: `pytrends` (free, no API key) for 5-year weekly interest data + own BSR time-series from scheduled research sessions
- **Model**: Prophet or ARIMA fit on combined signals → monthly demand index, peak week prediction
- **Output**: "Wooden building blocks peak week 47 (late Nov). Ship FBA by mid-October to capture Q4. Launching after Dec 1 costs you an entire season of review accumulation."
- New service: `src/services/season_forecaster.py`, "Best Launch Window" card on product detail
- **Why it matters**: For kids toys, Q4 is 3-4x baseline. Getting timing wrong by 6 weeks costs an entire season.

#### 6.6 - PPC Keyword Intelligence
Reverse-ASIN keyword lookup on top competitors → auto-generated campaign seeds.

- **Pipeline**: Top 5 competitor ASINs (already stored) → DataForSEO Amazon keywords API (~$0.025/product) → keyword dedup + tiering
- **Output tiers**:
  - Auto campaign seeds: all gap keywords with high volume
  - Manual exact match: keywords where competitors rank #1-3 (intercept)
  - Negative keyword list: irrelevant high-volume terms
- Exportable CSV + rendered table in product detail, wire into `excel_exporter.py`
- **Why it matters**: PPC keyword research is 3-5 hours per product launch. This automates it entirely. Competitors charge $99+/month for standalone versions (Helium 10 Cerebro).

### Sprint 3: Advanced ML (1 week each)

#### 6.7 - LLM Listing Autopsy
Feed top competitor listings into Claude for structured competitive analysis.

- **Input**: Bullet points, A+ content, titles from SP-API `getListingsItem` or SerpAPI product scrape
- **Output**: `{gaps: [], winning_angles: [], missing_claims: [], messaging_framework: ""}`
- "All top sellers mention ASTM certification and age 3+ but none mention sensory play — that is your opening"
- New service: `src/services/listing_analyzer.py`, on-demand from product detail
- **Why it matters**: Directly actionable — seller can draft their listing using the winning framework the same day.

#### 6.8 - Listing Quality Regression Model
Train a predictive model on accumulated competitor data to forecast sales from listing attributes.

- **Model**: XGBoost/LightGBM trained on `AmazonCompetitor` rows: title length, image count, price vs. median, review count, rating, badge → predict `bought_last_month`
- **Data flywheel**: Model improves with every research session. After 200+ competitors with sales data, predictions become niche-specific.
- **Use case**: "Your listing attributes predict 340 units/month. Adding ASTM certification mention increases prediction to 480 units/month."
- New service: `src/services/listing_predictor.py`, model serialized to `data/listing_model.joblib`
- **Why it matters**: Converts from "measure the market" to "optimize my listing." The data flywheel is a moat competitors can't replicate.

### Sprint 4: Experimental (exploratory)

#### 6.9 - Product Image Differentiation Scorer
CLIP-based visual analysis of competitor thumbnails.

- **Pipeline**: Download competitor thumbnails (URLs already in DB) → CLIP embeddings → cluster into visual styles (lifestyle, white-background, infographic, bundle) → score visual diversity
- "All competitors use white-background shots — be the only lifestyle photo for 15-30% CTR lift"
- New service: `src/services/image_analyzer.py`, visual grid in product detail
- **Why it matters**: Visual differentiation is top-3 factor in Amazon CTR. Genuinely novel — no tool does this.

#### 6.10 - Cross-Marketplace Gap Analyzer
Compare products and competitors across all 8 supported marketplaces.

- **Pipeline**: Multi-marketplace data already exists → diff-view across marketplace tables
- Flag ASINs high-performing in US but absent in DE/UK (white-space expansion)
- Flag pricing arbitrage: product at €32 in DE, $22 in US
- **Why it matters**: Lowest effort of all features — just a new view over existing data.

---

### Parallel Track: Codebase Health

Performance and architecture improvements to run alongside feature sprints.

#### P0 - Critical (do first)
| Issue | File | Fix |
|-------|------|-----|
| N+1 queries in category tree | `layout.py:129-180` | Add `selectinload(Category.children)` |
| Missing DB indexes | `database.py` | Add indexes on `product(status, created_at)`, `competitor(position)` |
| In-memory pagination | `products.py:1228-1306` | Move search/status/count filters to SQL |
| VVS never cached | `dashboard.py` | Store VVS score in DB, recompute on new research |
| No SerpAPI rate limiting | `amazon_search.py` | Add `asyncio.Semaphore(2)` |

#### P1 - Important
| Issue | File | Fix |
|-------|------|-----|
| Products page monolithic (1,629 lines) | `products.py` | Split into filters, render, bulk_actions modules |
| Product detail monolithic (1,959 lines) | `product_detail.py` | Extract research dialog, Xray UI to components |
| Duplicate session management (30+ try/finally) | All pages | Create `@contextmanager with_db()` helper |
| Async operations not cancelled on page leave | `products.py:647` | Use `asyncio.Task` with timeout |
| Dashboard subquery complexity | `dashboard.py:80-120` | Use window functions, batch VVS computation |

#### P2 - Nice to Have
| Issue | Fix |
|-------|-----|
| Filter presets browser-only (localStorage) | Persist to DB |
| Bulk selection lost on refresh | Restore by product IDs |
| Trend data underutilized | Add trending badges to dashboard |
| No decision log viewer | Add timeline in product detail |

---

### Phase 6 Scores (Projected)
| Area | Current | Target | Key Improvement |
|------|---------|--------|----------------|
| Feature completeness | 9/10 | 10/10 | AI briefs, review mining, PPC keywords |
| UI/UX | 9/10 | 9.5/10 | Loading states, performance fixes |
| ML/Intelligence | 8/10 | 9.5/10 | LLM synthesis, ABSA reviews, seasonal forecasting, CLIP vision |
| Code quality | 7/10 | 8.5/10 | Module splitting, session helpers, indexes |
| Testing | 0/10 | 0/10 | Deferred to Phase 7 |
| Production readiness | 8/10 | 9/10 | Rate limiting, caching, eager loading |
| Performance | 5/10 | 8/10 | DB indexes, SQL-level pagination, VVS caching |

### New Dependencies
| Library | Purpose | License | Size |
|---------|---------|---------|------|
| `anthropic` | Claude API for AI briefs, listing autopsy | MIT | ~5MB |
| `pytrends` | Google Trends data (free) | MIT | ~1MB |
| `pyabsa` | Aspect-based sentiment analysis | MIT | ~50MB |
| `xgboost` | Listing quality regression | Apache 2.0 | ~15MB |
| `transformers` + `torch` (optional) | CLIP image analysis | Apache 2.0 | ~600MB |
| DataForSEO API | PPC keyword intelligence | Commercial | API only |

---

## Architecture (Current + Phase 6 Planned)

```
┌──────────────────────────────────────────────────────┐
│               UI Layer (NiceGUI 3.x)                 │
│                                                       │
│  Dashboard    Products     Product Detail     Export   │
│  (action      (presets,    (5+ tabs: Overview,(Excel, │
│   widgets,    global       Competitors,        PDF,   │
│   VVS,        search,      Analysis, History,  AI     │
│   activity,   bulk ops,    Review Map*, AI     Brief) │
│   events*)    hierarchy)   Brief*, PPC*)              │
│                                                       │
│  Settings     Layout (global search bar, sidebar)     │
│  (category                                            │
│   tree, API                                           │
│   keys, sched)                                        │
└────────────────────────┬─────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────┐
│           Service Layer (23 + 7 planned)              │
│                                                       │
│  Search*     SP-API    Xray      TrendTracker         │
│  Analyzer    Scorer*   Price     Demand    VVS        │
│  Profit      Fees*     Export*   PDF*      Scheduler* │
│  ImageFetch  Cache     QueryOpt  CatHelpers*          │
│                                                       │
│  Phase 6 (planned):                                   │
│  GTMBrief*    ReviewMiner*   SeasonForecaster*        │
│  ListingAnalyzer*  ListingPredictor*  ImageAnalyzer*  │
│  KeywordIntel*                                        │
│                                                       │
│  * = new or upgraded                                  │
└────────────────────────┬─────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────┐
│               Data Layer (SQLAlchemy 2.0)             │
│                                                       │
│  Product (+ decision_log, status)                     │
│  AmazonCompetitor (19+ columns, trend support)        │
│  SearchSession (+ amazon_domain for marketplace)      │
│  Category (hierarchical tree)   SearchCache           │
│  ReviewAnalysis* (Phase 6)                            │
└──────────────────────────────────────────────────────┘

Deployment: Docker (Dockerfile + docker-compose.yml)
Scheduling: APScheduler (background research)
ML: sentence-transformers + scikit-learn + XGBoost* + CLIP*
LLM: Claude API (Haiku/Sonnet) for AI briefs + listing analysis
```

---

*Last updated: February 2026*
*Project: Verlumen Market Research Tool*
*Team: Verlumen Kids - Internal Tools*
