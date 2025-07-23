import os
import logging
import asyncio
import uuid

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

import replicate
from dotenv import load_dotenv

from sqlalchemy import select
from database.db import async_session
from database.models import User, PaymentRecord

from keyboards import main_menu_kb, MAIN_MENU_BUTTON_TEXT

# --- Init ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("imagegen4")

# --- FSM ---
class ImageGenState(StatesGroup):
    AWAITING_ASPECT = State()
    AWAITING_PROMPT = State()
    CONFIRM_GENERATION = State()

# --- Pricing ---
def calculate_imagegen4_price() -> float:
    return 10.0

# --- Balance logic ---
async def get_user_balance(user_id: int) -> float:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalars().first()
        if not user:
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

# --- Keyboards ---
def aspect_ratio_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1:1", callback_data="aspect_1:1"),
            InlineKeyboardButton(text="9:16", callback_data="aspect_9:16"),
            InlineKeyboardButton(text="16:9", callback_data="aspect_16:9"),
        ]
    ])

# --- Handlers ---
async def cmd_start_imagegen4(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🖼 Google Imagen 4 — генерация изображений по тексту на английском языке.\n\n"
        f"⚠️ Минимум 15 символов.\n💰 Стоимость: {calculate_imagegen4_price():.2f} ₽\n\n"
        "⬇️ Выберите соотношение сторон:",
        parse_mode="Markdown",
        reply_markup=aspect_ratio_kb()
    )
    await state.set_state(ImageGenState.AWAITING_ASPECT)

async def go_main_menu_imagegen4(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы в главном меню", reply_markup=main_menu_kb())

async def aspect_imagegen4(callback: CallbackQuery, state: FSMContext):
    aspect_value = callback.data.split("_")[1]
    await state.update_data(aspect_ratio=aspect_value)
    await callback.message.edit_reply_markup()
    await callback.message.answer("✏️ Введите промпт (на английском, минимум 15 символов):")
    await state.set_state(ImageGenState.AWAITING_PROMPT)
    await callback.answer()

async def handle_prompt_imagegen4(message: Message, state: FSMContext):
    text = message.text.strip()
    user_id = message.from_user.id

    if len(text) < 15:
        await message.answer("❌ Описание должно быть не короче 15 символов.")
        return

    price = calculate_imagegen4_price()
    balance = await get_user_balance(user_id)

    if balance < price:
        await message.answer(f"❌ Недостаточно средств.\n💰 Стоимость: {price:.2f} ₽\nБаланс: {balance:.2f} ₽")
        await state.clear()
        return

    await state.update_data(prompt=text, price=price)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить генерацию", callback_data="confirm_generation_imagegen4")]
    ])
    await message.answer(
        f"💰 Стоимость: {price:.2f} ₽\nБаланс: {balance:.2f} ₽\nПодтвердите генерацию:",
        reply_markup=kb
    )
    await state.set_state(ImageGenState.CONFIRM_GENERATION)

async def confirm_generation_imagegen4(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = callback.from_user.id

    if not await deduct_user_balance(user_id, data["price"]):
        await callback.message.edit_text("❌ Не удалось списать средства.")
        await state.clear()
        return

    await callback.message.edit_text("⏳ Генерация изображения...")

    try:
        replicate.api_token = REPLICATE_API_TOKEN
        prediction = await replicate.predictions.async_create(
            model="google/imagen-4",
            input={
                "prompt": data["prompt"],
                "aspect_ratio": data.get("aspect_ratio", "9:16"),
                "output_format": "png",
                "safety_filter_level": "block_medium_and_above",
                "guidance_scale": 7.5,
                "num_inference_steps": 50
            }
        )

        while prediction.status not in ("succeeded", "failed", "canceled"):
            await asyncio.sleep(2)
            prediction = await replicate.predictions.async_get(prediction.id)

        if prediction.status != "succeeded" or not prediction.output:
            raise RuntimeError("Генерация не удалась.")

        image_url = prediction.output[0] if isinstance(prediction.output, list) else prediction.output
        await callback.message.answer_photo(image_url, caption=f"✅ Prompt: {data['prompt']}")

    except Exception as e:
        logger.exception("Ошибка генерации изображения")
        await callback.message.answer("❌ Произошла ошибка при генерации.")

    await state.clear()

# --- Main ---
async def main():
    if not BOT_TOKEN or not REPLICATE_API_TOKEN:
        raise EnvironmentError("BOT_TOKEN или REPLICATE_API_TOKEN не установлены в .env")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start_imagegen4, Command("start"))
    dp.callback_query.register(aspect_imagegen4, F.data.startswith("aspect_"), StateFilter(ImageGenState.AWAITING_ASPECT))
    dp.message.register(handle_prompt_imagegen4, StateFilter(ImageGenState.AWAITING_PROMPT))
    dp.callback_query.register(confirm_generation_imagegen4, F.data == "confirm_generation_imagegen4", StateFilter(ImageGenState.CONFIRM_GENERATION))
    dp.message.register(go_main_menu_imagegen4, F.text == MAIN_MENU_BUTTON_TEXT)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
