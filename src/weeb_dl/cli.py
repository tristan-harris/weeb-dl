import argparse
import os
import queue
from threading import Thread

from . import __version__, util
from .data import *
from .downloader import RECOMMENDED_MAX_CHAPTER_NUM, WeebDownloader


class WeebCLI:
    def __init__(self):
        arguments = self.parse_arguments()

        self.series: str = arguments.series
        self.start_chapter: str = arguments.start_chapter or ""
        self.end_chapter: str = arguments.end_chapter or ""

        self.settings = WeebSettings(
            download_dir=arguments.download_dir,
            output_format=self.output_argument_to_enum(arguments.output_format),
            notify_on_completion=arguments.notify_upon_completion,
        )

        if not util.is_valid_series(self.series):
            print(f"Error: '{self.series}' is not a valid ID/URL")
            exit()

        if self.start_chapter and not util.is_num(self.start_chapter):
            print(f"Error: '{self.start_chapter}' is not a valid chapter number")
            exit()

        if self.end_chapter and not util.is_num(self.end_chapter):
            print(f"Error: '{self.end_chapter}' is not a valid chapter number")
            exit()

        self.download_thread: Thread | None = None

    def parse_arguments(self) -> argparse.Namespace:
        parser = argparse.ArgumentParser(
            description="Download manga/manhwa/manhua from weebcentral.com",
            epilog=f"If a series has many chapters (for example over {RECOMMENDED_MAX_CHAPTER_NUM}), it is recommended to download only part of it at a time using the --start and --end arguments",
        )
        parser.add_argument(
            "-s",
            "--start",
            dest="start_chapter",
            type=str,
            help="start download from this chapter",
            metavar="CHAPTER_NUMBER",
        )
        parser.add_argument(
            "-e",
            "--end",
            dest="end_chapter",
            type=str,
            help="end download at this chapter, including this chapter",
            metavar="CHAPTER_NUMBER",
        )
        parser.add_argument(
            "-f",
            "--format",
            dest="output_format",
            default="pdf",
            choices=[
                "pdf",
                "pdf-per-chapter",
                "cbz",
                "cbz-per-chapter",
                "images",
            ],
            help="output format (default is pdf)",
        )
        parser.add_argument(
            "-d",
            "--dir",
            dest="download_dir",
            type=str,
            default=os.getcwd(),
            metavar="DIRECTORY",
            help="download directory (default is current working directory)",
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
            "-v",
            "--version",
            action="version",
            version=f"weeb-dl {__version__}",
            help="print version and exit",
        )
        parser.add_argument(
            "series",
            metavar="[SERIES]",
            help="can be either the ID or the entire URL of a series",
        )
        return parser.parse_args()

    def output_argument_to_enum(self, output_arg: str) -> WeebOutputFormat:
        match output_arg:
            case "pdf":
                return WeebOutputFormat.PDF
            case "pdf-per-chapter":
                return WeebOutputFormat.PDF_PER_CHAPTER
            case "cbz":
                return WeebOutputFormat.CBZ
            case "cbz-per-chapter":
                return WeebOutputFormat.CBZ_PER_CHAPTER
            case "images":
                return WeebOutputFormat.IMAGES
            case _:
                raise Exception(f"Error: Invalid output argument '{output_arg}")

    def start_download(self):
        message_queue = queue.SimpleQueue()
        downloader = WeebDownloader(message_queue)
        self.download_thread = Thread(
            target=downloader.download,
            args=(
                self.series,
                self.start_chapter,
                self.end_chapter,
                self.settings.output_format,
                self.settings.download_dir,
            ),
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
        if isinstance(message, LogMessage):
            print(message.text)
            return

        if isinstance(message, ErrorMessage):
            print(f"{message.text}")
            exit(1)

        if isinstance(message, SelectionConfirmationMessage):
            return

        if isinstance(message, DownloadProgressMessage):
            return

        if isinstance(message, CompletionMessage):
            if self.download_thread:
                self.download_thread.join()

            if self.settings.notify_on_completion:
                util.send_notification(
                    "Download Complete", f"weeb-dl has finished downloading '{message.title}'"
                )

            print("Done")
            exit()


def main():
    cli = WeebCLI()
    cli.start_download()


if __name__ == "__main__":
    main()
