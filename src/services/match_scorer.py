"""Product relevance scoring using TF-IDF cosine similarity."""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def score_matches(product_name: str, competitors: list[dict]) -> list[dict]:
    """Score how relevant each Amazon competitor is to the given product name.

    Uses TF-IDF vectorization and cosine similarity to compare the source
    product name against each competitor title.

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

    # Work on a deep copy to avoid mutating the caller's list
    import copy
    scored = copy.deepcopy(competitors)

    if not product_name or not product_name.strip():
        for c in scored:
            c["match_score"] = 0
        return scored

    # Build corpus: first document is the source product, rest are competitor titles
    titles = [c.get("title", "") or "" for c in scored]
    corpus = [product_name] + titles

    try:
        vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=5000,
            ngram_range=(1, 2),
        )
        tfidf_matrix = vectorizer.fit_transform(corpus)

        # Compute similarity of each competitor title against the source product
        source_vec = tfidf_matrix[0:1]
        competitor_vecs = tfidf_matrix[1:]
        similarities = cosine_similarity(source_vec, competitor_vecs).flatten()

        for i, comp in enumerate(scored):
            comp["match_score"] = round(float(similarities[i]) * 100, 1)
    except Exception:
        # If TF-IDF fails (e.g. all empty titles), assign zero scores
        for c in scored:
            c["match_score"] = 0

    # Sort by match_score descending
    scored.sort(key=lambda c: c.get("match_score", 0), reverse=True)
    return scored
