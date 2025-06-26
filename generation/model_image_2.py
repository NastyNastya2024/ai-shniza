import logging
import requests
import fal_client
from aiogram import F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import Dispatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ImageGen2States(StatesGroup):
    waiting_for_image = State()
    waiting_for_prompt = State()
    processing_image = State()
    image_ready = State()

async def start_image_generation_2(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("📸 Пожалуйста, отправьте изображение для генерации.")
    await state.set_state(ImageGen2States.waiting_for_image)
    logger.info("🟢 FSM: Ожидаем изображение")

async def handle_photo(message: types.Message, state: FSMContext):
    logger.info("📥 Получено фото от пользователя")
    if not message.photo:
        await message.answer("❌ Пожалуйста, отправьте фотографию.")
        return

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    file_url = f"https://api.telegram.org/file/bot{message.bot.token}/{file.file_path}"
    logger.info(f"📤 Получаем изображение с URL: {file_url}")

    try:
        response = requests.get(file_url)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке изображения: {e}")
        await message.answer("❌ Не удалось получить изображение.")
        return

    # Загружаем на fal_client (если нужна загрузка, либо просто сохраняем URL)
    # fal_client.upload_file можно использовать, если надо

    await state.update_data(image_url=file_url)
    await message.answer("✅ Изображение получено! Введите текстовое описание (prompt).")
    await state.set_state(ImageGen2States.waiting_for_prompt)
    logger.info(f"📌 FSM перешёл в состояние: {ImageGen2States.waiting_for_prompt}")

async def handle_prompt(message: types.Message, state: FSMContext):
    prompt = message.text.strip()
    if not prompt:
        await message.answer("❌ Введите корректный текст.")
        return

    await state.update_data(prompt=prompt)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Генерировать изображение", callback_data="generate_image_2")],
    ])
    await message.answer("📋 Нажмите для генерации изображения:", reply_markup=keyboard)
    await state.set_state(ImageGen2States.processing_image)

async def generate_image_2(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    prompt = data.get("prompt")
    image_url = data.get("image_url")

    if not prompt or not image_url:
        await callback.message.answer("❌ Не хватает данных для генерации.")
        await state.clear()
        return

    await callback.message.edit_text("⏳ Генерирую изображение, подождите...")

    # Функция вызова fal_client
    def on_queue_update(update):
        if isinstance(update, fal_client.InProgress):
            for log in update.logs:
                logger.info(f"FAL log: {log['message']}")

    try:
        result = fal_client.subscribe(
            "fal-ai/flux-pro/v1.1-ultra",
            arguments={
                "prompt": prompt,
                "image_url": image_url,
                "num_images": 1,
                "enable_safety_checker": True,
                "safety_tolerance": "2",
                "output_format": "jpeg",
                "aspect_ratio": "16:9"
            },
            with_logs=True,
            on_queue_update=on_queue_update,
        )
    except Exception as e:
        logger.error(f"Ошибка генерации изображения: {e}")
        await callback.message.answer("❌ Ошибка генерации изображения.")
        await state.clear()
        return

    if result and "images" in result and result["images"]:
        img_url = result["images"][0]["url"]
        await callback.message.answer_photo(img_url, caption="🎉 Изображение готово!")
        await state.update_data(generated_image_url=img_url)
        await state.set_state(ImageGen2States.image_ready)
    else:
        await callback.message.answer("❌ Не удалось сгенерировать изображение.")
        await state.clear()

def setup_imagegen2_handlers(dp: Dispatcher):
    dp.callback_query.register(start_image_generation_2, F.data == "img_model_2")
    dp.message.register(handle_photo, ImageGen2States.waiting_for_image, F.photo)
    dp.message.register(handle_prompt, ImageGen2States.waiting_for_prompt, F.text)
    dp.callback_query.register(generate_image_2, F.data == "generate_image_2", ImageGen2States.processing_image)

