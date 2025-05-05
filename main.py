import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import ContentType, Message
from aiogram.utils import executor
from moviepy import VideoFileClip, ImageClip, CompositeVideoClip
import yt_dlp
from PIL import Image
import numpy as np
import math

# -------------------------------
# Настройки
# -------------------------------
API_TOKEN = "7840419442:AAEkZQsU5yjGquJfyCad2jWHnbKzIUNweOM"  # Замените на токен вашего бота
DOWNLOAD_DIR = "downloads"
WATERMARKS_DIR = "watermarks"
DEFAULT_QUALITY = "480p"
WATERMARK_OPACITY = 0.3
WATERMARK_SIZE_RATIO = 0.8
file_id_storage = {}
# -------------------------------
# Настройка логирования
# -------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.info("Инициализация бота...")

# Создаем необходимые директории
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(WATERMARKS_DIR, exist_ok=True)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)


# -------------------------------
# Функции для работы с видео
# -------------------------------

def download_video(url, resolution=DEFAULT_QUALITY):
    """Скачивание видео с YouTube с использованием yt-dlp."""
    try:
        if resolution.endswith("p"):
            height = int(resolution[:-1])
        else:
            height = int(resolution)
    except Exception:
        logging.error(f"Неверный формат разрешения: {resolution}. Использую значение по умолчанию 480p.")
        height = 480

    ydl_opts = {
        'format': f'bestvideo[height<={height}]+bestaudio/best',
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True
    }
    try:
        logging.info(f"Скачиваю видео с {url} с разрешением {resolution}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            video_id = info_dict.get('id', None)
            ext = info_dict.get('ext', 'mp4')
            filename = f"{video_id}.{ext}"
        logging.info(f"Видео успешно скачано: {filename}")
        return filename
    except Exception as e:
        logging.error(f"Ошибка при скачивании видео: {e}")
        return None


def add_watermark(video_path, watermark_path, output_path, opacity=WATERMARK_OPACITY, size_ratio=WATERMARK_SIZE_RATIO):
    """
    Наложение водяного знака на видео
    """
    try:
        logging.info(f"Наложение водяного знака: {watermark_path} на видео: {video_path}")
        video = VideoFileClip(video_path)

        # Обработка водяного знака
        with Image.open(watermark_path) as img:
            img = img.convert("RGBA")

            # Расчет нового размера
            new_height = int(video.h * size_ratio)
            width_percent = new_height / img.height
            new_width = int(img.width * width_percent)

            resized_img = img.resize(
                (new_width, new_height),
                resample=Image.Resampling.LANCZOS
            )

            # Применение прозрачности
            if opacity < 1.0:
                alpha = resized_img.split()[3]
                alpha = alpha.point(lambda p: p * opacity)
                resized_img.putalpha(alpha)

            watermark_array = np.array(resized_img)

        # Создание клипа с позицией
        watermark = ImageClip(
            watermark_array,
            duration=video.duration
        ).with_position("center")  # Исправление здесь

        # Сборка и сохранение
        final_clip = CompositeVideoClip([video, watermark])
        final_clip.write_videofile(output_path, codec='libx264', fps=video.fps, logger=None)
        logging.info(f"Видео с водяным знаком сохранено: {output_path}")
        return output_path
    except Exception as e:
        logging.error(f"Ошибка при наложении водяного знака: {e}")
        return None


# -------------------------------
# Обработчики входных сообщений
# -------------------------------

@dp.message_handler(content_types=ContentType.TEXT)
async def handle_text(message: Message):
    """Обработчик текста (ссылка на видео)"""
    url = message.text.strip()

    if url.startswith(('http://', 'https://')) and 'youtube.com' in url:
        # Извлекаем информацию о видео с помощью yt-dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'bestvideo+bestaudio/best',  # Получаем информацию о всех доступных форматах
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=False)  # Не скачиваем, только получаем информацию
                duration = info_dict.get('duration', 0)  # Длительность в секундах
                formats = info_dict.get('formats', [])

                # Словарь для хранения битрейтов по разрешению
                bitrate_map = {
                    '144p': 0,
                    '360p': 0,
                    '480p': 0,
                    '720p': 0,
                    '1080p': 0
                }

                # Проходим по форматам и ищем битрейты для нужных разрешений
                for fmt in formats:
                    height = fmt.get('height')
                    if height:
                        resolution = f"{height}p"
                        if resolution in bitrate_map:
                            # Битрейт видео + аудио (примерно, если есть tbr)
                            total_bitrate = fmt.get('tbr', 0) or 0
                            if 'audio' in fmt.get('acodec', ''):
                                total_bitrate += 128  # Добавляем примерный битрейт аудио (128 kbps)
                            bitrate_map[resolution] = total_bitrate

                # Рассчитываем примерный размер для каждого разрешения
                buttons = []
                for resolution in ['144p', '360p', '480p', '720p', '1080p']:
                    bitrate = bitrate_map.get(resolution, 0)  # Битрейт в kbps
                    if bitrate == 0:
                        # Если битрейт неизвестен, используем примерные значения
                        bitrate = {'144p': 200, '360p': 500, '480p': 1000, '720p': 2500, '1080p': 5000}.get(resolution, 1000)
                    # Размер в мегабайтах: (битрейт * длительность) / (8 * 1024)
                    size_mb = (bitrate * duration) / (8 * 1024) if duration else 0
                    size_text = f"~{math.ceil(size_mb)} MB" if size_mb > 0 else "неизвестно"
                    button_text = f"{resolution} ({size_text})"
                    buttons.append(types.InlineKeyboardButton(text=button_text, callback_data=f"quality_{resolution}_{url}"))

                keyboard = types.InlineKeyboardMarkup(row_width=2)  # Кнопки в ряд
                keyboard.add(*buttons)
                await message.reply("Выберите разрешение для скачивания видео:", reply_markup=keyboard)
        except Exception as e:
            logging.error(f"Ошибка при получении информации о видео: {e}")
            await message.reply("Ошибка при получении данных о видео. Попробуйте позже.")
    else:
        await message.reply("Пожалуйста, отправьте корректную ссылку на YouTube.")


