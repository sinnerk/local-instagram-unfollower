#!/usr/bin/env python3
"""Super simple GUI for Local Instagram Unfollower"""

import os
import sys
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Make sure we can import ig_audit from same folder
SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

import ig_audit


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Local Instagram Unfollower - EASY MODE")
        self.root.geometry("650x520")
        self.root.resizable(False, False)
        self.root.configure(bg="#0f0f13")

        # Style
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#0f0f13")
        style.configure(
            "TLabel", background="#0f0f13", foreground="#f5f5f8", font=("Segoe UI", 9)
        )
        style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Sub.TLabel", foreground="#9696a8")
        style.configure("TButton", font=("Segoe UI", 10))

        # Header
        header_frame = ttk.Frame(root)
        header_frame.pack(fill="x", padx=30, pady=(30, 10))

        ttk.Label(
            header_frame, text="LOCAL INSTAGRAM UNFOLLOWER", style="Header.TLabel"
        ).pack(anchor="w")
        ttk.Label(
            header_frame,
            text="Find out who doesn't follow you back. 100% local. No login.",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(5, 0))

        # Auto-detect section
        detect_frame = tk.Frame(
            root, bg="#15151c", highlightbackground="#282834", highlightthickness=1
        )
        detect_frame.pack(fill="x", padx=30, pady=20)

        tk.Label(
            detect_frame,
            text="STEP 1: FIND YOUR EXPORT",
            bg="#15151c",
            fg="#f5f5f8",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=20, pady=(15, 5))
        tk.Label(
            detect_frame,
            text="We'll look in your Downloads and Desktop for instagram export ZIPs",
            bg="#15151c",
            fg="#9696a8",
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=20)

        self.detect_btn = tk.Button(
            detect_frame,
            text="🔍 AUTO-FIND EXPORT",
            command=self.auto_find,
            bg="#d92d8f",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=20,
            pady=10,
            cursor="hand2",
        )
        self.detect_btn.pack(anchor="w", padx=20, pady=(10, 15))

        # Manual pick section
        pick_frame = tk.Frame(
            root, bg="#15151c", highlightbackground="#282834", highlightthickness=1
        )
        pick_frame.pack(fill="x", padx=30, pady=(0, 20))

        tk.Label(
            pick_frame,
            text="STEP 2: OR PICK IT YOURSELF",
            bg="#15151c",
            fg="#f5f5f8",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=20, pady=(15, 5))
        tk.Label(
            pick_frame,
            text="Pick the .ZIP file you downloaded from Instagram",
            bg="#15151c",
            fg="#9696a8",
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=20)

        btn_frame = tk.Frame(pick_frame, bg="#15151c")
        btn_frame.pack(anchor="w", padx=20, pady=(10, 15))

        self.pick_zip_btn = tk.Button(
            btn_frame,
            text="📁 Pick ZIP File",
            command=self.pick_zip,
            bg="#242430",
            fg="#f5f5f8",
            font=("Segoe UI", 9),
            relief="flat",
            padx=15,
            pady=8,
            cursor="hand2",
        )
        self.pick_zip_btn.pack(side="left")

        self.pick_folder_btn = tk.Button(
            btn_frame,
            text="📂 Pick Extracted Folder",
            command=self.pick_folder,
            bg="#242430",
            fg="#f5f5f8",
            font=("Segoe UI", 9),
            relief="flat",
            padx=15,
            pady=8,
            cursor="hand2",
        )
        self.pick_folder_btn.pack(side="left", padx=(10, 0))

        # Selected file
        self.selected_frame = tk.Frame(
            root, bg="#15151c", highlightbackground="#282834", highlightthickness=1
        )
        self.selected_frame.pack(fill="x", padx=30, pady=(0, 20))

        tk.Label(
            self.selected_frame,
            text="SELECTED:",
            bg="#15151c",
            fg="#9696a8",
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w", padx=20, pady=(15, 5))
        self.selected_label = tk.Label(
            self.selected_frame,
            text="None",
            bg="#15151c",
            fg="#f5f5f8",
            font=("Segoe UI", 9),
            wraplength=580,
            justify="left",
        )
        self.selected_label.pack(anchor="w", padx=20)

        self.clear_btn = tk.Button(
            self.selected_frame,
            text="Clear",
            command=self.clear_selection,
            bg="#15151c",
            fg="#9696a8",
            font=("Segoe UI", 8),
            relief="flat",
            cursor="hand2",
            borderwidth=0,
        )
        self.clear_btn.pack(anchor="w", padx=20, pady=(5, 15))
        self.clear_btn.pack_forget()

        # Generate button
        self.generate_btn = tk.Button(
            root,
            text="✨ GENERATE REPORT",
            command=self.generate_report,
            bg="#3a3a48",
            fg="#6e6e80",
            font=("Segoe UI", 12, "bold"),
            relief="flat",
            padx=30,
            pady=15,
            cursor="arrow",
            state="disabled",
        )
        self.generate_btn.pack(pady=10)

        # Status
        self.status_label = tk.Label(
            root, text="", bg="#0f0f13", fg="#9696a8", font=("Segoe UI", 9)
        )
        self.status_label.pack(pady=(5, 20))

        self.selected_path = None

    def auto_find(self):
        self.status_label.config(text="Searching...")
        self.root.update()

        search_paths = []
        home = Path.home()
        search_paths.extend([home / "Downloads", home / "Desktop", home / "Documents"])

        found = []
        for sp in search_paths:
            if sp.exists():
                for item in sp.glob("instagram*.zip"):
                    found.append(item)
                for item in sp.glob("*instagram*.zip"):
                    if item not in found:
                        found.append(item)

        if not found:
            messagebox.showinfo(
                "No exports found",
                "Couldn't find any 'instagram*.zip' files in Downloads/Desktop/Documents.\n\nJust click 'Pick ZIP File' instead.",
            )
            self.status_label.config(text="")
            return

        # Sort by newest first
        found.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        if len(found) == 1:
            self.select_path(found[0])
            self.status_label.config(text=f"Found: {found[0].name}")
        else:
            # Show choice
            win = tk.Toplevel(self.root)
            win.title("Pick your export")
            win.geometry("500x300")
            win.configure(bg="#0f0f13")
            win.resizable(False, False)
            win.grab_set()

            tk.Label(
                win,
                text="Found multiple exports - pick yours:",
                bg="#0f0f13",
                fg="#f5f5f8",
                font=("Segoe UI", 11, "bold"),
            ).pack(anchor="w", padx=20, pady=(20, 10))

            for f in found:
                frame = tk.Frame(
                    win,
                    bg="#15151c",
                    highlightbackground="#282834",
                    highlightthickness=1,
                )
                frame.pack(fill="x", padx=20, pady=5)
                tk.Label(
                    frame, text=f.name, bg="#15151c", fg="#f5f5f8", font=("Segoe UI", 9)
                ).pack(anchor="w", padx=15, pady=(10, 2))
                tk.Label(
                    frame,
                    text=f.parent.name,
                    bg="#15151c",
                    fg="#9696a8",
                    font=("Segoe UI", 8),
                ).pack(anchor="w", padx=15, pady=(0, 10))
                btn = tk.Button(
                    frame,
                    text="Select",
                    command=lambda x=f, w=win: [self.select_path(x), w.destroy()],
                    bg="#d92d8f",
                    fg="white",
                    font=("Segoe UI", 8),
                    relief="flat",
                    padx=12,
                    pady=4,
                )
                btn.place(relx=0.98, rely=0.5, anchor="e")

            tk.Button(
                win,
                text="Cancel",
                command=win.destroy,
                bg="#242430",
                fg="#f5f5f8",
                font=("Segoe UI", 9),
                relief="flat",
                padx=15,
                pady=6,
            ).pack(pady=15)

    def pick_zip(self):
        path = filedialog.askopenfilename(
            title="Select Instagram export ZIP",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
        )
        if path:
            self.select_path(Path(path))

    def pick_folder(self):
        path = filedialog.askdirectory(title="Select extracted Instagram export folder")
        if path:
            self.select_path(Path(path))

    def select_path(self, path):
        self.selected_path = path
        self.selected_label.config(text=str(path))
        self.clear_btn.pack(anchor="w", padx=20, pady=(5, 15))
        self.generate_btn.config(
            state="normal", bg="#d92d8f", fg="white", cursor="hand2"
        )
        self.status_label.config(text="Ready to generate!")

    def clear_selection(self):
        self.selected_path = None
        self.selected_label.config(text="None")
        self.clear_btn.pack_forget()
        self.generate_btn.config(
            state="disabled", bg="#3a3a48", fg="#6e6e80", cursor="arrow"
        )
        self.status_label.config(text="")

    def generate_report(self):
        if not self.selected_path:
            return

        self.generate_btn.config(
            state="disabled", text="⏳ GENERATING...", bg="#3a3a48"
        )
        self.detect_btn.config(state="disabled")
        self.pick_zip_btn.config(state="disabled")
        self.pick_folder_btn.config(state="disabled")
        self.clear_btn.config(state="disabled")
        self.status_label.config(text="Reading your export... this might take a second")
        self.root.update()

        def run():
            try:
                out_path = SCRIPT_DIR / "instagram_unfollowers.html"
                payload = ig_audit.build_payload(self.selected_path)
                ig_audit.write_report(out_path, payload)
                txt_path = SCRIPT_DIR / "instagram_unfollowers_not_following_back.txt"
                csv_path = SCRIPT_DIR / "instagram_unfollowers_accounts.csv"
                ig_audit.write_text_list(txt_path, payload["notFollowingBack"])
                ig_audit.write_csv(csv_path, payload)

                counts = payload["counts"]
                msg = f"Done!\n\nFollowing: {counts['following']:,}\nFollowers: {counts['followers']:,}\nNot following back: {counts['notFollowingBack']:,}\n\nOpening report in your browser..."

                self.root.after(
                    0,
                    lambda: [
                        messagebox.showinfo("Success!", msg),
                        webbrowser.open(out_path.as_uri()),
                        self.finish(),
                    ],
                )
            except Exception as e:
                self.root.after(
                    0, lambda: [messagebox.showerror("Error", str(e)), self.finish()]
                )

        threading.Thread(target=run, daemon=True).start()

    def finish(self):
        self.generate_btn.config(
            state="normal",
            text="✨ GENERATE REPORT",
            bg="#d92d8f",
            fg="white",
            cursor="hand2",
        )
        self.detect_btn.config(state="normal")
        self.pick_zip_btn.config(state="normal")
        self.pick_folder_btn.config(state="normal")
        self.clear_btn.config(state="normal")
        self.status_label.config(text="Report opened in browser!")


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
