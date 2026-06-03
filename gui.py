import math
import queue
import re
import tkinter as ttk
from pathlib import Path
from threading import Thread
from tkinter import filedialog

import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox, MessageDialog
from ttkbootstrap.icons import Icon
from ttkbootstrap.style import ThemeDefinition
from ttkbootstrap.widgets.scrolled import ScrolledText

import data
import util
from downloader import WeebDownloader
from settings import WeebSettingsManager

WEEB_VERSION = "0.0.1"

WEEB_TITLE = "weeb-dl"
WEEB_THEME = "litera"
WEEB_MIN_SIZE = (200, 200)
WEEB_SIZE = (700, 900)


class WeebGUI(tb.Frame):
    def __init__(self, master: tb.Window):
        super().__init__(master=master, padding=15)
        self.grid(sticky=(N, E, S, W))

        self.master = master

        self.master.protocol("WM_DELETE_WINDOW", self.window_close)

        self.message_queue = queue.SimpleQueue()
        self.downloader_thread: Thread | None = None

        self.downloader = WeebDownloader(self.message_queue)

        self.settings_manager = WeebSettingsManager()
        self.settings_manager.load(print)
        self.settings = self.settings_manager.settings

        #  === APPLICATION VARIABLES ===
        self.series = tb.StringVar()
        self.series.set(
            "https://weebcentral.com/series/01J76XY9WR4RCP6SS3A96Y8EK2/Log-Horizon"
        )

        self.output_format = tb.StringVar(value=self.settings.output_format)
        self.output_format.trace_add("write", self.on_settings_changed)

        self.notify_upon_completion = tb.BooleanVar(
            value=self.settings.notify_on_completion
        )
        self.notify_upon_completion.trace_add("write", self.on_settings_changed)

        self.download_dir = tb.StringVar(value=self.settings.download_dir)
        self.download_dir.trace_add("write", self.on_settings_changed)

        self.download_progress = tb.IntVar(value=0)
        self.download_progress_str = tb.StringVar(
            value=f"{self.download_progress.get()}%"
        )

        # === WIDGETS ===
        self.cancel_button = None  # Button widget
        self.log_messages = None  # ScrollText widget

        self.header_row = self.create_header_row()
        self.series_id_row = self.create_series_id_row()
        self.config_row = self.create_config_row()
        self.download_row = self.create_download_row()
        self.progress_row = self.create_progress_row()

        # required so that entire GUI reacts upon window resizing
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=10000)  # make config panel expand
        self.rowconfigure(3, weight=1)
        self.rowconfigure(4, weight=1)

        self.columnconfigure(0, weight=1)

        master.bind("<Control-q>", lambda _: self.window_close())

    def create_header_row(self) -> tb.Frame:
        """Add frame containing weeb-dl title and version text"""

        header_row = tb.Frame(master=self)
        header_row.grid(column=0, row=0, sticky=(N, E, S, W))

        tb.Label(
            master=header_row,
            text="weeb-dl",
            anchor=CENTER,
            bootstyle="primary",
            font=("TkDefaultFont", 48, "bold"),
        ).grid(column=0, row=0, sticky=(E, W))

        header_label = tb.Label(
            master=header_row,
            text="Download manga/manhwa/manhua from weebcentral.com",
            anchor=CENTER,
            font=("TkSmallCaptionFont"),
        )
        header_label.grid(column=0, row=1, sticky=(E, W))

        header_row.columnconfigure(0, weight=1)
        header_row.rowconfigure(0, weight=1)
        header_row.rowconfigure(1, weight=1)

        return header_row

    def create_series_id_row(self) -> tb.Labelframe:
        """Add frame containing widgets related to series URL/ID input"""

        series_id_row = tb.Labelframe(master=self, text=" Series ", padding=10)
        series_id_row.grid(column=0, row=1, sticky=(N, E, S, W))

        tb.Label(master=series_id_row, text="ID/URL").grid(column=0, row=1, sticky=W)

        series_id_entry = tb.Entry(master=series_id_row, textvariable=self.series)
        series_id_entry.grid(column=0, row=2, sticky=(E, W))
        series_id_entry.focus()

        series_id_row.columnconfigure(0, weight=1)

        return series_id_row

    def create_config_row(self) -> tb.Labelframe:
        """Add frame containing widgets related to configuration"""

        config_row = tb.Labelframe(master=self, text=" Options ", padding=10)
        config_row.grid(column=0, row=2, sticky=(N, E, S, W))

        tb.Label(master=config_row, text="\nOutput format").grid(
            column=0, row=0, sticky=W
        )

        combobox = tb.Combobox(
            master=config_row,
            textvariable=self.output_format,
            state=READONLY,
            values=[fmt.value for fmt in data.WeebOutputFormat],
        )
        combobox.grid(column=0, row=1)
        combobox.bind("<<ComboboxSelected>>", lambda _: combobox.selection_clear())

        notify_checkbutton = tb.Checkbutton(
            master=config_row,
            text="Notify upon completion",
            variable=self.notify_upon_completion,
        )
        notify_checkbutton.grid(column=0, row=2, pady=(10, 10), sticky=W)

        return config_row

    def create_download_row(self) -> tb.Labelframe:
        download_row = tb.Labelframe(master=self, text=" Download ", padding=10)
        download_row.grid(column=0, row=3, sticky=(N, E, S, W))

        tb.Label(master=download_row, text="Download Folder").grid(
            column=0, row=0, sticky=W
        )

        tb.Entry(master=download_row, textvariable=self.download_dir).grid(
            column=0, row=1, sticky=(E, W), padx=(0, 10)
        )

        tb.Button(
            master=download_row, text="📁 Browse", command=self.choose_download_dir
        ).grid(column=6, row=1, sticky=E)

        buttons_frame = tb.Frame(master=download_row, padding=(0, 10, 0, 0))
        buttons_frame.grid(column=0, row=2, sticky=W)

        tb.Button(
            master=buttons_frame,
            text="⬇️ Download",
            command=self.start_download,
            bootstyle=SUCCESS,
        ).grid(column=0, row=2, sticky=W, padx=(0, 10))

        self.cancel_button = tb.Button(
            master=buttons_frame,
            text="❌ Cancel",
            command=self.cancel_download,
            state=DISABLED,
            bootstyle=DANGER,
        )
        self.cancel_button.grid(column=1, row=2, sticky=W)

        download_row.columnconfigure(0, weight=1000)
        download_row.rowconfigure(0, weight=1)
        download_row.columnconfigure(1, weight=1)
        download_row.rowconfigure(1, weight=1)
        download_row.columnconfigure(2, weight=1)
        download_row.rowconfigure(2, weight=1)

        return download_row

    def create_progress_row(self) -> tb.Labelframe:
        """Add frame containing widgets showing download progress"""

        progress_row = tb.Labelframe(master=self, text=" Progress ", padding=10)
        progress_row.grid(column=0, row=4, sticky=(N, E, S, W))

        tb.Progressbar(
            master=progress_row, variable=self.download_progress, bootstyle=SUCCESS
        ).grid(column=0, row=0, padx=(0, 5), sticky=(E, W))

        tb.Label(master=progress_row, textvariable=self.download_progress_str).grid(
            column=1, row=0, sticky=(E, W)
        )

        self.log_messages = ScrolledText(
            master=progress_row,
            padding=0,
            height=5,
            state=DISABLED,
        )
        self.log_messages.grid(
            column=0, row=1, columnspan=2, pady=(5, 0), sticky=(N, E, S, W)
        )

        progress_row.columnconfigure(0, weight=10000)
        progress_row.columnconfigure(1, weight=1)

        return progress_row

    def on_settings_changed(self, *_args):
        self.settings.output_format = data.WeebOutputFormat(self.output_format.get())
        self.settings.notify_on_completion = self.notify_upon_completion.get()
        self.settings.download_dir = self.download_dir.get()
        self.settings_manager.save(print)

    def window_close(self):
        # if currently downloading
        if self.downloader_thread:
            dialog = MessageDialog(
                title="Confirm exit",
                message="weeb-dl is currently downloading, are you sure you want to quit?",
                buttons=["Cancel:Secondary", "Confirm:Primary"],
                icon=Icon.question,
            )
            dialog.show()
            if dialog.result == "Confirm":
                # TODO: end thread first?
                self.master.destroy()
        else:
            self.master.destroy()

    def choose_download_dir(self):
        dir = filedialog.askdirectory(initialdir=self.download_dir.get())
        if dir:
            self.download_dir.set(dir)

    def set_active_all_input(self, active: bool):
        """Set all input-related widgets to active or disabled"""
        widget_queue = queue.SimpleQueue()
        widget_queue.put(self)

        while not widget_queue.empty():
            widget = widget_queue.get()

            if isinstance(widget, (tb.Entry, tb.Button, tb.Checkbutton)):
                widget.configure(state=ACTIVE if active else DISABLED)
            if isinstance(widget, tb.Combobox):
                widget.configure(state=READONLY if active else DISABLED)

            for widget_child in widget.winfo_children():
                widget_queue.put(widget_child)

    def start_download(self):
        if not util.is_valid_series(self.series.get()):
            Messagebox.show_error(
                title="Invalid weebcentral.com ID/URL",
                message="You must provide either an ID (e.g. 01J76XY7E9FNDZ1DBBM6PBJPFK), or a complete URL (e.g. https://weebcentral.com/series/01J76XY7E9FNDZ1DBBM6PBJPFK/One-Piece).",
            )
            return

        # disable all input except cancel button
        self.set_active_all_input(False)
        if self.cancel_button:
            self.cancel_button.configure(state=ACTIVE)

        self.update_download_progress(0, 0)

        self.start_download_thread()
        self.process_message_queue()

    def start_download_thread(self):
        self.downloader_thread = Thread(
            target=self.downloader.download,
            args=(self.series.get(), self.download_dir.get()),
            daemon=True,
        )
        self.downloader_thread.start()

    def cancel_download(self):
        if self.downloader_thread:
            self.downloader.stop()
            self.downloader_thread.join()
            self.downloader_thread = None

        # enable all input except cancel button
        self.set_active_all_input(True)
        if self.cancel_button:
            self.cancel_button.configure(state=DISABLED)

    def process_message_queue(self):
        while True:
            try:
                message = self.message_queue.get_nowait()
            except queue.Empty:
                break
            except Exception as e:
                print(e)
                break

            self.handle_message(message)

        self.master.after(100, self.process_message_queue)

    def handle_message(self, message):
        if isinstance(message, data.LogMessage):
            self.print_log_message(message.text)
            return

        if isinstance(message, data.DownloadProgressMessage):
            self.update_download_progress(
                message.chapters_downloaded, message.total_chapters
            )
            return

        if isinstance(message, data.CompletionMessage):
            if self.notify_upon_completion:
                util.send_notification(
                    "Download Complete", "weeb-dl has finished downloading series"
                )

            # clear download progress
            self.update_download_progress(0, 0)

            self.set_active_all_input(True)
            if self.cancel_button:
                self.cancel_button.configure(state=DISABLED)

            if self.downloader_thread:
                self.downloader_thread.join()
                self.downloader_thread = None

    def print_log_message(self, message: str):
        if not self.log_messages:
            return

        # automatically scroll to end of output if user has not scrolled up
        _, bottom = self.log_messages.yview()
        at_bottom = bottom > 0.99

        # ScrollText Text must be temporarily set to 'normal' to insert text
        self.log_messages.text.configure(state=ttk.NORMAL)

        # insert newline before new message unless log is empty
        if self.log_messages.index("end-1c") == "1.0":
            self.log_messages.insert("end", message)
        else:
            self.log_messages.insert("end", f"\n{message}")

        # set to disabled afterwards so that output cannot be edited
        self.log_messages.text.configure(state=ttk.DISABLED)

        if at_bottom:
            self.log_messages.see(END)

    def update_download_progress(self, chapters_downloaded: int, total_chapters: int):
        if total_chapters == 0:
            self.download_progress.set(0)
        else:
            self.download_progress.set(
                math.floor((chapters_downloaded / total_chapters) * 100)
            )
        self.download_progress_str.set(f"{self.download_progress.get()}%")


if __name__ == "__main__":
    root = tb.Window(
        title=f"{WEEB_TITLE} v{WEEB_VERSION}",
        themename=WEEB_THEME,
        size=WEEB_SIZE,
        minsize=WEEB_MIN_SIZE,
        iconphoto=str(Path("assets", "icon", "app_icon.png")),
    )
    WeebGUI(root)
    root.mainloop()
