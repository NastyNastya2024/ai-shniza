import os
import logging
import asyncio
import replicate
import aiohttp
import ffmpeg
import uuid

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, FSInputFile, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from database.db import async_session
from database.models import User, PaymentRecord

from keyboards import main_menu_kb

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tg_bot")

class VoiceGenState(StatesGroup):
    CHOOSE_TEMPERATURE = State()
    CHOOSE_SEED = State()
    AWAITING_TEXT = State()
    CONFIRM_GENERATION = State()

# Кнопки
def temperature_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Низкий (0.2)", callback_data="temp_0.2")],
        [InlineKeyboardButton(text="Средний (0.5)", callback_data="temp_0.5")],
        [InlineKeyboardButton(text="Высокий (0.8)", callback_data="temp_0.8")]
    ])

def seed_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Случайность 1", callback_data="seed_0")],
        [InlineKeyboardButton(text="Случайность 2", callback_data="seed_42")],
        [InlineKeyboardButton(text="Случайность 3", callback_data="seed_123")]
    ])

def confirm_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить генерацию", callback_data="confirm_generation")]
    ])

# Цена в рублях (float)
def calculate_chatterbox_price() -> float:
    return 10.0

# Баланс
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

# /start
async def cmd_start_chatterbox(message: Message, state: FSMContext):
    await message.answer(
        "🗣️ Voice Generator Bot на базе нейросети **Chatterbox** — генерация выразительной и естественной речи по тексту.\n\n"
        "⚠️ Важно:текст — на английском языке\n"
        f"💰 Стоимость: {calculate_chatterbox_price():.2f} ₽ за генерацию",
        reply_markup=temperature_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(VoiceGenState.CHOOSE_TEMPERATURE)

# Температура
async def choose_temperature_chatterbox(callback: CallbackQuery, state: FSMContext):
    temperature = float(callback.data.split("_")[1])
    await state.update_data(temperature=temperature)
    await callback.message.edit_text(
        "🎲 Теперь выбери случайность:",
        reply_markup=seed_keyboard()
    )
    await state.set_state(VoiceGenState.CHOOSE_SEED)
    await callback.answer()

# Seed
async def choose_seed_chatterbox(callback: CallbackQuery, state: FSMContext):
    seed = int(callback.data.split("_")[1])
    await state.update_data(seed=seed)
    await callback.message.edit_text(
        "✍️ Отправь текст на английском",
        parse_mode="Markdown"
    )
    await state.set_state(VoiceGenState.AWAITING_TEXT)

# Текст
async def handle_voice_text_chatterbox(message: Message, state: FSMContext):
    text = message.text.strip()
    if len(text) < 10:
        await message.answer("❌ Текст слишком короткий.")
        return

    price = calculate_chatterbox_price()
    balance = await get_user_balance(message.from_user.id)

    if balance < price:
        await message.answer(f"❌ Недостаточно средств.\n💰 Стоимость: {price:.2f} ₽\n 💼 Ваш баланс: {balance:.2f} ₽.\n Пополнить кошелек можно в разделе Баланс")
        await state.clear()
        return

    await state.update_data(prompt=text, price=price, is_confirmed=False)
    await message.answer(
        f"💰 Стоимость генерации: {price:.2f} ₽\nВаш баланс: {balance:.2f} ₽\n\nПодтвердите генерацию:",
        reply_markup=confirm_keyboard()
    )
    await state.set_state(VoiceGenState.CONFIRM_GENERATION)

# Подтверждение
async def confirm_generation_chatterbox(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    if data.get("is_confirmed"):
        return

    await state.update_data(is_confirmed=True)
    await callback.message.edit_reply_markup(reply_markup=None)

    user_id = callback.from_user.id
    if not await deduct_user_balance(user_id, data["price"]):
        await callback.message.edit_text("❌ Не удалось списать средства.")
        await state.clear()
        return

    await callback.message.edit_text("🎤 Генерация озвучки - это может занять несколько минут...")

    try:
        replicate.api_token = REPLICATE_API_TOKEN
        prediction = await replicate.predictions.async_create(
            model="resemble-ai/chatterbox",
            input={
                "prompt": data["prompt"],
                "seed": data.get("seed", 0),
                "cfg_weight": 0.5,
                "temperature": data.get("temperature", 0.5),
                "exaggeration": 0.5
            }
        )

        while prediction.status not in ("succeeded", "failed"):
            await asyncio.sleep(2)
            prediction = await replicate.predictions.async_get(prediction.id)

        if prediction.status != "succeeded":
            raise Exception(f"Модель завершилась с ошибкой: {prediction.status}")

        audio_url = prediction.output
        if not isinstance(audio_url, str) or not audio_url.startswith("http"):
            raise ValueError("Невалидный URL аудио")

        async with aiohttp.ClientSession() as session:
            async with session.get(audio_url) as resp:
                if resp.status != 200:
                    raise Exception("Ошибка скачивания")
                with open("output.wav", "wb") as f:
                    f.write(await resp.read())

        (
            ffmpeg
            .input("output.wav")
            .output("voice.ogg", format='opus', audio_bitrate='64k', acodec='libopus')
            .overwrite_output()
            .run()
        )

        voice = FSInputFile("voice.ogg")
        await callback.message.answer_voice(voice)

    except Exception:
        logger.exception("Ошибка озвучки:")
        await callback.message.answer("⚠️ Ошибка генерации аудио.")
    finally:
        for f in ["output.wav", "voice.ogg"]:
            if os.path.exists(f):
                os.remove(f)
        await state.clear()

# Главное меню
async def go_main_menu_chatterbox(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы в главном меню.", reply_markup=main_menu_kb())

# Main
async def main():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(go_main_menu_chatterbox, F.text == "🏠 Главное меню", StateFilter("*"))
    dp.message.register(cmd_start_chatterbox, Command("start"))
    dp.callback_query.register(choose_temperature_chatterbox, F.data.startswith("temp_"), StateFilter(VoiceGenState.CHOOSE_TEMPERATURE))
    dp.callback_query.register(choose_seed_chatterbox, F.data.startswith("seed_"), StateFilter(VoiceGenState.CHOOSE_SEED))
    dp.message.register(handle_voice_text_chatterbox, StateFilter(VoiceGenState.AWAITING_TEXT))
    dp.callback_query.register(confirm_generation_chatterbox, F.data == "confirm_generation", StateFilter(VoiceGenState.CONFIRM_GENERATION))

    logging.info("🤖 Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())