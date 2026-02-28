<p align="center">
  <img src="public/images/logo.svg" alt="Verlumen Kids" width="200">
</p>

<h1 align="center">Verlumen Market Research Tool</h1>

<p align="center">
  <strong>Automated Amazon competition analysis for wood &amp; Montessori toy products</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/NiceGUI-3.x-green" alt="NiceGUI">
  <img src="https://img.shields.io/badge/SerpAPI-Amazon%20Search-orange" alt="SerpAPI">
  <img src="https://img.shields.io/badge/sentence--transformers-Semantic%20ML-red" alt="Sentence Transformers">
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white" alt="Docker">
</p>

---

## What is this?

An internal web tool for **Verlumen Kids** that automates the tedious process of researching Amazon competition for products sourced from Alibaba manufacturers. Instead of manually checking each product one-by-one on Amazon, this tool does it all automatically.

### The Problem
1. Find interesting wood/Montessori toys on Alibaba
2. Copy product URLs into an Excel spreadsheet
3. **Manually** open Amazon, search for each product, check prices, reviews, ratings, competition...
4. Repeat 20+ times. Tedious!

### The Solution
1. Import your Alibaba Excel file
2. Click "Run Research" (choose marketplace: US, UK, DE, CA, JP, ES, FR, IT)
3. Get full Amazon competition analysis: prices, ratings, reviews, opportunity scores, trend tracking
4. Export enriched Excel or branded PDF report

## Features

### Core Workflow
- **Excel Import** - Upload or auto-detect your Verlumen Product Research spreadsheet
- **Alibaba URL Parsing** - Automatically extracts product names from Alibaba URLs
- **Amazon Competition Search** - Multi-page SerpAPI search (40-60 results) with department filtering, subcategory query enhancement
- **Multi-Marketplace** - Research on amazon.com, .co.uk, .de, .ca, .co.jp, .es, .fr, .it
- **Competition Scoring** - Automated 0-100 competition and opportunity scores
- **VVS Viability Score** - 5-dimension GO/NO-GO verdict (demand, competition, profitability, market quality, differentiation)

### Product Management
- **Smart Dashboard** - Action widgets, VVS-enriched tables, category performance, activity feed
- **Global Search** - Search any product from the header bar
- **Hierarchical Categories** - Amazon-style category tree (e.g. Toys & Games > Puzzles > 3D Puzzles), move/re-parent, per-category department, subcategory search enhancement
- **Product Dashboard** - Browse by category with thumbnails, search, filter, sort, bulk operations
- **Tabbed Product Detail** - 4 focused tabs: Overview, Competitors, Analysis, History
- **Decision Log** - Timestamped entries per product, auto-logs status changes, manual notes
- **Saved Filter Presets** - Name and save filter combos, 4 built-in presets + custom
- **Recycle Bin** - Soft-delete products to a recoverable bin; restore or permanently delete anytime

### Competitor Analysis
- **Trend Tracking** - Compare research snapshots, price/rating trend arrows, NEW/GONE badges, ECharts timeline
- **Column Visibility** - Toggle columns with Core/Revenue/Seller/Full presets, persisted to localStorage
- **Drag-and-Drop Columns** - Reorder columns by dragging, persistent across sessions
- **Inline Editing** - Edit any competitor field directly in the table with auto-recalculation
- **Helium 10 Xray Import** - Upload Xray Excel to enrich competitors with real revenue/sales data
- **SP-API Integration** - Brand/manufacturer enrichment via Amazon Selling Partner API

### ML-Powered Intelligence
- **Semantic Match Scoring** - sentence-transformers (all-MiniLM-L6-v2) for meaning-aware matching with brand boost
- **Smart Query Optimizer** - TF-IDF keyword extraction cleans Alibaba product names for better searches
- **Price Recommender** - Budget/Competitive/Premium pricing strategies using K-means clustering
- **Demand Estimator** - Parses "bought last month" data to estimate monthly revenue and market size
- **Profit Calculator** - Full margin analysis with 2025-Q4 FBA fees: landed cost, Amazon fees, net profit, ROI%, break-even
- **LLM Listing Autopsy** - Claude-powered competitive analysis: gaps, winning angles, missing claims, messaging framework
- **Listing Quality Predictor** - GradientBoosting model predicts monthly sales from listing attributes (scikit-learn)
- **Cross-Marketplace Gap** - Compare products across 8 marketplaces: price arbitrage, whitespace detection, overlap matrix

