import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from platformdirs import user_config_path, user_downloads_dir

from data import WeebSettings

APP_NAME = "weeb-dl"
SETTINGS_FILE = "settings.json"


class WeebSettingsManager:
    def __init__(self):
        self.config_dir_path = user_config_path(appname=APP_NAME, ensure_exists=True)
        self.config_file_path = Path(self.config_dir_path, SETTINGS_FILE)
        self.settings = WeebSettings(download_dir=user_downloads_dir())

    def load(self, error_message_fn: Callable[[str], None]) -> WeebSettings:

        if self.config_file_path.exists():
            try:
                data = json.loads(self.config_file_path.read_text(encoding="utf-8"))
                self.settings = WeebSettings(**data)
            except Exception as e:
                error_message_fn(f"Error: Cannot load settings '{e}'")

        return self.settings

    def save(self, error_message_fn: Callable[[str], None]):
        try:
            data = asdict(self.settings)
            self.config_file_path.write_text(json.dumps(data), encoding="utf-8")
        except Exception as e:
            error_message_fn(f"Error: Cannot write settings '{e}'")
