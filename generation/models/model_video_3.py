
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

logger = logging.getLogger(__name__)

class PixverseStates(StatesGroup):
    waiting_for_image = State()
    waiting_for_prompt = State()
    processing_video = State()
    video_ready = State()

async def start_pixverse_generation(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("📸 Отправьте изображение для Pixverse 4.5.")
    await state.set_state(PixverseStates.waiting_for_image)

async def handle_pixverse_photo(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Пожалуйста, отправьте фото.")
        return

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"

    try:
        response = requests.get(file_url)
        response.raise_for_status()
        upload = requests.post(
            "https://api.imgbb.com/1/upload",
            params={"key": IMGBB_API_KEY},
            files={"image": response.content}
        )
        upload.raise_for_status()
        image_url = upload.json()["data"]["url"]
    except Exception as e:
        logger.error(f"Ошибка загрузки изображения: {e}")
        await message.answer("❌ Ошибка загрузки изображения.")
        return

    await state.update_data(image_url=image_url)
    await message.answer("✅ Отлично! Теперь введите текст (prompt):")
    await state.set_state(PixverseStates.waiting_for_prompt)

async def handle_pixverse_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()
    if not prompt:
        await message.answer("❌ Введите корректный текст.")
        return

    await state.update_data(prompt=prompt)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Генерировать", callback_data="pixverse_generate")],
        [InlineKeyboardButton(text="🔄 Статус", callback_data="pixverse_check")]
    ])
    await message.answer("📋 Что дальше?", reply_markup=keyboard)
    await state.set_state(PixverseStates.processing_video)

async def generate_pixverse_video(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    prompt = data.get("prompt")
    image_url = data.get("image_url")

    await callback.message.edit_text("⏳ Генерируем видео через Pixverse 4.5...")

    try:
        handler = await fal_client.submit_async(
            "fal-ai/pixverse/v4.5/image-to-video",
            arguments={
                "prompt": prompt,
                "image_url": image_url,
                "aspect_ratio": "16:9",
                "resolution": "720p",
                "duration": "5",
                "negative_prompt": "blurry, low quality, pixelated"
            }
        )

        async for event in handler.iter_events(with_logs=True):
            logger.info(f"Pixverse event: {event}")

        result = await handler.get()
        video_url = (
            result.get("video_url") or
            (result.get("video") and result["video"].get("url")) or
            (result.get("output") and result["output"].get("video"))
        )

        if video_url:
            await callback.message.answer_video(video_url, caption="🎉 Видео готово!")
            await state.update_data(video_url=video_url)
            await state.set_state(PixverseStates.video_ready)
        else:
            raise ValueError("Видео не получено")
    except Exception as e:
        logger.error(f"❌ Ошибка Pixverse: {e}")
        await callback.message.answer("❌ Ошибка при генерации.")
        await state.clear()

async def check_pixverse_status(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    video_url = data.get("video_url")
    if video_url:
        await callback.message.answer_video(video_url, caption="✅ Видео готово.")
    else:
        await callback.message.answer("⏳ Видео ещё не готово.")

def setup_pixverse_handlers(dp: Dispatcher):
    dp.message.register(handle_pixverse_photo, PixverseStates.waiting_for_image, F.photo)
    dp.message.register(handle_pixverse_prompt, PixverseStates.waiting_for_prompt, F.text)
    dp.callback_query.register(generate_pixverse_video, F.data == "pixverse_generate", PixverseStates.processing_video)
    dp.callback_query.register(check_pixverse_status, F.data == "pixverse_check", PixverseStates.processing_video)

