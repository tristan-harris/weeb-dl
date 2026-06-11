import platform
import re
from pathlib import Path

from notifypy import Notify

BASE_DIR = Path(__file__).resolve().parent

SERIES_ID_REGEX = r"[A-Z0-9]{26}"
SERIES_URL_REGEX = r"(https://)?weebcentral.com/series/[A-Z0-9]{26}/.+"

NUMBER_REGEX = r"\d+(\.\d+)?"

WINDOWS_ILLEGAL_FILENAME_CHARACTERS_REGEX = r'[<>:"/\\|?*\x00-\x1f]'


def is_valid_series(series: str) -> bool:
    if re.match(f"^{SERIES_ID_REGEX}$", series):
        return True
    if re.match(SERIES_URL_REGEX, series):
        return True
    return False


def get_id_from_series_url(series_url: str) -> str | None:
    match = re.search(SERIES_ID_REGEX, series_url)
    if match:
        return match.group(0)
    return None


def sanitize_series_title(title: str) -> str:
    if platform.system() == "Windows":
        title = re.sub(WINDOWS_ILLEGAL_FILENAME_CHARACTERS_REGEX, "", title)
    title = title.strip()
    return title


def send_notification(title: str, message: str):
    notification = Notify()
    notification.title = title
    notification.message = message
    notification.application_name = "weeb-dl"
    notification.icon = Path(BASE_DIR, "assets", "icon", "app_icon.png")
    notification.send(block=False)


def is_num(num: str) -> bool:
    """Returns whether number is positive integer or floating point value"""
    num_match = re.match(f"^{NUMBER_REGEX}$", num)
    return isinstance(num_match, re.Match)


def extract_num(text: str) -> str | None:
    """Extract positive integer or floating-point from string"""
    num_match = re.search(NUMBER_REGEX, text)
    if num_match:
        return num_match.group(0)


def pad_num(num: str, padding: int) -> str:
    """
    Pads numeric string with zeroes, ignores mantissa
    e.g. (64, 4) -> 0064, (8.5, 4) -> 0008.5
    """
    decimal_point_string = ""
    decimal_point_index = num.find(".")

    if decimal_point_index != -1:
        decimal_point_string = num[decimal_point_index:]
        num = num[:decimal_point_index]

    return f"{'0' * (padding - len(num))}{num}{decimal_point_string}"


def number_digits(num: int) -> int:
    """Returns number of digits in integer"""
    count = 0
    while num != 0:
        num //= 10
        count += 1
    return count
