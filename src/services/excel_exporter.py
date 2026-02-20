"""Export research data to a multi-sheet Excel workbook."""
import logging
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill, numbers
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)

# Style constants
_HEADER_FONT = Font(bold=True, size=11)
_HEADER_FILL = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
_GREEN_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
_YELLOW_FILL = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
_RED_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
_GREEN_FONT = Font(color="006100")
_YELLOW_FONT = Font(color="9C5700")
_RED_FONT = Font(color="9C0006")


class ExcelExporter:
    """Export enriched research data to a formatted .xlsx file."""

    def export(self, products_data: list[dict], output_path: str) -> str:
        """Export research data to an Excel workbook.

        Parameters
        ----------
        products_data : list[dict]
            Each dict should contain: category, name, alibaba_url,
            alibaba_price_min, alibaba_price_max, analysis (dict),
            competitors (list[dict]).
        output_path : str
            Destination file path for the .xlsx file.

        Returns
        -------
        str  The absolute path of the created file.
        """
        wb = Workbook()

        # Sheet 1 -- Summary
        ws_summary = wb.active
        ws_summary.title = "Summary"
        self._build_summary_sheet(ws_summary, products_data)

        # Sheet 2 -- Detailed Competitors
        ws_detail = wb.create_sheet("Detailed Competitors")
        self._build_detail_sheet(ws_detail, products_data)

        # Sheet 3 -- Category Analysis
        ws_cat = wb.create_sheet("Category Analysis")
        self._build_category_sheet(ws_cat, products_data)

        # Save
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        wb.save(output_path)
        logger.info("Excel exported to %s", output_path)
        return str(Path(output_path).resolve())

    # ------------------------------------------------------------------
    # Sheet builders
    # ------------------------------------------------------------------

    def _build_summary_sheet(self, ws: Any, products: list[dict]) -> None:
        headers = [
            "Category",
            "Product Name",
            "Alibaba URL",
            "Alibaba Price Range",
            "Amazon Avg Price",
            "Amazon Median Price",
            "# Competitors",
            "Avg Rating",
            "Avg Reviews",
            "Competition Score",
            "Opportunity Score",
            "Suggested Price Range",
        ]
        self._write_header_row(ws, headers)

        for row_idx, p in enumerate(products, start=2):
            a: dict = p.get("analysis") or {}
            alibaba_price = self._format_alibaba_price(
                p.get("alibaba_price_min"), p.get("alibaba_price_max")
            )
            suggested = self._format_price_range(
                a.get("suggested_price_min"), a.get("suggested_price_max")
            )
            ws.cell(row=row_idx, column=1, value=p.get("category", ""))
            ws.cell(row=row_idx, column=2, value=p.get("name", ""))
            ws.cell(row=row_idx, column=3, value=p.get("alibaba_url", ""))
            ws.cell(row=row_idx, column=4, value=alibaba_price)
            ws.cell(row=row_idx, column=5, value=a.get("price_mean", 0)).number_format = (
                numbers.FORMAT_NUMBER_COMMA_SEPARATED1
            )
            ws.cell(row=row_idx, column=6, value=a.get("price_median", 0)).number_format = (
                numbers.FORMAT_NUMBER_COMMA_SEPARATED1
            )
            ws.cell(row=row_idx, column=7, value=a.get("total_competitors", 0))
            ws.cell(row=row_idx, column=8, value=a.get("avg_rating", 0)).number_format = "0.0"
            ws.cell(row=row_idx, column=9, value=a.get("avg_reviews", 0))
            ws.cell(row=row_idx, column=10, value=a.get("competition_score", 0)).number_format = (
                "0.0"
            )
            ws.cell(row=row_idx, column=11, value=a.get("opportunity_score", 0)).number_format = (
                "0.0"
            )
            ws.cell(row=row_idx, column=12, value=suggested)

        # Conditional formatting on Opportunity Score (col 11)
        last_row = len(products) + 1
        if last_row >= 2:
            opp_range = f"K2:K{last_row}"
            ws.conditional_formatting.add(
                opp_range,
                CellIsRule(
                    operator="greaterThanOrEqual",
                    formula=["60"],
                    fill=_GREEN_FILL,
                    font=_GREEN_FONT,
                ),
            )
            ws.conditional_formatting.add(
                opp_range,
                CellIsRule(
                    operator="between",
                    formula=["30", "59.9"],
                    fill=_YELLOW_FILL,
                    font=_YELLOW_FONT,
                ),
            )
            ws.conditional_formatting.add(
                opp_range,
                CellIsRule(
                    operator="lessThan",
                    formula=["30"],
                    fill=_RED_FILL,
                    font=_RED_FONT,
                ),
            )

        self._auto_column_width(ws)

    def _build_detail_sheet(self, ws: Any, products: list[dict]) -> None:
        headers = [
            "Our Product",
            "Amazon ASIN",
            "Amazon Title",
            "Price",
            "Rating",
            "Reviews",
            "Bought Last Month",
            "Prime",
            "Badge",
            "Amazon URL",
        ]
        self._write_header_row(ws, headers)

        row = 2
        for p in products:
            name = p.get("name", "")
            for c in p.get("competitors", []):
                ws.cell(row=row, column=1, value=name)
                ws.cell(row=row, column=2, value=c.get("asin", ""))
                ws.cell(row=row, column=3, value=c.get("title", ""))
                price = c.get("price")
                cell_price = ws.cell(row=row, column=4, value=price if price is not None else "")
                if price is not None:
                    cell_price.number_format = numbers.FORMAT_NUMBER_COMMA_SEPARATED1
                ws.cell(row=row, column=5, value=c.get("rating", "")).number_format = "0.0"
                ws.cell(row=row, column=6, value=c.get("review_count", ""))
                ws.cell(row=row, column=7, value=c.get("bought_last_month", ""))
                ws.cell(row=row, column=8, value="Yes" if c.get("is_prime") else "No")
                ws.cell(row=row, column=9, value=c.get("badge", ""))
                ws.cell(row=row, column=10, value=c.get("amazon_url", ""))
                row += 1

        self._auto_column_width(ws)

    def _build_category_sheet(self, ws: Any, products: list[dict]) -> None:
        headers = [
            "Category",
            "Num Products",
            "Avg Competition Score",
            "Avg Opportunity Score",
            "Best Opportunity",
            "Avg Amazon Price",
        ]
        self._write_header_row(ws, headers)

        # Group products by category
        categories: dict[str, list[dict]] = {}
        for p in products:
            cat = p.get("category", "Uncategorized")
            categories.setdefault(cat, []).append(p)

        row = 2
        for cat, items in sorted(categories.items()):
            comp_scores = [
                i.get("analysis", {}).get("competition_score", 0) for i in items
            ]
            opp_scores = [
                i.get("analysis", {}).get("opportunity_score", 0) for i in items
            ]
            avg_prices = [
                i.get("analysis", {}).get("price_mean", 0) for i in items
            ]

            best_item = max(items, key=lambda x: x.get("analysis", {}).get("opportunity_score", 0))

            avg_comp = sum(comp_scores) / len(comp_scores) if comp_scores else 0
            avg_opp = sum(opp_scores) / len(opp_scores) if opp_scores else 0
            avg_price = sum(avg_prices) / len(avg_prices) if avg_prices else 0

            ws.cell(row=row, column=1, value=cat)
            ws.cell(row=row, column=2, value=len(items))
            ws.cell(row=row, column=3, value=round(avg_comp, 1)).number_format = "0.0"
            ws.cell(row=row, column=4, value=round(avg_opp, 1)).number_format = "0.0"
            ws.cell(row=row, column=5, value=best_item.get("name", ""))
            ws.cell(row=row, column=6, value=round(avg_price, 2)).number_format = (
                numbers.FORMAT_NUMBER_COMMA_SEPARATED1
            )
            row += 1

        # Conditional formatting on Avg Opportunity Score (col 4)
        last_row = row - 1
        if last_row >= 2:
            opp_range = f"D2:D{last_row}"
            ws.conditional_formatting.add(
                opp_range,
                CellIsRule(
                    operator="greaterThanOrEqual",
                    formula=["60"],
                    fill=_GREEN_FILL,
                    font=_GREEN_FONT,
                ),
            )
            ws.conditional_formatting.add(
                opp_range,
                CellIsRule(
                    operator="between",
                    formula=["30", "59.9"],
                    fill=_YELLOW_FILL,
                    font=_YELLOW_FONT,
                ),
            )
            ws.conditional_formatting.add(
                opp_range,
                CellIsRule(
                    operator="lessThan",
                    formula=["30"],
                    fill=_RED_FILL,
                    font=_RED_FONT,
                ),
            )

        self._auto_column_width(ws)

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _write_header_row(ws: Any, headers: list[str]) -> None:
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = _HEADER_FONT
            cell.fill = _HEADER_FILL
            cell.alignment = Alignment(horizontal="center")

    @staticmethod
    def _auto_column_width(ws: Any, min_width: int = 10, max_width: int = 50) -> None:
        for col_cells in ws.columns:
            max_len = min_width
            col_letter = get_column_letter(col_cells[0].column)
            for cell in col_cells:
                val = str(cell.value) if cell.value is not None else ""
                max_len = max(max_len, min(len(val) + 2, max_width))
            ws.column_dimensions[col_letter].width = max_len

    @staticmethod
    def _format_alibaba_price(pmin: Any, pmax: Any) -> str:
        if pmin is not None and pmax is not None:
            return f"${pmin:.2f} - ${pmax:.2f}"
        if pmin is not None:
            return f"${pmin:.2f}"
        if pmax is not None:
            return f"${pmax:.2f}"
        return ""

    @staticmethod
    def _format_price_range(pmin: Any, pmax: Any) -> str:
        if pmin and pmax:
            return f"${pmin:.2f} - ${pmax:.2f}"
        return ""
