import os
import asyncio
import logging
import uuid
import replicate

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from sqlalchemy import select
from dotenv import load_dotenv

from database.db import async_session
from database.models import User, PaymentRecord

# Загрузка .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

if not BOT_TOKEN or not REPLICATE_API_TOKEN:
    raise EnvironmentError("BOT_TOKEN или REPLICATE_API_TOKEN не установлены")

replicate.api_token = REPLICATE_API_TOKEN
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("minimax")

# FSM состояния
class VideoGenState(StatesGroup):
    waiting_image = State()
    waiting_prompt = State()
    confirming_payment = State()

# Стоимость в рублях
def calculate_minimax_price() -> float:
    return 150.0  # рубли

# Получение баланса
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

# Списание средств
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
async def minimax_start(message: Message, state: FSMContext):
    await state.clear()
    price = calculate_minimax_price()
    await message.answer(
        f"🎥 *Minimax Video Bot* — генерация видео из картинки и текста.\n\n"
        f"⚠️ *Только на английском языке*\n💰 Стоимость: {price:.2f} ₽\n\n"
        f"📌 Отправьте изображение для начала.",
        parse_mode="Markdown"
    )
    await state.set_state(VideoGenState.waiting_image)

# Приём изображения
async def minimax_handle_image(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Пожалуйста, отправьте изображение.")
        return

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"

    await state.update_data(image_url=image_url)
    await message.answer("✏️ Теперь отправьте описание (на английском).")
    await state.set_state(VideoGenState.waiting_prompt)

# Приём промпта и показ кнопки оплаты
async def minimax_handle_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()
    if len(prompt) < 10:
        await message.answer("❌ Описание должно содержать минимум 10 символов.")
        return

    user_id = message.from_user.id
    price = calculate_minimax_price()
    balance = await get_user_balance(user_id)

    if balance < price:
        await message.answer(
            f"❌ Недостаточно средств.\n💰 Стоимость: {price:.2f} ₽\nВаш баланс: {balance:.2f} ₽"
        )
        await state.clear()
        return

    await state.update_data(prompt=prompt, price=price)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Подтвердить генерацию за {price:.2f} ₽", callback_data="confirm_generation")]
    ])
    await message.answer(
        f"📋 Подтвердите генерацию видео.\n💰 Стоимость: {price:.2f} ₽\n💼 Ваш баланс: {balance:.2f} ₽",
        reply_markup=kb
    )
    await state.set_state(VideoGenState.confirming_payment)

# Подтверждение и запуск генерации
async def minimax_confirm_generation(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    user_id = callback.from_user.id
    prompt = data.get("prompt")
    image_url = data.get("image_url")
    price = data.get("price")

    if not (prompt and image_url and price):
        await callback.message.answer("❌ Недостаточно данных. Попробуйте сначала: /start")
        await state.clear()
        return

    if not await deduct_user_balance(user_id, price):
        await callback.message.answer("❌ Не удалось списать средства. Проверьте баланс.")
        await state.clear()
        return

    await callback.message.edit_text("⏳ Генерация видео... Это может занять до 1-2 минут.")

    try:
        prediction = await replicate.predictions.async_create(
            model="minimax/video-01-live",
            input={
                "prompt": prompt,
                "prompt_optimizer": True,
                "first_frame_image": image_url,
            }
        )
        logger.info(f"[Minimax] Prediction ID: {prediction.id}")

        while prediction.status not in ("succeeded", "failed"):
            await asyncio.sleep(5)
            prediction = await replicate.predictions.async_get(prediction.id)

        if prediction.status == "succeeded":
            video_url = prediction.output
            if isinstance(video_url, str):
                await callback.message.answer_video(video_url, caption="✅ Готово! Вот ваше видео.")
            else:
                await callback.message.answer("⚠️ Видео получено, но формат неизвестен.")
        else:
            logger.error(f"[Minimax] Ошибка генерации: {prediction.error}")
            await callback.message.answer("❌ Генерация не удалась.")
    except Exception as e:
        logger.exception("Ошибка при генерации:")
        await callback.message.answer("⚠️ Ошибка генерации. Попробуйте позже.")

    await state.clear()

# Запуск
async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(minimax_start, Command("start"))
    dp.message.register(minimax_handle_image, StateFilter(VideoGenState.waiting_image))
    dp.message.register(minimax_handle_prompt, StateFilter(VideoGenState.waiting_prompt))
    dp.callback_query.register(minimax_confirm_generation, StateFilter(VideoGenState.confirming_payment), lambda c: c.data == "confirm_generation")

    logger.info("Minimax бот запущен")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
