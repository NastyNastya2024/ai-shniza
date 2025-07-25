from aiogram import types, Bot, Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot.invoice import create_invoice
from database.db import async_session
from database.models import User, PaymentRecord
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
import logging
import json

router = Router()

# Показать пользователю кнопки с вариантами пополнения
async def show_payment_options(message: Message):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()
        balance = float(user.balance) if user else 0.0

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Пополнить на 100 ₽", callback_data="pay_100")],
            [InlineKeyboardButton(text="💳 Пополнить на 500 ₽", callback_data="pay_500")],
            [InlineKeyboardButton(text="💳 Пополнить на 1000 ₽", callback_data="pay_1000")],
            [InlineKeyboardButton(text="💼 Своя сумма (от 100 ₽)", callback_data="pay_custom")]
        ]
    )

    text = (
        f"💼 Ваш текущий баланс: {balance:.2f} ₽\n\n"
        "💡 Пополнение баланса на любую сумму от 100₽.\n"
        "⚠️ Деньги списываются только по факту успешной генерации.\n\n"
         f"🖼 *Генерация изображений:*\n"
        f"- Ideogram — от 9 ₽\n"
        f"- Imagen-4 — от 9 ₽\n"
        f"- FluxKontext — от 9 ₽\n\n"

        f"🎬 *Генерация видео:*\n"
        f"- Kling v2.1 — от 55 - 199 ₽\n"
        f"- Minimax Video — от 150 ₽\n"
        f"- Seedance  — от 80 ₽\n"
        f"- Veo3 (8 секунд) —  660 ₽\n\n"

        f"🎵 *Генерация музыки:*\n"
        f"- Minimax Music — от 9 ₽\n"
        f"- MusicGen — 9 ₽\n"
        f"- Chatterbox — 9 ₽\n\n"

        f"💬 *Текст и речь:*\n"
        f"- GPT перевод — бесплатно\n\n"
        
        "👇 Выберите сумму для пополнения:"
    )

    await message.answer(text, reply_markup=keyboard)
    
@router.callback_query(lambda c: c.data.startswith("pay_") and c.data != "pay_custom")
async def handle_fixed_payment(callback: CallbackQuery):
    try:
        amount_str = callback.data.split("_")[1]
        amount = int(amount_str)

        invoice = create_invoice(
            chat_id=callback.message.chat.id,
            amount=amount * 100,  # в копейках
            description=f"Пополнение на {amount} ₽"
        )

        invoice_for_log = invoice.copy()
        invoice_for_log["prices"] = [{"label": p.label, "amount": p.amount} for p in invoice["prices"]]
        logging.debug("Создан инвойс (fixed): %s", json.dumps(invoice_for_log, indent=2, ensure_ascii=False))

        await callback.message.bot.send_invoice(**invoice)
        await callback.answer()

    except Exception as e:
        logging.exception("Ошибка при создании инвойса")
        await callback.message.answer("🚫 Ошибка при создании счёта. Попробуйте позже.")
        

@router.message()
async def handle_custom_amount_input(message: Message):


    amount = int(text)
    if amount < 100:
        await message.answer("❗ Минимальная сумма пополнения — 100 ₽. Пожалуйста, введите сумму заново.")
        return

    try:
        invoice = create_invoice(
            chat_id=message.chat.id,
            amount=amount * 100,
            description=f"Пополнение на {amount} ₽"
        )

        invoice_for_log = invoice.copy()
        invoice_for_log["prices"] = [{"label": p.label, "amount": p.amount} for p in invoice["prices"]]
        logging.debug("Создан инвойс (custom): %s", json.dumps(invoice_for_log, indent=2, ensure_ascii=False))

        await message.bot.send_invoice(**invoice)

    except Exception as e:
        logging.exception("Ошибка при создании инвойса (custom)")
        await message.answer("🚫 Ошибка при создании счёта. Попробуйте позже.")


# Обработка кнопки "Своя сумма"
@router.callback_query(lambda c: c.data == "pay_custom")
async def handle_custom_amount_request(callback: CallbackQuery):
    await callback.message.answer("✏️ Введите сумму пополнения (от 100 ₽):")
    await callback.answer()

# Обработка пользовательского ввода суммы
@router.message()
async def handle_custom_amount_input(message: Message):
    
    amount = int(message.text.strip())
    if amount < 100:
        await message.answer("❗ Минимальная сумма пополнения — 100 ₽. Пожалуйста, введите сумму заново.")
        return

    try:
        invoice = create_invoice(
            chat_id=message.chat.id,
            amount=amount * 100,
            description=f"Пополнение на {amount} ₽"
        )

        invoice_for_log = invoice.copy()
        invoice_for_log["prices"] = [{"label": p.label, "amount": p.amount} for p in invoice["prices"]]
        logging.debug("Создан инвойс (custom): %s", json.dumps(invoice_for_log, indent=2, ensure_ascii=False))

        await message.bot.send_invoice(**invoice)

    except Exception as e:
        logging.exception("Ошибка при создании инвойса (custom)")
        await message.answer("🚫 Ошибка при создании счёта. Попробуйте позже.")


# Ответ ЮKassa на pre_checkout запрос
@router.pre_checkout_query()
async def checkout(pre_checkout_q: types.PreCheckoutQuery, bot: Bot):
    await bot.answer_pre_checkout_query(pre_checkout_q.id, ok=True)

# Успешная оплата
@router.message(lambda message: message.successful_payment)
async def success_payment(message: types.Message):
    payment = message.successful_payment
    amount_rub = payment.total_amount / 100
    payment_id = payment.provider_payment_charge_id
    tg_id = message.from_user.id
    username = message.from_user.username or "unknown"

    async with async_session() as session:
        try:
            result = await session.execute(select(User).where(User.telegram_id == tg_id))
            user = result.scalar_one_or_none()

            if user is None:
                user = User(telegram_id=tg_id, username=username, balance=amount_rub)
                session.add(user)
                await session.flush()
            else:
                user.balance += amount_rub

            session.add(PaymentRecord(
                user_id=user.id,
                amount=amount_rub,
                payment_id=payment_id,
                status="succeeded"
            ))

            await session.commit()

            await message.answer(
                f"✅ Платёж прошёл успешно!\n"
                f"💸 Сумма: {amount_rub:.2f} {payment.currency}\n"
                f"🧾 ID платежа: {payment_id}\n"
                f"💰 Ваш текущий баланс: {user.balance:.2f} ₽"
            )

        except SQLAlchemyError:
            await session.rollback()
            logging.exception("Ошибка при сохранении платежа")
            await message.answer("⚠️ Ошибка при сохранении платежа. Попробуйте позже.")
