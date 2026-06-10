from dataclasses import dataclass
from enum import StrEnum

import util

WEEB_VERSION = "0.0.1"


class WeebOutputFormat(StrEnum):
    PDF = "PDF"
    PDF_PER_CHAPTER = "PDF per chapter"
    CBZ = "CBZ"
    CBZ_PER_CHAPTER = "CBZ per chapter"
    IMAGES = "Images"


class WeebSeriesStatus(StrEnum):
    ONGOING = "Ongoing"
    COMPLETE = "Complete"
    HIATUS = "Hiatus"
    CANCELED = "Canceled"


@dataclass
class WeebSeriesMetadata:
    title: str
    title_sanitized: str
    status: WeebSeriesStatus


@dataclass
class WeebChapter:
    id: str  # used in URL (e.g. '01J76XZ3VG696B7Y02NABJ0XA3')
    num: str  # as listed on weeb central (e.g. '1', '2.5')


@dataclass
class WeebSettings:
    download_dir: str
    output_format: WeebOutputFormat = WeebOutputFormat.PDF
    notify_on_completion: bool = False


@dataclass
class LogMessage:
    text: str


@dataclass
class ErrorMessage:
    text: str


@dataclass
class SelectionConfirmationMessage:
    num_chapters: int
    num_chapters_recommended: int
    series_title: str


@dataclass
class DownloadProgressMessage:
    chapters_downloaded: int
    total_chapters: int


@dataclass
class CompletionMessage:
    title: str
