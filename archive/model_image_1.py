import logging
import requests
import fal_client
import asyncio
import os

from aiogram import F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import Dispatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")

class ImageGenStates(StatesGroup):
    waiting_for_image = State()
    waiting_for_prompt = State()
    processing_image = State()
    image_ready = State()

async def start_image_generation_1(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("🖼 Пожалуйста, отправьте изображение.")
    await state.set_state(ImageGenStates.waiting_for_image)
    logger.info("🟢 FSM (ImageGen1): Ожидаем изображение")

async def handle_photo_imagegen1(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Пожалуйста, отправьте изображение.")
        return

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
    logger.info(f"📤 Загружаем фото с: {file_url}")

    try:
        response = requests.get(file_url)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Ошибка загрузки изображения: {e}")
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
        logger.info(f"✅ Фото загружено на imgbb: {image_url}")
    except Exception as e:
        logger.error(f"Ошибка при загрузке на imgbb: {e}")
        await message.answer("❌ Ошибка загрузки изображения.")
        return

    await state.update_data(image_url=image_url)
    await message.answer("✏️ Введите описание (prompt) к изображению.")
    await state.set_state(ImageGenStates.waiting_for_prompt)

async def handle_prompt_imagegen1(message: Message, state: FSMContext):
    prompt = message.text.strip()
    if not prompt:
        await message.answer("❌ Введите корректный текст.")
        return

    await state.update_data(prompt=prompt)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎨 Генерировать изображение", callback_data="generate_image_1")]
    ])
    await message.answer("📋 Что дальше?", reply_markup=keyboard)
    await state.set_state(ImageGenStates.processing_image)

async def generate_image_1(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    prompt = data.get("prompt")
    image_url = data.get("image_url")

    if not prompt or not image_url:
        await callback.message.answer("❌ Не хватает данных.")
        await state.clear()
        return

    await callback.message.edit_text("⏳ Генерация изображения...")

    # Вызов синхронной функции в отдельном потоке, чтобы не блокировать event loop
    result_url = await asyncio.to_thread(generate_fluxpro_image_sync, prompt, image_url)

    if result_url:
        await callback.message.answer_photo(result_url, caption="✅ Готово!")
        await state.set_state(ImageGenStates.image_ready)
    else:
        await callback.message.answer("❌ Не удалось сгенерировать изображение.")
        await state.clear()

def on_queue_update(update):
    if isinstance(update, fal_client.InProgress) and update.logs:
        for log in update.logs:
            logger.info(f"FAL Log: {log['message']}")

def generate_fluxpro_image_sync(prompt: str, image_url: str) -> str | None:
    try:
        result = fal_client.subscribe(
            "fal-ai/flux-pro/kontext",
            arguments={
                "prompt": prompt,
                "guidance_scale": 3.5,
                "num_images": 1,
                "safety_tolerance": "2",
                "output_format": "jpeg",
                "image_url": image_url
            },
            with_logs=True,
            on_queue_update=on_queue_update
        )

        logger.info(f"Result from fal_client.subscribe: {result}")

        images = result.get("images")
        if images and isinstance(images, list) and len(images) > 0:
            return images[0].get("url")

        return None

    except Exception as e:
        logger.error(f"Ошибка генерации изображения: {e}")
        return None

def setup_imagegen1_handlers(dp: Dispatcher):
    dp.message.register(handle_photo_imagegen1, ImageGenStates.waiting_for_image, F.photo)
    dp.message.register(handle_prompt_imagegen1, ImageGenStates.waiting_for_prompt, F.text)
    dp.callback_query.register(generate_image_1, F.data == "generate_image_1", ImageGenStates.processing_image)

