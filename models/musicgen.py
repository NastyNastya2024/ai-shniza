import os
import asyncio
import logging
import uuid
import aiohttp
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import FSInputFile, Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from sqlalchemy import select
from database.db import async_session
from database.models import User, PaymentRecord

# === Конфигурация ===
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
REPLICATE_MODEL_VERSION = "671ac645ce5e552cc63a54a2bbff63fcf798043055d2dac5fc9e36a837eedcfb"
REPLICATE_API_URL = "https://api.replicate.com/v1/predictions"

MUSICGEN_PRICE_RUB = 10.0

HEADERS = {
    "Authorization": f"Token {REPLICATE_API_TOKEN}",
    "Content-Type": "application/json"
}

MODEL_VERSIONS = {
    "stereo-large": "Stereo Large",
    "stereo-melody-large": "Stereo Melody Large",
    "melody-large": "Melody Large",
    "large": "Large"
}

NORMALIZATION_STRATEGIES = {
    "loudness": "Loudness",
    "clip": "Clip",
    "peak": "Peak",
    "rms": "RMS"
}

# === FSM ===
class MusicGenStates(StatesGroup):
    choosing_model = State()
    choosing_normalization = State()
    waiting_for_prompt = State()
    confirming_payment = State()

# === База: баланс ===
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

# === Хендлеры ===
async def start_handler_musicgen(message: Message, state: FSMContext):
    await state.clear()
    model_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=key)] for key, name in MODEL_VERSIONS.items()
        ]
    )
    await message.answer(
        "👋 Привет! Я MusicGen — бот для генерации музыки по твоим описаниям.\n\n⚙ Выбери модель генерации музыки:",
        reply_markup=model_keyboard
    )
    await state.set_state(MusicGenStates.choosing_model)

async def model_chosen_musicgen(query: CallbackQuery, state: FSMContext):
    selected_model = query.data
    if selected_model not in MODEL_VERSIONS:
        await query.answer("Некорректный выбор модели.", show_alert=True)
        return

    await state.update_data(model_version=selected_model)
    await query.answer(f"✅ Модель: {MODEL_VERSIONS[selected_model]}")

    norm_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=key)] for key, name in NORMALIZATION_STRATEGIES.items()
        ]
    )
    await query.message.answer("🎚 Выбери стратегию нормализации:", reply_markup=norm_keyboard)
    await state.set_state(MusicGenStates.choosing_normalization)

async def normalization_chosen_musicgen(query: CallbackQuery, state: FSMContext):
    selected_norm = query.data
    if selected_norm not in NORMALIZATION_STRATEGIES:
        await query.answer("Некорректная стратегия.", show_alert=True)
        return

    await state.update_data(normalization_strategy=selected_norm)
    await query.answer(f"✅ Нормализация: {NORMALIZATION_STRATEGIES[selected_norm]}")
    await query.message.answer("✍️ Отправь музыкальный промпт (на англ.)")
    await state.set_state(MusicGenStates.waiting_for_prompt)

async def receive_prompt_musicgen(message: Message, state: FSMContext):
    prompt = message.text.strip()
    if len(prompt) < 5:
        await message.answer("❌ Слишком короткий промпт.")
        return

    user_id = message.from_user.id
    balance = await get_user_balance(user_id)

    if balance < MUSICGEN_PRICE_RUB:
        await message.answer(
            f"❌ Недостаточно средств.\n💰 Стоимость: {MUSICGEN_PRICE_RUB:.2f} ₽\n💼 Баланс: {balance:.2f} ₽"
        )
        await state.clear()
        return

    await state.update_data(prompt=prompt)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Подтвердить генерацию за {MUSICGEN_PRICE_RUB:.2f} ₽", callback_data="confirm_generation_musicgen")]
    ])
    await message.answer(
        f"📋 Подтвердите генерацию музыки.\n💰 Стоимость: {MUSICGEN_PRICE_RUB:.2f} ₽\n💼 Ваш баланс: {balance:.2f} ₽",
        reply_markup=kb
    )
    await state.set_state(MusicGenStates.confirming_payment)

async def confirm_generation_musicgen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    user_id = callback.from_user.id

    prompt = data.get("prompt")
    model_version = data.get("model_version", "stereo-large")
    normalization_strategy = data.get("normalization_strategy", "peak")

    if not prompt:
        await callback.message.answer("❌ Недостаточно данных. Начните заново.")
        await state.clear()
        return

    if not await deduct_user_balance(user_id, MUSICGEN_PRICE_RUB):
        await callback.message.answer("❌ Недостаточно средств. Попробуйте снова.")
        await state.clear()
        return

    await callback.message.edit_text("🎶 Генерация музыки... Пожалуйста, подождите.")

    async with aiohttp.ClientSession() as session:
        prediction_payload = {
            "version": REPLICATE_MODEL_VERSION,
            "input": {
                "prompt": prompt,
                "duration": 8,
                "output_format": "mp3",
                "model_version": model_version,
                "classifier_free_guidance": 3,
                "temperature": 1,
                "top_k": 250,
                "top_p": 0,
                "continuation": False,
                "multi_band_diffusion": False,
                "normalization_strategy": normalization_strategy
            }
        }

        async with session.post(REPLICATE_API_URL, json=prediction_payload, headers=HEADERS) as response:
            prediction = await response.json()
            prediction_id = prediction.get("id")
            if not prediction_id:
                await callback.message.answer("❌ Ошибка генерации.")
                logging.error(f"Ошибка запуска: {prediction}")
                return

        output_url = None
        for _ in range(40):
            async with session.get(f"{REPLICATE_API_URL}/{prediction_id}", headers=HEADERS) as poll_response:
                result = await poll_response.json()
                if result.get("status") == "succeeded":
                    output_url = result.get("output")
                    break
                elif result.get("status") == "failed":
                    await callback.message.answer("❌ Генерация не удалась.")
                    return
            await asyncio.sleep(1)

        if not output_url:
            await callback.message.answer("❌ Не удалось получить аудио.")
            return

        filename = "generated_track.mp3"
        async with session.get(output_url) as music_response:
            if music_response.status == 200:
                with open(filename, "wb") as f:
                    f.write(await music_response.read())
            else:
                await callback.message.answer("❌ Ошибка загрузки аудио.")
                return

        await callback.message.answer_audio(FSInputFile(filename), caption="🎧 Вот твоя музыка!")
        os.remove(filename)

    await state.clear()

# === Регистрация хендлеров ===
def register_musicgen_handlers(dp: Dispatcher):
    dp.message.register(start_handler_musicgen, Command("start"))
    dp.callback_query.register(model_chosen_musicgen, StateFilter(MusicGenStates.choosing_model))
    dp.callback_query.register(normalization_chosen_musicgen, StateFilter(MusicGenStates.choosing_normalization))
    dp.message.register(receive_prompt_musicgen, StateFilter(MusicGenStates.waiting_for_prompt))
    dp.callback_query.register(confirm_generation_musicgen, F.data == "confirm_generation_musicgen", StateFilter(MusicGenStates.confirming_payment))

# === Запуск ===
async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    register_musicgen_handlers(dp)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
