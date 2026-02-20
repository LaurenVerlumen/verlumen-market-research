"""Amazon competitor data table component."""
from nicegui import ui

from src.services.utils import parse_bought


COLUMNS = [
    {"name": "actions", "label": "", "field": "actions", "align": "center", "sortable": False},
    {"name": "reviewed", "label": "Seen", "field": "reviewed", "sortable": True, "align": "center"},
    {"name": "position", "label": "#", "field": "position", "sortable": True, "align": "center"},
    {"name": "match_score", "label": "Relevance", "field": "match_score_raw", "sortable": True, "align": "center"},
    {"name": "title", "label": "Title", "field": "title", "sortable": True, "align": "left"},
    {"name": "asin", "label": "ASIN", "field": "asin", "sortable": True, "align": "left"},
    {"name": "brand", "label": "Brand", "field": "brand", "sortable": True, "align": "left"},
    {"name": "price", "label": "Price", "field": "price_raw", "sortable": True, "align": "right"},
    {"name": "rating", "label": "Rating", "field": "rating_raw", "sortable": True, "align": "center"},
    {"name": "review_count", "label": "Reviews", "field": "review_count_raw", "sortable": True, "align": "right"},
    {"name": "bought_last_month", "label": "Bought/Mo", "field": "bought_raw", "sortable": True, "align": "right"},
    {"name": "est_revenue", "label": "Est. Rev/Mo", "field": "est_revenue_raw", "sortable": True, "align": "right"},
    {"name": "is_prime", "label": "Prime", "field": "is_prime", "align": "center"},
    {"name": "badge", "label": "Badge", "field": "badge", "align": "left"},
]

# Read-only columns: no actions, no reviewed checkbox
COLUMNS_READONLY = [c for c in COLUMNS if c["name"] not in ("actions", "reviewed")]


