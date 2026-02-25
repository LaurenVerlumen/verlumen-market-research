"""Amazon competitor data table component."""
import json

from nicegui import ui

from src.services.utils import parse_bought

# localStorage keys for persistent table settings
_COL_ORDER_KEY = "comp_table_col_order"
_SORT_KEY = "comp_table_sort"
_VIS_COLS_KEY = "comp_table_visible_cols"
_COL_WIDTHS_KEY = "comp_table_col_widths"

# Columns that are always visible and not toggleable
_ALWAYS_VISIBLE = {"actions", "position"}

# Column group presets (column names -> user-friendly group labels)
_COL_GROUPS = {
    "Core": ["title", "asin", "price", "rating", "review_count"],
    "Revenue": ["bought_last_month", "est_revenue", "monthly_sales", "monthly_revenue"],
    "Seller": ["brand", "seller", "fulfillment", "fba_fees"],
}


COLUMNS = [
    {"name": "actions", "label": "", "field": "actions", "align": "center", "sortable": False},
    {"name": "position", "label": "#", "field": "position", "sortable": True, "align": "center"},
    {"name": "trend", "label": "Trend", "field": "trend_status", "align": "center", "sortable": True},
    {"name": "match_score", "label": "Relevance", "field": "match_score_raw", "sortable": True, "align": "center"},
    {"name": "title", "label": "Title", "field": "title", "sortable": True, "align": "left"},
    {"name": "asin", "label": "ASIN", "field": "asin", "sortable": True, "align": "left"},
    {"name": "brand", "label": "Brand", "field": "brand", "sortable": True, "align": "left"},
    {"name": "price", "label": "Price", "field": "price_raw", "sortable": True, "align": "right"},
    {"name": "rating", "label": "Rating", "field": "rating_raw", "sortable": True, "align": "center"},
    {"name": "review_count", "label": "Reviews", "field": "review_count_raw", "sortable": True, "align": "right"},
    {"name": "bought_last_month", "label": "Bought/Mo", "field": "bought_raw", "sortable": True, "align": "right"},
    {"name": "est_revenue", "label": "Est. Rev/Mo", "field": "est_revenue_raw", "sortable": True, "align": "right"},
    {"name": "monthly_sales", "label": "H10 Sales", "field": "monthly_sales_raw", "sortable": True, "align": "right"},
    {"name": "monthly_revenue", "label": "H10 Revenue", "field": "monthly_revenue_raw", "sortable": True, "align": "right"},
    {"name": "seller", "label": "Seller", "field": "seller", "sortable": True, "align": "left"},
    {"name": "fulfillment", "label": "FBA/FBM", "field": "fulfillment", "sortable": True, "align": "center"},
    {"name": "fba_fees", "label": "Fees", "field": "fba_fees_raw", "sortable": True, "align": "right"},
    {"name": "is_prime", "label": "Prime", "field": "is_prime", "align": "center"},
    {"name": "badge", "label": "Badge", "field": "badge", "align": "left"},
]

# Read-only columns: no actions column
COLUMNS_READONLY = [c for c in COLUMNS if c["name"] != "actions"]

# All toggleable column names (excludes always-visible)
_TOGGLEABLE_COLS = [c["name"] for c in COLUMNS if c["name"] not in _ALWAYS_VISIBLE]

# Default column widths in pixels (used for table-layout:fixed initial sizing)
_DEFAULT_COL_WIDTHS = {
    "actions": 48, "position": 50, "trend": 70,
    "match_score": 85, "title": 280, "asin": 120, "brand": 110,
    "price": 80, "rating": 70, "review_count": 85,
    "bought_last_month": 95, "est_revenue": 105,
    "monthly_sales": 95, "monthly_revenue": 110,
    "seller": 120, "fulfillment": 75, "fba_fees": 70,
    "is_prime": 60, "badge": 100,
}


