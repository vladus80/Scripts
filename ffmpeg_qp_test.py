#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FFmpeg QP Test Suite — CLI-утилита для тестирования видео кодирования с различными параметрами.

Этот скрипт позволяет автоматизировать тестирование видео-кодирования с различными параметрами:
- Уровень квантования (QP)
- Масштабирование (1080p, 4k, original)
- Частота кадров (FPS)
- Выбор кодека (x264, x265, av1)
- Аппаратное или программное кодирование
- Пресеты кодирования
- CRF (для программных кодеков)
- Ограничение времени теста (duration)

Пример использования:
    python ffmpeg_qp_test.py -i input.mp4 -tests '[{"qp":35,"scale":"1080p","fps":30,"hw":1,"codec":"x265"}]'
    python ffmpeg_qp_test.py -i input.mp4 -tests '[{"crf":23,"scale":"1080p","codec":"x264"}]'
    python ffmpeg_qp_test.py -i input.mp4 -tests '[{"crf":30,"preset":5,"codec":"av1"}]' -duration 10

Поддерживаемые параметры тестов:
    qp (int)     - уровень квантования (обязателен для HW, опционален для SW)
    crf (int)    - constant rate factor (только для программных кодеков, опционален)
    scale (str)  - "1080p", "4k", "original" (по умолчанию)
    fps (int)    - желаемая частота кадров
    hw (0/1)     - 1 = аппаратное кодирование (vaapi), 0 = программное
    codec (str)  - "x264", "x265", "av1" (по умолчанию "x265")
    preset (str/int) -
        - для x264/x265: "ultrafast", "fast", "medium", "slow" (по умолчанию "medium")
        - для av1: число от 0 до 13 (по умолчанию 8)
    duration (int) - ограничить время теста (секунды), например 10 — только первые 10 секунд файла

Требования:
    - Python 3.10+
    - FFmpeg установлен в системе
    - Для аппаратного кодирования: Linux с поддержкой VAAPI