### Export & Reports
- **Excel Export** - 6-sheet report with Executive Summary, embedded charts, competitor data, profit analysis, AI recommendations
- **PDF Reports** - Branded Verlumen PDF with cover page, KPI summary, product tables, per-product competitor detail
- **Previous Exports** - Browse and re-download past exports

### Data Safety & Operations
- **Auto DB Backup** - SQL text dump on every app startup + git pre-commit hook; auto-restore on new machines
- **Rolling Backups** - Timestamped local DB copies (last 5) for quick recovery
- **Scheduled Research** - APScheduler with daily/weekly/monthly auto-research, configurable in Settings
- **Docker Ready** - Dockerfile + docker-compose.yml for one-command deployment
- **Health Endpoint** - `/_health` for monitoring
- **Search Caching** - 24h SQLite cache saves API credits on repeated searches

## Quick Start

### Prerequisites
- Python 3.11+
- Free SerpAPI account ([serpapi.com](https://serpapi.com)) - 100 searches/month free

### Setup

```bash
cd verlumen-market-research
python -m venv venv

# Activate (choose your OS):
source venv/bin/activate      # macOS / Linux
venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

Create a `.env` file:
```
SERPAPI_KEY=your_serpapi_key_here
```

### Run

```bash
python app.py
```

Or use the launcher script for your OS:
- **macOS / Linux**: `./start.sh`
- **Windows**: double-click `start.bat`

Open your browser to **http://localhost:8080**

> **New machine?** The app auto-restores the database from `data/backup.sql` on first launch. You can also run `bash scripts/restore_db.sh` manually.

### Docker

```bash
docker-compose up -d
```

## Deploying on a New Computer

Follow these steps to get the full app running with all your data on any machine.

### 1. Clone the repository

```bash
git clone https://github.com/LaurenVerlumen/verlumen-market-research.git
cd verlumen-market-research
```

### 2. Set up Python environment

Requires **Python 3.11+**. Check with `python --version`.

```bash
python -m venv venv
```

Activate the virtual environment:
```bash
# Windows (Command Prompt)
venv\Scripts\activate

# Windows (Git Bash / MSYS2)
source venv/Scripts/activate

# macOS / Linux
source venv/bin/activate
```

Install dependencies (this can take a few minutes due to torch/ML packages):
```bash
pip install -r requirements.txt
```

> **Compatibility**: Python 3.11, 3.12, and 3.13 are all supported, including macOS Apple Silicon (arm64). All packages including `torch` have native arm64 wheels.

### 3. Configure API keys

Copy the example and fill in your keys:
```bash
cp .env.example .env
```

Then edit `.env` and set at minimum:
```
SERPAPI_KEY=your_serpapi_key_here
```

The app will run without any API keys, but search and AI features need them. You can also paste keys in the **Settings** page after launching.

### 4. Launch

```bash
python app.py
```

Or use the launcher script for your OS:
- **macOS / Linux**: `./start.sh`
- **Windows**: double-click `start.bat`

Open **http://localhost:8080** — all your products, categories, competitors, and research data will be there.

> **Database auto-restore**: The database (`data/verlumen.db`) is gitignored. On first launch the app automatically rebuilds it from `data/backup.sql` (which IS tracked in git). No manual step needed.

### Keeping data in sync across machines

The database is backed up as a plain-text SQL file (`data/backup.sql`) tracked in git.

**Easiest way**: Use the **Save & Backup** button in the app's Settings page — it dumps the DB, commits, and pushes in one click.

**Manual sync**:

1. **Before leaving a machine**: click Save & Backup, or:
   ```bash
   git add -A && git commit -m "Data sync" && git push
   ```

2. **On the other machine**: pull and restart:
   ```bash
   git pull
   # Delete the old DB so it gets rebuilt from the latest backup:
   rm data/verlumen.db      # Linux/Mac/Git Bash
   del data\verlumen.db     # Windows CMD
   python app.py
   ```

> **Important**: Do not run the app on two machines simultaneously — SQLite is single-writer. Always save & push from one machine before pulling on another.

## Usage

1. **Settings** - Paste your SerpAPI key (+ optional Anthropic key for AI features), manage category tree, configure scheduled research
2. **Products** - Import Excel, browse by category (hierarchical filter with counts), use filter presets
3. **Research** - Select products, choose marketplace, run competition research
4. **Product Detail** - Review competitors across 4 tabs, approve/reject products, run Listing Autopsy, train sales predictor
5. **Marketplace Gap** - Compare products across multiple Amazon marketplaces, spot arbitrage
6. **Recycle Bin** - Recover deleted products or permanently remove them
7. **Export** - Download enriched Excel or branded PDF report

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Web UI | [NiceGUI](https://nicegui.io) 3.x (Python) |
| Database | SQLite + SQLAlchemy 2.0 |
| Amazon Data | [SerpAPI](https://serpapi.com) |
| ML/AI | sentence-transformers, scikit-learn (TF-IDF, K-means, GradientBoosting), Claude API |
| Charts | ECharts via NiceGUI |
| Excel | openpyxl + pandas |
| PDF | fpdf2 |
| Scheduling | APScheduler |
| Deployment | Docker |

## Project Structure

```
verlumenMarketResearch/
├── app.py                    # Main entry point (port 8080)
├── config.py                 # Configuration & marketplace settings
├── Dockerfile                # Docker deployment
├── docker-compose.yml        # Docker Compose orchestration
├── start.bat                 # Windows launcher
├── public/images/            # Verlumen logos
├── src/
│   ├── models/               # SQLAlchemy models (6 tables)
│   ├── services/             # Business logic & ML (27 services)
│   │   ├── amazon_search     # SerpAPI wrapper (multi-marketplace, rate-limited)
│   │   ├── match_scorer      # Semantic scoring (sentence-transformers)
│   │   ├── trend_tracker     # Competitor trend comparison
│   │   ├── category_helpers   # Hierarchical search context resolution
│   │   ├── db_backup         # Auto SQL dump, rolling backups, restore
│   │   ├── listing_analyzer  # LLM Listing Autopsy (Claude API)
│   │   ├── listing_predictor # Sales prediction (GradientBoosting)
│   │   ├── marketplace_gap   # Cross-marketplace gap analysis
│   │   ├── scheduler         # APScheduler background research
│   │   ├── pdf_exporter      # Branded PDF report generation
│   │   ├── excel_exporter    # 6-sheet Excel with charts
│   │   ├── fee_calculator    # 2025-Q4 FBA fee tables
│   │   ├── viability_scorer  # VVS 5-dimension scoring
│   │   ├── competition_analyzer  # Scoring engine
│   │   ├── price_recommender # K-means pricing strategies
│   │   ├── demand_estimator  # Market demand analysis
│   │   └── ...               # Query optimizer, image fetcher, etc.
│   └── ui/                   # NiceGUI pages & components
│       ├── layout.py         # Header with global search, sidebar nav
│       ├── pages/            # 8 app pages
│       └── components/       # Reusable UI widgets
├── scripts/                  # Backup & restore scripts
└── data/                     # SQLite DB + backup.sql + exports
```

## Completed Phases

### Phase 1-2: Foundation
Excel import, SerpAPI search, competition scoring, product dashboard, export system, category management, search caching.

### Phase 3: State of the Art
- VVS Viability Score (5-dimension GO/NO-GO verdict)
- UI consolidation (7 pages merged to 4)
- Fully editable competitor table (18+ columns, inline editing)
- Drag-and-drop column reorder with persistent layout
- SP-API integration for brand enrichment
- Helium 10 Xray import with cross-session dedup
- Dynamic progress dialogs for research
- Category navigation nesting in sidebar
- Profit analysis with 3 pricing strategies

### Phase 4: Next Level
- Tabbed product detail (Overview, Competitors, Analysis, History)
- Competitor trend tracking with NEW/GONE badges, price arrows, ECharts timeline
- Smart dashboard with action widgets, VVS tables, activity feed
- Column visibility toggle with Core/Revenue/Seller/Full presets
- Semantic match scoring (sentence-transformers replacing TF-IDF)
- Excel export with Executive Summary sheet and embedded charts
- Saved filter presets (4 built-in + custom user presets)
- Fee calculator updated to 2025-Q4 FBA rates (30 categories)
- Decision log with timestamped entries and auto-logging

### Phase 5: Professional Grade
- Global search bar in header
- Multi-marketplace support (US, UK, DE, CA, JP, ES, FR, IT)
- Scheduled research with APScheduler (daily/weekly/monthly)
- PDF report generation (branded Verlumen reports)
- Docker deployment (Dockerfile + docker-compose + health check)

### Phase 5.5: Hierarchical Categories
- Self-referencing category tree (unlimited nesting, e.g. Toys & Games > Puzzles > 3D Puzzles)
- Move/re-parent categories with full descendant-level fix
- Per-category Amazon department with inheritance (children inherit from parent)
- Subcategory search enhancement (leaf name appended to search queries)
- Hierarchical filter dropdowns with product counts on Products & Export pages
- Smart sidebar nav: only shows categories with products, clean indented tree
- Pre-seeded Toys & Games tree with 20 Amazon subcategories + Baby Products
- SQLite migration: safe table recreation for schema change, department mapping migration

### Phase 7: Profitability & Polish
- Profitability calculator persistence (save/load profit data per product)
- Unit toggle (metric/imperial) for shipping dimensions
- Competitor table column customization

### Phase 8: Data Safety & Recycle Bin
- Auto SQL dump on app startup + git pre-commit hook for database backup
- Rolling timestamped DB backups (local, max 5)
- Auto-restore from `backup.sql` when DB is missing (new machine setup)
- Recycle Bin with soft-delete, restore, and permanent delete
- Image upload override fix (cache-busting for browser-cached images)
- Re-import rejected products (reset to imported instead of blocking)

### Phase 9: Advanced Intelligence & Codebase Health
- **LLM Listing Autopsy** - Claude-powered competitive analysis: gaps, winning angles, missing claims, messaging framework
- **Listing Quality Predictor** - GradientBoosting ML model trained on competitor data to predict monthly sales from listing attributes
- **Cross-Marketplace Gap Analyzer** - New page comparing products across 8 Amazon marketplaces with price arbitrage alerts (>30% diff), whitespace detection, competitor overlap matrix, opportunity scores, ECharts price charts
- **P0 Codebase Health**: N+1 query fix (selectinload), DB indexes (status+created_at, position), SerpAPI rate limiting (semaphore + 1s spacing), `with_db()` session context manager

## Roadmap: Future

| Feature | Description |
|---------|-------------|
| **Image Differentiation** | CLIP-based visual analysis of competitor thumbnails → CTR differentiation opportunities |
| **In-memory pagination → SQL** | Move search/status/count filters to database level |
| **VVS caching** | Store VVS score in DB, recompute only on new research |
| **Module splitting** | Break up products.py (1700+ lines) and product_detail.py (2400+ lines) |
| **Test suite** | Currently 0/10 — add pytest coverage for services and models |

See **[PROJECT_PLAN.md](PROJECT_PLAN.md)** for the full detailed plan.

---

<p align="center">
  <sub>Built with care for <strong>Verlumen Kids</strong> - Natural wood toys inspired by Montessori principles</sub>
</p>
