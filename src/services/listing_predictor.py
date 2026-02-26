"""Listing Quality Regression — predict monthly sales from listing attributes."""
import logging
import os
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import cross_val_score
from sklearn.metrics import mean_absolute_error, r2_score

from src.models.database import get_session
from src.models.amazon_competitor import AmazonCompetitor
from src.services.utils import parse_bought

logger = logging.getLogger(__name__)

MODEL_PATH = Path("data/listing_model.joblib")

FEATURE_NAMES = [
    "title_length",
    "price",
    "rating",
    "review_count",
    "position",
    "match_score",
    "is_prime",
    "is_amazons_choice",
    "is_best_seller",
]

_model_cache: Optional[GradientBoostingRegressor] = None


def _extract_features(comp: AmazonCompetitor) -> Optional[dict]:
    """Extract feature dict from an AmazonCompetitor ORM row. Returns None if unusable."""
    bought = parse_bought(comp.bought_last_month)
    if bought is None or bought <= 0:
        return None

    badge = (comp.badge or "").lower()
    return {
        "title_length": len(comp.title) if comp.title else 0,
        "price": comp.price if comp.price is not None else 0.0,
        "rating": comp.rating if comp.rating is not None else 0.0,
        "review_count": comp.review_count if comp.review_count is not None else 0,
        "position": comp.position if comp.position is not None else 0,
        "match_score": comp.match_score if comp.match_score is not None else 0.0,
        "is_prime": 1 if comp.is_prime else 0,
        "is_amazons_choice": 1 if "amazon" in badge and "choice" in badge else 0,
        "is_best_seller": 1 if "best seller" in badge else 0,
        "target": bought,
    }


def _features_from_dict(d: dict) -> list[float]:
    """Convert a features dict (or raw competitor dict) to the ordered feature vector."""
    badge = (d.get("badge") or "").lower()
    title = d.get("title") or ""
    return [
        d.get("title_length", len(title)),
        d.get("price") or 0.0,
        d.get("rating") or 0.0,
        d.get("review_count") or 0,
        d.get("position") or 0,
        d.get("match_score") or 0.0,
        1 if d.get("is_prime") else 0,
        d.get("is_amazons_choice", 1 if "amazon" in badge and "choice" in badge else 0),
        d.get("is_best_seller", 1 if "best seller" in badge else 0),
    ]


def train() -> dict:
    """Train the listing quality regression model on all available competitor data.

    Returns a dict with training metrics:
        - r2, mae, sample_size, feature_importance, status, message
    """
    global _model_cache

    db = get_session()
    try:
        rows = db.query(AmazonCompetitor).all()
    finally:
        db.close()

    samples = []
    for row in rows:
        feat = _extract_features(row)
        if feat is not None:
            samples.append(feat)

    if len(samples) < 50:
        return {
            "status": "insufficient_data",
            "message": f"Need at least 50 competitors with sales data to train. Found {len(samples)}.",
            "sample_size": len(samples),
            "r2": None,
            "mae": None,
            "feature_importance": {},
        }

    X = np.array([_features_from_dict(s) for s in samples])
    y = np.array([s["target"] for s in samples])

    model = GradientBoostingRegressor(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.8,
        random_state=42,
    )

    # Cross-validated metrics
    cv_r2 = cross_val_score(model, X, y, cv=min(5, len(samples)), scoring="r2")
    cv_mae = cross_val_score(model, X, y, cv=min(5, len(samples)), scoring="neg_mean_absolute_error")

    # Final fit on all data
    model.fit(X, y)

    # Feature importance
    importance = dict(zip(FEATURE_NAMES, model.feature_importances_.tolist()))

    # Save model
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    _model_cache = model

    r2 = float(np.mean(cv_r2))
    mae = float(-np.mean(cv_mae))

    logger.info("Listing predictor trained: R²=%.3f, MAE=%.1f, n=%d", r2, mae, len(samples))

    return {
        "status": "ok",
        "message": f"Model trained on {len(samples)} samples.",
        "sample_size": len(samples),
        "r2": round(r2, 3),
        "mae": round(mae, 1),
        "feature_importance": {k: round(v, 4) for k, v in sorted(importance.items(), key=lambda x: -x[1])},
    }


def _load_model() -> Optional[GradientBoostingRegressor]:
    """Load the cached or persisted model."""
    global _model_cache
    if _model_cache is not None:
        return _model_cache
    if MODEL_PATH.exists():
        _model_cache = joblib.load(MODEL_PATH)
        return _model_cache
    return None


def predict(features_dict: dict) -> Optional[int]:
    """Predict bought_last_month for a single competitor from its feature dict.

    Parameters
    ----------
    features_dict : dict
        Must contain keys matching FEATURE_NAMES (or at least title, price, rating, etc.)

    Returns None if no model is available.
    """
    model = _load_model()
    if model is None:
        return None
    vec = np.array([_features_from_dict(features_dict)])
    pred = model.predict(vec)[0]
    return max(0, int(round(pred)))


def predict_batch(competitors: list[dict]) -> list[dict]:
    """Predict sales for a list of competitor dicts.

    Returns the same list enriched with 'predicted_sales' key.
    """
    model = _load_model()
    if model is None:
        return competitors

    results = []
    for c in competitors:
        enriched = dict(c)
        vec = np.array([_features_from_dict(c)])
        pred = model.predict(vec)[0]
        enriched["predicted_sales"] = max(0, int(round(pred)))
        results.append(enriched)
    return results


def get_model_info() -> Optional[dict]:
    """Return saved model metadata if model file exists, else None."""
    if not MODEL_PATH.exists():
        return None
    try:
        mtime = os.path.getmtime(MODEL_PATH)
        from datetime import datetime
        trained_at = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        return {"trained_at": trained_at, "path": str(MODEL_PATH)}
    except Exception:
        return None
