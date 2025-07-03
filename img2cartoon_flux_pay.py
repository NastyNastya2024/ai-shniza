import os
import logging
import asyncio
import random

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

import replicate
from dotenv import load_dotenv

# --- Загрузка переменных окружения ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

# --- Логирование ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger("tg_bot")

# --- Состояния FSM ---
class FluxKontextState(StatesGroup):
    WAITING_IMAGE = State()
    WAITING_ASPECT_RATIO = State()
    WAITING_STYLE_TYPE = State()
    WAITING_SAFETY_TOLERANCE = State()
    WAITING_PROMPT = State()

# --- Старт бота ---
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    text = (
        "🎬 *Cartoon Video Bot* на базе нейросети **Flux Kontext** — генерация мультфильмов из изображений и текста.\n\n"
        "📋 *Что умеет:*\n"
        "- Мультяшные стили (Pixar, Anime, Disney и др.)\n"
        "- Камера, движение, сюжет\n"
        "- Фоны и визуальные эффекты\n\n"
        "⚠️ *Важно:*\n"
        "- Промпт (описание) — на английском\n"
        "- 💰 Стоимость: ~$1.2 за генерацию"
    )

    await message.answer(text, parse_mode="Markdown")
    await message.answer("📌 Пришли изображение, с которым хочешь работать.")
    await state.set_state(FluxKontextState.WAITING_IMAGE)

# --- Обработка изображения ---
async def handle_image_flux(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Пожалуйста, пришли изображение.")
        return

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
    await state.update_data(image_url=image_url)

    # Кнопки aspect ratio
    aspect_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1:1", callback_data="aspect_1:1"),
            InlineKeyboardButton(text="16:9", callback_data="aspect_16:9"),
            InlineKeyboardButton(text="9:16", callback_data="aspect_9:16")
        ]
    ])

    await message.answer("📐 Выбери соотношение сторон (Aspect Ratio):", reply_markup=aspect_kb)
    await state.set_state(FluxKontextState.WAITING_ASPECT_RATIO)

# --- Обработка выбора aspect ratio ---
async def handle_aspect_ratio(callback: CallbackQuery, state: FSMContext):
    aspect_ratio = callback.data.replace("aspect_", "")
    await state.update_data(aspect_ratio=aspect_ratio)

    # Кнопки style type
    style_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Auto", callback_data="style_auto"),
            InlineKeyboardButton(text="General", callback_data="style_general"),
            InlineKeyboardButton(text="Realistic", callback_data="style_realistic"),
        ],
        [
            InlineKeyboardButton(text="Design", callback_data="style_design"),
            InlineKeyboardButton(text="Render 3D", callback_data="style_render3d"),
            InlineKeyboardButton(text="Anime", callback_data="style_anime"),
        ]
    ])

    await callback.message.edit_text("🎨 Выбери визуальный стиль:", reply_markup=style_kb)
    await state.set_state(FluxKontextState.WAITING_STYLE_TYPE)
    await callback.answer()

# --- Обработка выбора style type ---
async def handle_style_type(callback: CallbackQuery, state: FSMContext):
    style = callback.data.replace("style_", "")
    await state.update_data(style_type=style)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 (Минимум)", callback_data="safety_1"),
            InlineKeyboardButton(text="2 (Стандарт)", callback_data="safety_2"),
            InlineKeyboardButton(text="3 (Максимум)", callback_data="safety_3"),
        ]
    ])

    await callback.message.edit_text("🛡 Выбери уровень фильтрации контента (Safety Tolerance):", reply_markup=kb)
    await state.set_state(FluxKontextState.WAITING_SAFETY_TOLERANCE)
    await callback.answer()

# --- Обработка уровня безопасности ---
async def handle_safety_tolerance(callback: CallbackQuery, state: FSMContext):
    tolerance = int(callback.data.replace("safety_", ""))
    await state.update_data(safety_tolerance=tolerance)

    cartoon_styles = [
        "90s Arcade Style", "Disney Style", "Tim Burton Style", "Pixar Toy Look",
        "Sci-Fi Animation", "Anime Fantasy", "Animal Cartoon",
        "Dark Comic", "Noir Detective", "Studio Ghibli\n\n",
        "📝 *Пример промпта:*\n_Make this a 90s cartoon_"
    ]
    style_list = "\n".join(f"- {s}" for s in cartoon_styles)

    await callback.message.edit_text(
        f"✨ Теперь пришли описание сцены на английском языке (prompt).\n\n"
        f"*Примеры стилей:*\n{style_list}",
        parse_mode="Markdown"
    )
    await state.set_state(FluxKontextState.WAITING_PROMPT)
    await callback.answer()

# --- Обработка промпта и генерация ---
async def handle_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()
    data = await state.get_data()
    image_url = data.get("image_url")
    aspect_ratio = data.get("aspect_ratio", "match_input_image")
    safety_tolerance = data.get("safety_tolerance", 2)
    style_type = data.get("style_type", "auto")

    if not image_url:
        await message.answer("❌ Изображение не найдено. Начните с /start.")
        return

    await message.answer("⏳ Генерирую изображение...")

    try:
        client = replicate.Client(api_token=REPLICATE_API_TOKEN)
        seed = random.randint(0, 2**31 - 1)

        prediction = client.predictions.create(
            version="black-forest-labs/flux-kontext-pro",
            input={
                "prompt": prompt,
                "input_image": image_url,
                "aspect_ratio": aspect_ratio,
                "output_format": "jpg",
                "safety_tolerance": safety_tolerance,
                "seed": seed,
                "style": style_type
            }
        )

        logger.info(f"[handle_prompt] Prediction created: {prediction.id}")
        while prediction.status not in ("succeeded", "failed", "canceled"):
            await asyncio.sleep(2)
            prediction.reload()
            logger.info(f"[handle_prompt] Status: {prediction.status}")

        if prediction.status == "succeeded" and prediction.output:
            output = prediction.output
            image_result_url = output if isinstance(output, str) else output[0]
            await message.answer_photo(image_result_url, caption=f"✅ Готово!\n\n🔤 *Prompt:* {prompt}", parse_mode="Markdown")
        else:
            await message.answer("❌ Не удалось сгенерировать изображение.")
            logger.error(f"[handle_prompt] Generation failed. Status: {prediction.status}, Output: {prediction.output}")

    except Exception:
        logger.exception("[handle_prompt] Ошибка генерации изображения")
        await message.answer("❌ Произошла ошибка при генерации.")
    
    await state.clear()

# --- Запуск бота ---
async def main():
    logger.info("🚀 Запуск Telegram-бота...")

    if not BOT_TOKEN or not REPLICATE_API_TOKEN:
        raise EnvironmentError("BOT_TOKEN или REPLICATE_API_TOKEN не установлены в .env")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(handle_image_flux, StateFilter(FluxKontextState.WAITING_IMAGE))
    dp.callback_query.register(handle_aspect_ratio, StateFilter(FluxKontextState.WAITING_ASPECT_RATIO))
    dp.callback_query.register(handle_style_type, StateFilter(FluxKontextState.WAITING_STYLE_TYPE))
    dp.callback_query.register(handle_safety_tolerance, StateFilter(FluxKontextState.WAITING_SAFETY_TOLERANCE))
    dp.message.register(handle_prompt, StateFilter(FluxKontextState.WAITING_PROMPT))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
