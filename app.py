import os
import winreg
import ctypes
import threading
import subprocess
import re
import tempfile
import hashlib
import customtkinter as ctk
from tkinter import filedialog
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

ctk.set_appearance_mode("Dark")

# Constants
COLOR_BG = "#121212"
COLOR_FRAME = "#1E1E1E"
COLOR_ACCENT = "#00E5FF"
COLOR_ACCENT_HOVER = "#00B8CC"
COLOR_TEXTBOX_BG = "#0D0D0D"
COLOR_BUTTON_BG = "#2A2A2A"
COLOR_BUTTON_HOVER = "#3A3A3A"
COLOR_TEXT = "#FFFFFF"
COLOR_TEXT_SECONDARY = "#A0A0A0"
COLOR_CANCEL = "#C62828"
COLOR_CANCEL_HOVER = "#2A0A0A"
PROGRESS_UPDATE_INTERVAL = 5


class NexusCompressor(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Nexus Game Compressor")
        self.geometry("750x760")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG)

        self.steam_games = self.find_steam_games()
        self.selected_path = ""
        self.total_files = 0
        self.processed_files = 0
        self.max_cpu_threads = os.cpu_count() or 4
        self.is_scanning = False
        self.is_processing = False
        self.cancel_event = threading.Event()
        self.file_lock = threading.Lock()
        self.progress_lock = threading.Lock()

        self.blacklist = {
            '.mp4', '.avi', '.mkv', '.webm', '.bik',
            '.mp3', '.wav', '.ogg', '.flac',
            '.zip', '.rar', '.7z', '.tar', '.gz', '.gguf'
        }

        self.build_ui()

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def _ui(self, func, *args, **kwargs):
        """Thread-safe UI update helper."""
        self.after(0, lambda: func(*args, **kwargs))

    def safe_log(self, message):
        def update():
            self.textbox_log.configure(state="normal")
            self.textbox_log.insert("end", message + "\n")
            self.textbox_log.see("end")
            self.textbox_log.configure(state="disabled")
        self.after(0, update)

    def safe_progress(self, value):
        self._ui(self.progressbar.set, value)

    # ------------------------------------------------------------------
    # UI state
    # ------------------------------------------------------------------
    def disable_ui_state(self):
        self._ui(self.btn_compress.configure, state="disabled")
        self._ui(self.btn_decompress.configure, state="disabled")
        self._ui(self.combo_games.configure, state="disabled")
        self._ui(self.btn_browse.configure, state="disabled")
        self._ui(self.btn_cancel.configure, state="normal")

    def reset_ui_state(self):
        self._ui(self.btn_compress.configure, state="normal")
        self._ui(self.btn_decompress.configure, state="normal")
        self._ui(self.btn_cancel.configure, state="disabled")
        self._ui(self.combo_games.configure, state="normal")
        self._ui(self.btn_browse.configure, state="normal")

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------
    def build_ui(self):
        self.grid_columnconfigure(0, weight=1)

        self.lbl_title = ctk.CTkLabel(
            self, text="NEXUS COMPRESSOR",
            font=ctk.CTkFont(family="Segoe UI Black", size=28, weight="bold"),
            text_color=COLOR_ACCENT
        )
        self.lbl_title.grid(row=0, column=0, pady=(25, 15))

        # -- selection frame --
        self.frame_select = ctk.CTkFrame(self, fg_color=COLOR_FRAME, corner_radius=8)
        self.frame_select.grid(row=1, column=0, padx=40, pady=5, sticky="ew")

        self.lbl_steam = ctk.CTkLabel(
            self.frame_select, text="Steam:",
            font=ctk.CTkFont(size=14, weight="bold"), text_color="#E0E0E0"
        )
        self.lbl_steam.pack(pady=(15, 5))

        game_names = ["Select game..."] + list(self.steam_games.keys())
        self.combo_games = ctk.CTkOptionMenu(
            self.frame_select, values=game_names,
            command=self.on_steam_select, width=400,
            fg_color=COLOR_BUTTON_BG, button_color=COLOR_ACCENT,
            button_hover_color=COLOR_ACCENT_HOVER, text_color=COLOR_TEXT
        )
        self.combo_games.pack(pady=(0, 15))

        self.frame_manual = ctk.CTkFrame(self.frame_select, fg_color="transparent")
        self.frame_manual.pack(pady=(5, 15))

        self.entry_path = ctk.CTkEntry(
            self.frame_manual,
            placeholder_text="Or select path manually...",
            width=300, border_color=COLOR_BUTTON_BG, fg_color=COLOR_BG
        )
        self.entry_path.pack(side="left", padx=(0, 10))

        self.btn_browse = ctk.CTkButton(
            self.frame_manual, text="Select", width=90,
            fg_color=COLOR_BUTTON_BG, hover_color=COLOR_BUTTON_HOVER,
            command=self.browse_folder
        )
        self.btn_browse.pack(side="left")

        # -- settings frame --
        self.frame_settings = ctk.CTkFrame(self, fg_color=COLOR_FRAME, corner_radius=8)
        self.frame_settings.grid(row=2, column=0, padx=40, pady=10, sticky="ew")
        self.frame_settings.grid_columnconfigure((0, 1), weight=1)

        self.frame_drive_type = ctk.CTkFrame(self.frame_settings, fg_color="transparent")
        self.frame_drive_type.grid(row=0, column=0, padx=20, pady=15, sticky="w")

        self.lbl_drive_type = ctk.CTkLabel(
            self.frame_drive_type, text="Disk type:",
            font=ctk.CTkFont(weight="bold"), text_color=COLOR_TEXT_SECONDARY
        )
        self.lbl_drive_type.pack(anchor="w", pady=(0, 5))

        self.drive_var = ctk.StringVar(value="SSD")

        self.radio_ssd = ctk.CTkRadioButton(
            self.frame_drive_type, text="SSD (Multithreading)",
            variable=self.drive_var, value="SSD",
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            command=self.on_drive_change
        )
        self.radio_ssd.pack(anchor="w", pady=(5, 5))

        self.radio_hdd = ctk.CTkRadioButton(
            self.frame_drive_type, text="HDD (1 thread)",
            variable=self.drive_var, value="HDD",
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            command=self.on_drive_change
        )
        self.radio_hdd.pack(anchor="w")

        self.frame_cpu = ctk.CTkFrame(self.frame_settings, fg_color="transparent")
        self.frame_cpu.grid(row=0, column=1, padx=20, pady=15, sticky="e")

        self.lbl_cpu = ctk.CTkLabel(
            self.frame_cpu,
            text=f"CPU load: {self.max_cpu_threads} out of {self.max_cpu_threads} threads (100%)",
            font=ctk.CTkFont(weight="bold"), text_color=COLOR_TEXT_SECONDARY,
            width=280, anchor="center"
        )
        self.lbl_cpu.pack(pady=(0, 5))

        steps = max(1, self.max_cpu_threads - 1)
        self.slider_cpu = ctk.CTkSlider(
            self.frame_cpu, from_=1, to=self.max_cpu_threads,
            number_of_steps=steps, width=260,
            progress_color=COLOR_ACCENT, button_color=COLOR_ACCENT,
            button_hover_color=COLOR_ACCENT_HOVER,
            command=self.on_slider_change
        )
        self.slider_cpu.set(self.max_cpu_threads)
        self.slider_cpu.pack(pady=(10, 0))

        # -- stats frame --
        self.frame_stats = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_stats.grid(row=3, column=0, padx=40, pady=5, sticky="ew")
        self.frame_stats.grid_columnconfigure((0, 1), weight=1)

        self.lbl_total_size = ctk.CTkLabel(
            self.frame_stats, text="Total Size: 0.00 MB",
            font=ctk.CTkFont(size=14)
        )
        self.lbl_total_size.grid(row=0, column=0, sticky="w", padx=10, pady=(0, 2))

        self.lbl_compressed_size = ctk.CTkLabel(
            self.frame_stats, text="On Disk: 0.00 MB",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=COLOR_ACCENT
        )
        self.lbl_compressed_size.grid(row=0, column=1, sticky="e", padx=10, pady=(0, 2))

        self.lbl_compressible_size = ctk.CTkLabel(
            self.frame_stats, text="Available for compression: 0.00 MB",
            font=ctk.CTkFont(size=14), text_color=COLOR_TEXT_SECONDARY
        )
        self.lbl_compressible_size.grid(row=1, column=0, sticky="w", padx=10)

        # -- progress bar --
        self.progressbar = ctk.CTkProgressBar(
            self, width=670, height=8,
            progress_color=COLOR_ACCENT, fg_color=COLOR_BUTTON_BG
        )
        self.progressbar.grid(row=4, column=0, padx=40, pady=(10, 10))
        self.progressbar.set(0)

        # -- log --
        self.textbox_log = ctk.CTkTextbox(
            self, height=130, corner_radius=8,
            fg_color=COLOR_TEXTBOX_BG, text_color=COLOR_ACCENT,
            border_width=1, border_color=COLOR_BUTTON_BG,
            state="disabled",
            font=ctk.CTkFont(family="Consolas", size=12)
        )
        self.textbox_log.grid(row=5, column=0, padx=40, pady=5, sticky="ew")

        # -- action buttons --
        self.frame_actions = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_actions.grid(row=6, column=0, padx=40, pady=15)
        self.frame_actions.grid_columnconfigure((0, 1), weight=1)

        self.btn_compress = ctk.CTkButton(
            self.frame_actions, text="COMPRESS",
            font=ctk.CTkFont(weight="bold", size=14),
            fg_color=COLOR_ACCENT, text_color=COLOR_BG,
            hover_color=COLOR_ACCENT_HOVER, height=45, width=205,
            command=self.start_compression
        )
        self.btn_compress.grid(row=0, column=0, padx=(0, 10))

        self.btn_decompress = ctk.CTkButton(
            self.frame_actions, text="DECOMPRESS",
            font=ctk.CTkFont(weight="bold", size=14),
            fg_color="transparent", text_color=COLOR_ACCENT,
            border_width=2, border_color=COLOR_ACCENT,
            hover_color=COLOR_FRAME, height=45, width=205,
            command=self.start_decompression
        )
        self.btn_decompress.grid(row=0, column=1, padx=(10, 0))

        self.btn_cancel = ctk.CTkButton(
            self.frame_actions, text="CANCEL",
            font=ctk.CTkFont(weight="bold", size=14),
            fg_color="transparent", text_color=COLOR_CANCEL,
            border_width=2, border_color=COLOR_CANCEL,
            hover_color=COLOR_CANCEL_HOVER, height=45, width=430,
            command=self.cancel_operation, state="disabled"
        )
        self.btn_cancel.grid(row=1, column=0, columnspan=2, pady=(15, 0))

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    def on_slider_change(self, value):
        threads = int(value)
        percent = int((threads / self.max_cpu_threads) * 100)
        self._ui(
            self.lbl_cpu.configure,
            text=f"CPU load: {threads} out of {self.max_cpu_threads} threads ({percent}%)"
        )

    def on_drive_change(self):
        if self.drive_var.get() == "HDD":
            self.slider_cpu.set(1)
            self._ui(self.slider_cpu.configure, state="disabled")
            self._ui(self.lbl_cpu.configure, text="CPU load: HDD (1 thread)")
            self.safe_log("[!] HDD mode enabled. Multithreading disabled.")
        else:
            self._ui(self.slider_cpu.configure, state="normal")
            self.slider_cpu.set(self.max_cpu_threads)
            self.on_slider_change(self.max_cpu_threads)
            self.safe_log("[*] SSD mode enabled. Multithreading activated.")

    def browse_folder(self):
        if self.is_scanning:
            return
        folder = filedialog.askdirectory()
        if folder:
            self.combo_games.set("Select game...")
            self.entry_path.delete(0, "end")
            self.entry_path.insert(0, folder)
            self.selected_path = os.path.normpath(folder)
            self.safe_log(f"[*] Directory: {self.selected_path}")
            threading.Thread(target=self.calculate_sizes, daemon=True).start()

    def on_steam_select(self, choice):
        if self.is_scanning:
            return
        if choice in self.steam_games:
            self.entry_path.delete(0, "end")
            self.selected_path = os.path.normpath(self.steam_games[choice])
            self.safe_log(f"[*] Game: {self.selected_path}")
            threading.Thread(target=self.calculate_sizes, daemon=True).start()

    def cancel_operation(self):
        self.safe_log("[!] Cancellation requested. Waiting for current files to finish...")
        self.cancel_event.set()
        self._ui(self.btn_cancel.configure, state="disabled")

    # ------------------------------------------------------------------
    # Drive detection
    # ------------------------------------------------------------------
    def detect_drive_type(self, path):
        try:
            drive_letter = os.path.splitdrive(path)[0].replace(':', '')
            if not drive_letter:
                return "SSD"

            cmd = [
                'powershell', '-NoProfile', '-Command',
                f"try {{ $d = (Get-Partition -DriveLetter '{drive_letter}').DiskNumber; "
                f"(Get-PhysicalDisk | Where-Object DeviceID -eq $d).MediaType }} catch {{ 'Unknown' }}"
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            media_type = result.stdout.strip()

            if "HDD" in media_type:
                return "HDD"
            return "SSD"
        except Exception:
            # Default to SSD on detection failure
            return "SSD"

    def apply_drive_detection(self, path):
        detected_type = self.detect_drive_type(path)
        self._ui(self.drive_var.set, detected_type)
        self.on_drive_change()

    # ------------------------------------------------------------------
    # Steam discovery
    # ------------------------------------------------------------------
    def find_steam_games(self):
        games = {}
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\WOW6432Node\Valve\Steam"
            )
            steam_path, _ = winreg.QueryValueEx(key, "InstallPath")
            winreg.CloseKey(key)
        except (FileNotFoundError, OSError, WindowsError):
            # Steam not installed or registry inaccessible
            return games

        vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
        if not os.path.exists(vdf_path):
            return games

        try:
            with open(vdf_path, "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            return games

        paths = re.findall(r'"path"\s+"([^"]+)"', content)

        for path in paths:
            lib_path = path.replace("\\\\", "\\")
            steamapps_dir = os.path.join(lib_path, "steamapps")

            if not os.path.isdir(steamapps_dir):
                continue

            try:
                entries = os.listdir(steamapps_dir)
            except OSError:
                continue

            for file in entries:
                if file.startswith("appmanifest_") and file.endswith(".acf"):
                    manifest_path = os.path.join(steamapps_dir, file)
                    try:
                        with open(manifest_path, "r", encoding="utf-8") as mf:
                            m_content = mf.read()
                        name_match = re.search(r'"name"\s+"([^"]+)"', m_content)
                        dir_match = re.search(r'"installdir"\s+"([^"]+)"', m_content)

                        if name_match and dir_match:
                            game_name = name_match.group(1)
                            install_dir = dir_match.group(1)
                            full_path = os.path.join(steamapps_dir, "common", install_dir)

                            if os.path.isdir(full_path):
                                games[game_name] = full_path
                    except (OSError, UnicodeDecodeError):
                        continue
        return games

    # ------------------------------------------------------------------
    # File / size helpers
    # ------------------------------------------------------------------
    def get_compressed_size(self, filepath):
        abs_path = os.path.abspath(filepath)
        if not abs_path.startswith("\\\\?\\"):
            abs_path = "\\\\?\\" + abs_path

        try:
            high = ctypes.c_uint32()
            ctypes.windll.kernel32.GetCompressedFileSizeW.restype = ctypes.c_uint32
            low = ctypes.windll.kernel32.GetCompressedFileSizeW(
                ctypes.c_wchar_p(abs_path), ctypes.byref(high)
            )
            if low == 0xFFFFFFFF and ctypes.GetLastError() != 0:
                return os.path.getsize(filepath)
            return (high.value << 32) + low
        except Exception:
            return os.path.getsize(filepath)

    def get_all_files(self):
        file_list = []
        try:
            for root, _, files in os.walk(self.selected_path, followlinks=True):
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext not in self.blacklist:
                        file_list.append(os.path.join(root, file))
        except (OSError, RecursionError) as e:
            self.safe_log(f"[WARN] Error scanning files: {e}")
            return []
        return file_list

    def get_state_file(self):
        path_hash = hashlib.md5(self.selected_path.encode('utf-8')).hexdigest()
        return os.path.join(tempfile.gettempdir(), f"nexus_{path_hash}.txt")

    def format_size(self, size_in_bytes):
        if size_in_bytes >= 1024 ** 3:
            return f"{size_in_bytes / (1024 ** 3):.2f} GB"
        return f"{size_in_bytes / (1024 ** 2):.2f} MB"

    # ------------------------------------------------------------------
    # Size calculation (scan)
    # ------------------------------------------------------------------
    def calculate_sizes(self, silent=False):
        if not self.selected_path or not os.path.isdir(self.selected_path):
            return

        self.is_scanning = True
        self._ui(self.btn_compress.configure, state="disabled")
        self._ui(self.btn_decompress.configure, state="disabled")
        self._ui(self.btn_browse.configure, state="disabled")
        self._ui(self.combo_games.configure, state="disabled")

        if not silent:
            self.apply_drive_detection(self.selected_path)
            self.safe_log("[*] Analysis in progress...")

        total_original = 0
        total_compressed = 0
        compressible_size = 0

        file_list = self.get_all_files()
        # Only set total_files here — run_compact_multithreaded must not overwrite it
        self.total_files = len(file_list)

        for filepath in file_list:
            try:
                size = os.path.getsize(filepath)
                comp_size = self.get_compressed_size(filepath)

                total_original += size
                total_compressed += comp_size

                # File is not already compressed → available for compression
                if comp_size > size:
                    compressible_size += size
            except Exception:
                continue

        self._ui(
            self.lbl_total_size.configure,
            text=f"Total Size: {self.format_size(total_original)}"
        )
        self._ui(
            self.lbl_compressed_size.configure,
            text=f"On Disk: {self.format_size(total_compressed)}"
        )
        self._ui(
            self.lbl_compressible_size.configure,
            text=f"Available for compression: {self.format_size(compressible_size)}"
        )

        if not silent:
            self.safe_log(f"[*] Files found for processing: {self.total_files}")

        self._ui(self.btn_compress.configure, state="normal")
        self._ui(self.btn_decompress.configure, state="normal")
        self._ui(self.btn_browse.configure, state="normal")
        self._ui(self.combo_games.configure, state="normal")
        self.is_scanning = False

    # ------------------------------------------------------------------
    # Single file compact / decompress worker
    # ------------------------------------------------------------------
    def process_single_file(self, filepath, action):
        if self.cancel_event.is_set():
            return filepath, False

        abs_path = os.path.abspath(filepath)

        if action == "compress":
            cmd = ['compact', '/c', '/exe:lzx', abs_path]
        else:
            cmd = ['compact', '/u', abs_path]

        try:
            subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW, check=False
            )
            return filepath, True
        except Exception:
            return filepath, False

    # ------------------------------------------------------------------
    # Main async worker
    # ------------------------------------------------------------------
    def run_compact_multithreaded(self, action):
        if not self.selected_path:
            self.safe_log("[ERROR] Directory not selected.")
            return

        self.is_processing = True
        self.disable_ui_state()
        self.cancel_event.clear()
        self.safe_progress(0)

        file_list = self.get_all_files()
        state_file = self.get_state_file()
        processed_set = set()

        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    processed_set = set(f.read().splitlines())
                self.safe_log(
                    f"[*] Save file found. Resuming from {len(processed_set)} files."
                )
            except Exception:
                pass

        pending_files = [f for f in file_list if f not in processed_set]
        total = len(file_list)
        processed_count = len(processed_set)

        if not pending_files:
            self.safe_log("[!] No files to process, or all files have already been processed.")
            self._cleanup_state(state_file)
            self.safe_progress(1.0)
            self.is_processing = False
            self.reset_ui_state()
            return

        if self.drive_var.get() == "HDD":
            active_threads = 1
        else:
            active_threads = int(self.slider_cpu.get())

        self.safe_log(f"[*] Started. Threads: {active_threads}. Processing...")

        # Submit files one batch at a time so we can stop mid-way on cancel
        pending_iter = iter(pending_files)

        with ThreadPoolExecutor(max_workers=active_threads) as executor:
            # Prime the executor with initial batch
            futures = set()
            for _ in range(active_threads * 2):
                try:
                    f = next(pending_iter)
                    futures.add(executor.submit(self.process_single_file, f, action))
                except StopIteration:
                    break

            while futures and not self.cancel_event.is_set():
                done, futures = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    completed_file, success = future.result()
                    with self.file_lock:
                        processed_count += 1
                        if success:
                            try:
                                with open(state_file, 'a', encoding='utf-8') as sf:
                                    sf.write(completed_file + '\n')
                            except OSError:
                                pass

                # Refill with next file(s)
                try:
                    next_file = next(pending_iter)
                    futures.add(
                        executor.submit(self.process_single_file, next_file, action)
                    )
                except StopIteration:
                    pass

                # Update progress smoothly
                progress = min(processed_count / max(total, 1), 1.0)
                self.safe_progress(progress)

        # ── post-processing ──
        self._cleanup_state(state_file)

        if self.cancel_event.is_set():
            self.safe_log("[*] Operation was cancelled by the user.")
        else:
            self.safe_progress(1.0)
            self.safe_log("[*] Operation completed successfully.")

        self.calculate_sizes(silent=True)
        self.is_processing = False
        self.reset_ui_state()

    # ------------------------------------------------------------------
    # State file helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _cleanup_state(state_file):
        try:
            if os.path.exists(state_file):
                os.remove(state_file)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------
    def start_compression(self):
        if self.total_files == 0 or self.is_scanning or self.is_processing:
            self.safe_log("[ERROR] Wait for scan to complete or specify a valid folder.")
            return
        threading.Thread(
            target=self.run_compact_multithreaded, args=("compress",), daemon=True
        ).start()

    def start_decompression(self):
        if self.total_files == 0 or self.is_scanning or self.is_processing:
            self.safe_log("[ERROR] Wait for scan to complete or specify a valid folder.")
            return
        threading.Thread(
            target=self.run_compact_multithreaded, args=("decompress",), daemon=True
        ).start()


if __name__ == "__main__":
    app = NexusCompressor()
    app.mainloop()
