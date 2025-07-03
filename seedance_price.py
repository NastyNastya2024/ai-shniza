import os
import asyncio
import logging
import uuid
import replicate
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from database.db import async_session
from database.models import User, PaymentRecord

# Load .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
if not BOT_TOKEN or not REPLICATE_API_TOKEN:
    raise ValueError("BOT_TOKEN или REPLICATE_API_TOKEN не заданы")

replicate.api_token = REPLICATE_API_TOKEN

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VideoGenState(StatesGroup):
    waiting_image = State()
    waiting_prompt = State()
    waiting_duration = State()
    waiting_resolution = State()
    waiting_aspect_ratio = State()
    waiting_camera_fixed = State()
    confirm_pending = State()

# Цена в центах
def calculate_price(resolution: str, duration: int) -> int:
    prices = {
        ("480p", 5): 80,
        ("480p", 10): 120,
        ("1080p", 5): 150,
        ("1080p", 10): 250,
    }
    return prices.get((resolution, duration), 0)

# Баланс
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

# Инлайн-кнопки
def get_inline_keyboard(options: list[tuple[str, str]]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for label, data in options:
        kb.button(text=label, callback_data=data)
    kb.adjust(2)
    return kb

# /start
# Команда /start
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
    "👋 Привет! Я видео-бот на базе нейросети Seedance.\n\n"
    "🎥 Превращаю изображение и текст в короткое видео.\n\n"
    "📋 Возможности:\n"
    "- Выбор длительности\n"
    "- Настройка качества\n"
    "- Поворот камеры\n"
    "⚠️ ВАЖНО: генерация только на английском языке.\n"
    "🎛 Себестоимость $1.2"
)
    await message.answer("Начнем! Пришли изображение, с которого начнется видео.")
    await state.set_state(VideoGenState.waiting_image)

# Фото
async def handle_image(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Отправь изображение.")
        return
    file = await message.bot.get_file(message.photo[-1].file_id)
    url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
    await state.update_data(image_url=url)
    await message.answer("✏️ Введи описание сцены (на английском):")
    await state.set_state(VideoGenState.waiting_prompt)

# Промпт
async def handle_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()
    if len(prompt) < 15:
        await message.answer("❌ Описание слишком короткое.")
        return
    await state.update_data(prompt=prompt)
    kb = get_inline_keyboard([("⏱ 5 сек", "dur_5"), ("⏱ 10 сек", "dur_10")])
    await message.answer("Выбери длительность:", reply_markup=kb.as_markup())
    await state.set_state(VideoGenState.waiting_duration)

# Длительность
async def handle_duration(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    duration = 5 if callback.data == "dur_5" else 10
    await state.update_data(duration=duration)
    kb = get_inline_keyboard([("📺 480p", "res_480"), ("🎥 1080p", "res_1080")])
    await callback.message.edit_text("Выбери разрешение:", reply_markup=kb.as_markup())
    await state.set_state(VideoGenState.waiting_resolution)

# Разрешение
async def handle_resolution(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    res = "480p" if callback.data == "res_480" else "1080p"
    await state.update_data(resolution=res)
    kb = get_inline_keyboard([
        ("16:9", "ar_16_9"), ("4:3", "ar_4_3"), ("1:1", "ar_1_1"),
        ("3:4", "ar_3_4"), ("9:16", "ar_9_16"), ("21:9", "ar_21_9"), ("9:21", "ar_9_21")
    ])
    await callback.message.edit_text("Выбери соотношение сторон:", reply_markup=kb.as_markup())
    await state.set_state(VideoGenState.waiting_aspect_ratio)

# Соотношение сторон
async def handle_aspect_ratio(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    ar_map = {
        "ar_16_9": "16:9", "ar_4_3": "4:3", "ar_1_1": "1:1",
        "ar_3_4": "3:4", "ar_9_16": "9:16", "ar_21_9": "21:9", "ar_9_21": "9:21"
    }
    await state.update_data(aspect_ratio=ar_map[callback.data])
    kb = get_inline_keyboard([("📷 Зафиксирована", "cam_fixed"), ("🎥 Движущаяся", "cam_moving")])
    await callback.message.edit_text("📷 Зафиксировать камеру?", reply_markup=kb.as_markup())
    await state.set_state(VideoGenState.waiting_camera_fixed)

# Камера и подтверждение
async def handle_camera_fixed(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(camera_fixed=(callback.data == "cam_fixed"))

    data = await state.get_data()
    price = calculate_price(data["resolution"], data["duration"])
    balance = await get_user_balance(callback.from_user.id)

    if balance < price:
        await callback.message.edit_text(
            f"❌ Недостаточно средств: нужно {price} центов, у вас {balance}."
        )
        await state.clear()
        return

    await state.update_data(price=price, balance=balance, is_confirmed=False)
    kb = get_inline_keyboard([("✅ Продолжить", "confirm_generation")])
    await callback.message.edit_text(
        f"💰 Стоимость генерации: {price} центов\n"
        f"💼 Баланс: {balance} центов\n\nПродолжить?",
        reply_markup=kb.as_markup()
    )
    await state.set_state(VideoGenState.confirm_pending)

# Генерация
async def handle_confirm_generation(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()

    if data.get("is_confirmed"):
        return  # блок повторного клика

    await state.update_data(is_confirmed=True)
    user_id = callback.from_user.id

    await callback.message.edit_reply_markup(reply_markup=None)
    if not await deduct_user_balance(user_id, data["price"]):
        await callback.message.edit_text("❌ Не удалось списать средства.")
        await state.clear()
        return

    await callback.message.edit_text("🎬 Генерация видео...")

    try:
        prediction = await replicate.predictions.async_create(
            model="bytedance/seedance-1-pro",
            input={
                "fps": 24,
                "prompt": data["prompt"],
                "duration": data["duration"],
                "resolution": data["resolution"],
                "aspect_ratio": data["aspect_ratio"],
                "camera_fixed": data["camera_fixed"],
                "image": data["image_url"],
            }
        )

        while prediction.status not in ("succeeded", "failed"):
            await asyncio.sleep(5)
            prediction = await replicate.predictions.async_get(prediction.id)

        if prediction.status == "succeeded":
            await callback.message.answer_video(prediction.output, caption="✅ Готово!")
        else:
            await callback.message.answer("❌ Ошибка генерации.")
    except Exception as e:
        logger.exception("Ошибка генерации:")
        await callback.message.answer("⚠️ Возникла ошибка во время генерации.")

    await state.clear()

# Запуск
async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(handle_image, StateFilter(VideoGenState.waiting_image))
    dp.message.register(handle_prompt, StateFilter(VideoGenState.waiting_prompt))
    dp.callback_query.register(handle_duration, StateFilter(VideoGenState.waiting_duration))
    dp.callback_query.register(handle_resolution, StateFilter(VideoGenState.waiting_resolution))
    dp.callback_query.register(handle_aspect_ratio, StateFilter(VideoGenState.waiting_aspect_ratio))
    dp.callback_query.register(handle_camera_fixed, StateFilter(VideoGenState.waiting_camera_fixed))
    dp.callback_query.register(handle_confirm_generation, lambda c: c.data == "confirm_generation")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
