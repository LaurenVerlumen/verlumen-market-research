"""Amazon competitor data table component."""
from nicegui import ui


COLUMNS = [
    {"name": "position", "label": "#", "field": "position", "sortable": True, "align": "center"},
    {"name": "match_score", "label": "Relevance", "field": "match_score", "sortable": True, "align": "center"},
    {"name": "title", "label": "Title", "field": "title", "sortable": True, "align": "left"},
    {"name": "asin", "label": "ASIN", "field": "asin", "sortable": True, "align": "left"},
    {"name": "price", "label": "Price", "field": "price", "sortable": True, "align": "right"},
    {"name": "rating", "label": "Rating", "field": "rating", "sortable": True, "align": "center"},
    {"name": "review_count", "label": "Reviews", "field": "review_count", "sortable": True, "align": "right"},
    {"name": "bought_last_month", "label": "Bought/Mo", "field": "bought_last_month", "align": "right"},
    {"name": "is_prime", "label": "Prime", "field": "is_prime", "align": "center"},
    {"name": "badge", "label": "Badge", "field": "badge", "align": "left"},
]


def competitor_table(
    competitors: list[dict],
    title: str = "Amazon Competitors",
    min_relevance: int = 0,
):
    """Render a sortable, filterable data table of Amazon competitors.

    Parameters
    ----------
    competitors : list[dict]
        Competitor dicts (may include ``match_score``).
    title : str
        Card title.
    min_relevance : int
        Hide competitors with match_score below this threshold (0-100).
    """
    # Filter by minimum relevance if scores are present
    if min_relevance > 0:
        competitors = [
            c for c in competitors
            if (c.get("match_score") or 0) >= min_relevance
        ]

    rows = _prepare_rows(competitors)

    with ui.card().classes("w-full p-4"):
        ui.label(title).classes("text-subtitle1 font-bold mb-2")
        if not rows:
            ui.label("No competitor data available.").classes("text-body2 text-secondary")
            return

        # Default sort by match_score desc if scores are available, else position
        has_scores = any(r.get("match_score_raw", 0) > 0 for r in rows)
        default_sort = "match_score" if has_scores else "position"

        table = ui.table(
            columns=COLUMNS,
            rows=rows,
            row_key="asin",
            pagination={"rowsPerPage": 15, "sortBy": default_sort, "descending": has_scores},
        ).classes("w-full")
        table.props("flat bordered dense")

        # Color-coded relevance cell: green >= 60, yellow 30-59, red < 30
        table.add_slot('body-cell-match_score', r'''
            <q-td :props="props">
                <span v-if="props.row.match_score_raw > 0"
                      :style="{
                          color: props.row.match_score_raw >= 60 ? '#2e7d32' :
                                 props.row.match_score_raw >= 30 ? '#f57f17' : '#c62828',
                          fontWeight: 'bold'
                      }">
                    {{ props.value }}
                </span>
                <span v-else style="color:#999">-</span>
            </q-td>
        ''')

        table.add_slot('body-cell-title', r'''
            <q-td :props="props">
                <a v-if="props.row.amazon_url" :href="props.row.amazon_url" target="_blank"
                   class="text-primary" style="text-decoration:none">
                    {{ props.value }} <q-icon name="open_in_new" size="12px" class="q-ml-xs" />
                </a>
                <span v-else>{{ props.value }}</span>
            </q-td>
        ''')

        table.add_slot('body-cell-asin', r'''
            <q-td :props="props">
                <a :href="'https://amazon.com/dp/' + props.value" target="_blank"
                   class="text-primary" style="text-decoration:none">
                    {{ props.value }} <q-icon name="open_in_new" size="12px" class="q-ml-xs" />
                </a>
            </q-td>
        ''')


def _prepare_rows(competitors: list[dict]) -> list[dict]:
    rows = []
    for c in competitors:
        price = c.get("price")
        score = c.get("match_score")
        rows.append({
            "position": c.get("position", 0),
            "match_score": f"{score:.0f}" if score is not None else "-",
            "match_score_raw": score or 0,
            "title": _truncate(c.get("title", ""), 80),
            "asin": c.get("asin", ""),
            "price": f"${price:.2f}" if price is not None else "-",
            "rating": f"{c['rating']:.1f}" if c.get("rating") is not None else "-",
            "review_count": c.get("review_count") if c.get("review_count") is not None else "-",
            "bought_last_month": c.get("bought_last_month") or "-",
            "is_prime": "Yes" if c.get("is_prime") else "No",
            "badge": c.get("badge") or "-",
            "amazon_url": c.get("amazon_url", ""),
        })
    return rows


def _truncate(text: str, length: int) -> str:
    if len(text) <= length:
        return text
    return text[: length - 3] + "..."
