"""Services package."""
from src.services.alibaba_parser import parse_alibaba_url
from src.services.amazon_search import AmazonSearchError, AmazonSearchService
from src.services.category_helpers import get_search_context
from src.services.competition_analyzer import CompetitionAnalyzer
from src.services.demand_estimator import estimate_demand
from src.services.excel_exporter import ExcelExporter
from src.services.pdf_exporter import export_pdf
from src.services.excel_importer import parse_excel
from src.services.fee_calculator import calculate_fees, calculate_detailed_profitability
from src.services.image_fetcher import ImageFetcher, download_image, save_uploaded_image
from src.services.match_scorer import score_matches
from src.services.price_recommender import recommend_pricing
from src.services.profit_calculator import calculate_profit
from src.services.query_optimizer import optimize_query, suggest_queries
from src.services.search_cache import SearchCache
from src.services.viability_scorer import calculate_vvs
from src.services.brand_moat import classify_seller, compute_brand_concentration
from src.services.gtm_brief_generator import generate_gtm_brief
from src.services.market_events import detect_events, get_all_recent_events
from src.services.xray_importer import XrayImporter
from src.services.review_miner import mine_reviews, get_review_analysis
from src.services.season_forecaster import get_seasonal_data, forecast_demand
from src.services.keyword_intel import extract_keywords, generate_ppc_campaign
from src.services.listing_predictor import train as train_listing_model, predict as predict_listing, predict_batch as predict_listing_batch, get_model_info as get_listing_model_info

__all__ = [
    "parse_alibaba_url",
    "parse_excel",
    "AmazonSearchService",
    "AmazonSearchError",
    "CompetitionAnalyzer",
    "ExcelExporter",
    "export_pdf",
    "get_search_context",
    "ImageFetcher",
    "download_image",
    "save_uploaded_image",
    "optimize_query",
    "suggest_queries",
    "score_matches",
    "recommend_pricing",
    "estimate_demand",
    "calculate_profit",
    "calculate_fees",
    "calculate_detailed_profitability",
    "calculate_vvs",
    "classify_seller",
    "compute_brand_concentration",
    "SearchCache",
    "detect_events",
    "generate_gtm_brief",
    "get_all_recent_events",
    "XrayImporter",
    "mine_reviews",
    "get_review_analysis",
    "get_seasonal_data",
    "forecast_demand",
    "extract_keywords",
    "generate_ppc_campaign",
    "train_listing_model",
    "predict_listing",
    "predict_listing_batch",
    "get_listing_model_info",
]
