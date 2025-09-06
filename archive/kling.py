import os
import logging
import asyncio
import random

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from dotenv import load_dotenv
import replicate

from keyboards import main_menu_kb

# --- Загрузка переменных окружения ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

# --- Логирование ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("flux")

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

# --- Хендлер запуска генерации ---
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    description = (
        "🎬 *Cartoon Video Bot* на базе нейросети **Flux Kontext** — генерация мультфильмов из изображений и текста.\n\n"
        "📋 *Что умеет:*\n"
        "- Мультяшные стили (Pixar, Anime, Disney и др.)\n"
        "- Камера, движение, сюжет\n"
        "- Фоны и визуальные эффекты\n\n"
        "⚠️ *Важно:*\n"
        "- Промпт (описание) — на английском\n"
        "- 💰 Стоимость: ~$1.2 за генерацию"
    )
    await message.answer(description, parse_mode="Markdown")
    await message.answer("📌 Пришли изображение, с которым хочешь работать.", reply_markup=flux_menu_kb())
    await state.set_state(FluxKontextState.WAITING_IMAGE)

# --- Обработка изображения ---
async def handle_image_flux(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Пожалуйста, пришли изображение.", reply_markup=flux_menu_kb())
        return

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
    await state.update_data(image_url=image_url)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1:1", callback_data="aspect_1_1"),
            InlineKeyboardButton(text="16:9", callback_data="aspect_16_9"),
            InlineKeyboardButton(text="9:16", callback_data="aspect_9_16")
        ]
    ])
    await message.answer("📐 Выбери соотношение сторон (Aspect Ratio):", reply_markup=kb)
    await state.set_state(FluxKontextState.WAITING_ASPECT_RATIO)

# --- Выбор Aspect Ratio ---
async def handle_aspect_ratio(callback: CallbackQuery, state: FSMContext):
    aspect_raw = callback.data.replace("aspect_", "")
    aspect = aspect_raw.replace("_", ":")
    await state.update_data(aspect_ratio=aspect, safety_tolerance=3)

    await callback.message.edit_text("✅ Соотношение сторон выбрано. Загрузка стилей...")
    await callback.answer()

    await handle_flux_style(callback.message, state)

# --- Запрос стиля и промпта ---
async def handle_flux_style(message: Message, state: FSMContext):
    styles = [
        "90s Arcade Style", "Disney Style", "Tim Burton Style", "Pixar Toy Look",
        "Sci-Fi Animation", "Anime Fantasy", "Animal Cartoon",
        "Dark Comic", "Noir Detective", "Studio Ghibli"
    ]
    style_text = "\n".join(f"- {s}" for s in styles)

    await message.answer(
        f"✨ Пришли описание сцены на английском языке (prompt).\n\n"
        f"*Примеры стилей:*\n{style_text}\n\n"
        f"📝 *Пример:* _Make this a 90s cartoon_",
        parse_mode="Markdown",
        reply_markup=flux_menu_kb()
    )
    await state.set_state(FluxKontextState.WAITING_PROMPT)

# --- Обработка промпта ---
async def handle_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()
    if prompt == "🏠 Главное меню":
        await go_main_menu(message, state)
        return

    if prompt == "🔁 Повторить генерацию":
        await cmd_start(message, state)
        return

    if len(prompt) < 5:
        await message.answer("❌ Промпт слишком короткий.", reply_markup=flux_menu_kb())
        return

    data = await state.get_data()
    image_url = data.get("image_url")
    aspect_ratio = data.get("aspect_ratio", "match_input_image")
    safety_tolerance = data.get("safety_tolerance", 3)

    if not image_url:
        await message.answer("❌ Изображение не найдено. Начните заново.", reply_markup=flux_menu_kb())
        return

    await message.answer("⏳ Генерация изображения...", reply_markup=flux_menu_kb())

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

        if prediction.status == "succeeded" and prediction.output:
            output_url = (
                prediction.output if isinstance(prediction.output, str)
                else prediction.output[0] if isinstance(prediction.output, list)
                else None
            )

            if output_url:
                await message.answer_photo(
                    output_url,
                    caption=f"✅ Готово!\n\n🔤 *Prompt:* {prompt}",
                    parse_mode="Markdown",
                    reply_markup=flux_menu_kb()
                )
            else:
                raise ValueError("Ошибка: URL изображения не найден")

        else:
            await message.answer("❌ Не удалось сгенерировать изображение.", reply_markup=flux_menu_kb())
            logger.error(f"Ошибка генерации. Статус: {prediction.status}")

    except Exception as e:
        logger.exception("❌ Ошибка во время генерации:")
        await message.answer("⚠️ Ошибка генерации. Попробуйте позже.", reply_markup=flux_menu_kb())

    await state.clear()

# --- Главное меню ---
async def go_main_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы в главном меню.", reply_markup=main_menu_kb())

async def repeat_generation(message: Message, state: FSMContext):
    await cmd_start(message, state)

# --- Локальный запуск (если нужно) ---
async def main():
    logger.info("Запуск Flux Kontext...")

    if not BOT_TOKEN or not REPLICATE_API_TOKEN:
        raise EnvironmentError("❌ BOT_TOKEN или REPLICATE_API_TOKEN не установлены")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(handle_image_flux, StateFilter(FluxKontextState.WAITING_IMAGE))
    dp.callback_query.register(handle_aspect_ratio, StateFilter(FluxKontextState.WAITING_ASPECT_RATIO))
    dp.message.register(handle_prompt, StateFilter(FluxKontextState.WAITING_PROMPT))
    dp.message.register(go_main_menu, F.text == "🏠 Главное меню")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
