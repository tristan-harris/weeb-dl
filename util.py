import json
import re
from pathlib import Path

import platformdirs
from notifypy import Notify

import data

SERIES_ID_REGEX = r"[A-Z0-9]{26}"
SERIES_URL_REGEX = r"(https://)?weebcentral.com/series/[A-Z0-9]{26}/.+"


def is_valid_series(series: str) -> bool:
    if re.match(f"^{SERIES_ID_REGEX}$", series):
        return True
    if re.match(SERIES_URL_REGEX, series):
        return True
    return False


def get_id_from_series_url(series_url: str) -> str:
    match = re.search(SERIES_ID_REGEX, series_url)
    if match:
        return match.group(0)
    return ""


def send_notification(title: str, message: str):
    notification = Notify()
    notification.title = title
    notification.message = message
    notification.send(block=False)


# e.g. (64, 4) -> 0064, (8.5, 4) -> 0008.5
def pad_num(num: str, required_length: int) -> str:
    decimal_point_string = ""
    decimal_point_index = num.find(".")

    if decimal_point_index != -1:
        decimal_point_string = num[decimal_point_index:]
        num = num[:decimal_point_index]

    return "0" * (required_length - len(num)) + num + decimal_point_string
