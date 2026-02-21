"""Product relevance scoring using sentence-transformer embeddings.

Falls back to TF-IDF cosine similarity when sentence-transformers is not
installed.
"""

import copy
import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-loaded singleton for the SentenceTransformer model
# ---------------------------------------------------------------------------
_model = None
_USE_SBERT = True  # flipped to False if import fails


def _get_model():
    """Return the cached SentenceTransformer model (loaded once)."""
    global _model, _USE_SBERT
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading SentenceTransformer model 'all-MiniLM-L6-v2' ...")
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("SentenceTransformer model loaded successfully.")
        except ImportError:
            logger.warning(
                "sentence-transformers not installed – falling back to TF-IDF scoring."
            )
            _USE_SBERT = False
        except Exception as exc:
            logger.warning("Failed to load SentenceTransformer: %s – using TF-IDF fallback.", exc)
            _USE_SBERT = False
    return _model


# ---------------------------------------------------------------------------
# Brand-name boost helper
# ---------------------------------------------------------------------------
_STOPWORDS = frozenset(
    {"the", "a", "an", "and", "or", "of", "for", "with", "in", "on", "to", "by"}
)


def _brand_boost(product_name: str, competitor: dict, base_score: float) -> float:
    """Boost *base_score* by 10-15 % when the competitor brand overlaps with product name words."""
    brand = (competitor.get("brand") or "").strip().lower()
    if not brand:
        return base_score

    product_words = {
        w
        for w in re.split(r"\W+", product_name.lower())
        if w and w not in _STOPWORDS
    }
    brand_words = {
        w for w in re.split(r"\W+", brand) if w and w not in _STOPWORDS
    }
    if not product_words or not brand_words:
        return base_score

    overlap = product_words & brand_words
    if overlap:
        # Scale boost between 10 % (1 word) and 15 % (2+ words)
        boost_pct = 0.10 if len(overlap) == 1 else 0.15
        boosted = base_score * (1 + boost_pct)
        return min(boosted, 100.0)
    return base_score


# ---------------------------------------------------------------------------
# TF-IDF fallback (original implementation)
# ---------------------------------------------------------------------------
def _score_tfidf_fallback(product_name: str, scored: list[dict]) -> list[dict]:
    """Score competitors using TF-IDF vectorization + cosine similarity."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    if not product_name or not product_name.strip():
        for c in scored:
            c["match_score"] = 0
        return scored

    titles = [c.get("title", "") or "" for c in scored]
    corpus = [product_name] + titles

    try:
        vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=5000,
            ngram_range=(1, 2),
        )
        tfidf_matrix = vectorizer.fit_transform(corpus)

        source_vec = tfidf_matrix[0:1]
        competitor_vecs = tfidf_matrix[1:]
        similarities = cosine_similarity(source_vec, competitor_vecs).flatten()

        for i, comp in enumerate(scored):
            raw = round(float(similarities[i]) * 100, 1)
            comp["match_score"] = round(_brand_boost(product_name, comp, raw), 1)
    except Exception:
        for c in scored:
            c["match_score"] = 0

    scored.sort(key=lambda c: c.get("match_score", 0), reverse=True)
    return scored


# ---------------------------------------------------------------------------
# Sentence-transformer scoring
# ---------------------------------------------------------------------------
def _score_sbert(product_name: str, scored: list[dict]) -> list[dict]:
    """Score competitors using sentence-transformer embeddings."""
    model = _get_model()
    if model is None:
        # Model failed to load or library missing – delegate to fallback
        return _score_tfidf_fallback(product_name, scored)

    from sentence_transformers import util

    if not product_name or not product_name.strip():
        for c in scored:
            c["match_score"] = 0
        return scored

    titles = [c.get("title", "") or "" for c in scored]

    try:
        product_embedding = model.encode(product_name, convert_to_tensor=True)
        title_embeddings = model.encode(titles, convert_to_tensor=True)

        similarities = util.cos_sim(product_embedding, title_embeddings).squeeze(0)

        for i, comp in enumerate(scored):
            raw = round(float(similarities[i].item()) * 100, 1)
            raw = max(raw, 0.0)  # clamp negatives
            comp["match_score"] = round(_brand_boost(product_name, comp, raw), 1)
    except Exception:
        logger.exception("Sentence-transformer scoring failed – falling back to TF-IDF.")
        return _score_tfidf_fallback(product_name, scored)

    scored.sort(key=lambda c: c.get("match_score", 0), reverse=True)
    return scored


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def score_matches(product_name: str, competitors: list[dict]) -> list[dict]:
    """Score how relevant each Amazon competitor is to the given product name.

    Uses sentence-transformer embeddings (``all-MiniLM-L6-v2``) for semantic
    similarity.  Falls back to TF-IDF if the library is unavailable.

    Parameters
    ----------
    product_name : str
        The source product name (e.g. from Alibaba).
    competitors : list[dict]
        List of competitor dicts, each expected to have a ``"title"`` key.

    Returns
    -------
    list[dict]
        The same competitor dicts with an added ``"match_score"`` key (0-100).
        Sorted by match_score descending.
    """
    if not competitors:
        return []

    scored = copy.deepcopy(competitors)

    if _USE_SBERT:
        return _score_sbert(product_name, scored)
    return _score_tfidf_fallback(product_name, scored)
