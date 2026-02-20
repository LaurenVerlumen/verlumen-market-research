"""Settings page - configure API keys and app preferences."""
import os

from nicegui import ui

from config import BASE_DIR, SERPAPI_KEY
from src.services import AmazonSearchService
from src.ui.layout import build_layout


ENV_FILE = BASE_DIR / ".env"


def settings_page():
    """Render the settings page."""
    content = build_layout()

    with content:
        ui.label("Settings").classes("text-h5 font-bold")

        # SerpAPI configuration
        with ui.card().classes("w-full p-4 mb-4"):
            ui.label("SerpAPI Configuration").classes("text-subtitle1 font-bold mb-2")
            ui.label(
                "Enter your SerpAPI key to enable Amazon product research. "
                "Get a key at serpapi.com."
            ).classes("text-body2 text-secondary mb-3")

            current_key = SERPAPI_KEY or ""
            masked = _mask_key(current_key) if current_key else "Not configured"

            with ui.row().classes("items-center gap-2 mb-3"):
                ui.label("Current key:").classes("text-body2 font-medium")
                status_label = ui.label(masked).classes("text-body2 text-secondary")

                if current_key:
                    ui.icon("check_circle").classes("text-positive")
                else:
                    ui.icon("warning").classes("text-warning")

            api_input = ui.input(
                label="SerpAPI Key",
                password=True,
                password_toggle_button=True,
                value="",
                placeholder="Paste your SerpAPI key here",
            ).classes("w-full mb-2")

            validation_label = ui.label("").classes("text-body2 mt-1")

            def save_key():
                new_key = api_input.value.strip()
                if not new_key:
                    ui.notify("Please enter a key.", type="warning")
                    return

                _update_env_file("SERPAPI_KEY", new_key)
                os.environ["SERPAPI_KEY"] = new_key

                status_label.text = _mask_key(new_key)
                api_input.value = ""
                ui.notify("API key saved! Restart the app for full effect.", type="positive")

            async def validate_key():
                key = api_input.value.strip() or current_key
                if not key:
                    validation_label.text = "No key to validate."
                    return
                validation_label.text = "Validating..."
                service = AmazonSearchService(api_key=key)
                valid = service.check_api_key()
                if valid:
                    validation_label.text = "Key is valid!"
                    validation_label.classes("text-positive", remove="text-negative")
                    remaining = service.get_remaining_searches()
                    if remaining is not None:
                        validation_label.text += f" ({remaining} searches remaining)"
                else:
                    validation_label.text = "Key is invalid or API is unreachable."
                    validation_label.classes("text-negative", remove="text-positive")

            with ui.row().classes("gap-2"):
                ui.button("Save Key", icon="save", on_click=save_key).props("color=primary")
                ui.button("Validate Key", icon="verified", on_click=validate_key).props("flat color=grey")

        # Database info
        with ui.card().classes("w-full p-4 mb-4"):
            ui.label("Database").classes("text-subtitle1 font-bold mb-2")
            from config import DB_PATH
            db_exists = DB_PATH.exists()
            db_size = DB_PATH.stat().st_size / 1024 if db_exists else 0

            with ui.row().classes("gap-6"):
                ui.label(f"Location: {DB_PATH}").classes("text-body2 text-secondary")
                ui.label(f"Size: {db_size:.1f} KB").classes("text-body2 text-secondary")

            def reset_db():
                from src.models import init_db
                init_db()
                ui.notify("Database tables recreated.", type="info")

            ui.button("Recreate Tables", icon="refresh", on_click=reset_db).props(
                "flat color=grey"
            ).classes("mt-2")

        # About
        with ui.card().classes("w-full p-4"):
            ui.label("About").classes("text-subtitle1 font-bold mb-2")
            ui.label("Verlumen Market Research Tool").classes("text-body2")
            ui.label(
                "Automates Amazon competition analysis for wood/Montessori toy products. "
                "Import products from Alibaba, search Amazon via SerpAPI, and export analysis reports."
            ).classes("text-body2 text-secondary")


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def _update_env_file(key: str, value: str):
    lines = []
    found = False

    if ENV_FILE.exists():
        lines = ENV_FILE.read_text().splitlines()

    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(new_lines) + "\n")
