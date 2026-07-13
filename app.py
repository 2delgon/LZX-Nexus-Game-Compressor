import os
import winreg
import ctypes
import threading
import subprocess
import re
import customtkinter as ctk
from tkinter import filedialog
from concurrent.futures import ThreadPoolExecutor, as_completed

ctk.set_appearance_mode("Dark")

class NexusCompressor(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Nexus Game Compressor")
        self.geometry("750x700")
        self.resizable(False, False)
        self.configure(fg_color="#121212")
        
        self.steam_games = self.find_steam_games()
        self.selected_path = ""
        self.total_files = 0
        self.processed_files = 0
        self.max_cpu_threads = os.cpu_count() or 4
        self.is_scanning = False

        self.build_ui()

    def build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        
        self.lbl_title = ctk.CTkLabel(self, text="NEXUS COMPRESSOR", font=ctk.CTkFont(family="Segoe UI Black", size=28, weight="bold"), text_color="#00E5FF")
        self.lbl_title.grid(row=0, column=0, pady=(25, 15))

        self.frame_select = ctk.CTkFrame(self, fg_color="#1E1E1E", corner_radius=8)
        self.frame_select.grid(row=1, column=0, padx=40, pady=5, sticky="ew")
        
        self.lbl_steam = ctk.CTkLabel(self.frame_select, text="Библиотека Steam:", font=ctk.CTkFont(size=14, weight="bold"), text_color="#E0E0E0")
        self.lbl_steam.pack(pady=(15, 5))

        game_names = ["Выберите игру..."] + list(self.steam_games.keys())
        self.combo_games = ctk.CTkOptionMenu(self.frame_select, values=game_names, command=self.on_steam_select, width=400, fg_color="#2A2A2A", button_color="#00E5FF", button_hover_color="#00B8CC", text_color="#FFFFFF")
        self.combo_games.pack(pady=(0, 15))

        self.frame_manual = ctk.CTkFrame(self.frame_select, fg_color="transparent")
        self.frame_manual.pack(pady=(5, 15))

        self.entry_path = ctk.CTkEntry(self.frame_manual, placeholder_text="Или укажите путь вручную...", width=300, border_color="#2A2A2A", fg_color="#121212")
        self.entry_path.pack(side="left", padx=(0, 10))

        self.btn_browse = ctk.CTkButton(self.frame_manual, text="Обзор", width=90, fg_color="#2A2A2A", hover_color="#3A3A3A", command=self.browse_folder)
        self.btn_browse.pack(side="left")

        self.frame_settings = ctk.CTkFrame(self, fg_color="#1E1E1E", corner_radius=8)
        self.frame_settings.grid(row=2, column=0, padx=40, pady=10, sticky="ew")
        self.frame_settings.grid_columnconfigure((0, 1), weight=1)

        self.frame_drive_type = ctk.CTkFrame(self.frame_settings, fg_color="transparent")
        self.frame_drive_type.grid(row=0, column=0, padx=20, pady=15, sticky="w")
        
        self.lbl_drive_type = ctk.CTkLabel(self.frame_drive_type, text="Тип накопителя", font=ctk.CTkFont(weight="bold"), text_color="#A0A0A0")
        self.lbl_drive_type.pack(anchor="w", pady=(0, 5))
        
        self.drive_var = ctk.StringVar(value="SSD")
        
        self.radio_ssd = ctk.CTkRadioButton(self.frame_drive_type, text="SSD (Многопоточность)", variable=self.drive_var, value="SSD", fg_color="#00E5FF", hover_color="#00B8CC", command=self.on_drive_change)
        self.radio_ssd.pack(anchor="w", pady=(5, 5))
        
        self.radio_hdd = ctk.CTkRadioButton(self.frame_drive_type, text="HDD (Безопасный режим)", variable=self.drive_var, value="HDD", fg_color="#00E5FF", hover_color="#00B8CC", command=self.on_drive_change)
        self.radio_hdd.pack(anchor="w")

        self.frame_cpu = ctk.CTkFrame(self.frame_settings, fg_color="transparent")
        self.frame_cpu.grid(row=0, column=1, padx=20, pady=15, sticky="e")
        
        self.lbl_cpu = ctk.CTkLabel(self.frame_cpu, text=f"Нагрузка CPU: 100% ({self.max_cpu_threads} потоков)", font=ctk.CTkFont(weight="bold"), text_color="#A0A0A0")
        self.lbl_cpu.pack(anchor="w", pady=(0, 5))

        self.slider_cpu = ctk.CTkSlider(self.frame_cpu, from_=10, to=100, number_of_steps=9, width=200, progress_color="#00E5FF", button_color="#00E5FF", button_hover_color="#00B8CC", command=self.on_slider_change)
        self.slider_cpu.set(100)
        self.slider_cpu.pack(pady=(10, 0))

        self.frame_stats = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_stats.grid(row=3, column=0, padx=40, pady=5, sticky="ew")
        self.frame_stats.grid_columnconfigure((0, 1), weight=1)

        self.lbl_original_size = ctk.CTkLabel(self.frame_stats, text="Исходный: 0.00 ГБ", font=ctk.CTkFont(size=14))
        self.lbl_original_size.grid(row=0, column=0, sticky="w", padx=10)

        self.lbl_compressed_size = ctk.CTkLabel(self.frame_stats, text="На диске: 0.00 ГБ", font=ctk.CTkFont(size=14, weight="bold"), text_color="#00E5FF")
        self.lbl_compressed_size.grid(row=0, column=1, sticky="e", padx=10)

        self.progressbar = ctk.CTkProgressBar(self, width=670, height=8, progress_color="#00E5FF", fg_color="#2A2A2A")
        self.progressbar.grid(row=4, column=0, padx=40, pady=(10, 10))
        self.progressbar.set(0)

        self.textbox_log = ctk.CTkTextbox(self, height=130, corner_radius=8, fg_color="#0D0D0D", text_color="#00E5FF", border_width=1, border_color="#2A2A2A", state="disabled", font=ctk.CTkFont(family="Consolas", size=12))
        self.textbox_log.grid(row=5, column=0, padx=40, pady=5, sticky="ew")

        self.frame_actions = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_actions.grid(row=6, column=0, padx=40, pady=15)

        self.btn_compress = ctk.CTkButton(self.frame_actions, text="СЖАТЬ", font=ctk.CTkFont(weight="bold", size=14), fg_color="#00E5FF", text_color="#121212", hover_color="#00B8CC", height=45, width=200, command=self.start_compression)
        self.btn_compress.grid(row=0, column=0, padx=15)

        self.btn_decompress = ctk.CTkButton(self.frame_actions, text="РАСПАКОВАТЬ", font=ctk.CTkFont(weight="bold", size=14), fg_color="transparent", text_color="#00E5FF", border_width=2, border_color="#00E5FF", hover_color="#1E1E1E", height=45, width=200, command=self.start_decompression)
        self.btn_decompress.grid(row=0, column=1, padx=15)

    def on_slider_change(self, value):
        threads = max(1, int((value / 100) * self.max_cpu_threads))
        self.lbl_cpu.configure(text=f"Нагрузка CPU: {int(value)}% ({threads} потоков)")

    def on_drive_change(self):
        if self.drive_var.get() == "HDD":
            self.slider_cpu.set(10)
            self.slider_cpu.configure(state="disabled")
            self.lbl_cpu.configure(text="Нагрузка CPU: Режим HDD (1 поток)")
            self.safe_log("[!] Включен режим HDD. Многопоточность отключена.")
        else:
            self.slider_cpu.configure(state="normal")
            self.slider_cpu.set(100)
            self.on_slider_change(100)
            self.safe_log("[*] Включен режим SSD. Многопоточность активирована.")

    def safe_log(self, message):
        def update():
            self.textbox_log.configure(state="normal")
            self.textbox_log.insert("end", message + "\n")
            self.textbox_log.see("end")
            self.textbox_log.configure(state="disabled")
        self.after(0, update)

    def safe_progress(self, value):
        self.after(0, lambda: self.progressbar.set(value))

    def detect_drive_type(self, path):
        try:
            drive_letter = os.path.splitdrive(path)[0].replace(':', '')
            if not drive_letter:
                return "SSD"
            
            cmd = [
                'powershell', '-NoProfile', '-Command',
                f"try {{ $d = (Get-Partition -DriveLetter '{drive_letter}').DiskNumber; (Get-PhysicalDisk | Where-Object DeviceID -eq $d).MediaType }} catch {{ 'Unknown' }}"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            media_type = result.stdout.strip()
            
            if "HDD" in media_type:
                return "HDD"
            return "SSD"
        except Exception:
            return "SSD"

    def apply_drive_detection(self, path):
        detected_type = self.detect_drive_type(path)
        self.after(0, lambda: self.drive_var.set(detected_type))
        self.after(0, self.on_drive_change)

    def find_steam_games(self):
        games = {}
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")
            steam_path, _ = winreg.QueryValueEx(key, "InstallPath")
            winreg.CloseKey(key)

            vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
            if not os.path.exists(vdf_path):
                return games

            with open(vdf_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            paths = re.findall(r'"path"\s+"([^"]+)"', content)
            
            for path in paths:
                lib_path = path.replace("\\\\", "\\")
                apps_dir = os.path.join(lib_path, "steamapps", "common")
                if os.path.isdir(apps_dir):
                    for game_folder in os.listdir(apps_dir):
                        full_path = os.path.join(apps_dir, game_folder)
                        if os.path.isdir(full_path):
                            games[game_folder] = full_path
        except Exception:
            pass
        return games

    def browse_folder(self):
        if self.is_scanning:
            return
        folder = filedialog.askdirectory()
        if folder:
            self.combo_games.set("Выберите игру...")
            self.entry_path.delete(0, "end")
            self.entry_path.insert(0, folder)
            self.selected_path = os.path.normpath(folder)
            self.safe_log(f"[*] Директория: {self.selected_path}")
            threading.Thread(target=self.calculate_sizes, daemon=True).start()

    def on_steam_select(self, choice):
        if self.is_scanning:
            return
        if choice in self.steam_games:
            self.entry_path.delete(0, "end")
            self.selected_path = os.path.normpath(self.steam_games[choice])
            self.safe_log(f"[*] Игра Steam: {self.selected_path}")
            threading.Thread(target=self.calculate_sizes, daemon=True).start()

    def get_compressed_size(self, filepath):
        high = ctypes.c_uint32()
        low = ctypes.windll.kernel32.GetCompressedFileSizeW(str(filepath), ctypes.byref(high))
        if low == 0xFFFFFFFF and ctypes.GetLastError() != 0:
            return os.path.getsize(filepath)
        return (high.value << 32) + low

    def get_all_files(self):
        file_list = []
        for root, _, files in os.walk(self.selected_path):
            for file in files:
                file_list.append(os.path.join(root, file))
        return file_list

    def calculate_sizes(self):
        if not self.selected_path or not os.path.isdir(self.selected_path):
            return

        self.is_scanning = True
        self.after(0, lambda: self.btn_compress.configure(state="disabled"))
        self.after(0, lambda: self.btn_decompress.configure(state="disabled"))
        self.after(0, lambda: self.btn_browse.configure(state="disabled"))
        self.after(0, lambda: self.combo_games.configure(state="disabled"))
        
        self.apply_drive_detection(self.selected_path)
        self.safe_log("[*] Анализ файлов...")
        
        total_original = 0
        total_compressed = 0
        
        file_list = self.get_all_files()
        self.total_files = len(file_list)

        for filepath in file_list:
            try:
                total_original += os.path.getsize(filepath)
                total_compressed += self.get_compressed_size(filepath)
            except Exception:
                continue

        orig_gb = total_original / (1024**3)
        comp_gb = total_compressed / (1024**3)

        self.after(0, lambda: self.lbl_original_size.configure(text=f"Исходный: {orig_gb:.2f} ГБ"))
        self.after(0, lambda: self.lbl_compressed_size.configure(text=f"На диске: {comp_gb:.2f} ГБ"))
        self.safe_log(f"[*] Найдено файлов: {self.total_files}")
        
        self.after(0, lambda: self.btn_compress.configure(state="normal"))
        self.after(0, lambda: self.btn_decompress.configure(state="normal"))
        self.after(0, lambda: self.btn_browse.configure(state="normal"))
        self.after(0, lambda: self.combo_games.configure(state="normal"))
        self.is_scanning = False

    def process_single_file(self, filepath, action):
        cmd = ['compact', '/c', '/exe:lzx', filepath] if action == "compress" else ['compact', '/u', filepath]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW, check=False)
            return True
        except Exception:
            return False

    def run_compact_multithreaded(self, action):
        if not self.selected_path:
            self.safe_log("[ОШИБКА] Директория не выбрана.")
            return

        self.after(0, lambda: self.btn_compress.configure(state="disabled"))
        self.after(0, lambda: self.btn_decompress.configure(state="disabled"))
        self.after(0, lambda: self.combo_games.configure(state="disabled"))
        self.after(0, lambda: self.btn_browse.configure(state="disabled"))
        self.safe_progress(0)
        
        file_list = self.get_all_files()
        self.total_files = len(file_list)
        self.processed_files = 0

        if self.total_files == 0:
            self.safe_log("[!] Выбранная папка пуста.")
            self.after(0, lambda: self.btn_compress.configure(state="normal"))
            self.after(0, lambda: self.btn_decompress.configure(state="normal"))
            self.after(0, lambda: self.combo_games.configure(state="normal"))
            self.after(0, lambda: self.btn_browse.configure(state="normal"))
            return

        if self.drive_var.get() == "HDD":
            active_threads = 1
        else:
            percent = self.slider_cpu.get()
            active_threads = max(1, int((percent / 100) * self.max_cpu_threads))

        self.safe_log(f"[*] Начало операции. Потоков: {active_threads}. Ожидайте...")

        with ThreadPoolExecutor(max_workers=active_threads) as executor:
            futures = [executor.submit(self.process_single_file, f, action) for f in file_list]
            for future in as_completed(futures):
                self.processed_files += 1
                if self.processed_files % 50 == 0 or self.processed_files == self.total_files:
                    progress = min(self.processed_files / self.total_files, 1.0)
                    self.safe_progress(progress)

        self.safe_progress(1.0)
        self.safe_log("[*] Операция завершена.")
        self.calculate_sizes()

    def start_compression(self):
        if self.total_files == 0 or self.is_scanning:
            self.safe_log("[ОШИБКА] Дождитесь окончания сканирования или укажите корректную папку.")
            return
        threading.Thread(target=self.run_compact_multithreaded, args=("compress",), daemon=True).start()

    def start_decompression(self):
        if self.total_files == 0 or self.is_scanning:
             self.safe_log("[ОШИБКА] Дождитесь окончания сканирования или укажите корректную папку.")
             return
        threading.Thread(target=self.run_compact_multithreaded, args=("decompress",), daemon=True).start()

if __name__ == "__main__":
    app = NexusCompressor()
    app.mainloop()