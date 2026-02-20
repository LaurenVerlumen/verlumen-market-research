"""Progress tracker component for long-running batch operations."""
from nicegui import ui


class ProgressTracker:
    """Displays a progress bar with status text for batch operations."""

    def __init__(self, total: int = 0, label: str = "Processing..."):
        self.total = total
        self.current = 0
        self._container = ui.column().classes("w-full gap-2")
        with self._container:
            self._label = ui.label(label).classes("text-body2")
            self._progress = ui.linear_progress(value=0, show_value=False).classes("w-full")
            self._detail = ui.label("").classes("text-caption text-secondary")

    def update(self, current: int, detail: str = ""):
        """Update the progress bar."""
        self.current = current
        fraction = current / self.total if self.total > 0 else 0
        self._progress.set_value(fraction)
        self._label.set_text(f"Processing {current} / {self.total}")
        if detail:
            self._detail.set_text(detail)

    def complete(self, message: str = "Done!"):
        """Mark operation as complete."""
        self._progress.set_value(1.0)
        self._label.set_text(message)
        self._detail.set_text("")

    def set_total(self, total: int):
        """Reset the total count (e.g. after loading data)."""
        self.total = total
        self.current = 0
        self._progress.set_value(0)

    def set_error(self, message: str):
        """Show an error state."""
        self._label.set_text(message)
        self._label.classes(add="text-negative")
