#!/usr/bin/env python3
"""Simple desktop app for Local Instagram Unfollower.

Double-click the standalone EXE (or START_HERE.bat), choose an Instagram JSON
export, and generate the local dashboard. No terminal commands, no Instagram
login, no uploads.
"""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

APP_DIR = (
    Path(sys.executable).parent.resolve()
    if getattr(sys, "frozen", False)
    else Path(__file__).parent.resolve()
)
sys.path.insert(0, str(APP_DIR))

import ig_audit


def _resource_path(relative: str) -> Path:
    """Find bundled files both in source runs and in the PyInstaller EXE."""
    base = Path(getattr(sys, "_MEIPASS", APP_DIR))
    return base / relative


def _report_dir() -> Path:
    """Prefer a report folder next to the app, fall back to Documents."""
    preferred = APP_DIR / "report"
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        probe = preferred / ".write-test"
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return preferred
    except OSError:
        fallback = Path.home() / "Documents" / "Local Instagram Unfollower"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


BG = "#0f0f13"
CARD = "#17171f"
CARD_2 = "#20202a"
LINE = "#2b2b38"
TEXT = "#f5f5f8"
MUTED = "#9a9aac"
MUTED_2 = "#6f6f82"
PINK = "#d92d8f"
PINK_HOVER = "#ec49a4"
DISABLED = "#3a3a48"
DISABLED_TEXT = "#777789"
LINK = "#f3a8cc"


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Local Instagram Unfollower")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        icon = _resource_path("assets/icon.ico")
        if icon.exists():
            try:
                self.root.iconbitmap(default=str(icon))
            except tk.TclError:
                pass

        self.selected_path: Path | None = None
        self._worker_events: queue.Queue = queue.Queue()
        self._working = False
        self._build_ui()

        self.root.update_idletasks()
        width = 700
        height = max(640, self.root.winfo_reqheight() + 16)
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 3)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(660, 600)

        if len(sys.argv) > 1:
            candidate = Path(sys.argv[1]).expanduser()
            if candidate.exists():
                self.select_path(candidate)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        tk.Frame(self.root, bg=PINK, height=4).pack(fill="x")

        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=28, pady=(24, 18))

        tk.Label(
            header,
            text="LOCAL / PRIVATE / READ-ONLY",
            bg=BG,
            fg=LINK,
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w")

        tk.Label(
            header,
            text="Local Instagram Unfollower",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 19, "bold"),
        ).pack(anchor="w", pady=(4, 2))

        tk.Label(
            header,
            text="See who doesn't follow you back. No login, no uploads, no terminal.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w")

        choose = self._card()
        self._step_title(choose, "STEP 1   CHOOSE YOUR EXPORT")
        tk.Label(
            choose,
            text="Auto-find looks in your Downloads, Desktop and Documents for an Instagram ZIP.",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9),
            wraplength=590,
            justify="left",
        ).pack(anchor="w", padx=18, pady=(4, 12))

        self.detect_btn = self._primary_button(
            choose, "AUTO-FIND MY EXPORT", self.auto_find
        )
        self.detect_btn.pack(fill="x", padx=18)

        button_row = tk.Frame(choose, bg=CARD)
        button_row.pack(fill="x", padx=18, pady=(9, 0))

        self.pick_zip_btn = self._secondary_button(
            button_row, "Pick ZIP file", self.pick_zip
        )
        self.pick_zip_btn.pack(side="left", expand=True, fill="x")

        self.pick_folder_btn = self._secondary_button(
            button_row, "Pick extracted folder", self.pick_folder
        )
        self.pick_folder_btn.pack(side="left", expand=True, fill="x", padx=(9, 0))

        self.help_btn = tk.Label(
            choose,
            text="How do I download my Instagram export?",
            bg=CARD,
            fg=LINK,
            font=("Segoe UI", 8, "underline"),
            cursor="hand2",
        )
        self.help_btn.pack(anchor="w", padx=18, pady=(11, 15))
        self.help_btn.bind("<Button-1>", lambda _event: self.show_help())

        selected = self._card()
        self._step_title(selected, "STEP 2   CHECK THE SELECTED EXPORT")

        selected_row = tk.Frame(selected, bg=CARD)
        selected_row.pack(fill="x", padx=18, pady=(5, 15))

        self.selected_label = tk.Label(
            selected_row,
            text="No export selected yet.",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9),
            wraplength=525,
            justify="left",
            anchor="w",
        )
        self.selected_label.pack(side="left", fill="x", expand=True)

        self.clear_btn = tk.Button(
            selected_row,
            text="Clear",
            command=self.clear_selection,
            bg=CARD,
            fg=MUTED_2,
            activebackground=CARD,
            activeforeground=TEXT,
            font=("Segoe UI", 8, "underline"),
            relief="flat",
            borderwidth=0,
            cursor="hand2",
        )
        self.clear_btn.pack(side="right", padx=(10, 0))
        self.clear_btn.pack_forget()

        self.generate_btn = tk.Button(
            self.root,
            text="STEP 3   GENERATE REPORT",
            command=self.generate_report,
            bg=DISABLED,
            fg=DISABLED_TEXT,
            activebackground=DISABLED,
            activeforeground=DISABLED_TEXT,
            disabledforeground=DISABLED_TEXT,
            font=("Segoe UI", 11, "bold"),
            relief="flat",
            padx=24,
            pady=13,
            cursor="arrow",
            state="disabled",
        )
        self.generate_btn.pack(fill="x", padx=28, pady=(2, 8))

        self.status_label = tk.Label(
            self.root,
            text="",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        )
        self.status_label.pack(pady=(0, 6))

        tk.Label(
            self.root,
            text="Nothing is uploaded. Unfollowing is still manual.",
            bg=BG,
            fg=MUTED_2,
            font=("Segoe UI", 8),
        ).pack(pady=(0, 14))

    def _card(self) -> tk.Frame:
        frame = tk.Frame(
            self.root,
            bg=CARD,
            highlightbackground=LINE,
            highlightthickness=1,
        )
        frame.pack(fill="x", padx=28, pady=(0, 12))
        return frame

    def _step_title(self, parent: tk.Frame, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=18, pady=(14, 0))

    def _primary_button(self, parent: tk.Widget, text: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=PINK,
            fg="white",
            activebackground=PINK_HOVER,
            activeforeground="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=18,
            pady=10,
            cursor="hand2",
        )

    def _secondary_button(self, parent: tk.Widget, text: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=CARD_2,
            fg=TEXT,
            activebackground="#2b2b38",
            activeforeground=TEXT,
            font=("Segoe UI", 9),
            relief="flat",
            padx=14,
            pady=8,
            cursor="hand2",
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def show_help(self) -> None:
        answer = messagebox.askyesno(
            "Get your Instagram export",
            "1. Open Instagram Accounts Center.\n"
            "2. Go to 'Your information and permissions'.\n"
            "3. Choose 'Download your information'.\n"
            "4. Select 'Some of your information'.\n"
            "5. Tick 'Followers and following' and choose JSON.\n"
            "6. Download the ZIP when Instagram is ready.\n\n"
            "Open Accounts Center now?",
        )
        if answer:
            webbrowser.open("https://accountscenter.instagram.com/")

    def auto_find(self) -> None:
        self.status_label.config(text="Searching your folders...")
        self.root.update_idletasks()

        home = Path.home()
        search_paths = [home / "Downloads", home / "Desktop", home / "Documents"]

        found: dict[str, Path] = {}
        for folder in search_paths:
            if not folder.exists():
                continue
            try:
                for item in folder.glob("*.zip"):
                    if "instagram" in item.name.lower():
                        found[str(item.resolve())] = item
            except OSError:
                continue

        exports = sorted(
            found.values(),
            key=lambda path: path.stat().st_mtime if path.exists() else 0,
            reverse=True,
        )

        if not exports:
            messagebox.showinfo(
                "No export found",
                "I couldn't find an Instagram ZIP in Downloads, Desktop or Documents.\n\n"
                "Click 'Pick ZIP file' and choose it yourself.",
            )
            self.status_label.config(text="")
            return

        if len(exports) == 1:
            self.select_path(exports[0])
            self.status_label.config(text=f"Found {exports[0].name}")
            return

        self._show_export_choices(exports)

    def _show_export_choices(self, exports: list[Path]) -> None:
        visible = exports[:6]
        window = tk.Toplevel(self.root)
        window.title("Pick your export")
        window.configure(bg=BG)
        window.resizable(False, False)
        window.transient(self.root)
        window.grab_set()

        width = 570
        height = 120 + len(visible) * 72 + (30 if len(exports) > 6 else 0)
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + 60
        window.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

        tk.Label(
            window,
            text="Which export should I use?",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", padx=20, pady=(18, 2))
        tk.Label(
            window,
            text="Newest first. Pick the ZIP you downloaded from Instagram.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=20, pady=(0, 12))

        for path in visible:
            row = tk.Frame(
                window,
                bg=CARD,
                highlightbackground=LINE,
                highlightthickness=1,
            )
            row.pack(fill="x", padx=20, pady=(0, 6))

            info = tk.Frame(row, bg=CARD)
            info.pack(side="left", fill="x", expand=True, padx=14, pady=9)

            tk.Label(
                info,
                text=path.name,
                bg=CARD,
                fg=TEXT,
                font=("Segoe UI", 9, "bold"),
                anchor="w",
                justify="left",
                wraplength=390,
            ).pack(anchor="w")
            tk.Label(
                info,
                text=str(path.parent),
                bg=CARD,
                fg=MUTED_2,
                font=("Segoe UI", 8),
                anchor="w",
                justify="left",
                wraplength=390,
            ).pack(anchor="w")

            tk.Button(
                row,
                text="Use this",
                command=lambda chosen=path: self._choose_export(chosen, window),
                bg=PINK,
                fg="white",
                activebackground=PINK_HOVER,
                activeforeground="white",
                font=("Segoe UI", 8, "bold"),
                relief="flat",
                padx=12,
                pady=5,
                cursor="hand2",
            ).pack(side="right", padx=12)

        if len(exports) > 6:
            tk.Label(
                window,
                text="Showing the 6 newest. Use 'Pick ZIP file' for an older export.",
                bg=BG,
                fg=MUTED_2,
                font=("Segoe UI", 8),
            ).pack(anchor="w", padx=20, pady=(2, 0))

        tk.Button(
            window,
            text="Cancel",
            command=window.destroy,
            bg=CARD_2,
            fg=TEXT,
            activebackground="#2b2b38",
            activeforeground=TEXT,
            font=("Segoe UI", 9),
            relief="flat",
            padx=18,
            pady=6,
            cursor="hand2",
        ).pack(pady=12)

    def _choose_export(self, path: Path, window: tk.Toplevel) -> None:
        self.select_path(path)
        self.status_label.config(text=f"Selected {path.name}")
        window.destroy()

    def pick_zip(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Instagram export ZIP",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
        )
        if path:
            self.select_path(Path(path))
            self.status_label.config(text=f"Selected {Path(path).name}")

    def pick_folder(self) -> None:
        path = filedialog.askdirectory(title="Select extracted Instagram export folder")
        if path:
            self.select_path(Path(path))
            self.status_label.config(text=f"Selected {Path(path).name}")

    def select_path(self, path: Path) -> None:
        self.selected_path = path
        self.selected_label.config(text=str(path), fg=TEXT)
        self.clear_btn.pack(side="right", padx=(10, 0))
        self.generate_btn.config(
            state="normal",
            bg=PINK,
            fg="white",
            activebackground=PINK_HOVER,
            activeforeground="white",
            cursor="hand2",
        )
        self.status_label.config(text="Ready to generate.")

    def clear_selection(self) -> None:
        self.selected_path = None
        self.selected_label.config(text="No export selected yet.", fg=MUTED)
        self.clear_btn.pack_forget()
        self.generate_btn.config(
            state="disabled",
            bg=DISABLED,
            fg=DISABLED_TEXT,
            activebackground=DISABLED,
            activeforeground=DISABLED_TEXT,
            cursor="arrow",
        )
        self.status_label.config(text="")

    def generate_report(self) -> None:
        if not self.selected_path:
            return

        self._set_busy(True)
        self._working = True
        self.status_label.config(
            text="Reading your export... this can take a few seconds."
        )
        self.root.update_idletasks()

        export_path = self.selected_path

        def worker() -> None:
            try:
                report_dir = _report_dir()
                out_path = report_dir / "instagram_unfollowers.html"
                payload = ig_audit.build_payload(export_path)
                ig_audit.write_report(out_path, payload)
                ig_audit.write_text_list(
                    report_dir / "instagram_unfollowers_not_following_back.txt",
                    payload["notFollowingBack"],
                )
                ig_audit.write_csv(
                    report_dir / "instagram_unfollowers_accounts.csv", payload
                )

                counts = payload["counts"]
                message = (
                    "Report generated.\n\n"
                    f"Following: {counts['following']:,}\n"
                    f"Followers: {counts['followers']:,}\n"
                    f"Not following back: {counts['notFollowingBack']:,}\n\n"
                    f"Saved in: {report_dir}\n\n"
                    "Opening it in your browser now."
                )
                self._worker_events.put(("success", message, out_path))
            except Exception as error:
                self._worker_events.put(("error", str(error), None))

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(100, self._poll_worker)

    def _poll_worker(self) -> None:
        try:
            kind, message, out_path = self._worker_events.get_nowait()
        except queue.Empty:
            if self._working:
                self.root.after(100, self._poll_worker)
            return

        self._working = False
        if kind == "success":
            messagebox.showinfo("Done", message)
            webbrowser.open(out_path.as_uri())
            self._finish(True)
        else:
            messagebox.showerror(
                "Could not read that export",
                f"{message}\n\n"
                "Make sure you downloaded Instagram's JSON export and "
                "selected 'Followers and following'.",
            )
            self._finish(False)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.detect_btn.config(state=state)
        self.pick_zip_btn.config(state=state)
        self.pick_folder_btn.config(state=state)
        self.clear_btn.config(state=state)
        if busy:
            self.generate_btn.config(
                state="disabled",
                text="GENERATING REPORT...",
                bg=DISABLED,
                fg=DISABLED_TEXT,
                cursor="arrow",
            )
        else:
            self.generate_btn.config(
                state="normal" if self.selected_path else "disabled",
                text="STEP 3   GENERATE REPORT",
                bg=PINK if self.selected_path else DISABLED,
                fg="white" if self.selected_path else DISABLED_TEXT,
                cursor="hand2" if self.selected_path else "arrow",
            )

    def _finish(self, success: bool) -> None:
        self._set_busy(False)
        self.status_label.config(
            text="Report opened in your browser."
            if success
            else "Could not generate the report. Try another export."
        )


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
