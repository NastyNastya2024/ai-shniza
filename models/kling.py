import os
import asyncio
import logging
import replicate
import uuid
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from aiogram.types import Message


from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from database.db import async_session
from database.models import User, PaymentRecord
from keyboards import main_menu_kb


# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

if not BOT_TOKEN or not REPLICATE_API_TOKEN:
    raise ValueError("Не заданы BOT_TOKEN или REPLICATE_API_TOKEN в .env файле")

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tg_bot")

# Установка токена Replicate
replicate.api_token = REPLICATE_API_TOKEN

# FSM
class KlingVideoState(StatesGroup):
    waiting_image = State()
    waiting_mode = State()
    waiting_duration = State()
    waiting_prompt = State()
    confirm_pending = State()

# Цены
KLING_PRICES = {
    ("standard", 5): 140,
    ("standard", 10): 275,
    ("pro", 5): 250,
    ("pro", 10): 495,
}

def calculate_kling_price(mode: str, duration: int) -> int:
    return KLING_PRICES.get((mode, duration), 0)

async def go_main_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы в главном меню.", reply_markup=main_menu_kb())
    

async def repeat_generation_kling(message: Message, state: FSMContext):
    await state.clear()
    await cmd_start_kling(message, state)

async def get_user_balance(user_id: int) -> int:
    async with async_session() as session:
        try:
            result = await session.execute(select(User).where(User.telegram_id == user_id))
            user = result.scalars().one()
            return int(user.balance)
        except NoResultFound:
            return 0

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

# /start
async def cmd_start_kling(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Видео-бот на базе нейросети **Kling**\n\n"
        "🎥 Превращает изображение и текстовое описание в видео.\n"
        "⚙️ Режимы: Standard и Pro\n"
        "⏱️ Длительность: 5 или 10 секунд\n\n"
        "💰 Стоимость зависит от режима.\n"
        "🔤 Нажмите /main чтобы выйти\n\n"
        "📌 Пришли изображение, с которого начнется видео.",
    )
    await state.set_state(KlingVideoState.waiting_image)

# Изображение
async def handle_image_kling(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Пожалуйста, отправь изображение.", reply_markup=kling_menu_kb())
        await send_kling_footer(message)
        return

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
    await state.update_data(image_url=image_url)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎛 Standard", callback_data="mode_standard"),
            InlineKeyboardButton(text="🚀 Pro", callback_data="mode_pro"),
        ]
    ])
    await message.answer("Выбери режим генерации:", reply_markup=keyboard)
    await state.set_state(KlingVideoState.waiting_mode)

# Режим
async def handle_mode_selection_kling(callback: CallbackQuery, state: FSMContext):
    mode = callback.data.replace("mode_", "")
    await state.update_data(mode=mode)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏱ 5 сек", callback_data="duration_5"),
            InlineKeyboardButton(text="⏱ 10 сек", callback_data="duration_10"),
        ]
    ])
    await callback.message.edit_text("Выбери длительность:", reply_markup=keyboard)
    await state.set_state(KlingVideoState.waiting_duration)
    await callback.answer()

# Длительность
async def handle_duration_selection_kling(callback: CallbackQuery, state: FSMContext):
    duration = int(callback.data.replace("duration_", ""))
    await state.update_data(duration=duration)

    await callback.message.edit_text("✏️ Введи описание сцены на английском:")
    await state.set_state(KlingVideoState.waiting_prompt)
    await callback.answer()

# Prompt
async def handle_prompt_kling(message: Message, state: FSMContext):
    prompt = message.text.strip()
    
    
    if len(prompt) < 15:
        await message.answer("❌ Описание слишком короткое. Минимум 15 символов.", reply_markup=kling_menu_kb())
        return

    await state.update_data(prompt=prompt)
    data = await state.get_data()
    price = calculate_kling_price(data["mode"], data["duration"])
    balance = await get_user_balance(message.from_user.id)

    if balance < price:
        await message.answer(
            f"❌ Недостаточно средств: нужно {price} центов, у вас {balance} 💼 Для пополнения перейдите в раздел «Баланс».",
            reply_markup=kling_menu_kb()
        )
        await state.clear()
        return

    await state.update_data(price=price)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить генерацию", callback_data="confirm_gen")]
    ])
    await message.answer(
        f"💰 Стоимость генерации: {price} центов\n💼 Ваш баланс: {balance} центов\n Нажми, чтобы подтвердить.",
        reply_markup=keyboard
    )
    
    await state.set_state(KlingVideoState.confirm_pending)

# Генерация
async def handle_confirm_generation_kling(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    prompt = data.get("prompt", "")
    user_id = callback.from_user.id

    if not await deduct_user_balance(user_id, data["price"]):
        await callback.message.edit_text("❌ Не удалось списать средства. Попробуй снова.")
        await state.clear()
        return

    await callback.message.edit_text("🎥 Генерация видео... Это может занять пару минут.")

    try:
        prediction = await replicate.predictions.async_create(
            model="kwaivgi/kling-v2.1",
            input={
                "mode": data["mode"],
                "prompt": prompt,
                "duration": data["duration"],
                "start_image": data["image_url"],
                "negative_prompt": ""
            }
        )
        logger.info(f"Создан prediction: {prediction.id}")

        while prediction.status not in ("succeeded", "failed"):
            logger.info(f"Статус: {prediction.status}")
            await asyncio.sleep(5)
            prediction = await replicate.predictions.async_get(prediction.id)

        if prediction.status == "succeeded":
            output = prediction.output
            video_url = None

            if isinstance(output, str):
                video_url = output
            elif isinstance(output, list):
                video_url = next((url for url in output if isinstance(url, str) and url.endswith(".mp4")), None)

            if video_url:
                await callback.message.answer_video(video_url, caption="✅ Готово! Вот твое видео.")
            else:
                await callback.message.answer("⚠️ Видео получено, но формат неожидан или пустой.")
        else:
            logger.error(f"Ошибка генерации: {prediction.error}")
            await callback.message.answer("❌ Ошибка генерации видео.")

    except Exception as e:
        logger.exception("Ошибка при генерации:")
        await callback.message.answer("⚠️ Произошла ошибка при генерации видео.")
    finally:
        await state.clear()

# Запуск
async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start_kling, Command("start"))
    dp.message.register(handle_image_kling, StateFilter(KlingVideoState.waiting_image))
    dp.callback_query.register(handle_mode_selection_kling, lambda c: c.data.startswith("mode_"), StateFilter(KlingVideoState.waiting_mode))
    dp.callback_query.register(handle_duration_selection_kling, lambda c: c.data.startswith("duration_"), StateFilter(KlingVideoState.waiting_duration))
    dp.message.register(handle_prompt_kling, StateFilter(KlingVideoState.waiting_prompt))
    dp.callback_query.register(handle_confirm_generation_kling, lambda c: c.data == "confirm_gen", StateFilter(KlingVideoState.confirm_pending))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())