def competitor_table(
    competitors: list[dict],
    title: str = "Amazon Competitors",
    on_delete=None,
    on_bulk_delete=None,
    on_score_change=None,
    on_review_toggle=None,
    pagination_state: dict | None = None,
    on_pagination_change=None,
):
    """Render a sortable, filterable data table of Amazon competitors.

    Parameters
    ----------
    competitors : list[dict]
        Competitor dicts (may include ``match_score``, ``reviewed``).
    title : str
        Card title.
    on_delete : callable or None
        If provided, adds a delete button per row. Called with ``asin`` (str).
    on_bulk_delete : callable or None
        If provided, enables multi-select with a "Delete selected" button.
        Called with a list of ASINs.
    on_score_change : callable or None
        If provided, makes the Relevance column editable. Called with
        ``(asin: str, new_score: float)``.
    on_review_toggle : callable or None
        If provided, adds a "Seen" checkbox per row. Called with
        ``(asin: str, checked: bool)``.
    pagination_state : dict or None
        Saved pagination state (page, rowsPerPage, sortBy, descending) to
        restore after a refresh.  When *None* defaults are computed.
    on_pagination_change : callable or None
        If provided, called with the full pagination dict whenever the user
        changes page, rows-per-page, or sort settings.
    """
    all_rows = _prepare_rows(competitors)
    is_editable = on_delete or on_score_change or on_review_toggle
    columns = COLUMNS if is_editable else COLUMNS_READONLY

    with ui.card().classes("w-full p-4"):
        with ui.row().classes("items-center gap-2 mb-2"):
            ui.label(title).classes("text-subtitle1 font-bold")
            count_label = ui.label(f"({len(all_rows)})").classes("text-body2 text-secondary")
            if on_bulk_delete:
                ui.space()
                sel_label = ui.label("").classes("text-body2 text-secondary")
                del_sel_btn = ui.button(
                    "Delete selected", icon="delete_sweep",
                ).props("color=negative outline size=sm")
                sel_label.set_visibility(False)
                del_sel_btn.set_visibility(False)

        if not all_rows:
            ui.label("No competitor data available.").classes("text-body2 text-secondary")
            return

        # --- Filter bar ---
        badges = sorted({r["badge"] for r in all_rows if r["badge"] != "-"})

        with ui.expansion("Filters", icon="filter_list").classes("w-full mb-2").props("dense"):
            with ui.row().classes("items-end gap-3 flex-wrap w-full py-2"):
                keyword_input = ui.input(
                    label="Search keywords",
                    placeholder="title, ASIN...",
                ).props("dense outlined clearable").classes("min-w-[200px]")

                price_min = ui.number(
                    label="Min price", format="%.2f",
                ).props("dense outlined").classes("w-28")
                price_max = ui.number(
                    label="Max price", format="%.2f",
                ).props("dense outlined").classes("w-28")

                relevance_min = ui.number(
                    label="Min relevance", value=0,
                ).props("dense outlined").classes("w-28")

                rating_min = ui.number(
                    label="Min rating",
                ).props("dense outlined").classes("w-28")

                prime_toggle = ui.checkbox("Prime only").classes("self-center")

                if on_review_toggle:
                    reviewed_select = ui.select(
                        options={"all": "All", "seen": "Seen only", "unseen": "Unseen only"},
                        value="all",
                        label="Reviewed",
                    ).props("dense outlined").classes("w-36")
                else:
                    reviewed_select = None

                if badges:
                    badge_select = ui.select(
                        options=badges,
                        label="Badge",
                        multiple=True,
                    ).props("dense outlined clearable").classes("min-w-[160px]")
                else:
                    badge_select = None

                ui.button("Clear filters", icon="clear_all", on_click=lambda: _clear_filters()).props(
                    "flat dense color=secondary size=sm"
                )

        # Default sort by match_score desc if scores are available, else position
        has_scores = any(r.get("match_score_raw", 0) > 0 for r in all_rows)
        default_sort = "match_score" if has_scores else "position"

        if pagination_state:
            pagination = dict(pagination_state)
        else:
            pagination = {"rowsPerPage": 15, "sortBy": default_sort, "descending": has_scores}

        table = ui.table(
            columns=columns,
            rows=all_rows,
            row_key="asin",
            pagination=pagination,
            selection="multiple" if on_bulk_delete else None,
        ).classes("w-full")
        table.props("flat bordered dense")

        if on_pagination_change:
            def _handle_pagination(e):
                if isinstance(e.args, dict):
                    on_pagination_change(e.args)

            table.on("update:pagination", _handle_pagination)

        if on_bulk_delete:
            def _on_selection_change():
                n = len(table.selected)
                sel_label.set_visibility(n > 0)
                del_sel_btn.set_visibility(n > 0)
                sel_label.text = f"{n} selected"

            table.on("selection", lambda e: _on_selection_change())

            def _handle_bulk_delete():
                asins = [r["asin"] for r in table.selected if r.get("asin")]
                if asins:
                    table.selected.clear()
                    on_bulk_delete(asins)

            del_sel_btn.on_click(_handle_bulk_delete)

        def _apply_filters():
            kw = (keyword_input.value or "").strip().lower()
            p_min = price_min.value
            p_max = price_max.value
            rel_min = relevance_min.value or 0
            rat_min = rating_min.value
            prime_only = prime_toggle.value
            sel_badges = (badge_select.value or []) if badge_select else []
            rev_filter = (reviewed_select.value or "all") if reviewed_select else "all"

            filtered = []
            for r in all_rows:
                # Keyword filter
                if kw:
                    text = f"{r['title']} {r['asin']} {r['brand']}".lower()
                    if not all(k in text for k in kw.split()):
                        continue
                # Price filter
                raw_price = r.get("price_raw")
                if p_min is not None and raw_price is not None and raw_price < p_min:
                    continue
                if p_min is not None and raw_price is None:
                    continue
                if p_max is not None and raw_price is not None and raw_price > p_max:
                    continue
                if p_max is not None and raw_price is None:
                    continue
                # Relevance filter
                if rel_min and r.get("match_score_raw", 0) < rel_min:
                    continue
                # Rating filter
                raw_rating = r.get("rating_raw")
                if rat_min is not None and raw_rating is not None and raw_rating < rat_min:
                    continue
                if rat_min is not None and raw_rating is None:
                    continue
                # Prime filter
                if prime_only and r.get("is_prime") != "Yes":
                    continue
                # Badge filter
                if sel_badges and r.get("badge", "-") not in sel_badges:
                    continue
                # Reviewed filter
                if rev_filter == "seen" and not r.get("reviewed_raw"):
                    continue
                if rev_filter == "unseen" and r.get("reviewed_raw"):
                    continue
                filtered.append(r)

            table.rows = filtered
            count_label.text = f"({len(filtered)} / {len(all_rows)})"
            table.update()

        def _clear_filters():
            keyword_input.value = ""
            price_min.value = None
            price_max.value = None
            relevance_min.value = 0
            rating_min.value = None
            prime_toggle.value = False
            if badge_select:
                badge_select.value = []
            if reviewed_select:
                reviewed_select.value = "all"
            table.rows = all_rows
            count_label.text = f"({len(all_rows)})"
            table.update()

        # Bind filter changes
        filter_ctrls = [keyword_input, price_min, price_max, relevance_min, rating_min]
        for ctrl in filter_ctrls:
            ctrl.on("update:model-value", lambda: _apply_filters())
        prime_toggle.on("update:model-value", lambda: _apply_filters())
        if badge_select:
            badge_select.on("update:model-value", lambda: _apply_filters())
        if reviewed_select:
            reviewed_select.on("update:model-value", lambda: _apply_filters())

        # --- Reviewed checkbox column ---
        if on_review_toggle:
            table.add_slot('body-cell-reviewed', r'''
                <q-td :props="props">
                    <q-checkbox
                        :model-value="props.row.reviewed_raw"
                        @update:model-value="val => $parent.$emit('review', {asin: props.row.asin, checked: val})"
                        dense
                        :color="props.row.reviewed_raw ? 'positive' : 'grey'"
                    />
                </q-td>
            ''')

            def _handle_review(e):
                data = e.args
                asin = data.get("asin", "") if isinstance(data, dict) else ""
                checked = data.get("checked", False) if isinstance(data, dict) else False
                if asin:
                    # Update local row state so the checkbox stays toggled
                    for r in all_rows:
                        if r["asin"] == asin:
                            r["reviewed_raw"] = checked
                            r["reviewed"] = "Yes" if checked else ""
                            break
                    # Reassign rows to force Vue reactivity (in-place mutation isn't detected)
                    table.rows = list(all_rows)
                    on_review_toggle(asin, checked)

            table.on("review", _handle_review)

        # --- Color-coded relevance cell ---
        if on_score_change:
            table.add_slot('body-cell-match_score', r'''
                <q-td :props="props">
                    <q-input
                        :model-value="props.row.match_score_raw || ''"
                        type="number"
                        dense borderless
                        input-class="text-center"
                        style="width:60px; display:inline-block"
                        :input-style="{
                            color: Number(props.row.match_score_raw) >= 60 ? '#2e7d32' :
                                   Number(props.row.match_score_raw) >= 30 ? '#f57f17' : '#c62828',
                            fontWeight: 'bold'
                        }"
                        @change="val => $parent.$emit('score', {asin: props.row.asin, score: val})"
                    />
                </q-td>
            ''')
        else:
            table.add_slot('body-cell-match_score', r'''
                <q-td :props="props">
                    <span v-if="props.row.match_score_raw > 0"
                          :style="{
                              color: props.row.match_score_raw >= 60 ? '#2e7d32' :
                                     props.row.match_score_raw >= 30 ? '#f57f17' : '#c62828',
                              fontWeight: 'bold'
                          }">
                        {{ Math.round(props.row.match_score_raw) }}
                    </span>
                    <span v-else style="color:#999">-</span>
                </q-td>
            ''')

        # --- Price cell (formatted from raw) ---
        table.add_slot('body-cell-price', r'''
            <q-td :props="props">
                <span v-if="props.row.price_raw != null">
                    ${{ props.row.price_raw.toFixed(2) }}
                </span>
                <span v-else style="color:#999">-</span>
            </q-td>
        ''')

        # --- Rating cell (formatted from raw) ---
        table.add_slot('body-cell-rating', r'''
            <q-td :props="props">
                <span v-if="props.row.rating_raw != null">
                    {{ props.row.rating_raw.toFixed(1) }}
                </span>
                <span v-else style="color:#999">-</span>
            </q-td>
        ''')

        # --- Review count cell (formatted from raw) ---
        table.add_slot('body-cell-review_count', r'''
            <q-td :props="props">
                <span v-if="props.row.review_count_raw > 0">
                    {{ props.row.review_count_raw.toLocaleString() }}
                </span>
                <span v-else style="color:#999">-</span>
            </q-td>
        ''')

        # --- Bought/Mo cell (display string, sorted by raw) ---
        table.add_slot('body-cell-bought_last_month', r'''
            <q-td :props="props">
                <span v-if="props.row.bought_last_month && props.row.bought_last_month !== '-'">
                    {{ props.row.bought_last_month }}
                </span>
                <span v-else style="color:#999">-</span>
            </q-td>
        ''')

        # --- Estimated Revenue/Mo cell (color-coded) ---
        table.add_slot('body-cell-est_revenue', r'''
            <q-td :props="props">
                <span v-if="props.row.est_revenue_raw > 0"
                      :style="{
                          color: props.row.est_revenue_raw >= 10000 ? '#2e7d32' :
                                 props.row.est_revenue_raw >= 3000 ? '#f57f17' : '#666',
                          fontWeight: props.row.est_revenue_raw >= 3000 ? 'bold' : 'normal'
                      }">
                    ${{ props.row.est_revenue_raw.toLocaleString(undefined, {maximumFractionDigits: 0}) }}
                </span>
                <span v-else style="color:#999">-</span>
            </q-td>
        ''')

        _thumb_html = r'''
            <q-avatar v-if="props.row.thumbnail_url" square size="36px" class="q-mr-sm cursor-pointer" style="flex-shrink:0">
                <img :src="props.row.thumbnail_url" style="object-fit:contain" />
                <q-tooltip anchor="center right" self="center left" :offset="[10, 0]"
                           class="bg-white shadow-4" style="padding:4px; border-radius:8px">
                    <img :src="props.row.thumbnail_url"
                         style="max-width:250px; max-height:250px; object-fit:contain; display:block" />
                </q-tooltip>
            </q-avatar>
        '''

        if on_review_toggle:
            # Title & ASIN links auto-mark as "Seen" on click
            table.add_slot('body-cell-title', r'''
                <q-td :props="props">
                    <div style="display:flex; align-items:center">
                        ''' + _thumb_html + r'''
                        <a v-if="props.row.amazon_url" :href="props.row.amazon_url" target="_blank"
                           class="text-primary" style="text-decoration:none"
                           @click="() => { if (!props.row.reviewed_raw) $parent.$emit('review', {asin: props.row.asin, checked: true}) }">
                            {{ props.row.title }} <q-icon name="open_in_new" size="12px" class="q-ml-xs" />
                        </a>
                        <span v-else>{{ props.row.title }}</span>
                    </div>
                </q-td>
            ''')
            table.add_slot('body-cell-asin', r'''
                <q-td :props="props">
                    <a :href="'https://amazon.com/dp/' + props.row.asin" target="_blank"
                       class="text-primary" style="text-decoration:none"
                       @click="() => { if (!props.row.reviewed_raw) $parent.$emit('review', {asin: props.row.asin, checked: true}) }">
                        {{ props.row.asin }} <q-icon name="open_in_new" size="12px" class="q-ml-xs" />
                    </a>
                </q-td>
            ''')
        else:
            table.add_slot('body-cell-title', r'''
                <q-td :props="props">
                    <div style="display:flex; align-items:center">
                        ''' + _thumb_html + r'''
                        <a v-if="props.row.amazon_url" :href="props.row.amazon_url" target="_blank"
                           class="text-primary" style="text-decoration:none">
                            {{ props.row.title }} <q-icon name="open_in_new" size="12px" class="q-ml-xs" />
                        </a>
                        <span v-else>{{ props.row.title }}</span>
                    </div>
                </q-td>
            ''')
            table.add_slot('body-cell-asin', r'''
                <q-td :props="props">
                    <a :href="'https://amazon.com/dp/' + props.row.asin" target="_blank"
                       class="text-primary" style="text-decoration:none">
                        {{ props.row.asin }} <q-icon name="open_in_new" size="12px" class="q-ml-xs" />
                    </a>
                </q-td>
            ''')

        # --- Delete button column (first column) ---
        if is_editable:
            if on_delete:
                table.add_slot('body-cell-actions', r'''
                    <q-td :props="props">
                        <q-btn flat dense round icon="close" color="negative" size="sm"
                               @click="() => $parent.$emit('delete', props.row)" />
                    </q-td>
                ''')
            else:
                table.add_slot('body-cell-actions', r'''
                    <q-td :props="props"></q-td>
                ''')

            if on_delete:
                def _handle_delete(e):
                    row = e.args
                    asin = row.get("asin", "")
                    if asin and on_delete:
                        on_delete(asin)

                table.on("delete", _handle_delete)

        if on_score_change:
            def _handle_score(e):
                data = e.args
                asin = data.get("asin", "") if isinstance(data, dict) else ""
                raw = data.get("score") if isinstance(data, dict) else None
                try:
                    score = max(0.0, min(100.0, float(raw)))
                except (TypeError, ValueError):
                    return
                if asin:
                    on_score_change(asin, score)

            table.on("score", _handle_score)