@dp.message_handler(content_types=ContentType.VIDEO)
async def handle_video(message: Message):
    """Обработчик для видео, отправленного напрямую"""
    file_id = message.video.file_id  # Получаем уникальный идентификатор для видео

    # Генерируем короткий уникальный идентификатор
    short_id = str(len(file_id_storage))  # Простой способ: используем длину словаря как ID
    file_id_storage[short_id] = file_id  # Сохраняем file_id в словаре

    # Скачиваем видео в директорию
    video_file = await bot.get_file(file_id)
    video_path = os.path.join(DOWNLOAD_DIR, f"{file_id}.mp4")

    # Сохраняем видео в директорию
    await video_file.download(video_path)

    # После скачивания видео отправляем кнопки для выбора водяного знака
    buttons = [
        types.InlineKeyboardButton(text="PushEnter", callback_data=f"watermark_pushenter_{short_id}"),
        types.InlineKeyboardButton(text="Ваншот", callback_data=f"watermark_vanshot_{short_id}"),
        types.InlineKeyboardButton(text="Без водяного знака", callback_data=f"no_watermark_{short_id}")
    ]
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(*buttons)

    await message.reply("Выберите действие с видео:", reply_markup=keyboard)

# Обработчик выбора водяного знака
@dp.callback_query_handler(lambda c: c.data.startswith('watermark_'))
async def handle_watermark(callback_query: types.CallbackQuery):
    """Обработка выбора водяного знака"""
    parts = callback_query.data.split('_')
    action, watermark_type = parts[0], parts[1]
    identifier = parts[2]  # Это либо short_id (для прямых видео), либо video_path (для скачанных)

    # Определяем, является ли identifier short_id (для прямых видео) или video_path (для скачанных)
    if identifier in file_id_storage:
        # Это видео, отправленное напрямую
        file_id = file_id_storage[identifier]
        video_path = os.path.join(DOWNLOAD_DIR, f"{file_id}.mp4")
    else:
        # Это видео, скачанное по ссылке
        video_path = os.path.join(DOWNLOAD_DIR, f"{identifier}")

    # Определяем путь к водяному знаку в зависимости от выбора
    if watermark_type == "pushenter":
        watermark_file = "pushenter.png"
    else:
        watermark_file = "vanshot.png"

    watermark_path = os.path.join(WATERMARKS_DIR, watermark_file)
    output_path = video_path.replace(".mp4", f"_{watermark_type}.mp4")

    watermarked_video = add_watermark(video_path, watermark_path, output_path)
    if watermarked_video:
        await bot.send_video(callback_query.from_user.id, open(watermarked_video, 'rb'))
        os.remove(video_path)
        os.remove(watermarked_video)
        # Удаляем file_id из хранилища, если это прямое видео
        if identifier in file_id_storage:
            file_id_storage.pop(identifier, None)
        logging.info("Видео с водяным знаком отправлено и временные файлы удалены.")
    else:
        await bot.send_message(callback_query.from_user.id, "Ошибка при наложении водяного знака!")

