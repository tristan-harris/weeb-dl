import argparse
import os
import queue
from threading import Thread
from typing import Any

import colorama
import requests

import data
import util
from downloader import WeebDownloader

RESET = "\x1b[0m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"


class WeebCLI:
    def __init__(self):
        colorama.just_fix_windows_console()  # make ANSI sequences work on Windows
        arguments = self.parse_arguments()

        self.series: str = arguments.series

        self.settings = data.WeebSettings(
            download_dir=arguments.download_dir,
            output_format=arguments.output_format,
            notify_on_completion=arguments.notify_upon_completion,
        )

        if not util.is_valid_series(self.series):
            print(f"{RED}Error: '{self.series}' is not a valid ID/URL{RESET}")
            exit(1)

        self.download_thread: Thread | None = None

    def parse_arguments(self) -> argparse.Namespace:
        parser = argparse.ArgumentParser(
            description="Download manga/manhwa/manhua from weebcentral.com"
        )
        parser.add_argument(
            "-d",
            "--downloaddir",
            dest="download_dir",
            type=str,
            default=os.getcwd(),
            help="download directory (default is current working directory)",
            metavar="DIRECTORY",
        )
        parser.add_argument(
            "-f",
            "--format",
            dest="output_format",
            default="pdf",
            choices=["pdf", "pdf-per-chapter", "cbz", "cb7", "images"],
            help="output format (default is pdf)",
        )
        parser.add_argument(
            "-n",
            "--notify",
            dest="notify_upon_completion",
            default=False,
            action="store_true",
            help="send notification upon completing download (default is false)",
        )
        parser.add_argument(
            "series",
            metavar="[SERIES]",
            help="can be either the ID or the entire URL of a series",
        )
        return parser.parse_args()

    def start_download(self):
        message_queue = queue.SimpleQueue()
        downloader = WeebDownloader(message_queue)
        self.download_thread = Thread(
            target=downloader.download,
            args=(self.series, self.settings.download_dir),
            daemon=True,
        )
        self.download_thread.start()

        while True:  # while this process is running
            while True:  # while there is potentially at least one message to process
                try:
                    message = message_queue.get_nowait()
                except queue.Empty:
                    break

                self.handle_message(message)

    def handle_message(self, message):
        if isinstance(message, data.LogMessage):
            print(message.text)
            return

        if isinstance(message, data.ErrorMessage):
            print(f"{RED}{message.text}{RESET}")
            exit(1)

        if isinstance(message, data.DownloadProgressMessage):
            print(
                f"Downloaded {message.chapters_downloaded}/{message.total_chapters} chapters"
            )
            return

        if isinstance(message, data.CompletionMessage):
            if self.download_thread:
                self.download_thread.join()

            if self.settings.notify_on_completion:
                util.send_notification(
                    "Download Complete", "weeb-dl has finished download"
                )

            print(f"{GREEN}Done{RESET}")
            return


if __name__ == "__main__":
    cli = WeebCLI()
    cli.start_download()