def _prepare_rows(competitors: list[dict]) -> list[dict]:
    rows = []
    for c in competitors:
        price = c.get("price")
        score = c.get("match_score")
        rating = c.get("rating")
        reviewed = c.get("reviewed", False)
        review_count = c.get("review_count")
        bought_str = c.get("bought_last_month") or ""
        bought_num = parse_bought(bought_str)

        # Estimated monthly revenue = price * units bought
        est_revenue = None
        if price is not None and bought_num is not None and bought_num > 0:
            est_revenue = price * bought_num

        rows.append({
            "position": c.get("position", 0),
            "match_score_raw": score or 0,
            "title": _truncate(c.get("title", ""), 80),
            "asin": c.get("asin", ""),
            "brand": c.get("brand") or "-",
            "price_raw": price,
            "rating_raw": rating,
            "review_count_raw": review_count if review_count is not None else 0,
            "bought_last_month": bought_str or "-",
            "bought_raw": bought_num or 0,
            "est_revenue_raw": est_revenue or 0,
            "is_prime": "Yes" if c.get("is_prime") else "No",
            "badge": c.get("badge") or "-",
            "amazon_url": c.get("amazon_url", ""),
            "thumbnail_url": c.get("thumbnail_url", ""),
            "reviewed": "Yes" if reviewed else "",
            "reviewed_raw": bool(reviewed),
        })
    return rows


def _truncate(text: str, length: int) -> str:
    if len(text) <= length:
        return text
    return text[: length - 3] + "..."
