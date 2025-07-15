import os
import logging
import asyncio
import random

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery, FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

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
    WAITING_PROMPT = State()

# --- Клавиатуры ---
def flux_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔁 Повторить генерацию")],
        [KeyboardButton(text="🏠 Главное меню")]
    ], resize_keyboard=True)

def back_main_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🏠 Главное меню")]
    ], resize_keyboard=True)

# --- Новый стартовый хендлер ---
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    try:
        photo = FSInputFile("welcome.jpg")
        await message.answer_photo(photo, caption="👋 Добро пожаловать в Flux Kontext!")
    except Exception as e:
        logger.warning(f"[cmd_start] Не удалось отправить изображение: {e}")
        await message.answer("👋 Добро пожаловать в Flux Kontext!")

    text = (
        "🎬 *Cartoon Video Bot* на базе нейросети **Flux Kontext** — генерация мультфильмов из изображений и текста.\n\n"
        "📋 *Что умеет:*\n"
        "- Мультяшные стили (Pixar, Anime, Disney и др.)\n"
        "- Камера, движение, сюжет\n"
        "- Фоны и визуальные эффекты\n\n"
        "⚠️ *Важно:*\n"
        "- Промпт (описание) — на английском\n"
        "- 💰 Стоимость: ~$1.2 за генерацию\n"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=back_main_menu_kb())
    await message.answer("📌 Пришли изображение, с которым хочешь работать.")
    await state.set_state(FluxKontextState.WAITING_IMAGE)

# --- Обработка изображения с выбором Aspect Ratio ---
async def handle_image_flux(message: Message, state: FSMContext):
    if message.text == "🏠 Главное меню":
        await cmd_start(message, state)
        return

    if not message.photo:
        await message.answer("❌ Пожалуйста, пришли изображение.", reply_markup=back_main_menu_kb())
        return

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
    await state.update_data(image_url=image_url)

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="1:1", callback_data="aspect_1_1"),
        InlineKeyboardButton(text="16:9", callback_data="aspect_16_9"),
        InlineKeyboardButton(text="9:16", callback_data="aspect_9_16")
    )
    await message.answer("📐 Выбери соотношение сторон (Aspect Ratio):", reply_markup=kb.as_markup())
    await state.set_state(FluxKontextState.WAITING_ASPECT_RATIO)

# --- Выбор Aspect Ratio ---
async def handle_aspect_ratio(callback: CallbackQuery, state: FSMContext):
    aspect_raw = callback.data.replace("aspect_", "")
    aspect = aspect_raw.replace("_", ":")
    await state.update_data(aspect_ratio=aspect, safety_tolerance=3)  # по умолчанию максимум

    await callback.message.edit_text("✅ Соотношение сторон выбрано. Загрузка стилей...")
    await callback.answer()

    await handle_flux_style(callback.message, state)

# --- Отображение стилей ---
async def handle_flux_style(message: Message, state: FSMContext):
    cartoon_styles = [
        "90s Arcade Style", "Disney Style", "Tim Burton Style", "Pixar Toy Look",
        "Sci-Fi Animation", "Anime Fantasy", "Animal Cartoon",
        "Dark Comic", "Noir Detective", "Studio Ghibli\n\n",
        "📝 *Пример промпта:*\n"
        "_Make this a 90s cartoon_"
    ]
    style_list = "\n".join(f"- {s}" for s in cartoon_styles)

    await message.answer(
        f"✨ Теперь пришли описание сцены на английском языке (prompt).\n\n"
        f"*Примеры стилей:*\n{style_list}",
        parse_mode="Markdown",
        reply_markup=back_main_menu_kb()
    )
    await state.set_state(FluxKontextState.WAITING_PROMPT)

# --- Обработка промпта и генерация изображения ---
async def handle_prompt(message: Message, state: FSMContext):
    if message.text == "🏠 Главное меню":
        await cmd_start(message, state)
        return

    if message.text == "🔁 Повторить генерацию":
        await cmd_start(message, state)
        return

    prompt = message.text.strip()
    data = await state.get_data()
    image_url = data.get("image_url")
    aspect_ratio = data.get("aspect_ratio", "match_input_image")
    safety_tolerance = data.get("safety_tolerance", 3)

    if not image_url:
        await message.answer("❌ Изображение не найдено. Попробуй сначала с /start.")
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
                "seed": seed
            }
        )
        logger.info(f"[handle_prompt] Prediction created: {prediction.id}")
        while prediction.status not in ("succeeded", "failed", "canceled"):
            await asyncio.sleep(2)
            prediction.reload()
            logger.info(f"[handle_prompt] Status: {prediction.status}")
        if prediction.status == "succeeded" and prediction.output:
            output = prediction.output
            logger.info(f"[handle_prompt] Output: {output}")
            if isinstance(output, str) and output.startswith(("http://", "https://")):
                image_result_url = output
            elif isinstance(output, list) and output and isinstance(output[0], str) and output[0].startswith(("http://", "https://")):
                image_result_url = output[0]
            else:
                raise ValueError(f"Неверный результат от модели: {output}")
            await message.answer_photo(
                image_result_url,
                caption=f"✅ Готово!\n\n🔤 *Prompt:* {prompt}",
                parse_mode="Markdown",
                reply_markup=flux_menu_kb()
            )
        else:
            await message.answer("❌ Не удалось сгенерировать изображение. Попробуйте позже.", reply_markup=flux_menu_kb())
            logger.error(f"[handle_prompt] Generation failed. Status: {prediction.status}, Output: {prediction.output}")
    except Exception:
        logger.exception("[handle_prompt] Ошибка генерации изображения")
        await message.answer("❌ Произошла ошибка при генерации. Попробуйте позже.", reply_markup=flux_menu_kb())

    await state.clear()

# --- Основной запуск ---
async def main():
    logger.info("Запуск Telegram-бота...")

    if not BOT_TOKEN or not REPLICATE_API_TOKEN:
        raise EnvironmentError("BOT_TOKEN или REPLICATE_API_TOKEN не установлены в .env")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрация хендлеров
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(handle_image_flux, StateFilter(FluxKontextState.WAITING_IMAGE))
    dp.callback_query.register(handle_aspect_ratio, StateFilter(FluxKontextState.WAITING_ASPECT_RATIO))
    dp.message.register(handle_prompt, StateFilter(FluxKontextState.WAITING_PROMPT))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