# Обработчик выбора без водяного знака
@dp.callback_query_handler(lambda c: c.data.startswith('no_watermark_'))
async def handle_no_watermark(callback_query: types.CallbackQuery):
    """Обработка выбора без водяного знака"""
    identifier = callback_query.data.split('_')[2]  # Это либо short_id, либо video_path

    # Определяем, является ли identifier short_id (для прямых видео) или video_path (для скачанных)
    if identifier in file_id_storage:
        # Это видео, отправленное напрямую
        file_id = file_id_storage[identifier]
        video_path = os.path.join(DOWNLOAD_DIR, f"{file_id}.mp4")
    else:
        # Это видео, скачанное по ссылке
        video_path = os.path.join(DOWNLOAD_DIR, f"{identifier}")

    await bot.send_video(callback_query.from_user.id, open(video_path, 'rb'))
    os.remove(video_path)
    # Удаляем file_id из хранилища, если это прямое видео
    if identifier in file_id_storage:
        file_id_storage.pop(identifier, None)
    logging.info("Видео без водяного знака отправлено.")

# Обработчик выбора качества (остается без изменений)
@dp.callback_query_handler(lambda c: c.data.startswith('quality_'))
async def handle_quality_selection(callback_query: types.CallbackQuery):
    """Обработка выбора качества видео"""
    quality, url = callback_query.data.split('_')[1], '_'.join(callback_query.data.split('_')[2:])

    await callback_query.answer(f"Скачиваю видео с качеством {quality}...")

    # Скачиваем видео с выбранным качеством
    video_path = download_video(url, resolution=quality)
    if video_path:
        # После скачивания, предлагаем добавить водяной знак или не добавлять
        buttons = [
            types.InlineKeyboardButton(text="PushEnter", callback_data=f"watermark_pushenter_{video_path}"),
            types.InlineKeyboardButton(text="Ваншот", callback_data=f"watermark_vanshot_{video_path}"),
            types.InlineKeyboardButton(text="Без водяного знака", callback_data=f"no_watermark_{video_path}")
        ]
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(*buttons)
        await bot.send_message(callback_query.from_user.id, "Выберите действие с видео:", reply_markup=keyboard)
    else:
        await bot.send_message(callback_query.from_user.id, "Ошибка при скачивании видео!")


# -------------------------------
# Запуск бота
# -------------------------------
if __name__ == "__main__":
    logging.info("Запуск бота...")
    executor.start_polling(dp, skip_updates=True)
