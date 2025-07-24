import os
import logging
import asyncio
import replicate
import uuid
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from sqlalchemy import select
from database.db import async_session
from database.models import User, PaymentRecord
from keyboards import main_menu_kb, MAIN_MENU_BUTTON_TEXT

# --- Загрузка переменных окружения ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

# --- Логирование ---
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("ideogram")

# --- FSM ---
class IdeogramImageGenState(StatesGroup):
    SELECTING_ASPECT = State()
    SELECTING_STYLE = State()
    AWAITING_PROMPT = State()
    CONFIRM_GENERATION_IDEOGRAM = State()

# --- Стоимость генерации ---
def calculate_ideogram_price() -> float:
    return 9.0

# --- Работа с балансом ---
async def get_user_balance(user_id: int) -> float:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalars().first()
        if user is None:
            user = User(telegram_id=user_id, balance=0)
            session.add(user)
            await session.commit()
            return 0.0
        return float(user.balance)

async def deduct_user_balance(user_id: int, amount: float) -> bool:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalars().first()
        if user and user.balance >= amount:
            user.balance -= amount
            session.add(user)
            session.add(PaymentRecord(
                user_id=user.id,
                amount=amount,
                payment_id=str(uuid.uuid4()),
                status="succeeded"
            ))
            await session.commit()
            return True
        return False

# --- Клавиатура ---
def aspect_ratio_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1:1", callback_data="ideogram_aspect_1:1"),
            InlineKeyboardButton(text="9:16", callback_data="ideogram_aspect_2:3"),
            InlineKeyboardButton(text="16:9", callback_data="ideogram_aspect_16:9"),
        ]
    ])

def style_type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Auto", callback_data="ideogram_style_auto"),
            InlineKeyboardButton(text="General", callback_data="ideogram_style_general"),
            InlineKeyboardButton(text="Anime", callback_data="ideogram_style_anime"),
        ],
        [
            InlineKeyboardButton(text="Realistic", callback_data="ideogram_style_realistic"),
            InlineKeyboardButton(text="Design", callback_data="ideogram_style_design"),
            InlineKeyboardButton(text="Render 3D", callback_data="ideogram_style_render3d"),
        ]
    ])

# --- Старт ---
async def ideogram_start(message: Message, state: FSMContext):
    await state.clear()

    description = (
        "🖼️ Image Generation Bot на базе нейросети **Ideogram V2 Turbo** — быстрый и мощный генератор изображений с поддержкой современного **инпейнтинга**, точного понимания промптов и качественной генерации текста на изображениях.\n\n"
        "⚠️ Важно:промпт — на английском языке\n"
        f"💰 Стоимость: {calculate_ideogram_price():.2f} ₽ за генерацию"
    )
    await message.answer(description, parse_mode="Markdown")
    await state.set_state(IdeogramImageGenState.SELECTING_ASPECT)
    await message.answer("⬇️ Выбери соотношение сторон:", reply_markup=aspect_ratio_kb())

# --- Главное меню ---
async def go_main_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🏠 Вы в главном меню", reply_markup=main_menu_kb())

# --- Обработка ---
async def handle_aspect_ideogram(callback: CallbackQuery, state: FSMContext):
    aspect = callback.data.replace("ideogram_aspect_", "")
    await state.update_data(aspect_ratio=aspect)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✅ Соотношение выбрано. Теперь выбери стиль:", reply_markup=style_type_kb())
    await state.set_state(IdeogramImageGenState.SELECTING_STYLE)
    await callback.answer()

async def handle_style_aspect_ideogram(callback: CallbackQuery, state: FSMContext):
    style = callback.data.replace("ideogram_style_", "")
    await state.update_data(style=style)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✏️ Введите описание (prompt) на английском:")
    await state.set_state(IdeogramImageGenState.AWAITING_PROMPT)
    await callback.answer()

async def handle_prompt_aspect_ideogram(message: Message, state: FSMContext):
    prompt = message.text.strip()
    if len(prompt) < 5:
        await message.answer("❌ Промпт слишком короткий.")
        return

    price = calculate_ideogram_price()
    balance = await get_user_balance(message.from_user.id)

    if balance < price:
        await message.answer(f"❌ Недостаточно средств. Стоимость: {price:.2f} ₽ | Баланс: {balance:.2f} ₽. 💼 Для пополнения перейдите в раздел «Баланс».")
        await state.clear()
        return

    await state.update_data(prompt=prompt, price=price)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить генерацию", callback_data="confirm_generation_ideogram")]
    ])
    await message.answer(f"💰 Стоимость: {price:.2f} ₽\nВаш баланс: {balance:.2f} ₽\n Подтвердите генерацию:", reply_markup=kb)
    await state.set_state(IdeogramImageGenState.CONFIRM_GENERATION_IDEOGRAM)

async def confirm_generation_ideogram(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    user_id = callback.from_user.id

    if not await deduct_user_balance(user_id, data["price"]):
        await callback.message.edit_text("❌ Не удалось списать средства.")
        await state.clear()
        return

    await callback.message.edit_text("🎥 Генерация изображения... Это может занять пару минут.")

    try:
        replicate.api_token = REPLICATE_API_TOKEN
        prediction = await replicate.predictions.async_create(
            model="ideogram-ai/ideogram-v2-turbo",
            input={
                "prompt": data["prompt"],
                "aspect_ratio": data.get("aspect_ratio", "1:1"),
                "style": data.get("style", "auto")
            }
        )

        while prediction.status not in ("succeeded", "failed", "canceled"):
            await asyncio.sleep(2)
            prediction = await replicate.predictions.async_get(prediction.id)

        if prediction.status != "succeeded" or not prediction.output:
            raise RuntimeError("Генерация не удалась")

        image_url = prediction.output[0] if isinstance(prediction.output, list) else prediction.output
        await callback.message.answer_photo(image_url, caption=f"✅ Prompt: {data['prompt']}")

    except Exception as e:
        logger.exception("Ошибка генерации изображения")
        await callback.message.answer("❌ Произошла ошибка при генерации.")

    await state.clear()

# --- main ---
async def main():
    if not BOT_TOKEN or not REPLICATE_API_TOKEN:
        raise EnvironmentError("BOT_TOKEN или REPLICATE_API_TOKEN не установлены")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(ideogram_start, Command("start"))
    dp.callback_query.register(handle_aspect_ideogram, F.data.startswith("ideogram_aspect_"), StateFilter(IdeogramImageGenState.SELECTING_ASPECT))
    dp.callback_query.register(handle_style_aspect_ideogram, F.data.startswith("ideogram_style_"), StateFilter(IdeogramImageGenState.SELECTING_STYLE))
    dp.message.register(handle_prompt_aspect_ideogram, StateFilter(IdeogramImageGenState.AWAITING_PROMPT))
    dp.callback_query.register(confirm_generation_ideogram, F.data == "confirm_generation_ideogram", StateFilter(IdeogramImageGenState.CONFIRM_GENERATION_IDEOGRAM))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
