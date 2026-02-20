"""Reusable statistics card component."""
from nicegui import ui


def stats_card(title: str, value: str, icon: str = "info", color: str = "primary"):
    """Render a small KPI / stats card."""
    with ui.card().classes("w-48 p-4"):
        with ui.row().classes("items-center gap-3 w-full"):
            ui.icon(icon).classes(f"text-{color} text-3xl")
            with ui.column().classes("gap-0"):
                ui.label(value).classes("text-h5 font-bold")
                ui.label(title).classes("text-caption text-secondary")
