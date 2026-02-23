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

### Export & Reports
- **Excel Export** - 6-sheet report with Executive Summary, embedded charts, competitor data, profit analysis, AI recommendations
- **PDF Reports** - Branded Verlumen PDF with cover page, KPI summary, product tables, per-product competitor detail
- **Previous Exports** - Browse and re-download past exports

### Operations
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
cd verlumenMarketResearch
python -m venv venv
venv\Scripts\activate        # Windows
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

Or just **double-click `start.bat`** on Windows.

Open your browser to **http://localhost:8080**

### Docker

```bash
docker-compose up -d
```

## Usage

1. **Settings** - Paste your SerpAPI key, manage category tree, configure scheduled research
2. **Products** - Import Excel, browse by category (hierarchical filter with counts), use filter presets
3. **Research** - Select products, choose marketplace, run competition research
4. **Product Detail** - Review competitors across 4 tabs, approve/reject products, add notes
5. **Export** - Download enriched Excel or branded PDF report

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Web UI | [NiceGUI](https://nicegui.io) 3.x (Python) |
| Database | SQLite + SQLAlchemy 2.0 |
| Amazon Data | [SerpAPI](https://serpapi.com) |
| ML/AI | sentence-transformers, scikit-learn (TF-IDF, K-means) |
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
│   ├── services/             # Business logic & ML (23 services)
│   │   ├── amazon_search     # SerpAPI wrapper (multi-marketplace)
│   │   ├── match_scorer      # Semantic scoring (sentence-transformers)
│   │   ├── trend_tracker     # Competitor trend comparison
│   │   ├── category_helpers   # Hierarchical search context resolution
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
│       ├── pages/            # 5 app pages
│       └── components/       # Reusable UI widgets
└── data/                     # SQLite DB + exports
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

## Roadmap: Phase 6 - Next-Gen Intelligence

| Sprint | Feature | Description |
|--------|---------|-------------|
| 1 | **AI Go-to-Market Brief** | Claude-powered 1-page brief per product: launch price, listing angles, risk flags, 90-day plan |
| 1 | **Brand Moat Detector** | Classify sellers (Amazon 1P / private label / established brand), add as 6th VVS dimension |
| 1 | **Review Velocity Monitor** | Alert on competitor launch surges, decline signals, market events |
| 2 | **Review NLP Pain Map** | Aspect-based sentiment mining: cluster complaints → product improvement opportunities |
| 2 | **Seasonal Forecasting** | Google Trends + BSR history → Prophet model → optimal launch window recommendations |
| 2 | **PPC Keyword Intelligence** | Reverse-ASIN keywords from top competitors → auto-generated campaign seeds |
| 3 | **LLM Listing Autopsy** | "Why is this beating me?" — structured competitive analysis of bullet points, A+ content |
| 3 | **Listing Quality Regression** | XGBoost model trained on own data → predict sales from listing attributes (data flywheel) |
| 4 | **Image Differentiation** | CLIP-based visual analysis of competitor thumbnails → CTR differentiation opportunities |
| 4 | **Cross-Marketplace Gap** | Diff products across 8 marketplaces → white-space expansion + pricing arbitrage |

See **[PROJECT_PLAN.md](PROJECT_PLAN.md)** for the full detailed plan.

---

<p align="center">
  <sub>Built with care for <strong>Verlumen Kids</strong> - Natural wood toys inspired by Montessori principles</sub>
</p>
