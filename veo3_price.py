import os
import asyncio
import logging
import uuid
import replicate
from aiogram import Bot, Dispatcher
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from dotenv import load_dotenv

from database.db import async_session
from database.models import User, PaymentRecord

# Загрузка переменных окружения из .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

if not BOT_TOKEN or not REPLICATE_API_TOKEN:
    raise ValueError("Не заданы BOT_TOKEN или REPLICATE_API_TOKEN в .env файле")

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tg_bot")

# Инициализация Replicate API
replicate.api_token = REPLICATE_API_TOKEN

# FSM состояние для ожидания текста для генерации видео
class VideoGenState(StatesGroup):
    waiting_for_prompt = State()
    confirming_payment = State()
    processing = State()

# Стоимость генерации видео (в центах)
GENERATION_COST = 600  # 6 долларов = 600 центов

# Получение баланса пользователя
async def get_user_balance(user_id: int) -> int:
    async with async_session() as session:
        try:
            result = await session.execute(select(User).where(User.telegram_id == user_id))
            user = result.scalars().one()
            return int(user.balance)
        except NoResultFound:
            return 0

# Списание баланса
async def deduct_user_balance(user_id: int, amount: int) -> bool:
    async with async_session() as session:
        try:
            result = await session.execute(select(User).where(User.telegram_id == user_id))
            user = result.scalars().one()
            if user.balance >= amount:
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
        except NoResultFound:
            return False

# Обработчик команды /start — сразу запрашиваем промпт
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Модель Veo3 генерирует видео с звуком по описанию.\n"
        "💡 Описание (prompt) — на английском.\n"
        "🛠️ Разрешение видео 16:9 .\n"
        "🛠️ Звук соответствует описанию.\n"
        f"💲 Себестоимость: {GENERATION_COST / 100:.2f}$.\n"
        "Отправьте описание сцены."
    )
    await state.set_state(VideoGenState.waiting_for_prompt)

# Обработка текста с описанием сцены
async def handle_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()
    if len(prompt) < 15:
        await message.answer("❌ Описание слишком короткое, минимум 15 символов. Попробуйте еще раз:")
        return

    user_id = message.from_user.id
    balance = await get_user_balance(user_id)

    if balance < GENERATION_COST:
        await message.answer(
            f"❌ Недостаточно средств.\n💸 Стоимость генерации: {GENERATION_COST} центов\n"
            f"💼 Ваш баланс: {balance} центов"
        )
        await state.clear()
        return

    await state.update_data(prompt=prompt)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Подтвердить списание {GENERATION_COST} центов", callback_data="confirm_generation")]
    ])
    await message.answer(
        f"📋 Подтвердите генерацию видео.\n💸 Стоимость: {GENERATION_COST} центов\n💼 Ваш баланс: {balance} центов",
        reply_markup=keyboard
    )
    await state.set_state(VideoGenState.confirming_payment)

# Подтверждение и генерация видео
async def confirm_generation(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    prompt = data.get("prompt")
    user_id = callback.from_user.id

    if not prompt:
        await callback.message.answer("❌ Описание не найдено. Попробуйте сначала.")
        await state.clear()
        return

    success = await deduct_user_balance(user_id, GENERATION_COST)
    if not success:
        await callback.message.answer("❌ Не удалось списать средства. Попробуйте позже.")
        await state.clear()
        return

    await callback.message.edit_text("🎬 Генерируем видео, это может занять некоторое время...")

    try:
        output = replicate.run(
            "google/veo-3",
            input={
                "prompt": prompt,
                "enhance_prompt": True,
                "aspect_ratio": "9:16"
            }
        )
        video_url = output.url if hasattr(output, "url") else output
        logger.info(f"Видео сгенерировано: {video_url}")
        await callback.message.answer_video(video_url, caption="✅ Видео готово!")
    except Exception as e:
        logger.exception("Ошибка при генерации видео:")
        await callback.message.answer("⚠️ Произошла ошибка при генерации видео.")

    await state.clear()

# Основная функция запуска бота
async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(handle_prompt, StateFilter(VideoGenState.waiting_for_prompt))
    dp.callback_query.register(confirm_generation, StateFilter(VideoGenState.confirming_payment), lambda c: c.data == "confirm_generation")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
