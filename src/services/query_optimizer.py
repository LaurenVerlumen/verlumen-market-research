"""Smart search query optimizer using NLP/TF-IDF to turn Alibaba product names into Amazon search queries."""
import re
from typing import Optional

from sklearn.feature_extraction.text import TfidfVectorizer

# Noise patterns commonly found in Alibaba product titles
_NOISE_WORDS = {
    "hot sale", "factory direct", "wholesale", "high quality", "new arrival",
    "free shipping", "fast shipping", "drop shipping", "dropshipping",
    "low price", "best price", "cheap", "oem", "odm", "custom logo",
    "customized", "in stock", "ready to ship", "moq", "sample",
    "supplier", "manufacturer", "china", "made in china",
    "top quality", "premium quality", "super quality",
}

# Regex patterns to strip
_STRIP_PATTERNS = [
    re.compile(r"20[12]\d", re.IGNORECASE),          # year numbers like 2023, 2024, 2025
    re.compile(r"[\u4e00-\u9fff]+"),                  # Chinese characters
    re.compile(r"\b\d+\s*(?:pcs?|pieces?|lots?)\b", re.IGNORECASE),  # quantity: "10pcs"
    re.compile(r"\b\d+\s*(?:cm|mm|inch|m)\b", re.IGNORECASE),  # measurements
    re.compile(r"[^\w\s/-]"),                          # special characters except / and -
]

# Feature keywords to prioritise (material, type, age group, style)
_FEATURE_CATEGORIES = {
    "material": {
        "cotton", "polyester", "nylon", "leather", "silk", "linen", "wool",
        "bamboo", "stainless steel", "aluminum", "plastic", "wood", "metal",
        "glass", "ceramic", "rubber", "silicone", "acrylic", "titanium",
    },
    "age_group": {
        "baby", "toddler", "kids", "children", "teen", "adult", "women",
        "men", "boys", "girls", "infant", "unisex",
    },
    "style": {
        "vintage", "modern", "minimalist", "bohemian", "casual", "formal",
        "sporty", "luxury", "retro", "classic", "elegant", "cute",
    },
}


def optimize_query(alibaba_name: str) -> str:
    """Clean an Alibaba product title into an optimized Amazon search query.

    Parameters
    ----------
    alibaba_name : str
        Raw Alibaba product title.

    Returns
    -------
    str
        Cleaned query string ready for Amazon search.
    """
    if not alibaba_name or not alibaba_name.strip():
        return ""

    text = alibaba_name.lower()

    # Remove noise phrases
    for noise in _NOISE_WORDS:
        text = text.replace(noise, " ")

    # Apply regex strips
    for pattern in _STRIP_PATTERNS:
        text = pattern.sub(" ", text)

    # Collapse whitespace
    tokens = text.split()
    if not tokens:
        return alibaba_name.strip()

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_tokens: list[str] = []
    for t in tokens:
        lower = t.lower()
        if lower not in seen and len(lower) > 1:
            seen.add(lower)
            unique_tokens.append(t)

    # Reorder: feature keywords first, then remaining tokens
    feature_tokens: list[str] = []
    other_tokens: list[str] = []
    all_features = set()
    for cat_words in _FEATURE_CATEGORIES.values():
        all_features.update(cat_words)

    for t in unique_tokens:
        if t.lower() in all_features:
            feature_tokens.append(t)
        else:
            other_tokens.append(t)

    reordered = feature_tokens + other_tokens

    # Cap at 10 words to keep query focused
    reordered = reordered[:10]

    return " ".join(reordered).strip()


def suggest_queries(alibaba_name: str) -> list[str]:
    """Generate up to 3 Amazon search query suggestions from an Alibaba product title.

    Uses TF-IDF keyword extraction to produce variations.

    Parameters
    ----------
    alibaba_name : str
        Raw Alibaba product title.

    Returns
    -------
    list[str]
        Up to 3 query suggestions, ordered from broadest to most specific.
    """
    base = optimize_query(alibaba_name)
    if not base:
        return []

    tokens = base.split()
    if len(tokens) <= 2:
        return [base]

    suggestions: list[str] = []

    # Suggestion 1: full optimized query
    suggestions.append(base)

    # Use TF-IDF to rank tokens by importance
    try:
        # Build a small corpus: the full query plus individual tokens
        corpus = [base] + [t for t in tokens if len(t) > 2]
        vectorizer = TfidfVectorizer(stop_words="english")
        tfidf_matrix = vectorizer.fit_transform(corpus)
        feature_names = vectorizer.get_feature_names_out()

        # Get scores from the first document (the full query)
        scores = tfidf_matrix[0].toarray().flatten()
        ranked = sorted(zip(feature_names, scores), key=lambda x: x[1], reverse=True)

        # Suggestion 2: top 4 keywords only
        top_keywords = [word for word, _ in ranked[:4] if word in tokens]
        if top_keywords and len(top_keywords) >= 2:
            s2 = " ".join(top_keywords)
            if s2 != base:
                suggestions.append(s2)

        # Suggestion 3: top 2 keywords (broadest)
        broad_keywords = [word for word, _ in ranked[:2] if word in tokens]
        if broad_keywords:
            s3 = " ".join(broad_keywords)
            if s3 not in suggestions:
                suggestions.append(s3)
    except Exception:
        # Fallback: simple truncation
        if len(tokens) >= 4:
            s2 = " ".join(tokens[:4])
            if s2 != base:
                suggestions.append(s2)
        if len(tokens) >= 2:
            s3 = " ".join(tokens[:2])
            if s3 not in suggestions:
                suggestions.append(s3)

    return suggestions[:3]