Автор: vladus
Версия: 1.1.0
"""

import os
import sys
import json
import time
import shutil
import subprocess
import argparse
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
import platform
import re

@dataclass
class TestConfig:
    qp: int
    scale: str = "original"
    fps: Optional[int] = None
    hw: int = 0
    codec: str = "x265"
    preset: Any = "medium"  # Может быть str или int для av1
    crf: Optional[int] = None  # Новый параметр
    duration: Optional[int] = None  # Новый параметр

@dataclass
class TestResult:
    input_file: str
    output_file: str
    config: TestConfig
    file_size: int
    bitrate: float
    compression_ratio: float
    duration: float
    encoding_time: float

class FFmpegQPTest:
    def __init__(self):
        self.ffmpeg_path = self._find_ffmpeg()
        self.results: List[TestResult] = []
        
    def _find_ffmpeg(self) -> str:
        """Находит путь к FFmpeg в системе"""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("FFmpeg не найден в системе")
        return ffmpeg

    def _check_hw_support(self) -> bool:
        """Проверяет поддержку аппаратного ускорения"""
        if platform.system() != "Linux":
            return False
        return os.path.exists("/dev/dri/renderD128")

    def _validate_config(self, config: Dict[str, Any]) -> TestConfig:
        """Валидирует конфигурацию теста"""
        if "qp" not in config and "crf" not in config:
            raise ValueError("QP или CRF является обязательным параметром")
        if config.get("hw", 0) == 1 and not self._check_hw_support():
            print("Предупреждение: Аппаратное ускорение недоступно, переключение на программное кодирование")
            config["hw"] = 0
        codec = config.get("codec", "x265")
        # Для av1 preset по умолчанию 8 (число), для остальных medium (строка)
        if codec == "av1":
            preset = config.get("preset", 8)
            # preset должен быть числом от 0 до 13
            try:
                preset = int(preset)
                if not (0 <= preset <= 13):
                    raise ValueError
            except Exception:
                raise ValueError("Для av1 preset должен быть числом от 0 до 13")
        else:
            preset = config.get("preset", "medium")
        crf = config.get("crf")
        duration = config.get("duration")
        return TestConfig(
            qp=config.get("qp", 0),
            scale=config.get("scale", "original"),
            fps=config.get("fps"),
            hw=config.get("hw", 0),
            codec=codec,
            preset=preset,
            crf=crf,
            duration=duration
        )

    def _get_scale_filter(self, scale: str, width: int, height: int) -> str:
        """Генерирует фильтр масштабирования"""
        if scale == "original":
            return ""
        
        target_height = 1080 if scale == "1080p" else 2160
        return f"scale=-2:{target_height}"

    def _build_ffmpeg_command(self, input_file: str, output_file: str, config: TestConfig) -> List[str]:
        """Строит команду FFmpeg"""
        cmd = [self.ffmpeg_path, "-y"]
        
        if config.hw == 1:
            # Добавляем параметры аппаратного ускорения до входного файла
            cmd.extend([
                "-hwaccel", "vaapi",
                "-hwaccel_device", "/dev/dri/renderD128",
                "-hwaccel_output_format", "vaapi"
            ])
        
        # Добавляем входной файл
        cmd.extend(["-i", input_file])
        
        # duration
        if config.duration:
            cmd.extend(["-t", str(config.duration)])
        
        if config.hw == 1:
            # Добавляем фильтры масштабирования и FPS
            filters = []
            if config.scale != "original":
                target_height = 1080 if config.scale == "1080p" else 2160
                filters.append(f"scale_vaapi=-2:{target_height}")
            if config.fps:
                filters.append(f"fps={config.fps}")
            
            if filters:
                cmd.extend(["-vf", f"format=vaapi,hwupload,{','.join(filters)}"])
            else:
                cmd.extend(["-vf", "format=vaapi,hwupload"])

            # Добавляем кодировщик и параметры качества
            if config.codec == "x265":
                cmd.extend([
                    "-c:v", "hevc_vaapi",
                    "-qp", str(config.qp),
                    "-preset", str(config.preset)
                ])
            elif config.codec == "x264":
                cmd.extend([
                    "-c:v", "h264_vaapi",
                    "-qp", str(config.qp),
                    "-preset", str(config.preset)
                ])
            elif config.codec == "av1":
                cmd.extend([
                    "-c:v", "av1_vaapi",
                    "-qp", str(config.qp),
                    "-preset", str(config.preset)
                ])
            else:
                cmd.extend([
                    "-c:v", f"{config.codec}_vaapi",
                    "-qp", str(config.qp),
                    "-preset", str(config.preset)
                ])
            
            # Копируем аудио поток без перекодирования
            cmd.extend(["-c:a", "copy"])
        else:
            # Программное кодирование
            if config.codec == "x265":
                cmd.extend(["-c:v", "libx265"])
                if config.crf is not None:
                    cmd.extend(["-crf", str(config.crf)])
                else:
                    cmd.extend(["-qp", str(config.qp)])
                cmd.extend(["-preset", str(config.preset)])
            elif config.codec == "x264":
                cmd.extend(["-c:v", "libx264"])
                if config.crf is not None:
                    cmd.extend(["-crf", str(config.crf)])
                else:
                    cmd.extend(["-qp", str(config.qp)])
                cmd.extend(["-preset", str(config.preset)])
            elif config.codec == "av1":
                cmd.extend(["-c:v", "libsvtav1"])
                if config.crf is not None:
                    cmd.extend(["-crf", str(config.crf)])
                else:
                    cmd.extend(["-qp", str(config.qp)])
                cmd.extend(["-preset", str(config.preset)])
            else:
                cmd.extend([
                    "-c:v", config.codec,
                    "-qp", str(config.qp),
                    "-preset", str(config.preset)
                ])
            
            # Добавляем фильтры для программного кодирования
            filters = []
            if config.scale != "original":
                filters.append(self._get_scale_filter(config.scale, 0, 0))
            if config.fps:
                filters.append(f"fps={config.fps}")
            
            if filters:
                cmd.extend(["-vf", ",".join(filters)])
            
            # Добавляем параметры качества
            cmd.extend([
                "-c:a", "copy"
            ])
        
        cmd.append(output_file)
        return cmd

    def _get_file_size(self, file_path: str) -> int:
        """Получает размер файла в байтах"""
        return os.path.getsize(file_path)

    def _calculate_bitrate(self, file_size: int, duration: float) -> float:
        """Вычисляет битрейт в Mbps"""
        return (file_size * 8) / (duration * 1000000)

    def _calculate_compression_ratio(self, input_size: int, output_size: int) -> float:
        """Вычисляет коэффициент сжатия"""
        return input_size / output_size

    def _parse_ffmpeg_time(self, timestr: str) -> float:
        """Преобразует строку времени вида 00:00:01.04 в секунды"""
        h, m, s = timestr.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    def _get_duration(self, input_file: str) -> float:
        """Определяет длительность видео через ffmpeg"""
        cmd = [self.ffmpeg_path, "-i", input_file]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        out, err = proc.communicate()
        match = re.search(r"Duration: (\d{2}:\d{2}:\d{2}\.\d+)", err)
        if match:
            return self._parse_ffmpeg_time(match.group(1))
        else:
            raise RuntimeError("Не удалось определить длительность видео")

    def _get_input_info(self, input_file: str) -> Dict[str, Any]:
        """Получает информацию о входном видеофайле через ffprobe"""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,bit_rate,codec_name,codec_long_name",
            "-of", "json",
            input_file
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            stream_info = json.loads(result.stdout)['streams'][0]
            
            # Парсим FPS из строки вида "30000/1001"
            fps_parts = stream_info['r_frame_rate'].split('/')
            fps = float(fps_parts[0]) / float(fps_parts[1])
            
            video_info = {
                'width': stream_info['width'],
                'height': stream_info['height'],
                'fps': fps,
                'bitrate': int(stream_info['bit_rate']) // 1000,  # конвертируем в kbps
                'size': os.path.getsize(input_file),
                'codec': stream_info['codec_name'],
                'codec_long_name': stream_info['codec_long_name']
            }
            
            return video_info
            
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
            print(f"Ошибка при получении информации о видео: {str(e)}")
            return {
                'width': 0,
                'height': 0,
                'fps': 0,
                'bitrate': 0,
                'size': os.path.getsize(input_file),
                'codec': 'unknown',
                'codec_long_name': 'Unknown codec'
            }

    def print_input_info(self, input_file: str):
        """Выводит информацию о входном файле"""
        info = self._get_input_info(input_file)
        
        print("\nИнформация о входном файле:")
        print("=" * 50)
        print(f"Файл: {os.path.basename(input_file)}")
        print(f"Размер: {info['size'] / 1024 / 1024:.1f} MB")
        print(f"Разрешение: {info['width']}x{info['height']}")
        print(f"Битрейт: {info['bitrate']} kbps")
        print(f"FPS: {info['fps']}")
        print(f"Кодек: {info['codec']} ({info['codec_long_name']})")
        print("=" * 50)

    def run_test(self, input_file: str, config: Dict[str, Any]) -> TestResult:
        """Выполняет один тест кодирования"""
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"Входной файл не найден: {input_file}")

        # Выводим информацию о входном файле перед первым тестом
        if not self.results:
            self.print_input_info(input_file)

        test_config = self._validate_config(config)
        # Формируем имя файла с учетом qp, crf, preset, codec, scale
        qp_part = f"qp{test_config.qp}" if test_config.qp else ""
        crf_part = f"crf{test_config.crf}" if test_config.crf is not None else ""
        preset_part = f"preset{test_config.preset}" if test_config.preset is not None else ""
        parts = [qp_part, crf_part, preset_part, test_config.codec, test_config.scale]
        name = "_".join([p for p in parts if p])
        output_file = f"output_{name}.mp4"
        
        # Получаем длительность входного видео
        duration = self._get_duration(input_file)

        # Строим и выполняем команду кодирования
        cmd = self._build_ffmpeg_command(input_file, output_file, test_config)
        print(f"\nВыполняется команда: {' '.join(cmd)}")
        
        # Засекаем время начала кодирования
        start_time = time.time()
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        # Собираем весь вывод FFmpeg
        ffmpeg_output = []
        while True:
            if process.stderr is None:
                break
            output = process.stderr.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                ffmpeg_output.append(output.strip())
                if "time=" in output:
                    print(f"\rПрогресс: {output.strip()}", end="")
        print()

        # Вычисляем время кодирования
        encoding_time = time.time() - start_time

        if process.returncode != 0:
            error_msg = "\n".join(ffmpeg_output)
            print("\nПодробный вывод FFmpeg:")
            print("-" * 80)
            print(error_msg)
            print("-" * 80)
            
            # Проверяем наличие VAAPI
            if test_config.hw == 1 and "vaapi" in error_msg.lower():
                print("\nВозможные проблемы с VAAPI:")
                print("1. Проверьте, что драйверы VAAPI установлены:")
                print("   sudo apt-get install intel-media-va-driver-non-free")
                print("2. Проверьте, что устройство доступно:")
                print("   ls -l /dev/dri/renderD128")
                print("3. Проверьте, что пользователь в группе video:")
                print("   groups $USER")
                print("4. Проверьте поддержку кодека:")
                print("   ffmpeg -hide_banner -hwaccels")
                print("   ffmpeg -hide_banner -encoders | grep vaapi")
            
            raise RuntimeError(f"Ошибка при выполнении FFmpeg (код возврата: {process.returncode})")

        # Собираем результаты
        input_size = self._get_file_size(input_file)
        output_size = self._get_file_size(output_file)
        
        return TestResult(
            input_file=input_file,
            output_file=output_file,
            config=test_config,
            file_size=output_size,
            bitrate=self._calculate_bitrate(output_size, duration),
            compression_ratio=self._calculate_compression_ratio(input_size, output_size),
            duration=duration,
            encoding_time=encoding_time
        )

    def print_results(self):
        """Выводит таблицу результатов"""
        # Определяем ширину колонок
        col_widths = {
            'file': 40,    # Имя файла (увеличено для длинных имён)
            'qp': 4,       # QP
            'crf': 5,      # CRF
            'preset': 8,   # Preset
            'scale': 8,    # Scale
            'fps': 5,      # FPS
            'codec': 10,   # Кодек
            'mode': 6,     # Режим (HW/SW)
            'size': 12,    # Размер
            'bitrate': 12, # Битрейт
            'ratio': 10,   # Сжатие
            'time': 10     # Время кодирования
        }

        # Формируем заголовок таблицы
        header = (
            f"{'Файл':<{col_widths['file']}} "
            f"{'QP':<{col_widths['qp']}} "
            f"{'CRF':<{col_widths['crf']}} "
            f"{'Preset':<{col_widths['preset']}} "
            f"{'Scale':<{col_widths['scale']}} "
            f"{'FPS':<{col_widths['fps']}} "
            f"{'Кодек':<{col_widths['codec']}} "
            f"{'Режим':<{col_widths['mode']}} "
            f"{'Размер':<{col_widths['size']}} "
            f"{'Битрейт':<{col_widths['bitrate']}} "
            f"{'Сжатие':<{col_widths['ratio']}} "
            f"{'Время':<{col_widths['time']}}"
        )

        # Выводим заголовок и разделитель
        print("\nРезультаты тестирования:")
        print("=" * len(header))
        print(header)
        print("-" * len(header))
        
        # Выводим результаты
        for result in self.results:
            # Форматируем размер файла
            size_mb = result.file_size / 1024 / 1024
            size_str = f"{size_mb:.1f} MB"
            
            # Форматируем битрейт
            bitrate_str = f"{result.bitrate:.1f} Mbps"
            
            # Форматируем коэффициент сжатия
            ratio_str = f"{result.compression_ratio:.1f}x"
            
            # Форматируем FPS
            fps_str = str(result.config.fps) if result.config.fps else "-"
            
            # Форматируем время кодирования
            time_str = f"{result.encoding_time:.1f}с"
            
            # CRF и PRESET
            crf_str = str(result.config.crf) if result.config.crf is not None else "-"
            preset_str = str(result.config.preset) if result.config.preset is not None else "-"
            
            # Формируем строку результата
            row = (
                f"{os.path.basename(result.output_file):<{col_widths['file']}} "
                f"{result.config.qp:<{col_widths['qp']}} "
                f"{crf_str:<{col_widths['crf']}} "
                f"{preset_str:<{col_widths['preset']}} "
                f"{result.config.scale:<{col_widths['scale']}} "
                f"{fps_str:<{col_widths['fps']}} "
                f"{result.config.codec:<{col_widths['codec']}} "
                f"{'HW' if result.config.hw else 'SW':<{col_widths['mode']}} "
                f"{size_str:<{col_widths['size']}} "
                f"{bitrate_str:<{col_widths['bitrate']}} "
                f"{ratio_str:<{col_widths['ratio']}} "
                f"{time_str:<{col_widths['time']}}"
            )
            print(row)
        
        # Выводим нижнюю границу таблицы
        print("=" * len(header))

def main():
    parser = argparse.ArgumentParser(
        description="FFmpeg QP Test Suite — CLI-утилита для тестирования видео кодирования с различными параметрами.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

1. Базовый тест с одним набором параметров:
   python ffmpeg_qp_test.py -i input.mp4 -tests '[{"qp":35,"scale":"1080p","fps":30,"hw":1,"codec":"x265"}]'

2. Несколько тестов с разными параметрами:
   python ffmpeg_qp_test.py -i input.mp4 -tests '[{"qp":35,"scale":"1080p","fps":30,"hw":1},{"crf":28,"scale":"4k","fps":60,"hw":0,"codec":"av1","preset":5}]'

3. Тест только с обязательными параметрами:
   python ffmpeg_qp_test.py -i input.mp4 -tests '[{"qp":35}]'

4. Тест с ограничением времени:
   python ffmpeg_qp_test.py -i input.mp4 -tests '[{"qp":35}]' -duration 10

Подробное описание параметров:

qp (обязательный для HW, опциональный для SW):
    - Целое число от 0 до 51
    - Чем меньше значение, тем выше качество и размер файла
    - Рекомендуемый диапазон: 18-35

crf (только для программных кодеков):
    - Целое число (например, 18-35 для x264/x265, 1+ для av1)
    - Если указан, используется вместо qp

scale:
    - "1080p" - масштабирование до 1080p
    - "4k" - масштабирование до 4K (2160p)
    - "original" - без масштабирования

fps:
    - Целое число (например, 24, 30, 60)
    - Если не указан, сохраняется оригинальная частота кадров

hw:
    - 1 - использование аппаратного ускорения (VAAPI)
    - 0 - программное кодирование
    - При недоступности аппаратного ускорения автоматически переключается на программное

codec:
    - "x264" - H.264/AVC
    - "x265" - H.265/HEVC
    - "av1" - AV1
    - По умолчанию используется x265

preset:
    - Для x264/x265: "ultrafast", "fast", "medium", "slow"
    - Для av1: число от 0 до 13 (по умолчанию 8)

Возможные ошибки и их решения:

1. "FFmpeg не найден в системе"
   Решение: Установите FFmpeg и добавьте его в PATH

2. "Аппаратное ускорение недоступно"
   Решение: Убедитесь, что система поддерживает VAAPI и драйверы установлены

3. "Некорректный JSON в параметре -tests"
   Решение: Проверьте синтаксис JSON и экранирование кавычек

4. "Входной файл не найден"
   Решение: Проверьте путь к файлу и права доступа

-duration:
    - Ограничить время теста (секунды), например 10 — только первые 10 секунд файла
"""
    )
    parser.add_argument("-i", "--input", required=True, help="Путь к исходному видеофайлу")
    parser.add_argument("-tests", required=True, help="JSON-массив конфигураций кодирования")
    parser.add_argument("-duration", type=int, default=None, help="Ограничить время теста (секунды), например 10 — только первые 10 секунд файла")
    
    # Устанавливаем ширину консоли для лучшего форматирования
    try:
        import shutil
        columns = shutil.get_terminal_size().columns
        if columns > 80:  # Если консоль достаточно широкая
            parser.formatter_class = lambda prog: argparse.RawDescriptionHelpFormatter(prog, width=columns)
    except:
        pass  # Если не удалось получить размер консоли, используем значения по умолчанию
    
    args = parser.parse_args()
    
    try:
        tests = json.loads(args.tests)
        if not isinstance(tests, list):
            raise ValueError("Параметр -tests должен быть JSON-массивом")
        
        tester = FFmpegQPTest()
        for i, test_config in enumerate(tests, 1):
            print(f"\nТест {i} из {len(tests)}")
            # duration из CLI имеет приоритет, если задан
            if args.duration is not None:
                test_config["duration"] = args.duration
            result = tester.run_test(args.input, test_config)
            tester.results.append(result)
        
        tester.print_results()
        
    except json.JSONDecodeError:
        print("Ошибка: Некорректный JSON в параметре -tests")
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
