import os, winreg, ctypes, threading, subprocess, re, tempfile, hashlib
import customtkinter as ctk
from tkinter import filedialog
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

ctk.set_appearance_mode("Dark")

BG, FRAME, ACCENT, AC_HVR = "#121212", "#1E1E1E", "#00E5FF", "#00B8CC"
TXTBG, BTN_BG, BTN_HVR = "#0D0D0D", "#2A2A2A", "#3A3A3A"
TXT, TXT2 = "#FFFFFF", "#A0A0A0"
CNCL, CNCL_HVR = "#C62828", "#2A0A0A"
BUF_LIMIT = 100

BLACKLIST = {'.mp4','.avi','.mkv','.webm','.bik','.mp3','.wav','.ogg','.flac',
             '.zip','.rar','.7z','.tar','.gz','.gguf'}


class NexusCompressor(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Nexus Game Compressor")
        self.geometry("750x760")
        self.resizable(False, False)
        self.configure(fg_color=BG)

        self.steam_games = self._find_steam_games()
        self.selected_path = ""
        self.total_files = 0
        self.max_threads = os.cpu_count() or 4
        self.is_processing = False
        self.cancel_event = threading.Event()
        self.buf_lock = threading.Lock()
        self.scan_lock = threading.Lock()
        self.drive_lock = threading.Lock()
        self._cache_path = None
        self._cache_type = None

        ctypes.windll.kernel32.GetCompressedFileSizeW.restype = ctypes.c_uint32

        self.build_ui()
        self.drive_var.trace_add("write", lambda *_: self._ui(self.apply_drive_mode))

    def _ui(self, fn, *a, **kw):
        self.after(0, lambda: fn(*a, **kw))

    def log(self, msg):
        def _():
            self.tb.configure(state="normal")
            self.tb.insert("end", msg + "\n")
            self.tb.see("end")
            self.tb.configure(state="disabled")
        self.after(0, _)

    def disable_ui(self):
        for b in (self.btn_c, self.btn_d, self.combo, self.btn_b):
            self._ui(b.configure, state="disabled")
        self._ui(self.btn_x.configure, state="normal")

    def reset_ui(self):
        for b in (self.btn_c, self.btn_d, self.btn_x):
            self._ui(b.configure, state="normal" if b != self.btn_x else "disabled")
        self._ui(self.combo.configure, state="normal")
        self._ui(self.btn_b.configure, state="normal")

    def build_ui(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="NEXUS COMPRESSOR",
            font=ctk.CTkFont(family="Segoe UI Black", size=28, weight="bold"),
            text_color=ACCENT).grid(row=0, column=0, pady=(25, 15))

        sf = ctk.CTkFrame(self, fg_color=FRAME, corner_radius=8)
        sf.grid(row=1, column=0, padx=40, pady=5, sticky="ew")
        ctk.CTkLabel(sf, text="Steam:", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#E0E0E0").pack(pady=(15, 5))
        names = ["Select game..."] + list(self.steam_games.keys())
        self.combo = ctk.CTkOptionMenu(sf, values=names,
            command=self.on_steam, width=400,
            fg_color=BTN_BG, button_color=ACCENT,
            button_hover_color=AC_HVR, text_color=TXT)
        self.combo.pack(pady=(0, 15))

        mf = ctk.CTkFrame(sf, fg_color="transparent")
        mf.pack(pady=(5, 15))
        self.entry = ctk.CTkEntry(mf,
            placeholder_text="Or select path manually...",
            width=300, border_color=BTN_BG, fg_color=BG)
        self.entry.pack(side="left", padx=(0, 10))
        self.entry.bind("<Return>", lambda e: self._on_enter())
        self.btn_b = ctk.CTkButton(mf, text="Select", width=90,
            fg_color=BTN_BG, hover_color=BTN_HVR, command=self.browse)
        self.btn_b.pack(side="left")

        sf2 = ctk.CTkFrame(self, fg_color=FRAME, corner_radius=8)
        sf2.grid(row=2, column=0, padx=40, pady=10, sticky="ew")
        sf2.grid_columnconfigure((0, 1), weight=1)

        df = ctk.CTkFrame(sf2, fg_color="transparent")
        df.grid(row=0, column=0, padx=20, pady=15, sticky="w")
        ctk.CTkLabel(df, text="Disk type:", font=ctk.CTkFont(weight="bold"),
                     text_color=TXT2).pack(anchor="w", pady=(0, 5))
        self.drive_var = ctk.StringVar(value="SSD")
        for t, v in [("SSD (Multithreading)", "SSD"), ("HDD (1 thread)", "HDD")]:
            ctk.CTkRadioButton(df, text=t, variable=self.drive_var, value=v,
                fg_color=ACCENT, hover_color=AC_HVR).pack(anchor="w", pady=(5, 5) if v=="SSD" else (0,0))

        cf = ctk.CTkFrame(sf2, fg_color="transparent")
        cf.grid(row=0, column=1, padx=20, pady=15, sticky="e")
        self.lbl_cpu = ctk.CTkLabel(cf,
            text=f"CPU load: {self.max_threads}/{self.max_threads} threads (100%)",
            font=ctk.CTkFont(weight="bold"), text_color=TXT2,
            width=280, anchor="center")
        self.lbl_cpu.pack(pady=(0, 5))
        steps = max(1, self.max_threads - 1)
        self.slider = ctk.CTkSlider(cf, from_=1, to=self.max_threads,
            number_of_steps=steps, width=260,
            progress_color=ACCENT, button_color=ACCENT,
            button_hover_color=AC_HVR, command=self.on_slider)
        self.slider.set(self.max_threads)
        self.slider.pack(pady=(10, 0))

        st = ctk.CTkFrame(self, fg_color="transparent")
        st.grid(row=3, column=0, padx=40, pady=5, sticky="ew")
        st.grid_columnconfigure((0, 1), weight=1)
        self.lbl_total = ctk.CTkLabel(st, text="Total Size: 0.00 MB", font=ctk.CTkFont(size=14))
        self.lbl_total.grid(row=0, column=0, sticky="w", padx=10, pady=(0, 2))
        self.lbl_disk = ctk.CTkLabel(st, text="On Disk: 0.00 MB",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=ACCENT)
        self.lbl_disk.grid(row=0, column=1, sticky="e", padx=10, pady=(0, 2))

        self.prog = ctk.CTkProgressBar(self, width=670, height=8,
            progress_color=ACCENT, fg_color=BTN_BG)
        self.prog.grid(row=4, column=0, padx=40, pady=(10, 10))
        self.prog.set(0)

        self.tb = ctk.CTkTextbox(self, height=130, corner_radius=8,
            fg_color=TXTBG, text_color=ACCENT,
            border_width=1, border_color=BTN_BG, state="disabled",
            font=ctk.CTkFont(family="Consolas", size=12))
        self.tb.grid(row=5, column=0, padx=40, pady=5, sticky="ew")

        af = ctk.CTkFrame(self, fg_color="transparent")
        af.grid(row=6, column=0, padx=40, pady=15)
        af.grid_columnconfigure((0, 1), weight=1)
        self.btn_c = ctk.CTkButton(af, text="COMPRESS",
            font=ctk.CTkFont(weight="bold", size=14),
            fg_color=ACCENT, text_color=BG,
            hover_color=AC_HVR, height=45, width=205, command=self.start_compress)
        self.btn_c.grid(row=0, column=0, padx=(0, 10))
        self.btn_d = ctk.CTkButton(af, text="DECOMPRESS",
            font=ctk.CTkFont(weight="bold", size=14),
            fg_color="transparent", text_color=ACCENT,
            border_width=2, border_color=ACCENT,
            hover_color=FRAME, height=45, width=205, command=self.start_decompress)
        self.btn_d.grid(row=0, column=1, padx=(10, 0))
        self.btn_x = ctk.CTkButton(af, text="CANCEL",
            font=ctk.CTkFont(weight="bold", size=14),
            fg_color="transparent", text_color=CNCL,
            border_width=2, border_color=CNCL,
            hover_color=CNCL_HVR, height=45, width=430,
            command=self.cancel, state="disabled")
        self.btn_x.grid(row=1, column=0, columnspan=2, pady=(15, 0))

    def on_slider(self, v):
        t = int(v)
        self._ui(self.lbl_cpu.configure,
            text=f"CPU load: {t}/{self.max_threads} threads ({int(t/self.max_threads*100)}%)")

    def apply_drive_mode(self):
        if self.drive_var.get() == "HDD":
            self._ui(self.slider.set, 1)
            self._ui(self.slider.configure, state="disabled")
            self._ui(self.lbl_cpu.configure, text="CPU load: HDD (1 thread)")
            self.log("[!] HDD mode enabled. Multithreading disabled.")
        else:
            self._ui(self.slider.configure, state="normal")
            self._ui(self.slider.set, self.max_threads)
            self.on_slider(self.max_threads)
            self.log("[*] SSD mode enabled. Multithreading activated.")

    def browse(self):
        if self.scan_lock.locked():
            return
        f = filedialog.askdirectory()
        if f:
            self.combo.set("Select game...")
            self.entry.delete(0, "end")
            self.entry.insert(0, f)
            self.selected_path = os.path.normpath(f)
            self.log(f"[*] Directory: {self.selected_path}")
            threading.Thread(target=self.scan, daemon=True).start()

    def _on_enter(self):
        if self.scan_lock.locked():
            return
        t = self.entry.get().strip()
        if t:
            self.combo.set("Select game...")
            self.selected_path = os.path.normpath(t)
            self.log(f"[*] Directory: {self.selected_path}")
            threading.Thread(target=self.scan, daemon=True).start()

    def on_steam(self, choice):
        if self.scan_lock.locked() or choice not in self.steam_games:
            return
        self.entry.delete(0, "end")
        self.selected_path = os.path.normpath(self.steam_games[choice])
        self.log(f"[*] Game: {self.selected_path}")
        threading.Thread(target=self.scan, daemon=True).start()

    def cancel(self):
        self.log("[!] Cancellation requested. Waiting for current files to finish...")
        self.cancel_event.set()
        self._ui(self.btn_x.configure, state="disabled")

    def detect_drive(self, path):
        with self.drive_lock:
            if path == self._cache_path and self._cache_type:
                return self._cache_type
            dl = os.path.splitdrive(path)[0].replace(':', '')
            if not dl:
                self._cache_path, self._cache_type = path, "SSD"
                return "SSD"
            try:
                r = subprocess.run(['powershell','-NoProfile','-Command',
                    f"try {{$d=(Get-Partition -DriveLetter '{dl}').DiskNumber;"
                    f"(Get-PhysicalDisk|Where-Object DeviceID -eq $d).MediaType}} catch {{'Unknown'}}"],
                    capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                t = "HDD" if "HDD" in r.stdout.strip() else "SSD"
            except Exception:
                t = "SSD"
            self._cache_path, self._cache_type = path, t
            return t

    def _find_steam_games(self):
        games = {}
        try:
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")
            sp, _ = winreg.QueryValueEx(k, "InstallPath")
            winreg.CloseKey(k)
        except Exception:
            return games
        vdf = os.path.join(sp, "steamapps", "libraryfolders.vdf")
        if not os.path.exists(vdf):
            return games
        try:
            with open(vdf, "r", encoding="utf-8") as f:
                c = f.read()
        except Exception:
            return games
        for p in re.findall(r'"path"\s+"([^"]+)"', c):
            sd = os.path.join(p.replace("\\\\", "\\"), "steamapps")
            if not os.path.isdir(sd):
                continue
            try:
                ents = os.listdir(sd)
            except Exception:
                continue
            for e in ents:
                if not (e.startswith("appmanifest_") and e.endswith(".acf")):
                    continue
                try:
                    with open(os.path.join(sd, e), "r", encoding="utf-8") as mf:
                        mc = mf.read()
                    nm = re.search(r'"name"\s+"([^"]+)"', mc)
                    di = re.search(r'"installdir"\s+"([^"]+)"', mc)
                    if nm and di:
                        fp = os.path.join(sd, "common", di.group(1))
                        if os.path.isdir(fp):
                            games[nm.group(1)] = fp
                except Exception:
                    continue
        return games

    def _comp_size(self, fp):
        ap = os.path.abspath(fp)
        if not ap.startswith("\\\\?\\"):
            ap = "\\\\?\\" + ap
        try:
            ctypes.windll.kernel32.SetLastError(0)
            h = ctypes.c_uint32()
            lo = ctypes.windll.kernel32.GetCompressedFileSizeW(
                ctypes.c_wchar_p(ap), ctypes.byref(h)
            )
            err = ctypes.windll.kernel32.GetLastError()
            if lo == 0xFFFFFFFF and err != 0:
                return os.path.getsize(fp)
            return (h.value << 32) | lo
        except Exception:
            return os.path.getsize(fp)

    def _files(self):
        fl = []
        try:
            for r, _, fs in os.walk(self.selected_path):
                for f in fs:
                    if os.path.splitext(f)[1].lower() not in BLACKLIST:
                        fl.append(os.path.join(r, f))
        except OSError:
            return []
        return fl

    def _state_file(self, action):
        return os.path.join(
            tempfile.gettempdir(),
            f"nexus_{hashlib.sha256(self.selected_path.encode()).hexdigest()}_{action}.txt"
        )

    @staticmethod
    def _fmt(b):
        return f"{b / (1024**3):.2f} GB" if b >= 1024**3 else f"{b / (1024**2):.2f} MB"

    def _enable_scan_buttons(self):
        for b in (self.btn_c, self.btn_d, self.btn_b, self.combo):
            b.configure(state="normal")

    def scan(self, silent=False):
        if not self.selected_path or not os.path.isdir(self.selected_path):
            return
        if not self.scan_lock.acquire(blocking=False):
            return
        try:
            for b in (self.btn_c, self.btn_d, self.btn_b, self.combo):
                self._ui(b.configure, state="disabled")
            if not silent:
                self._ui(self.drive_var.set, self.detect_drive(self.selected_path))
                self._ui(self.apply_drive_mode)
                self.log("[*] Analysis in progress...")
            orig = comp = 0
            fl = self._files()
            cnt = len(fl)
            for fp in fl:
                try:
                    s = os.path.getsize(fp)
                    cs = self._comp_size(fp)
                    orig += s
                    comp += cs
                except Exception:
                    continue

            def up():
                self.total_files = cnt
                self.lbl_total.configure(text=f"Total Size: {self._fmt(orig)}")
                self.lbl_disk.configure(text=f"On Disk: {self._fmt(comp)}")
                self._enable_scan_buttons()
            self._ui(up)
            if not silent:
                self.log(f"[*] Files found for processing: {cnt}")
        except Exception:
            self._ui(self._enable_scan_buttons)
            raise
        finally:
            self.scan_lock.release()

    def _is_compressed(self, fp):
        cs = self._comp_size(fp)
        s = os.path.getsize(fp)
        return cs < s

    def _process(self, fp, action):
        try:
            if action == "compress":
                if self._is_compressed(fp):
                    return fp, True, "skip"
                cmd = ['compact', '/c', '/exe:lzx', os.path.abspath(fp)]
            else:
                if not self._is_compressed(fp):
                    return fp, True, "skip"
                cmd = ['compact', '/u', '/exe:lzx', os.path.abspath(fp)]

            r = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW, check=False
            )

            ok = r.returncode == 0

            if not ok:
                out = (r.stdout + r.stderr).decode('utf-8', errors='replace').strip()
                self.log(f"  [!] {os.path.basename(fp)} (exit={r.returncode}): {out[:200]}")
            else:
                if action == "decompress":
                    if self._is_compressed(fp):
                        self.log(f"  [WARN] {os.path.basename(fp)} — still compressed")
                    else:
                        self.log(f"  [*] {os.path.basename(fp)} (decompressed)")
                else:
                    if not self._is_compressed(fp):
                        self.log(f"  [WARN] {os.path.basename(fp)} — not compressed")
                    else:
                        self.log(f"  [*] {os.path.basename(fp)} (compressed)")

            return fp, ok, "ok"
        except Exception as e:
            self.log(f"  [ERROR] {os.path.basename(fp)}: {e}")
            return fp, False, "ok"

    def _flush(self, buf, sf):
        if not buf:
            return
        try:
            with open(sf, 'a', encoding='utf-8') as f:
                f.writelines(buf)
        except Exception as e:
            self.log(f"[ERROR] State file write failed: {e}")
        buf.clear()

    def run(self, action, thr):
        if not self.selected_path or not os.path.isdir(self.selected_path):
            self.log("[ERROR] Invalid directory.")
            return

        self.disable_ui()
        self.cancel_event.clear()
        self._ui(self.prog.set, 0)

        try:
            fl = self._files()
            sf = self._state_file(action)

            done = set()
            if os.path.exists(sf):
                try:
                    with open(sf, 'r', encoding='utf-8') as f:
                        done = set(f.read().splitlines())
                    self.log(f"[*] Save file found. Resuming from {len(done)} files.")
                except Exception:
                    pass

            pending = [f for f in fl if f not in done]
            total = len(fl)
            cnt = len(done)

            if not pending:
                self.log("[!] No files to process.")
                self._clean(sf)
                self._ui(self.prog.set, 1)
            else:
                self.log(f"[*] Started. Threads: {thr}. Processing...")
                it = iter(pending)
                buf = []

                with ThreadPoolExecutor(max_workers=thr) as ex:
                    futures = set()
                    for _ in range(thr * 2):
                        try:
                            futures.add(ex.submit(self._process, next(it), action))
                        except StopIteration:
                            break

                    while futures and not self.cancel_event.is_set():
                        done_futs, futures = wait(futures, return_when=FIRST_COMPLETED)
                        for f in done_futs:
                            fp, ok, reason = f.result()
                            cnt += 1
                            if ok or reason == "skip":
                                with self.buf_lock:
                                    buf.append(fp + '\n')
                                    if len(buf) >= BUF_LIMIT:
                                        self._flush(buf, sf)
                        try:
                            futures.add(ex.submit(self._process, next(it), action))
                        except StopIteration:
                            pass
                        self._ui(self.prog.set, min(cnt / max(total, 1), 1.0))

                with self.buf_lock:
                    self._flush(buf, sf)

                if self.cancel_event.is_set():
                    self.log("[*] Operation was cancelled by the user.")
                else:
                    self._clean(sf)
                    self._ui(self.prog.set, 1)
                    self.log("[*] Operation completed successfully.")

            self.scan(silent=True)

        finally:
            self.is_processing = False
            self.reset_ui()

    @staticmethod
    def _clean(sf):
        try:
            if os.path.exists(sf):
                os.remove(sf)
        except Exception:
            pass

    def _start(self, action):
        if not self.selected_path:
            self.log("[ERROR] Directory not selected.")
            return
        if not os.path.isdir(self.selected_path):
            self.log("[ERROR] Invalid directory.")
            return
        if self.is_processing or self.scan_lock.locked():
            self.log("[ERROR] Operation in progress.")
            return
        if self.total_files == 0:
            self.log("[ERROR] No files. Scan first.")
            return
        self.is_processing = True
        thr = 1 if self.drive_var.get() == "HDD" else int(self.slider.get())
        threading.Thread(target=self.run, args=(action, thr), daemon=True).start()

    def start_compress(self):
        self._start("compress")

    def start_decompress(self):
        self._start("decompress")


if __name__ == "__main__":
    NexusCompressor().mainloop()
