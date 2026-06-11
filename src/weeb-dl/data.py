from dataclasses import dataclass
from enum import StrEnum

import util

WEEB_VERSION = "1.0"


class WeebOutputFormat(StrEnum):
    PDF = "PDF"
    PDF_PER_CHAPTER = "PDF per chapter"
    CBZ = "CBZ"
    CBZ_PER_CHAPTER = "CBZ per chapter"
    IMAGES = "Images"


class WeebSeriesMetadata:
    def __init__(self, title: str, url: str):
        self.title = title
        self.title_sanitized = util.sanitize_series_title(self.title)
        self.url = url

        self.description: str | None = None
        self.associated_names: list[str] | None = None
        self.note: str | None = None
        self.authors: list[str] | None = None
        self.tags: list[str] | None = None
        self.type: str | None = None
        self.status: str | None = None
        self.released: str | None = None  # year
        self.official_translation: bool | None = None
        self.anime_adaption: bool | None = None
        self.adult_content: bool | None = None

    def __str__(self):
        return (
            f"WeebSeriesMetadata: title='{self.title} "
            f"description='{self.description}' "
            f"associated_names='{self.associated_names}' "
            f"note='{self.note}' "
            f"authors='{self.authors}' "
            f"tags='{self.tags}' "
            f"type='{self.type}' "
            f"status='{self.status}' "
            f"released='{self.released}' "
            f"official_translation='{self.official_translation}' "
            f"anime_adaption='{self.anime_adaption}' "
            f"adult_content='{self.adult_content}'"
        )

    def to_comicinfo(self) -> str:
        """
        Produce xml output suitable for 'ComicInfo.xml'
        Refer to https://anansi-project.github.io/docs/category/comicinfo for more details
        """
        output: list[str] = []

        output.append('<?xml version="1.0" encoding="utf-8"?>')
        output.append(
            '<ComicInfo xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        )

        output.append(f"  <Title>{self.title}</Title>")

        if self.associated_names:
            output.append(
                f"  <AlternateSeries>{', '.join(self.associated_names)}</AlternateSeries>"
            )

        if self.description:
            output.append(f"  <Summary>{self.description}</Summary>")

        if self.note:
            output.append(f"  <Note>{self.note}</Note>")

        if self.released:
            output.append(f"  <Year>{self.released}</Year>")

        # unfortunately weeb central does not distinguish between types of creators, so everyone will be listed as a writer
        if self.authors:
            output.append(f"  <Writer>{', '.join(self.authors)}</Writer>")

        if self.tags:
            output.append(f"  <Tags>{', '.join(self.tags)}</Tags>")

        if self.url:
            output.append(f"  <Web>{self.url}</Web>")

        if self.adult_content:
            output.append("f  <AgeRating>Mature 17+</AgeRating>")

        output.append("</ComicInfo>")

        return "\n".join(output)


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
