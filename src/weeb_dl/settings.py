"""Used to store and retrieve persistent settings from a JSON file"""

import json
import queue
from dataclasses import asdict
from pathlib import Path

from platformdirs import user_config_path, user_downloads_dir

from .data import ErrorMessage, WeebSettings

APP_NAME = "weeb-dl"
SETTINGS_FILE = "settings.json"


class WeebSettingsManager:
    def __init__(self):
        self.config_dir_path = user_config_path(appname=APP_NAME, ensure_exists=True)
        self.config_file_path = Path(self.config_dir_path, SETTINGS_FILE)
        self.settings = WeebSettings(download_dir=user_downloads_dir())

    def load(self, message_queue: queue.SimpleQueue) -> WeebSettings:
        if self.config_file_path.exists():
            try:
                data = json.loads(self.config_file_path.read_text(encoding="utf-8"))
                self.settings = WeebSettings(**data)
            except Exception as e:
                message_queue.put(ErrorMessage(f"Error: Cannot load settings '{e}'"))

        return self.settings

    def save(self, message_queue: queue.SimpleQueue):
        try:
            data = asdict(self.settings)
            self.config_file_path.write_text(json.dumps(data), encoding="utf-8")
        except Exception as e:
            message_queue.put(ErrorMessage(f"Error: Cannot write settings '{e}'"))
