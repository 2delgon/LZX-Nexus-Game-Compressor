# EN Nexus Game Compressor

A GUI utility for compressing game files and freeing up storage space without compromising performance.

The program acts as a smart wrapper for the Windows built-in `compact.exe` utility. It utilizes the native LZX compression algorithm at the NTFS file system level. The operating system and game engine still read the files at their original size, while decompression happens on-the-fly in RAM using CPU resources.

## Key Features

* **Smart Steam Integration:** Automatically reads the registry, `libraryfolders.vdf`, and `appmanifest_*.acf` manifests to precisely locate currently installed games (ignoring leftover empty folders).
* **Parallel Processing:** Bypasses the system limitation of `compact.exe` (which runs single-threaded). The utility scans files and initiates parallel compression via `ThreadPoolExecutor`, reducing processing time significantly.
* **Drive Auto-Detection (WMI):** When a folder is selected, the program runs a hidden PowerShell query to determine the physical drive type. If an HDD is detected, multithreading is forcefully disabled to prevent hardware wear and read head "stuttering".
* **CPU Load Control:** A user-adjustable slider to limit the number of active worker threads (based on the CPU's logical cores).
* **Progress Resume:** Supports safe operation cancellation. If the process is interrupted, the program remembers already compressed files and resumes from where it left off upon the next launch.
* **Smart Filter (Blacklist):** Automatically excludes files that are uncompressible by design (video, audio, archives) to save CPU resources and processing time.
* **Anti-Cheat Safe:** Compression occurs at the file system level without interfering with game code (`.exe`, `.dll`). No bans from VAC, Vanguard, Faceit, or Easy Anti-Cheat.

# RU Nexus Game Compressor

Утилита с графическим интерфейсом для сжатия файлов игр и освобождения места на накопителе без ущерба для производительности. 

Программа работает как умная оболочка для системной утилиты Windows `compact.exe`. Используется нативный алгоритм сжатия LZX на уровне файловой системы NTFS. Операционная система и движок игры видят файлы в их оригинальном размере, а распаковка происходит «на лету» в оперативной памяти силами процессора.

## Ключевые возможности

* **Умная интеграция со Steam:** Автоматическое чтение реестра, `libraryfolders.vdf` и манифестов `appmanifest_*.acf` для 100% точного поиска только установленных игр (игнорирует остаточные пустые папки).
* **Многопоточность (Parallel Processing):** Обход системного ограничения `compact.exe` (работающего в 1 поток). Утилита сканирует файлы и запускает параллельное сжатие через `ThreadPoolExecutor`, сокращая время обработки в несколько раз.
* **Автоопределение накопителя (WMI):** При выборе папки программа делает скрытый запрос в PowerShell для определения физического типа носителя. При обнаружении HDD многопоточность принудительно отключается, чтобы избежать аппаратного износа и "заикания" считывающей головки.
* **Регулятор нагрузки CPU:** Пользовательский ползунок для ограничения числа активных рабочих потоков (зависит от логических ядер процессора).
* **Сохранение прогресса (Resume):** Поддержка безопасной отмены операций. При прерывании процесса программа запоминает уже сжатые файлы и при повторном запуске продолжает работу с места остановки.
* **Интеллектуальный фильтр (Blacklist):** Автоматическое исключение файлов (видео, аудио, архивы), не поддающихся алгоритмам сжатия, для экономии ресурсов процессора и времени.
* **Безопасность для античитов:** Сжатие происходит на уровне ФС без вмешательства в код (`.exe`, `.dll`). Никаких блокировок от VAC, Vanguard, Faceit или Easy Anti-Cheat.
