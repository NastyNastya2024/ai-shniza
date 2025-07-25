import os
import logging
import asyncio
import random
import uuid

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
import replicate

from sqlalchemy import select
from database.db import async_session
from database.models import User, PaymentRecord

from keyboards import main_menu_kb

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("flux")

class FluxKontextState(StatesGroup):
    WAITING_IMAGE = State()
    WAITING_ASPECT_RATIO = State()
    WAITING_PROMPT = State()
    CONFIRM_GENERATION_FLUX = State()

def calculate_flux_price() -> float:
    return 9.0

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

async def cmd_start_flux(message: Message, state: FSMContext):
    await state.clear()
    description = (
        "🎨 Cartoon Video Bot на базе нейросети **Flux Kontext** — генерация мультфильмов из изображений и текста.(Pixar, Anime, Disney и др.)\n\n"
        "⚠️ Важно: промпт — на английском\n"
        "🔤 Нажмите /main чтобы выйти\n"
        f"💰 Стоимость: {calculate_flux_price():.2f} ₽ за генерацию"
    )
    await message.answer(description, parse_mode="Markdown")
    await message.answer("📌 Пришли изображение, с которым хочешь работать.")
    await state.set_state(FluxKontextState.WAITING_IMAGE)

async def handle_image_flux(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Пожалуйста, пришли изображение.")
        return

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
    await state.update_data(image_url=image_url)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1:1", callback_data="aspect_1_1"),
            InlineKeyboardButton(text="16:9", callback_data="aspect_16_9"),
            InlineKeyboardButton(text="9:16", callback_data="aspect_9_16")
        ]
    ])
    await message.answer("🖐 Выбери соотношение сторон (Aspect Ratio):", reply_markup=kb)
    await state.set_state(FluxKontextState.WAITING_ASPECT_RATIO)

async def handle_aspect_ratio_flux(callback: CallbackQuery, state: FSMContext):
    aspect_raw = callback.data.replace("aspect_", "")
    aspect = aspect_raw.replace("_", ":")
    await state.update_data(aspect_ratio=aspect, safety_tolerance=3)

    await callback.message.edit_text("✅ Соотношение сторон выбрано. Загрузка стилей...")
    await callback.answer()

    await handle_flux_style_flux(callback.message, state)

async def handle_flux_style_flux(message: Message, state: FSMContext):
    styles = [
        "90s Arcade Style", "Disney Style", "Tim Burton Style", "Pixar Toy Look",
        "Sci-Fi Animation", "Anime Fantasy", "Animal Cartoon",
        "Dark Comic", "Noir Detective", "Studio Ghibli"
    ]
    style_text = "\n".join(f"- {s}" for s in styles)

    await message.answer(
        f"✨ Пришли описание сцены на английском языке (prompt).\n\n"
        f"*Примеры стилей:*\n{style_text}\n\n"
        f"📝 *Пример:* _Make this a 90s cartoon_",
        parse_mode="Markdown",
    )
    await state.set_state(FluxKontextState.WAITING_PROMPT)

async def handle_prompt_flux(message: Message, state: FSMContext):
    prompt = message.text.strip()
    if prompt == "🏠 Главное меню":
        await go_main_menu_flux(message, state)
        return

    if len(prompt) < 5:
        await message.answer("❌ Промпт слишком короткий.")
        return

    price = calculate_flux_price()
    balance = await get_user_balance(message.from_user.id)

    if balance < price:
        await message.answer(f"❌ Недостаточно средств.\n💰 Стоимость: {price:.2f} ₽\n💼 Ваш баланс: {balance:.2f} ₽. 💼 Для пополнения перейдите в раздел «Баланс».")
        await state.clear()
        return

    await state.update_data(prompt=prompt, price=price)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить генерацию", callback_data="confirm_generation_flux")]
    ])
    await message.answer(f"💰 Стоимость генерации: {price:.2f} ₽\nВаш баланс: {balance:.2f} ₽. 💼 Для пополнения перейдите в раздел «Баланс». \n\nПодтвердите генерацию:", reply_markup=kb)
    await state.set_state(FluxKontextState.CONFIRM_GENERATION_FLUX)

async def confirm_generation_flux(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()

    user_id = callback.from_user.id
    if not await deduct_user_balance(user_id, data["price"]):
        await callback.message.edit_text("❌ Не удалось списать средства.")
        await state.clear()
        return

    await callback.message.edit_text("⏳ Генерация изображения...")

    try:
        client = replicate.Client(api_token=REPLICATE_API_TOKEN)
        seed = random.randint(0, 2**31 - 1)
        prediction = client.predictions.create(
            version="black-forest-labs/flux-kontext-pro",
            input={
                "prompt": data["prompt"],
                "input_image": data["image_url"],
                "aspect_ratio": data.get("aspect_ratio", "match_input_image"),
                "output_format": "jpg",
                "safety_tolerance": data.get("safety_tolerance", 3),
                "seed": seed
            }
        )

        logger.info(f"[confirm_generation_flux] Prediction created: {prediction.id}")
        while prediction.status not in ("succeeded", "failed", "canceled"):
            await asyncio.sleep(2)
            prediction.reload()

        if prediction.status == "succeeded" and prediction.output:
            output_url = prediction.output[0] if isinstance(prediction.output, list) else prediction.output
            if output_url:
                await callback.message.answer_photo(
                    output_url,
                    caption=f"✅ Готово!\n\n🌍 *Prompt:* {data['prompt']}",
                    parse_mode="Markdown",
                )
            else:
                raise ValueError("Ошибка: URL изображения не найден")
        else:
            await callback.message.answer("❌ Не удалось сгенерировать изображение.")
            logger.error(f"Ошибка генерации. Статус: {prediction.status}")

    except Exception as e:
        logger.exception("❌ Ошибка во время генерации:")
        await callback.message.answer("⚠️ Ошибка генерации. Попробуйте позже.")

    await state.clear()

async def go_main_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы в главном меню.", reply_markup=main_menu_kb())

async def main():
    logger.info("Запуск Flux Kontext...")

    if not BOT_TOKEN or not REPLICATE_API_TOKEN:
        raise EnvironmentError("❌ BOT_TOKEN или REPLICATE_API_TOKEN не установлены")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start_flux, Command("start"))
    dp.message.register(handle_image_flux, StateFilter(FluxKontextState.WAITING_IMAGE))
    dp.callback_query.register(handle_aspect_ratio_flux, StateFilter(FluxKontextState.WAITING_ASPECT_RATIO))
    dp.message.register(handle_prompt_flux, StateFilter(FluxKontextState.WAITING_PROMPT))
    dp.message.register(go_main_menu, F.text == "🏠 Главное меню")
    dp.callback_query.register(confirm_generation_flux, F.data == "confirm_generation_flux", StateFilter(FluxKontextState.CONFIRM_GENERATION_FLUX))


    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
