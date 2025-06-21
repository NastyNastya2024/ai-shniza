import os
import logging
import requests
import fal_client
from aiogram import F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import Dispatcher
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VideoGenStates(StatesGroup):
    waiting_for_image = State()
    waiting_for_prompt = State()
    processing_video = State()
    video_ready = State()

async def start_video_generation(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("📸 Пожалуйста, отправьте изображение для генерации видео.")
    await state.set_state(VideoGenStates.waiting_for_image)
    logger.info("🟢 FSM: Ожидаем изображение")

async def handle_photo(message: Message, state: FSMContext):
    logger.info("📥 Получено фото от пользователя")
    if not message.photo:
        await message.answer("❌ Пожалуйста, отправьте фотографию.")
        return

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
    logger.info(f"📤 Получаем изображение с URL: {file_url}")

    try:
        response = requests.get(file_url)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке изображения: {e}")
        await message.answer("❌ Не удалось получить изображение.")
        return

    try:
        upload = requests.post(
            "https://api.imgbb.com/1/upload",
            params={"key": IMGBB_API_KEY},
            files={"image": response.content}
        )
        upload.raise_for_status()
        image_url = upload.json()["data"]["url"]
        logger.info(f"✅ Изображение загружено: {image_url}")
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке на imgbb: {e}")
        await message.answer("❌ Ошибка загрузки изображения.")
        return

    await state.update_data(image_url=image_url)
    await message.answer("✅ Изображение получено! Введите текстовое описание (prompt).")
    await state.set_state(VideoGenStates.waiting_for_prompt)
    logger.info(f"📌 FSM перешёл в состояние: {VideoGenStates.waiting_for_prompt}")

async def handle_prompt(message: Message, state: FSMContext):
    logger.info("🔍 Обработка промпта")
    prompt = message.text.strip()
    if not prompt:
        await message.answer("❌ Введите корректный текст.")
        return

    await state.update_data(prompt=prompt)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Генерировать видео", callback_data="generate_video")],
        [InlineKeyboardButton(text="🔄 Проверить статус", callback_data="check_status")]
    ])
    await message.answer("📋 Что дальше?", reply_markup=keyboard)
    await state.set_state(VideoGenStates.processing_video)
    logger.info("🟢 FSM: ожидаем действия")

async def generate_video(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    prompt = data.get("prompt")
    image_url = data.get("image_url")

    if not prompt or not image_url:
        await callback.message.answer("❌ Не хватает данных.")
        await state.clear()
        return

    await callback.message.edit_text("⏳ Генерирую видео. Это может занять несколько минут...")

    video_url = await generate_video_kling(prompt, image_url)

    if video_url:
        await callback.message.answer_video(video_url, caption="🎉 Видео готово!")
        await state.update_data(video_url=video_url)
        await state.set_state(VideoGenStates.video_ready)
    else:
        await callback.message.answer("❌ Не удалось сгенерировать видео.")
        await state.clear()

async def check_status(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    video_url = data.get("video_url")
    if video_url:
        await callback.message.answer_video(video_url, caption="✅ Видео готово.")
    else:
        await callback.message.answer("⏳ Видео ещё не готово.")

async def generate_video_kling(prompt: str, image_url: str) -> str | None:
    try:
        handler = await fal_client.submit_async(
            "fal-ai/kling-video/v2.1/master/image-to-video",
            arguments={
                "prompt": prompt,
                "image_url": image_url,
                "duration": 5,
                "aspect_ratio": "16:9",
                "cfg_scale": 0.7,
                "negative_prompt": "blur, distortion, low quality"
            }
        )

        async for event in handler.iter_events(with_logs=True):
            logger.info(f"FAL event: {event}")

        result = await handler.get()
        return (
            result.get("video_url") or
            (result.get("video") and result["video"].get("url")) or
            (result.get("output") and result["output"].get("video"))
        )
    except Exception as e:
        logger.error(f"FAL AI Error: {e}")
        return None

def setup_video_handlers(dp: Dispatcher):
    # Регистрируем обработчики FSM в первую очередь
    dp.message.register(handle_photo, VideoGenStates.waiting_for_image, F.photo)
    dp.message.register(handle_prompt, VideoGenStates.waiting_for_prompt, F.text)
    dp.callback_query.register(generate_video, F.data == "generate_video", VideoGenStates.processing_video)
    dp.callback_query.register(check_status, F.data == "check_status", VideoGenStates.processing_video)

