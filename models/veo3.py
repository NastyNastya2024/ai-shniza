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
class Veo3State(StatesGroup):
    waiting_for_prompt = State()
    confirming_payment = State()
    processing = State()

# Стоимость генерации видео (в рублях)
GENERATION_COST_RUB = 600

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
async def cmd_start_veo3(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Модель Veo3 генерирует видео с звуком по описанию.\n"
        "💡 Описание (prompt) — на английском.\n"
        "🛠️ Разрешение видео 16:9.\n"
        "🛠️ Звук соответствует описанию.\n"
        f"💲 Себестоимость: {GENERATION_COST_RUB}₽.\n"
        "Отправьте описание сцены."
    )
    await state.set_state(Veo3State.waiting_for_prompt)

# Обработка текста с описанием сцены
async def handle_prompt_veo3(message: Message, state: FSMContext):
    prompt = message.text.strip()
    if len(prompt) < 15:
        await message.answer("❌ Описание слишком короткое, минимум 15 символов. Попробуйте еще раз:")
        return

    user_id = message.from_user.id
    balance = await get_user_balance(user_id)

    if balance < GENERATION_COST_RUB:
        await message.answer(
            f"❌ Недостаточно средств.\n💸 Стоимость генерации: {GENERATION_COST_RUB}₽. \n"
            f"💼 Ваш баланс: {balance}₽. \n 💼 Для пополнения перейдите в раздел «Баланс»."
        )
        await state.clear()
        return

    await state.update_data(prompt=prompt)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Подтвердить списание {GENERATION_COST_RUB}₽", callback_data="confirm_generation_veo3")]
    ])
    await message.answer(
        f"📋 Подтвердите генерацию видео.\n💸 Стоимость: {GENERATION_COST_RUB}₽\n💼 Ваш баланс: {balance}₽",
        reply_markup=keyboard
    )
    await state.set_state(Veo3State.confirming_payment)

# Подтверждение и генерация видео
async def confirm_generation_veo3(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    prompt = data.get("prompt")
    user_id = callback.from_user.id

    if not prompt:
        await callback.message.answer("❌ Описание не найдено. Попробуйте сначала.")
        await state.clear()
        return

    success = await deduct_user_balance(user_id, GENERATION_COST_RUB)
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
                "aspect_ratio": "9:16",
                "duration": 5,
                "seed": 42
            }
        )
        video_url = output.url if hasattr(output, "url") else output
        logger.info(f"Видео сгенерировано: {video_url}")
        await callback.message.answer_video(video_url, caption="✅ Видео готово!")
    except replicate.exceptions.ModelError as e:
        logger.warning(f"Модель отклонила prompt как чувствительный: {e}")
        await callback.message.answer("⚠️ Модель отклонила описание как чувствительное. Пожалуйста, измените prompt.")
    except Exception as e:
        logger.exception("Ошибка при генерации видео:")
        await callback.message.answer("⚠️ Произошла ошибка при генерации видео.")

    await state.clear()

# Основная функция запуска бота
async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start_veo3, Command("start"))
    dp.message.register(handle_prompt_veo3, StateFilter(Veo3State.waiting_for_prompt))
    dp.callback_query.register(confirm_generation_veo3, StateFilter(Veo3State.confirming_payment), lambda c: c.data == "confirm_generation_veo3")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