def competitor_table(
    competitors: list[dict],
    title: str = "Amazon Competitors",
    on_delete=None,
    on_bulk_delete=None,
    on_score_change=None,
    on_review_toggle=None,
    on_field_change=None,
    pagination_state: dict | None = None,
    on_pagination_change=None,
    trend_data: dict | None = None,
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
    on_field_change : callable or None
        If provided, makes most columns inline-editable. Called with
        ``(asin: str, field_name: str, new_value)``.
    pagination_state : dict or None
        Saved pagination state (page, rowsPerPage, sortBy, descending) to
        restore after a refresh.  When *None* defaults are computed.
    on_pagination_change : callable or None
        If provided, called with the full pagination dict whenever the user
        changes page, rows-per-page, or sort settings.
    """
    all_rows = _prepare_rows(competitors, trend_data=trend_data)
    is_editable = on_delete or on_score_change
    # Deep-copy columns so we can attach per-instance width styles
    columns = [dict(c) for c in (COLUMNS if is_editable else COLUMNS_READONLY)]
    for _col in columns:
        _w = _DEFAULT_COL_WIDTHS.get(_col["name"], 100)
        _col["style"] = (
            f"width:{_w}px;min-width:{_w}px;"
            "overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
        )
        _col["headerStyle"] = f"width:{_w}px;min-width:{_w}px"

    # Track visible columns (all toggleable shown by default)
    visible_cols = list(_TOGGLEABLE_COLS)

    with ui.card().classes("w-full p-5"):
        # --- Row 1: Title bar ---
        with ui.row().classes("items-center gap-2 mb-1"):
            ui.icon("groups").classes("text-accent")
            ui.label(title).classes("text-subtitle1 font-bold")
            count_label = ui.label(f"({len(all_rows)})").classes("text-body2 text-secondary")

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

        # --- Toolbar (directly above table) ---
        with ui.row().classes("items-center gap-2 mb-2 flex-wrap"):

            def _apply_group(group_cols: list[str]):
                visible_cols.clear()
                visible_cols.extend(group_cols)
                for cb_name, cb_ref in _col_checkboxes.items():
                    cb_ref.value = cb_name in visible_cols
                _sync_visible_cols()

            # "Columns" button with dropdown menu for individual column toggles
            with ui.button("Columns", icon="view_column").props(
                "outline dense size=sm color=primary no-caps"
            ):
                with ui.menu().props("auto-close=false").classes("q-pa-sm"):
                    _col_checkboxes: dict = {}
                    _col_label_map = {c["name"]: c["label"] for c in COLUMNS}
                    for col_name in _TOGGLEABLE_COLS:
                        label_text = _col_label_map.get(col_name, col_name)

                        def _on_toggle(val, cn=col_name):
                            if val and cn not in visible_cols:
                                visible_cols.append(cn)
                            elif not val and cn in visible_cols:
                                visible_cols.remove(cn)
                            _sync_visible_cols()

                        cb = ui.checkbox(
                            label_text,
                            value=True,
                            on_change=lambda e, cn=col_name: _on_toggle(e.value, cn),
                        ).props("dense").classes("q-my-none")
                        _col_checkboxes[col_name] = cb

            # Group preset chips (inline in toolbar)
            ui.separator().props("vertical").classes("q-mx-xs")
            for gname, gcols in _COL_GROUPS.items():
                ui.button(
                    gname,
                    on_click=lambda g=gcols: _apply_group(g),
                ).props("outline dense size=sm color=primary no-caps")
            ui.button(
                "Full",
                on_click=lambda: _apply_group(list(_TOGGLEABLE_COLS)),
            ).props("outline dense size=sm color=positive no-caps")

            # Reset layout button
            ui.separator().props("vertical").classes("q-mx-xs")
            ui.button(
                "Reset layout", icon="restart_alt",
                on_click=lambda: _reset_table_layout(),
            ).props("outline dense size=sm color=grey-7 no-caps")

            # Bulk delete controls (pushed to the right)
            if on_bulk_delete:
                ui.space()
                sel_label = ui.label("").classes("text-body2 text-secondary")
                del_sel_btn = ui.button(
                    "Delete selected", icon="delete_sweep",
                ).props("color=negative outline size=sm")
                sel_label.set_visibility(False)
                del_sel_btn.set_visibility(False)

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

        # Apply initial visible-columns (all always-visible + all toggleable = everything)
        _all_vis = list(_ALWAYS_VISIBLE) + visible_cols
        table._props["visible-columns"] = _all_vis

        def _sync_visible_cols():
            """Update table visible-columns prop and persist to localStorage."""
            cols_to_show = list(_ALWAYS_VISIBLE) + visible_cols
            table._props["visible-columns"] = cols_to_show
            table.update()
            # Persist to localStorage
            ui.run_javascript(
                f"localStorage.setItem('{_VIS_COLS_KEY}', {json.dumps(json.dumps(visible_cols))})"
            )

        def _handle_pagination(e):
            if isinstance(e.args, dict):
                pag = e.args
                if on_pagination_change:
                    on_pagination_change(pag)
                # Persist sort settings to localStorage
                _sort_data = json.dumps({
                    "sortBy": pag.get("sortBy"),
                    "descending": pag.get("descending"),
                    "rowsPerPage": pag.get("rowsPerPage"),
                })
                ui.run_javascript(
                    f"localStorage.setItem('{_SORT_KEY}', {json.dumps(_sort_data)})"
                )

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

            filtered = []
            for r in all_rows:
                # Keyword filter
                if kw:
                    text = f"{r['title']} {r['asin']} {r['brand']} {r['seller']}".lower()
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

        # --- Trend indicator cell ---
        table.add_slot('body-cell-trend', r'''
            <q-td :props="props">
                <q-badge v-if="props.row.trend_status === 'new'" color="positive" label="NEW" />
                <q-badge v-else-if="props.row.trend_status === 'gone'" color="negative" label="GONE" />
                <span v-else-if="props.row.trend_price_delta != null && props.row.trend_price_delta < 0"
                      style="color:#2e7d32; font-weight:bold">
                    <q-icon name="arrow_downward" size="14px" />
                    ${{ Math.abs(props.row.trend_price_delta).toFixed(2) }}
                </span>
                <span v-else-if="props.row.trend_price_delta != null && props.row.trend_price_delta > 0"
                      style="color:#c62828; font-weight:bold">
                    <q-icon name="arrow_upward" size="14px" />
                    ${{ Math.abs(props.row.trend_price_delta).toFixed(2) }}
                </span>
                <span v-else style="color:#999">-</span>
            </q-td>
        ''')

        # --- Price cell ---
        if on_field_change:
            table.add_slot('body-cell-price', r'''
                <q-td :props="props">
                    <q-input
                        :model-value="props.row.price_raw != null ? props.row.price_raw : ''"
                        type="number"
                        step="0.01"
                        dense borderless
                        input-class="text-right"
                        style="width:80px; display:inline-block"
                        @change="val => $parent.$emit('fieldchange', {asin: props.row.asin, field: 'price', value: val})"
                    />
                </q-td>
            ''')
        else:
            table.add_slot('body-cell-price', r'''
                <q-td :props="props">
                    <span v-if="props.row.price_raw != null">
                        ${{ props.row.price_raw.toFixed(2) }}
                    </span>
                    <span v-else style="color:#999">-</span>
                </q-td>
            ''')

        # --- Brand cell ---
        if on_field_change:
            table.add_slot('body-cell-brand', r'''
                <q-td :props="props">
                    <q-input
                        :model-value="props.row.brand || ''"
                        type="text"
                        dense borderless
                        style="width:100px; display:inline-block"
                        @change="val => $parent.$emit('fieldchange', {asin: props.row.asin, field: 'brand', value: val})"
                    />
                </q-td>
            ''')

        # --- Seller cell ---
        if on_field_change:
            table.add_slot('body-cell-seller', r'''
                <q-td :props="props">
                    <q-input
                        :model-value="props.row.seller || ''"
                        type="text"
                        dense borderless
                        style="width:100px; display:inline-block"
                        @change="val => $parent.$emit('fieldchange', {asin: props.row.asin, field: 'seller', value: val})"
                    />
                </q-td>
            ''')

        # --- Fulfillment cell ---
        if on_field_change:
            table.add_slot('body-cell-fulfillment', r'''
                <q-td :props="props">
                    <q-input
                        :model-value="props.row.fulfillment || ''"
                        type="text"
                        dense borderless
                        style="width:70px; display:inline-block"
                        @change="val => $parent.$emit('fieldchange', {asin: props.row.asin, field: 'fulfillment', value: val})"
                    />
                </q-td>
            ''')

        # --- Rating cell ---
        if on_field_change:
            table.add_slot('body-cell-rating', r'''
                <q-td :props="props">
                    <q-input
                        :model-value="props.row.rating_raw != null ? props.row.rating_raw : ''"
                        type="number"
                        step="0.1"
                        max="5"
                        dense borderless
                        input-class="text-center"
                        style="width:60px; display:inline-block"
                        @change="val => $parent.$emit('fieldchange', {asin: props.row.asin, field: 'rating', value: val})"
                    />
                </q-td>
            ''')
        else:
            table.add_slot('body-cell-rating', r'''
                <q-td :props="props">
                    <span v-if="props.row.rating_raw != null">
                        {{ props.row.rating_raw.toFixed(1) }}
                    </span>
                    <span v-else style="color:#999">-</span>
                </q-td>
            ''')

        # --- Review count cell ---
        if on_field_change:
            table.add_slot('body-cell-review_count', r'''
                <q-td :props="props">
                    <q-input
                        :model-value="props.row.review_count_raw > 0 ? props.row.review_count_raw : ''"
                        type="number"
                        dense borderless
                        input-class="text-right"
                        style="width:70px; display:inline-block"
                        @change="val => $parent.$emit('fieldchange', {asin: props.row.asin, field: 'review_count', value: val})"
                    />
                </q-td>
            ''')
        else:
            table.add_slot('body-cell-review_count', r'''
                <q-td :props="props">
                    <span v-if="props.row.review_count_raw > 0">
                        {{ props.row.review_count_raw.toLocaleString() }}
                    </span>
                    <span v-else style="color:#999">-</span>
                </q-td>
            ''')

        # --- Bought/Mo cell ---
        if on_field_change:
            table.add_slot('body-cell-bought_last_month', r'''
                <q-td :props="props">
                    <q-input
                        :model-value="props.row.bought_last_month && props.row.bought_last_month !== '-' ? props.row.bought_last_month : ''"
                        type="text"
                        dense borderless
                        input-class="text-right"
                        style="width:80px; display:inline-block"
                        @change="val => $parent.$emit('fieldchange', {asin: props.row.asin, field: 'bought_last_month', value: val})"
                    />
                </q-td>
            ''')
        else:
            table.add_slot('body-cell-bought_last_month', r'''
                <q-td :props="props">
                    <span v-if="props.row.bought_last_month && props.row.bought_last_month !== '-'">
                        {{ props.row.bought_last_month }}
                    </span>
                    <span v-else style="color:#999">-</span>
                </q-td>
            ''')

        # --- Estimated Revenue/Mo cell (color-coded, read-only -- derived value) ---
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

        # --- H10 Sales cell ---
        if on_field_change:
            table.add_slot('body-cell-monthly_sales', r'''
                <q-td :props="props">
                    <q-input
                        :model-value="props.row.monthly_sales_raw > 0 ? props.row.monthly_sales_raw : ''"
                        type="number"
                        dense borderless
                        input-class="text-right"
                        style="width:80px; display:inline-block"
                        @change="val => $parent.$emit('fieldchange', {asin: props.row.asin, field: 'monthly_sales', value: val})"
                    />
                </q-td>
            ''')
        else:
            table.add_slot('body-cell-monthly_sales', r'''
                <q-td :props="props">
                    <span v-if="props.row.monthly_sales_raw > 0"
                          :style="{
                              color: props.row.monthly_sales_raw >= 500 ? '#2e7d32' :
                                     props.row.monthly_sales_raw >= 100 ? '#f57f17' : '#666',
                              fontWeight: props.row.monthly_sales_raw >= 100 ? 'bold' : 'normal'
                          }">
                        {{ props.row.monthly_sales_raw.toLocaleString() }}
                    </span>
                    <span v-else style="color:#999">-</span>
                </q-td>
            ''')

        # --- H10 Revenue cell ---
        if on_field_change:
            table.add_slot('body-cell-monthly_revenue', r'''
                <q-td :props="props">
                    <q-input
                        :model-value="props.row.monthly_revenue_raw > 0 ? props.row.monthly_revenue_raw : ''"
                        type="number"
                        dense borderless
                        input-class="text-right"
                        style="width:90px; display:inline-block"
                        @change="val => $parent.$emit('fieldchange', {asin: props.row.asin, field: 'monthly_revenue', value: val})"
                    />
                </q-td>
            ''')
        else:
            table.add_slot('body-cell-monthly_revenue', r'''
                <q-td :props="props">
                    <span v-if="props.row.monthly_revenue_raw > 0"
                          :style="{
                              color: props.row.monthly_revenue_raw >= 10000 ? '#2e7d32' :
                                     props.row.monthly_revenue_raw >= 3000 ? '#f57f17' : '#666',
                              fontWeight: props.row.monthly_revenue_raw >= 3000 ? 'bold' : 'normal'
                          }">
                        ${{ props.row.monthly_revenue_raw.toLocaleString(undefined, {maximumFractionDigits: 0}) }}
                    </span>
                    <span v-else style="color:#999">-</span>
                </q-td>
            ''')

        # --- FBA Fees cell ---
        if on_field_change:
            table.add_slot('body-cell-fba_fees', r'''
                <q-td :props="props">
                    <q-input
                        :model-value="props.row.fba_fees_raw != null ? props.row.fba_fees_raw : ''"
                        type="number"
                        step="0.01"
                        dense borderless
                        input-class="text-right"
                        style="width:70px; display:inline-block"
                        @change="val => $parent.$emit('fieldchange', {asin: props.row.asin, field: 'fba_fees', value: val})"
                    />
                </q-td>
            ''')
        else:
            table.add_slot('body-cell-fba_fees', r'''
                <q-td :props="props">
                    <span v-if="props.row.fba_fees_raw != null">
                        ${{ props.row.fba_fees_raw.toFixed(2) }}
                    </span>
                    <span v-else style="color:#999">-</span>
                </q-td>
            ''')

        # --- Prime cell ---
        if on_field_change:
            table.add_slot('body-cell-is_prime', r'''
                <q-td :props="props">
                    <q-checkbox
                        :model-value="props.row.is_prime === 'Yes'"
                        @update:model-value="val => $parent.$emit('fieldchange', {asin: props.row.asin, field: 'is_prime', value: val})"
                        dense
                        style="width:40px"
                    />
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

        # --- Generic field-change handler for inline editing ---
        if on_field_change:
            # Map emitted field names → row dict keys for local update
            _FIELD_ROW_KEY = {
                "price": "price_raw",
                "brand": "brand",
                "seller": "seller",
                "fulfillment": "fulfillment",
                "rating": "rating_raw",
                "review_count": "review_count_raw",
                "bought_last_month": "bought_last_month",
                "monthly_sales": "monthly_sales_raw",
                "monthly_revenue": "monthly_revenue_raw",
                "fba_fees": "fba_fees_raw",
                "is_prime": "is_prime",
            }

            def _handle_field_change(e):
                data = e.args
                if not isinstance(data, dict):
                    return
                asin = data.get("asin", "")
                field = data.get("field", "")
                value = data.get("value")

                # Update local row data so the input retains the new value
                row_key = _FIELD_ROW_KEY.get(field)
                if row_key and asin:
                    for r in all_rows:
                        if r["asin"] == asin:
                            if field in ("price", "rating", "fba_fees"):
                                try:
                                    r[row_key] = float(value) if value not in (None, "") else None
                                except (ValueError, TypeError):
                                    pass
                            elif field in ("review_count", "monthly_sales", "monthly_revenue"):
                                try:
                                    r[row_key] = int(float(value)) if value not in (None, "") else 0
                                except (ValueError, TypeError):
                                    pass
                            elif field == "is_prime":
                                r[row_key] = "Yes" if value else "No"
                            elif field == "bought_last_month":
                                r[row_key] = str(value) if value else "-"
                                r["bought_raw"] = parse_bought(str(value)) if value else 0
                                # Recalculate est. revenue
                                p = r.get("price_raw")
                                b = r["bought_raw"]
                                r["est_revenue_raw"] = (p * b) if p and b else 0
                            else:
                                r[row_key] = value if value else "-"

                            # Recalc est. revenue when price changes
                            if field == "price":
                                b = r.get("bought_raw", 0)
                                p = r.get("price_raw")
                                r["est_revenue_raw"] = (p * b) if p and b else 0
                            break
                    table.rows = list(all_rows)
                    table.update()

                on_field_change(asin, field, value)

            table.on('fieldchange', _handle_field_change)

        # --- Drag-and-drop column reorder (Vue template — no window refs!) ---
        # Merge column's headerStyle with our grab-cursor / position styles
        # so that width definitions from Python aren't overridden.
        table.add_slot('header-cell', r'''
            <q-th :props="props"
                  :data-col="props.col.name"
                  draggable="true"
                  :style="'cursor:grab;user-select:none;position:relative;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;' + (props.col.headerStyle || '')"
                  @dragstart="e => {
                      e.dataTransfer.effectAllowed = 'move';
                      e.dataTransfer.setData('text/plain', props.col.name);
                      setTimeout(() => { e.target.style.opacity = '0.4' }, 0);
                  }"
                  @dragend="e => { e.target.style.opacity = '1' }"
                  @dragover.prevent
                  @dragenter="e => { e.target.style.background = '#E8E0D6' }"
                  @dragleave="e => { e.target.style.background = '' }"
                  @drop.prevent="e => {
                      e.target.style.background = '';
                      const from = e.dataTransfer.getData('text/plain');
                      if (from && from !== props.col.name)
                          $parent.$emit('colreorder', {from: from, to: props.col.name});
                  }">
                {{ props.col.label }}
            </q-th>
        ''')

        def _handle_col_reorder(e):
            data = e.args
            if not isinstance(data, dict):
                return
            from_col = data.get("from", "")
            to_col = data.get("to", "")
            if not from_col or not to_col or from_col == to_col:
                return
            cols = list(table._props.get("columns", []))
            names = [c["name"] for c in cols]
            if from_col not in names or to_col not in names:
                return
            from_idx = names.index(from_col)
            to_idx = names.index(to_col)
            col = cols.pop(from_idx)
            cols.insert(to_idx, col)
            table._props["columns"] = cols
            table.update()
            # Save column order to localStorage
            new_order = [c["name"] for c in cols]
            ui.run_javascript(
                f"localStorage.setItem('{_COL_ORDER_KEY}', {json.dumps(json.dumps(new_order))})"
            )

        table.on("colreorder", _handle_col_reorder)

        # --- Column resize: inject handles + event handlers via pure JS ---
        # (Cannot use window refs in Vue 3 sandboxed templates, so all
        #  resize logic lives in JS injected after the table renders.)
        _resize_js = r'''
(function() {
    /* ---- CSS (injected once) ---- */
    if (!document.getElementById("col-resize-css")) {
        var s = document.createElement("style");
        s.id = "col-resize-css";
        s.textContent = [
            ".col-resize-handle {",
            "  position:absolute; right:-3px; top:0; bottom:0;",
            "  width:7px; cursor:col-resize; z-index:10;",
            "  transition: background 0.15s;",
            "}",
            ".col-resize-handle:hover,",
            ".col-resize-handle.active {",
            "  background: rgba(160,137,104,0.5);",
            "}"
        ].join("\n");
        document.head.appendChild(s);
    }

    /* ---- Document-level mouse handlers (once) ---- */
    if (!window.__colResizeInit) {
        window.__colResizeInit = true;
        window.__colResizing = false;

        document.addEventListener("mousemove", function(e) {
            if (!window.__colResizing || !window.__resizeTh) return;
            e.preventDefault();
            var delta = e.clientX - window.__resizeStartX;
            var newW = Math.max(40, window.__resizeStartW + delta);
            window.__resizeTh.style.width = newW + "px";
            window.__resizeTh.style.minWidth = newW + "px";
        });

        document.addEventListener("mouseup", function() {
            if (!window.__colResizing) return;
            window.__colResizing = false;
            document.body.style.cursor = "";
            document.body.style.userSelect = "";
            if (window.__resizeHandle) {
                window.__resizeHandle.classList.remove("active");
                window.__resizeHandle = null;
            }
            /* Save all column widths & recalculate table width */
            var widths = {};
            var totalW = 0;
            var tableEl = null;
            document.querySelectorAll("th[data-col]").forEach(function(th) {
                var w = th.offsetWidth;
                widths[th.getAttribute("data-col")] = w;
                totalW += w;
                if (!tableEl) tableEl = th.closest("table");
            });
            if (tableEl) {
                var cw = (tableEl.parentElement || tableEl).clientWidth || 800;
                tableEl.style.width = Math.max(totalW, cw) + "px";
            }
            localStorage.setItem("WIDTHS_KEY", JSON.stringify(widths));
            window.__resizeTh = null;
        });
    }

    /* ---- Core: attach handles & apply widths ---- */
    function attachHandles() {
        var ths = document.querySelectorAll("th[data-col]");
        if (ths.length === 0) return false;

        /* Set table-layout:fixed on the <table> element */
        var tableEl = ths[0].closest("table");
        if (tableEl) {
            tableEl.style.tableLayout = "fixed";
        }

        /* Load saved widths or use defaults */
        var saved = {};
        try { saved = JSON.parse(localStorage.getItem("WIDTHS_KEY") || "{}"); } catch(e) {}
        var defaults = DEFAULTS_JSON;

        /* Apply widths & calculate total */
        var totalW = 0;
        ths.forEach(function(th) {
            var col = th.getAttribute("data-col");
            var w = saved[col] || defaults[col] || 100;
            th.style.width = w + "px";
            th.style.minWidth = w + "px";
            totalW += w;
        });

        /* Set table width = sum of columns (min: container width) */
        if (tableEl) {
            var cw = (tableEl.parentElement || tableEl).clientWidth || 800;
            tableEl.style.width = Math.max(totalW, cw) + "px";
        }

        /* Inject resize-handle divs on headers that don't have one yet */
        ths.forEach(function(th) {
            if (th.querySelector(".col-resize-handle")) return;
            th.style.position = "relative";
            var handle = document.createElement("div");
            handle.className = "col-resize-handle";
            handle.draggable = false;
            handle.addEventListener("mousedown", function(e) {
                e.stopPropagation();
                e.preventDefault();
                window.__colResizing = true;
                window.__resizeTh = th;
                window.__resizeHandle = handle;
                handle.classList.add("active");
                window.__resizeStartX = e.clientX;
                window.__resizeStartW = th.offsetWidth;
                document.body.style.cursor = "col-resize";
                document.body.style.userSelect = "none";
            });
            th.appendChild(handle);
        });

        return true;
    }

    /* ---- Retry until table headers are in the DOM ---- */
    var _att = 0;
    function tryAttach() {
        if (attachHandles()) return;
        if (++_att < 20) setTimeout(tryAttach, 300);
    }
    tryAttach();

    /* ---- MutationObserver: re-attach after Quasar re-renders ---- */
    var _debounce = null;
    var obs = new MutationObserver(function() {
        if (_debounce) clearTimeout(_debounce);
        _debounce = setTimeout(function() {
            var ths = document.querySelectorAll("th[data-col]");
            var need = false;
            ths.forEach(function(th) {
                if (!th.querySelector(".col-resize-handle")) need = true;
            });
            if (need && ths.length > 0) attachHandles();
        }, 250);
    });
    var root = document.querySelector(".q-table__container") || document.body;
    obs.observe(root, { childList: true, subtree: true });
})();
        '''.replace('WIDTHS_KEY', _COL_WIDTHS_KEY).replace(
            'DEFAULTS_JSON', json.dumps(_DEFAULT_COL_WIDTHS),
        )
        # Inject after a short delay; the JS itself retries up to 6 seconds
        ui.timer(0.3, lambda: ui.run_javascript(_resize_js), once=True)

        # --- Reset layout helper (column order, widths, visibility) ---
        def _reset_table_layout():
            visible_cols.clear()
            visible_cols.extend(list(_TOGGLEABLE_COLS))
            for cb_name, cb_ref in _col_checkboxes.items():
                cb_ref.value = True
            table._props["columns"] = list(columns)
            _sync_visible_cols()
            _djs = json.dumps(_DEFAULT_COL_WIDTHS)
            ui.run_javascript(
                'localStorage.removeItem("' + _COL_ORDER_KEY + '");'
                'localStorage.removeItem("' + _COL_WIDTHS_KEY + '");'
                'localStorage.removeItem("' + _SORT_KEY + '");'
                'localStorage.removeItem("' + _VIS_COLS_KEY + '");'
                'var d=' + _djs + ';var tot=0;'
                'document.querySelectorAll("th[data-col]").forEach(function(t){'
                'var c=t.getAttribute("data-col"),w=d[c]||100;'
                't.style.width=w+"px";t.style.minWidth=w+"px";tot+=w;'
                '});'
                'var tb=document.querySelector("table");'
                'if(tb){var cw=tb.parentElement?tb.parentElement.clientWidth:800;'
                'tb.style.width=Math.max(tot,cw)+"px";}'
            )

        # --- Restore saved column order and sort from localStorage ---
        async def _restore_table_settings():
            # Restore column order
            col_json = await ui.run_javascript(
                f"return localStorage.getItem('{_COL_ORDER_KEY}')", timeout=2
            )
            if col_json:
                try:
                    order = json.loads(col_json)
                    if isinstance(order, list) and order:
                        col_map = {c["name"]: c for c in table._props.get("columns", [])}
                        reordered = []
                        for name in order:
                            if name in col_map:
                                reordered.append(col_map.pop(name))
                        reordered.extend(col_map.values())
                        if reordered:
                            table._props["columns"] = reordered
                except (json.JSONDecodeError, TypeError):
                    pass

            # Restore sort/pagination settings
            sort_json = await ui.run_javascript(
                f"return localStorage.getItem('{_SORT_KEY}')", timeout=2
            )
            if sort_json:
                try:
                    sort_data = json.loads(sort_json)
                    if isinstance(sort_data, dict):
                        current_pag = dict(table._props.get("pagination", {}))
                        current_pag.update(sort_data)
                        table._props["pagination"] = current_pag
                except (json.JSONDecodeError, TypeError):
                    pass

            # Restore visible columns
            vis_json = await ui.run_javascript(
                f"return localStorage.getItem('{_VIS_COLS_KEY}')", timeout=2
            )
            if vis_json:
                try:
                    saved_cols = json.loads(vis_json)
                    if isinstance(saved_cols, list):
                        # Only keep names that are valid toggleable columns
                        valid = [c for c in saved_cols if c in _TOGGLEABLE_COLS]
                        visible_cols.clear()
                        visible_cols.extend(valid)
                        # Update checkbox states
                        for cb_name, cb_ref in _col_checkboxes.items():
                            cb_ref.value = cb_name in visible_cols
                        # Update table prop
                        cols_to_show = list(_ALWAYS_VISIBLE) + visible_cols
                        table._props["visible-columns"] = cols_to_show
                except (json.JSONDecodeError, TypeError):
                    pass

            table.update()

        ui.timer(0.3, _restore_table_settings, once=True)


def _prepare_rows(competitors: list[dict], trend_data: dict | None = None) -> list[dict]:
    rows = []
    comp_trends = (trend_data or {}).get("competitor_trends", {})
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

        # Xray / Helium 10 fields
        monthly_sales = c.get("monthly_sales")
        monthly_revenue = c.get("monthly_revenue")
        fba_fees = c.get("fba_fees")

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
            "monthly_sales_raw": monthly_sales if monthly_sales is not None else 0,
            "monthly_revenue_raw": monthly_revenue if monthly_revenue is not None else 0,
            "seller": c.get("seller") or "-",
            "fulfillment": c.get("fulfillment") or "-",
            "fba_fees_raw": fba_fees,
            "is_prime": "Yes" if c.get("is_prime") else "No",
            "badge": c.get("badge") or "-",
            "amazon_url": c.get("amazon_url", ""),
            "thumbnail_url": c.get("thumbnail_url", ""),
            "reviewed": "Yes" if reviewed else "",
            "reviewed_raw": bool(reviewed),
            "trend_status": comp_trends.get(c.get("asin", ""), {}).get("status", "stable"),
            "trend_price_delta": comp_trends.get(c.get("asin", ""), {}).get("price_delta"),
            "trend_rating_delta": comp_trends.get(c.get("asin", ""), {}).get("rating_delta"),
        })
    return rows


def _truncate(text: str, length: int) -> str:
    if len(text) <= length:
        return text
    return text[: length - 3] + "..."
