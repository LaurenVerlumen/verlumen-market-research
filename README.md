<p align="center">
  <img src="public/images/logo.svg" alt="Verlumen Kids" width="200">
</p>

<h1 align="center">Verlumen Market Research Tool</h1>

<p align="center">
  <strong>Automated Amazon competition analysis for wood &amp; Montessori toy products</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/NiceGUI-2.0+-green" alt="NiceGUI">
  <img src="https://img.shields.io/badge/SerpAPI-Amazon%20Search-orange" alt="SerpAPI">
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
2. Click "Run Research"
3. Get full Amazon competition analysis: prices, ratings, reviews, opportunity scores
4. Export enriched Excel report

## Features

- **Excel Import** - Upload or auto-detect your Verlumen Product Research spreadsheet
- **Alibaba URL Parsing** - Automatically extracts product names from Alibaba URLs
- **Amazon Competition Search** - Uses SerpAPI to find competing products on Amazon.com
- **Competition Scoring** - Automated 0-100 competition and opportunity scores
- **Product Dashboard** - Browse products by category with competition metrics
- **Excel Export** - 3-sheet report: Summary, Detailed Competitors, Category Analysis (with conditional formatting)
- **SerpAPI Integration** - 100 free searches/month (more than enough for typical research)

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

## Usage

1. **Settings** - Paste your SerpAPI key and validate it
2. **Import Data** - Click "Import Default Spreadsheet" or upload a new Excel file
3. **Products** - Browse imported products by category
4. **Amazon Search** - Select products and run competition research
5. **Export** - Download enriched Excel with competition scores and analysis

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Web UI | [NiceGUI](https://nicegui.io) (Python) |
| Database | SQLite + SQLAlchemy |
| Amazon Data | [SerpAPI](https://serpapi.com) |
| Excel | openpyxl + pandas |

## Project Structure

```
verlumenMarketResearch/
├── app.py                    # Main entry point (port 8080)
├── start.bat                 # Windows launcher
├── config.py                 # Configuration
├── public/images/            # Verlumen logos
├── src/
│   ├── models/               # SQLAlchemy models (4 tables)
│   ├── services/             # Business logic
│   │   ├── alibaba_parser    # URL parsing
│   │   ├── amazon_search     # SerpAPI wrapper
│   │   ├── competition_analyzer  # Scoring engine
│   │   ├── excel_importer    # Excel parsing
│   │   └── excel_exporter    # Report generation
│   └── ui/                   # NiceGUI pages & components
│       ├── layout.py         # Shared navigation
│       ├── pages/            # 7 app pages
│       └── components/       # Reusable UI widgets
└── data/                     # SQLite DB + exports
```

---

<p align="center">
  <sub>Built with care for <strong>Verlumen Kids</strong> - Natural wood toys inspired by Montessori principles</sub>
</p>
