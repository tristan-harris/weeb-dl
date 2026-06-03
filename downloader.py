import os
import queue
import random
import re
import sys
import threading
from enum import Enum
from io import BytesIO
from pathlib import Path
from time import sleep

import requests
from bs4 import BeautifulSoup
from PIL import Image
from pypdf import PdfWriter

import data
import util

# selects the max_page value found in the JS of a chapter page
MAX_PAGE_REGEX = r"max_page:\s*parseInt\('(\d+)'\)"

PAGE_NUM_REGEX = r"-(\d+)\."

# TODO: is domain the right term?
WEEB_DOMAIN = "weebcentral.com"
WEEB_BASE_URL = f"https://{WEEB_DOMAIN}"

REQUESTS_MAX_RETRIES = 4
REQUESTS_TIMEOUT = 60  # network request timeout (seconds)

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
        self.stop_event = threading.Event()

        self.headers = {
            "Referer": WEEB_BASE_URL,
            "User-Agent": random.choice(USER_AGENTS),
        }

    def _delete_dir(self, path: Path):
        """Recursively delete directory"""
        if not path.exists():
            return

        for sub_path in path.iterdir():
            if sub_path.is_dir():
                self._delete_dir(sub_path)
            else:
                sub_path.unlink()
        path.rmdir()

    def _validate_response(self, response: requests.Response):
        if response.status_code != 200:
            self._log_message(
                f"Error: Recieved status code of {response.status_code} for requested URL {response.url}"
            )
            exit(1)

    def _log_message(self, text: str):
        self.message_queue.put(data.LogMessage(text))

    def _error_message(self, text: str):
        self.message_queue.put(data.ErrorMessage(text))

    def _progress_message(self, current_chapter_index: int, total_chapters: int):
        self.message_queue.put(
            data.DownloadProgressMessage(current_chapter_index, total_chapters)
        )

    def _completion_message(self):
        self.message_queue.put(data.CompletionMessage())

    def download(self, series: str, download_dir: str):
        self.stop_event.clear()

        if not util.is_valid_series(series):
            self._log_message(f"Error: Invalid series '{series}'")
            exit(1)

        os.chdir(download_dir)

        # if entire url provided, extract ID
        if WEEB_DOMAIN in series:
            series_id = util.get_id_from_series_url(series)
        else:
            series_id = series

        session = requests.Session()
        session.headers.update(self.headers)

        params = {"is_prev": "False", "reading_style": "long_strip"}
        response = session.get(
            f"{WEEB_BASE_URL}/chapters/01J76XYZJ6BTZCRXJZ11JH9JSK/images",
            params=params,
            timeout=REQUESTS_TIMEOUT,
        )
        print(response.text)
        self._completion_message()

        series_title: str = ""
        series_status: str = ""

        response = session.get(
            f"{WEEB_BASE_URL}/series/{series_id}", timeout=REQUESTS_TIMEOUT
        )
        self._validate_response(response)

        # === MAIN PAGE ===
        soup: BeautifulSoup = BeautifulSoup(response.text, "html.parser")

        # get series title
        title_h1 = soup.find("h1")
        if title_h1 and title_h1.string:
            series_title = title_h1.string
        else:
            self._log_message("Error: Could not access series title")
            exit(1)

        # get series status
        statuses: list[str] = ["Ongoing", "Complete", "Hiatus", "Canceled"]
        for status in statuses:
            match = soup.find(string=status)
            if match:
                series_status = status
                break

        if not series_status:
            self._error_message("Error: Series status not found")
            return

        # check if a file already exists
        series_dir_path: Path = Path(series_title)
        if series_dir_path.is_file():
            self._error_message(f"Error: File already exists at '{series_title}'")
            return

        try:
            os.makedirs(series_dir_path, exist_ok=True)
            os.chdir(series_dir_path)
        except PermissionError:
            self._error_message(
                f"Error: Not allowed to download series at '{download_dir}'"
            )
            exit(1)
        except Exception as e:
            self._error_message(f"Error: {e}")
            exit(1)

        # if series is not finished, create note.txt file detailing last chapter
        if series_status == "Ongoing" or series_status == "Hiatus":
            # first chapter listed on website, last in series
            latest_chapter_container = soup.find("a", href=re.compile(r"/chapters/"))
            if not latest_chapter_container:
                self._log_message("Error: Latest chapter not found")
                exit(1)

            latest_chapter_name = latest_chapter_container.find(  # ty: ignore[no-matching-overload]
                "span", string=re.compile(r"\d+")
            )

            self._log_message("Creating 'notes.txt' file")
            with open("note.txt", "w") as note_file:
                note_file.write(f"PDF goes up to {latest_chapter_name.text}.")

        # === CHAPTERS ===
        self._log_message(f"Downloading series '{series_title}'")
        response = session.get(
            f"{WEEB_BASE_URL}/series/{series_id}/full-chapter-list",
            timeout=REQUESTS_TIMEOUT,
        )
        self._validate_response(response)

        soup = BeautifulSoup(response.text, "html.parser")
        chapter_ids: list[str] = []

        elements = soup.find_all("a")
        for element in elements:
            link = str(element.get("href", ""))
            if f"{WEEB_BASE_URL}/chapters" in link:
                chapter_id: str = link.replace(f"{WEEB_BASE_URL}/chapters/", "")
                chapter_ids.append(chapter_id)

        # so first chapter in list is first in series
        chapter_ids.reverse()

        # HACK: temporary
        chapter_ids = chapter_ids[:2]

        for chapter_idx, chapter_id in enumerate(chapter_ids):
            response = session.get(
                f"{WEEB_BASE_URL}/chapters/{chapter_id}", timeout=REQUESTS_TIMEOUT
            )
            self._validate_response(response)

            soup = BeautifulSoup(response.text, "html.parser")

            link_element = soup.find("link", attrs={"rel": "preload", "as": "image"})
            if not link_element:
                self._log_message("Error: Image host link element not found")
                exit(1)

            image_host_url: str = str(link_element.get("href", ""))
            if not image_host_url:
                self._log_message("Error: Image host link not found")
                exit(1)

            match = re.search(MAX_PAGE_REGEX, response.text)
            if not match:
                self._log_message("Error: Value for 'max_page' not found")
                exit(1)

            # if interrupted
            if self.stop_event.is_set():
                self._delete_dir(series_dir_path)
                return

            # number of pages in chapter
            number_pages: int = int(match.group(1))

            chapter_images: list[Image.Image] = []

            for page_i in range(1, number_pages + 1):
                # substitute first page index (as part of image host URL) with current page index
                page_url: str = re.sub(
                    PAGE_NUM_REGEX, f"-{util.pad_num(str(page_i), 3)}.", image_host_url
                )
                response = session.get(page_url, timeout=REQUESTS_TIMEOUT)
                self._validate_response(response)

                img = Image.open(BytesIO(response.content))
                img = img.convert("RGB")  # consistent processing
                chapter_images.append(img)

                # if interrupted
                if self.stop_event.is_set():
                    self._delete_dir(series_dir_path)
                    chapter_images.clear()
                    return

            self._log_message(
                f"Downloaded images for chapter {chapter_idx + 1}/{len(chapter_ids)}"
            )

            # save images as PDF
            chapter_images[0].save(
                f"{chapter_id}.pdf",
                format="PDF",
                resolution=100.0,  # DPI
                append_images=chapter_images[1:],
            )

            for img in chapter_images:
                img.close()

            self._log_message(
                f"Assembled PDF for chapter {chapter_idx + 1}/{len(chapter_ids)}"
            )
            self._progress_message(chapter_idx + 1, len(chapter_ids))

        # === MERGE PDFS ===
        self._log_message("Assembling final PDF")

        writer = PdfWriter()

        for chapter_id in chapter_ids:
            writer.append(f"{chapter_id}.pdf")
        with open(f"{series_title.replace(' ', '_')}.pdf", "wb") as pdf_file:
            writer.write(pdf_file)

        # delete all other pdfs
        for chapter_id in chapter_ids:
            os.unlink(f"{chapter_id}.pdf")

        self._completion_message()

    def stop(self):
        self.stop_event.set()
        self._log_message(f"Download cancelled")
