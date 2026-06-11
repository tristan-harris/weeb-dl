import os
import queue
import random
import threading
import time
import zipfile
from io import BytesIO
from pathlib import Path

import pikepdf
import requests
from bs4 import BeautifulSoup
from PIL import Image

from . import util
from .data import *

WEEB_BASE_URL = "https://weebcentral.com"

REQUESTS_MAX_RETRIES = 4
REQUESTS_TIMEOUT = 60  # network request timeout (seconds)

# if number of chapters to be downloaded exceeds this value
# prompt user for confirmation first
RECOMMENDED_MAX_CHAPTER_NUM = 250

# https://www.useragents.me
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.10 Safari/605.1.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.3",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.3",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.3",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Trailer/93.3.8652.5",
]


class WeebDownloader:
    def __init__(
        self,
        message_queue: queue.SimpleQueue,
    ):
        self.message_queue: queue.SimpleQueue = message_queue

        self.confirm_event = threading.Event()
        self.stop_event = threading.Event()

        headers = {
            "Referer": WEEB_BASE_URL,
            "User-Agent": random.choice(USER_AGENTS),
        }

        self.session = requests.Session()
        self.session.headers.update(headers)

    def _get_response(self, url: str, params: dict | None = None) -> requests.Response:  # ty: ignore[invalid-return-type]
        """Make a GET request with retries, exponential backoff + jitter."""
        for attempt in range(REQUESTS_MAX_RETRIES):
            try:
                response = self.session.get(
                    url,
                    params=params or {},
                    timeout=REQUESTS_TIMEOUT,
                )
                response.raise_for_status()
                return response

            except requests.RequestException as error:
                is_last_attempt = attempt == REQUESTS_MAX_RETRIES - 1

                if is_last_attempt:
                    self._log_message(
                        f"Failed to request '{url}' after {REQUESTS_MAX_RETRIES} attempts: {error}"
                    )
                    raise

                if isinstance(error, requests.HTTPError) and error.response is not None:
                    status = error.response.status_code
                    if 400 <= status < 500:  # client errors (4xx) won't be retried
                        self._log_message(
                            f"Error: Client error {status} for '{url}' - not retrying"
                        )
                        raise

                self._log_message(
                    f"Request to '{url}' failed (attempt {attempt + 1}/{REQUESTS_MAX_RETRIES}): {type(error).__name__} - retrying"
                )

                # exponential backoff with jitter
                backoff = (2**attempt) * 0.5 + random.uniform(0, 0.5)
                time.sleep(min(backoff, 10))  # cap at 10 seconds

    def _get_chapter_output_str(
        self,
        title: str = "",
        num: str = "",
        start: str = "",
        end: str = "",
        total_chapters: int = 0,
    ) -> str:

        chapter_digits = util.number_digits(total_chapters)

        output_str = ""

        if num:
            output_str = f"Chapter {util.pad_num(num, chapter_digits)}"
        elif start and end and start == end:
            output_str = f"Chapter {util.pad_num(start, chapter_digits)}"
        elif start and end:
            output_str = f"Chapters {util.pad_num(start, chapter_digits)}-{util.pad_num(end, chapter_digits)}"

        if title:
            if output_str:
                output_str = f"{title} - {output_str}"
            else:
                output_str = title

        if not output_str:
            raise Exception(
                f"Error: Could not create output string (title={title}, num={num}, start={start}, end={end})"
            )

        return output_str

    def _delete_dir(self, path: Path):
        """Recursively delete directory"""
        self._log_message(f"Deleting folder '{path}'")

        if not path.exists():
            return

        for sub_path in path.iterdir():
            if sub_path.is_dir():
                self._delete_dir(sub_path)
            else:
                sub_path.unlink()
        path.rmdir()

    def _log_message(self, text: str):
        self.message_queue.put(LogMessage(text))

    def _error_message(self, text: str):
        self.message_queue.put(ErrorMessage(text))

    def _selection_confirm_message(
        self, num_chapters: int, num_chapters_recommended: int, series_title: str
    ):
        self.message_queue.put(
            SelectionConfirmationMessage(num_chapters, num_chapters_recommended, series_title)
        )

    def _progress_message(self, current_chapter_index: int, total_chapters: int):
        self.message_queue.put(DownloadProgressMessage(current_chapter_index, total_chapters))

    def _completion_message(self, title: str):
        self.message_queue.put(CompletionMessage(title))

    def _get_series_metadata(self, series_id: str) -> WeebSeriesMetadata:
        self._log_message("Requesting series metadata")

        url = f"{WEEB_BASE_URL}/series/{series_id}"
        response = self._get_response(url)

        soup = BeautifulSoup(response.text, "html.parser")

        # get series title
        title_h1 = soup.find("h1")
        if title_h1 and title_h1.string:
            series_title = title_h1.string
        else:
            raise Exception("Error: Series title not found")

        metadata = WeebSeriesMetadata(title=series_title, url=url)

        # attempt to extract all other metadata from HTML
        for li_element in soup.find_all("li"):
            strong_element = li_element.find("strong")

            if not strong_element:
                continue

            match strong_element.text:
                case "Description":
                    element = li_element.find("p")
                    if element:
                        metadata.description = element.text

                case "Associated Name(s)":
                    elements = li_element.find_all("li")
                    if elements:
                        metadata.associated_names = [e.text for e in elements]

                case "Note":
                    element = li_element.find("p")
                    if element:
                        metadata.note = element.text

                case "Author(s): ":
                    elements = li_element.find_all("a")
                    if elements:
                        metadata.authors = [e.text for e in elements]

                # [sic]
                case "Tags(s): ":
                    elements = li_element.find_all("a")
                    if elements:
                        metadata.tags = [e.text for e in elements]

                case "Type: ":
                    element = li_element.find("a")
                    if element:
                        metadata.type = element.text

                case "Status: ":
                    element = li_element.find("a")
                    if element:
                        metadata.status = element.text

                case "Released: ":
                    element = li_element.find("span")
                    if element:
                        metadata.released = element.text

                case "Official Translation: ":
                    element = li_element.find("a")
                    if element:
                        metadata.official_translation = element.text == "Yes"

                case "Anime Adaptation: ":
                    element = li_element.find("a")
                    if element:
                        metadata.anime_adaption = element.text == "Yes"

                case "Adult Content: ":
                    element = li_element.find("a")
                    if element:
                        metadata.adult_content = element.text == "Yes"

        return metadata

    def _get_series_chapters(self, series_id: str) -> list[WeebChapter]:
        self._log_message("Requesting series chapter list")
        response = self._get_response(
            f"{WEEB_BASE_URL}/series/{series_id}/full-chapter-list",
        )

        soup = BeautifulSoup(response.text, "html.parser")
        chapters: list[WeebChapter] = []

        chapter_divs = soup.find_all("div", class_="flex items-center")

        for chapter_div in chapter_divs:
            chapter_id: str | None = None

            # parse chapter id
            link_element = chapter_div.find("a")

            if not link_element:
                continue

            link = str(link_element.get("href"))
            if f"{WEEB_BASE_URL}/chapters" in link:
                chapter_id = link.replace(f"{WEEB_BASE_URL}/chapters/", "")

            # parse chapter number
            span_parent_element = chapter_div.find("span", class_="grow flex items-center gap-2")
            if not span_parent_element:
                continue

            span_child_element = span_parent_element.find("span", class_="")
            if not span_child_element:
                continue

            chapter_listing = span_child_element.text

            # extract chapter number from listing (e.g. 'Chapter 2.5' -> '2.5')
            chapter_num: str | None = util.extract_num(chapter_listing)

            if chapter_id and chapter_num:
                chapters.append(WeebChapter(id=chapter_id, num=chapter_num))

        # so that first chapter in list is first in series
        chapters.reverse()

        return chapters

    def _get_chapter_range(
        self, chapters: list[WeebChapter], start_chapter: str | None, end_chapter: str | None
    ) -> list[WeebChapter]:
        """Select specified range of chapters from all"""

        # swap chapters if end before start
        if start_chapter and end_chapter:
            if float(end_chapter) < float(start_chapter):
                start_chapter, end_chapter = end_chapter, start_chapter

        selected_chapters: list[WeebChapter] = []

        # whether to start adding chapters during iteration
        add_chapters: bool = False if start_chapter else True

        # to check whether given start and end chapters actually exist
        found_start_chapter: bool = False if start_chapter else True
        found_end_chapter: bool = False if end_chapter else True

        for chapter in chapters:
            if start_chapter and chapter.num == start_chapter:
                add_chapters = True
                found_start_chapter = True

            if add_chapters:
                selected_chapters.append(chapter)

            if end_chapter and chapter.num == end_chapter:
                found_end_chapter = True
                break

        if not found_start_chapter:
            raise Exception(f"Error: Chapter {start_chapter} does not exist")
        if not found_end_chapter:
            raise Exception(f"Error: Chapter {end_chapter} does not exist")

        return selected_chapters

    def _get_chapter_image_urls(self, chapter_id: str) -> list[str]:
        """Extract image urls from /chapters/[ID]/images at weeb central"""
        params = {"is_prev": "False", "reading_style": "long_strip"}
        response = self._get_response(
            f"{WEEB_BASE_URL}/chapters/{chapter_id}/images",
            params=params,
        )

        soup = BeautifulSoup(response.text, "html.parser")
        chapter_img_elements = soup.find_all("img")
        chapter_image_urls = [str(img.get("src")) for img in chapter_img_elements]

        return chapter_image_urls

    def _download_chapter_images(
        self, chapter: WeebChapter, chapter_image_urls: list[str], total_chapters: int
    ):
        image_dir = self._get_chapter_output_str(num=chapter.num, total_chapters=total_chapters)
        os.makedirs(image_dir, exist_ok=True)

        img_idx = 1

        for chapter_image_url in chapter_image_urls:
            response = self._get_response(chapter_image_url)

            with Image.open(BytesIO(response.content)) as img:
                img = img.convert("RGB")  # consistent processing

                # how many digits the number of images has
                # used for zero-padding so that natural sorting is not required
                digits = util.number_digits(len(chapter_image_urls))

                # if image is two-page spread, use hyphenated filename
                if img.width > img.height:
                    img_file_name = f"{util.pad_num(str(img_idx), digits)}-{util.pad_num(str(img_idx + 1), digits)}"
                    img_idx += 1
                else:
                    img_file_name = util.pad_num(str(img_idx), digits)

                img_file_extension = chapter_image_url[chapter_image_url.rfind(".") :]

                img.save(Path(image_dir, f"{img_file_name}{img_file_extension}"))

            img_idx += 1

            if self.stop_event.is_set():
                exit()

    def _assemble_pdfs(self, chapters: list[WeebChapter], metadata: WeebSeriesMetadata):
        for chapter in chapters:
            self._log_message(f"Assembling PDF for {self._get_chapter_output_str(num=chapter.num)}")

            img_list: list[Image.Image] = []
            dir_path = Path(
                self._get_chapter_output_str(num=chapter.num, total_chapters=len(chapters))
            )

            for img_path in sorted((dir_path).glob("*")):
                img_list.append(Image.open(img_path))

            pdf_file_name = f"{self._get_chapter_output_str(title=metadata.title_sanitized, num=chapter.num, total_chapters=len(chapters))}.pdf"

            # create PDF from images
            img_list[0].save(
                pdf_file_name,
                format="PDF",
                resolution=100.0,  # DPI
                append_images=img_list[1:],
            )

            # set metadata of chapter PDF
            with pikepdf.open(pdf_file_name) as pdf:
                with pdf.open_metadata() as pdf_metadata:
                    pdf_metadata["xmp:CreatorTool"] = f"weeb-dl v{WEEB_VERSION}"
                    pdf_metadata["xmp:Producer"] = "pikepdf"

            for img in img_list:
                img.close()
            img_list.clear()

    def _assemble_complete_pdf(
        self,
        chapters: list[WeebChapter],
        metadata: WeebSeriesMetadata,
        start_chapter: str,
        end_chapter: str,
    ):
        self._log_message("Assembling final PDF")

        complete_pdf = pikepdf.Pdf.new()

        for chapter in chapters:
            chapter_pdf_filename = f"{self._get_chapter_output_str(title=metadata.title_sanitized, num=chapter.num, total_chapters=len(chapters))}.pdf"

            chapter_pdf = pikepdf.Pdf.open(chapter_pdf_filename)
            complete_pdf.pages.extend(chapter_pdf.pages)
            chapter_pdf.close()

        with complete_pdf.open_metadata() as pdf_metadata:
            pdf_metadata["xmp:CreatorTool"] = f"weeb-dl v{WEEB_VERSION}"
            pdf_metadata["xmp:Producer"] = "pikepdf"

        # set final pdf filename based on chapter selection
        if not start_chapter and not end_chapter:
            complete_pdf_name = self._get_chapter_output_str(title=metadata.title_sanitized)
        else:
            complete_pdf_name = self._get_chapter_output_str(
                title=metadata.title_sanitized,
                start=start_chapter or chapters[0].num,
                end=end_chapter or chapters[-1].num,
                total_chapters=len(chapters),
            )

        complete_pdf.save(f"{complete_pdf_name}.pdf")

    def _assemble_cbzs(self, chapters: list[WeebChapter], metadata: WeebSeriesMetadata):
        for chapter in chapters:
            self._log_message(f"Assembling CBZ for {self._get_chapter_output_str(num=chapter.num)}")

            chapter_dir_path = Path(
                self._get_chapter_output_str(num=chapter.num, total_chapters=len(chapters))
            )

            with open(Path(chapter_dir_path, "ComicInfo.xml"), "w") as xml:
                xml.write(metadata.to_comicinfo())

            cbz_name = self._get_chapter_output_str(
                title=metadata.title_sanitized, num=chapter.num, total_chapters=len(chapters)
            )

            with zipfile.ZipFile(f"{cbz_name}.cbz", "w") as cbz:
                for file_path in chapter_dir_path.glob("*"):
                    cbz.write(file_path, file_path.relative_to(chapter_dir_path))

    def _assemble_complete_cbz(
        self,
        chapters: list[WeebChapter],
        metadata: WeebSeriesMetadata,
        start_chapter: str,
        end_chapter: str,
    ):
        self._log_message("Assembling CBZ")

        # set cbz filename based on chapter selection
        if not start_chapter and not end_chapter:
            complete_cbz_name = self._get_chapter_output_str(title=metadata.title_sanitized)
        else:
            complete_cbz_name = self._get_chapter_output_str(
                title=metadata.title_sanitized,
                start=start_chapter or chapters[0].num,
                end=end_chapter or chapters[-1].num,
                total_chapters=len(chapters),
            )

        cwd = Path(".")

        with zipfile.ZipFile(f"{complete_cbz_name}.cbz", "w") as cbz:
            for chapter in chapters:
                chapter_dir_path = Path(
                    self._get_chapter_output_str(num=chapter.num, total_chapters=len(chapters))
                )

                for chapter_image_path in chapter_dir_path.glob("*"):
                    if chapter_image_path.is_file():
                        cbz.write(chapter_image_path, chapter_image_path.relative_to(cwd))

            cbz.writestr("ComicInfo.xml", metadata.to_comicinfo())

    def _download(
        self,
        series: str,
        start_chapter: str,
        end_chapter: str,
        output_format: WeebOutputFormat,
        download_dir: str,
    ):
        self.confirm_event.clear()
        self.stop_event.clear()

        if not util.is_valid_series(series):
            raise Exception(f"Error: Invalid series '{series}'")

        os.chdir(download_dir)

        series_id = util.get_id_from_series_url(series)
        if not series_id:
            raise Exception(f"Error: Could not extract ID from '{series}'")

        series_metadata = self._get_series_metadata(series_id)

        if self.stop_event.is_set():
            exit()

        # check if a file already exists
        series_dir_path: Path = Path(series_metadata.title_sanitized)
        if series_dir_path.is_file():
            raise Exception(f"Error: File already exists at '{series_metadata.title_sanitized}'")

        try:
            os.makedirs(series_dir_path, exist_ok=True)
        except PermissionError:
            raise Exception(f"Error: Not allowed to create directory at '{download_dir}'")
        except Exception:
            raise Exception(f"Error: Could not create directory at '{download_dir}")

        os.chdir(series_dir_path)

        chapters = self._get_series_chapters(series_id)
        if not chapters:
            raise Exception("Error: No chapters found")

        if self.stop_event.is_set():
            exit()

        # slice chapters list if range specified
        if start_chapter or end_chapter:
            chapters = self._get_chapter_range(chapters, start_chapter, end_chapter)

        # if downloading large chapter range for single file output, warn user first
        if len(chapters) > RECOMMENDED_MAX_CHAPTER_NUM:
            if output_format in [WeebOutputFormat.PDF, WeebOutputFormat.CBZ]:
                self._selection_confirm_message(
                    len(chapters), RECOMMENDED_MAX_CHAPTER_NUM, series_metadata.title
                )
                # wait for confirmation or cancellation
                while not self.confirm_event.is_set() and not self.stop_event.is_set():
                    time.sleep(0.5)

        if self.stop_event.is_set():
            exit()

        self._log_message(f"Downloading series '{series_metadata.title}'")

        # download images
        for chapter_idx, chapter in enumerate(chapters):
            self._log_message(f"Downloading images for Chapter {chapter.num}")

            chapter_image_urls = self._get_chapter_image_urls(chapter.id)
            self._download_chapter_images(chapter, chapter_image_urls, total_chapters=len(chapters))

            self._progress_message(chapter_idx + 1, len(chapters))

        # assemble output from images
        match output_format:
            case WeebOutputFormat.PDF:
                self._assemble_pdfs(chapters, series_metadata)
                self._assemble_complete_pdf(
                    chapters,
                    series_metadata,
                    start_chapter,
                    end_chapter,
                )
            case WeebOutputFormat.PDF_PER_CHAPTER:
                self._assemble_pdfs(chapters, series_metadata)

            case WeebOutputFormat.CBZ:
                self._assemble_complete_cbz(chapters, series_metadata, start_chapter, end_chapter)

            case WeebOutputFormat.CBZ_PER_CHAPTER:
                self._assemble_cbzs(chapters, series_metadata)

            case WeebOutputFormat.IMAGES:
                pass

        # clean up images
        if output_format != WeebOutputFormat.IMAGES:
            self._log_message("Deleting intermediate images")
            for chapter in chapters:
                dir_path_str = self._get_chapter_output_str(
                    num=chapter.num, total_chapters=len(chapters)
                )
                self._delete_dir(Path(dir_path_str))

        # clean up intermediate PDFs
        if output_format == WeebOutputFormat.PDF:
            self._log_message("Deleting intermediate PDFs")

            for chapter in chapters:
                pdf_filename = self._get_chapter_output_str(
                    title=series_metadata.title_sanitized,
                    num=chapter.num,
                    total_chapters=len(chapters),
                )
                os.unlink(f"{pdf_filename}.pdf")

        self._completion_message(series_metadata.title)

    def download(
        self,
        series: str,
        start_chapter: str,
        end_chapter: str,
        output_format: WeebOutputFormat,
        download_dir: str,
    ):
        try:
            self._download(series, start_chapter, end_chapter, output_format, download_dir)
        except Exception as e:
            self._error_message(str(e))
            exit(1)

    def confirm(self):
        self.confirm_event.set()

    def stop(self):
        self.stop_event.set()
        self._log_message("Download canceled")
