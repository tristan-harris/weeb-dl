from dataclasses import dataclass
from enum import StrEnum


class WeebOutputFormat(StrEnum):
    PDF = "PDF"
    PDF_PER_CHAPTER = "PDF per chapter"
    CBZ = "CBZ"
    CB7 = "CB7"
    IMAGES = "Images"


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
class DownloadProgressMessage:
    chapters_downloaded: int
    total_chapters: int


@dataclass
class CompletionMessage:
    pass
