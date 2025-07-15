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

# Загрузка переменных из .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

if not BOT_TOKEN or not REPLICATE_API_TOKEN:
    raise ValueError("Не заданы BOT_TOKEN или REPLICATE_API_TOKEN в .env файле")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tg_bot")
replicate.api_token = REPLICATE_API_TOKEN

# Стоимость генерации видео
GENERATION_COST = 275  # в центах ($2.75)

# Состояния
class VideoGenState(StatesGroup):
    waiting_image = State()
    waiting_prompt = State()
    confirming_payment = State()

# Получение баланса пользователя
async def get_user_balance(user_id: int) -> int:
    async with async_session() as session:
        try:
            result = await session.execute(select(User).where(User.telegram_id == user_id))
            user = result.scalars().one()
            return int(user.balance)
        except NoResultFound:
            return 0

# Списание средств
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

# Команда /start
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🎥 Видео-бот **Minimax** превращает изображение и текст в видео.\n\n"
        "📋 Возможности:\n- Анимация по описанию\n- Реалистичное движение\n"
        "⚠️ Только на английском.\n💰 Стоимость: $2.75 (~275 центов)\n\n"
        "📌 Отправьте изображение для начала."
    )
    await state.set_state(VideoGenState.waiting_image)

# Обработка изображения
async def handle_image(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Пожалуйста, отправьте изображение.")
        return

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"

    await state.update_data(image_url=image_url)
    await message.answer("✏️ Теперь отправьте описание (на английском).")
    await state.set_state(VideoGenState.waiting_prompt)

# Обработка промпта
async def handle_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()
    if len(prompt) < 10:
        await message.answer("❌ Описание слишком короткое. Минимум 10 символов.")
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

# Подтверждение и генерация
async def confirm_generation(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    user_id = callback.from_user.id
    prompt = data.get("prompt")
    image_url = data.get("image_url")

    if not (prompt and image_url):
        await callback.message.answer("❌ Данные не найдены. Начните заново: /start")
        await state.clear()
        return

    if not await deduct_user_balance(user_id, GENERATION_COST):
        await callback.message.answer("❌ Не удалось списать средства. Попробуйте позже.")
        await state.clear()
        return

    await callback.message.edit_text("🎬 Генерация видео, это может занять несколько минут...")

    try:
        prediction = await replicate.predictions.async_create(
            model="minimax/video-01-live",
            input={
                "prompt": prompt,
                "prompt_optimizer": True,
                "first_frame_image": image_url,
            }
        )
        logger.info(f"Создан prediction: {prediction.id}")

        while prediction.status not in ("succeeded", "failed"):
            logger.info(f"Статус: {prediction.status}")
            await asyncio.sleep(5)
            prediction = await replicate.predictions.async_get(prediction.id)

        if prediction.status == "succeeded":
            output_url = prediction.output
            if isinstance(output_url, str):
                await callback.message.answer_video(output_url, caption="✅ Готово! Вот твое видео.")
            else:
                await callback.message.answer("⚠️ Видео получено, но формат неожиданный.")
        else:
            logger.error(f"Ошибка генерации: {prediction.error}")
            await callback.message.answer("❌ Ошибка генерации видео.")
    except Exception as e:
        logger.exception("Ошибка генерации:")
        await callback.message.answer("⚠️ Произошла ошибка при вызове генерации.")
    await state.clear()

# Запуск бота
async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(handle_image, StateFilter(VideoGenState.waiting_image))
    dp.message.register(handle_prompt, StateFilter(VideoGenState.waiting_prompt))
    dp.callback_query.register(confirm_generation, StateFilter(VideoGenState.confirming_payment), lambda c: c.data == "confirm_generation")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
