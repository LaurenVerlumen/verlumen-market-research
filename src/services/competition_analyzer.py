"""Analyze Amazon search results and compute competition/opportunity metrics."""
import statistics
from typing import Optional

from src.services.match_scorer import score_matches
from src.services.price_recommender import recommend_pricing
from src.services.demand_estimator import estimate_demand


class CompetitionAnalyzer:
    """Compute competition and opportunity metrics from Amazon competitor data."""

    def analyze(self, competitors: list[dict]) -> dict:
        """Analyze a list of Amazon competitors and return aggregated metrics.

        Parameters
        ----------
        competitors : list[dict]
            List of competitor dicts as returned by
            ``AmazonSearchService.search_products()["competitors"]``.

        Returns
        -------
        dict  with competition/opportunity scores and price statistics.
        """
        if not competitors:
            return self._empty_result()

        prices = [c["price"] for c in competitors if c.get("price") is not None]
        ratings = [c["rating"] for c in competitors if c.get("rating") is not None]
        reviews = [c["review_count"] for c in competitors if c.get("review_count") is not None]
        prime_count = sum(1 for c in competitors if c.get("is_prime"))
        badges = [c.get("badge") or "" for c in competitors]
        has_best_seller = any("Best Seller" in b for b in badges)
        has_amazon_choice = any("Amazon" in b and "Choice" in b for b in badges)
        bought_count = sum(1 for c in competitors if c.get("bought_last_month"))

        # Price stats
        price_min = min(prices) if prices else 0.0
        price_max = max(prices) if prices else 0.0
        price_median = statistics.median(prices) if prices else 0.0
        price_mean = statistics.mean(prices) if prices else 0.0

        # Suggested price range (25th-75th percentile)
        suggested_min, suggested_max = self._percentile_range(prices)

        # Review distribution
        review_distribution = self._review_distribution(reviews)

        avg_rating = statistics.mean(ratings) if ratings else 0.0
        avg_reviews = int(statistics.mean(reviews)) if reviews else 0
        max_reviews = max(reviews) if reviews else 0

        competition_score = self._competition_score(
            competitors=competitors,
            reviews=reviews,
            ratings=ratings,
            has_best_seller=has_best_seller,
            has_amazon_choice=has_amazon_choice,
        )

        opportunity_score = self._opportunity_score(
            competition_score=competition_score,
            avg_reviews=avg_reviews,
            bought_count=bought_count,
            total=len(competitors),
            prices=prices,
        )

        return {
            "total_competitors": len(competitors),
            "price_min": round(price_min, 2),
            "price_max": round(price_max, 2),
            "price_median": round(price_median, 2),
            "price_mean": round(price_mean, 2),
            "avg_rating": round(avg_rating, 2),
            "avg_reviews": avg_reviews,
            "max_reviews": max_reviews,
            "review_distribution": review_distribution,
            "prime_percentage": round(prime_count / len(competitors) * 100, 1),
            "has_best_seller": has_best_seller,
            "has_amazon_choice": has_amazon_choice,
            "competition_score": round(competition_score, 1),
            "opportunity_score": round(opportunity_score, 1),
            "suggested_price_min": round(suggested_min, 2),
            "suggested_price_max": round(suggested_max, 2),
        }

    def analyze_enhanced(
        self,
        competitors: list[dict],
        product_name: str,
        alibaba_cost: Optional[float] = None,
    ) -> dict:
        """Run full analysis including ML-powered match scoring, pricing, and demand.

        Extends the base ``analyze()`` output with match scores, pricing
        strategies, and demand estimates.

        Parameters
        ----------
        competitors : list[dict]
            Competitor dicts from ``AmazonSearchService.search_products()``.
        product_name : str
            The source product name (e.g. Alibaba title) used for relevance scoring.
        alibaba_cost : float | None
            Optional unit cost for margin calculations.

        Returns
        -------
        dict  with all keys from ``analyze()`` plus:
            - match_scores: list of competitors with ``match_score`` added
            - pricing_strategies: pricing recommendation dict
            - demand_estimates: market demand estimation dict
        """
        # Base analysis (unchanged)
        result = self.analyze(competitors)

        # Work on a copy to avoid mutating the caller's list
        scored_competitors = [dict(c) for c in competitors]

        # ML services
        match_scores = score_matches(product_name, scored_competitors)
        pricing_strategies = recommend_pricing(competitors, alibaba_cost)
        demand_estimates = estimate_demand(competitors)

        result["match_scores"] = match_scores
        result["pricing_strategies"] = pricing_strategies
        result["demand_estimates"] = demand_estimates

        return result

    # ------------------------------------------------------------------
    # Internal scoring helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _competition_score(
        *,
        competitors: list[dict],
        reviews: list[int],
        ratings: list[float],
        has_best_seller: bool,
        has_amazon_choice: bool,
    ) -> float:
        """Compute a 0-100 competition score (higher = more competitive)."""
        total = len(competitors)
        if total == 0:
            return 0.0

        # Factor 1: Fraction of listings with 500+ reviews (0-40 pts)
        established = sum(1 for r in reviews if r >= 500)
        f1 = (established / total) * 40

        # Factor 2: Fraction of listings with 4+ star rating (0-25 pts)
        high_rated = sum(1 for r in ratings if r >= 4.0)
        f2 = (high_rated / max(len(ratings), 1)) * 25

        # Factor 3: Badge presence (0-15 pts)
        f3 = 0.0
        if has_best_seller:
            f3 += 10
        if has_amazon_choice:
            f3 += 5

        # Factor 4: Overall review maturity via max reviews (0-20 pts)
        max_rev = max(reviews) if reviews else 0
        if max_rev >= 10000:
            f4 = 20.0
        elif max_rev >= 5000:
            f4 = 15.0
        elif max_rev >= 1000:
            f4 = 10.0
        elif max_rev >= 500:
            f4 = 5.0
        else:
            f4 = 0.0

        return min(f1 + f2 + f3 + f4, 100.0)

    @staticmethod
    def _opportunity_score(
        *,
        competition_score: float,
        avg_reviews: int,
        bought_count: int,
        total: int,
        prices: list[float],
    ) -> float:
        """Compute a 0-100 opportunity score (higher = better opportunity)."""
        if total == 0:
            return 0.0

        # Start from inverse of competition
        base = 100 - competition_score  # 0-100

        # Demand signal: products with "bought last month" data (+0-15)
        demand_ratio = bought_count / total
        demand_bonus = demand_ratio * 15

        # Growing-market bonus: moderate avg reviews (50-500) = sweet spot (+0-15)
        if 50 <= avg_reviews <= 500:
            maturity_bonus = 15.0
        elif avg_reviews < 50:
            maturity_bonus = 10.0  # very new market, risky but possible
        elif avg_reviews <= 2000:
            maturity_bonus = 5.0
        else:
            maturity_bonus = 0.0

        # Price spread bonus: wide spread = room for positioning (+0-10)
        if len(prices) >= 2:
            spread = max(prices) - min(prices)
            mean_p = statistics.mean(prices) if prices else 1
            coeff = spread / mean_p if mean_p > 0 else 0
            spread_bonus = min(coeff * 10, 10.0)
        else:
            spread_bonus = 0.0

        raw = base * 0.6 + demand_bonus + maturity_bonus + spread_bonus
        return max(0.0, min(raw, 100.0))

    @staticmethod
    def _review_distribution(reviews: list[int]) -> dict:
        dist = {"under_50": 0, "50_to_500": 0, "500_to_5000": 0, "over_5000": 0}
        for r in reviews:
            if r < 50:
                dist["under_50"] += 1
            elif r < 500:
                dist["50_to_500"] += 1
            elif r < 5000:
                dist["500_to_5000"] += 1
            else:
                dist["over_5000"] += 1
        return dist

    @staticmethod
    def _percentile_range(prices: list[float]) -> tuple[float, float]:
        """Return 25th and 75th percentile of prices."""
        if not prices:
            return (0.0, 0.0)
        sorted_p = sorted(prices)
        n = len(sorted_p)
        q25_idx = max(int(n * 0.25) - 1, 0)
        q75_idx = min(int(n * 0.75), n - 1)
        return (sorted_p[q25_idx], sorted_p[q75_idx])

    @staticmethod
    def _empty_result() -> dict:
        return {
            "total_competitors": 0,
            "price_min": 0.0,
            "price_max": 0.0,
            "price_median": 0.0,
            "price_mean": 0.0,
            "avg_rating": 0.0,
            "avg_reviews": 0,
            "max_reviews": 0,
            "review_distribution": {
                "under_50": 0,
                "50_to_500": 0,
                "500_to_5000": 0,
                "over_5000": 0,
            },
            "prime_percentage": 0.0,
            "has_best_seller": False,
            "has_amazon_choice": False,
            "competition_score": 0.0,
            "opportunity_score": 0.0,
            "suggested_price_min": 0.0,
            "suggested_price_max": 0.0,
        }
