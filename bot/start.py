from aiogram import types, Bot, Router
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from bot.invoice import create_invoice
from database.db import async_session
from database.models import User, PaymentRecord
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

router = Router()

# === FSM состояние для суммы ===
class PaymentState(StatesGroup):
    waiting_for_amount = State()

# === Показать варианты оплаты ===
async def show_payment_options(message: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Платить через ЮKassa", callback_data="pay_yookassa")],
            [InlineKeyboardButton(text="💵 Платить через РобоКасса", callback_data="pay_robokassa")]
        ]
    )

    text = (
        "💡 Пополнение баланса возможно на любую сумму.\n"
        "⚠️ Деньги списываются только по факту успешной генерации. \n\n"
        "🖼️ Изображения:\n"
        "- ideogram-v2-turbo — 9₽\n"
        "- imagen-4 — 9₽\n"
        "- flux-kontext-pro — 9₽\n"
        "- kwaivgi/kling-v2.1 — 55₽\n"
        "- kwaivgi/kling-v2.2 — 110₽\n"
        "- kwaivgi/kling-v2.3 — 99₽\n"
        "- kwaivgi/kling-v2.4 — 199₽\n\n"
        "🎞️ Видео:\n"
        "- minimax / video-01-live — 150₽\n"
        "- seedance-1-pro 480p/5с — 80₽\n"
        "- seedance-1-pro 480p/10с — 120₽\n"
        "- seedance-1-pro 1080p/5с — 150₽\n"
        "- seedance-1-pro 1080p/10с — 250₽\n"
        "- google / veo-3 (8с) — 660₽\n\n"
        "🎵 Аудио:\n"
        "- minimax/music-01 — 9₽\n"
        "- meta/musicgen — 9₽\n\n"
        "🧠 Текст:\n"
        "- GPT — 0₽/ 300 символов\n"
        "- Chatterbox — 9₽ / 1000 символов\n\n"
        "⚠️ Пополненные средства не возвращаются. Ответственность за качество генераций не несётся, так как они выполняются сторонними ИИ-сервисами."
    )

    await message.answer(text, reply_markup=keyboard)

# === Обработка кнопки ЮKassa ===
@router.callback_query(lambda c: c.data == "pay_yookassa")
async def handle_yookassa_payment(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите сумму пополнения в рублях (например, 100):")
    await state.set_state(PaymentState.waiting_for_amount)
    await callback.answer()

# === Приём суммы от пользователя ===
@router.message(PaymentState.waiting_for_amount)
async def process_amount_input(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount < 10:
            await message.answer("⚠️ Минимальная сумма пополнения — 10₽. Попробуйте снова.")
            return

        invoice = create_invoice(
            chat_id=message.chat.id,
            amount=int(amount * 100),
            description=f"Пополнение на {amount:.2f} ₽"
        )

        await message.bot.send_invoice(**invoice)
        await state.clear()

    except ValueError:
        await message.answer("❌ Введите корректное число. Пример: 150")
    except Exception as e:
        await message.answer("🚫 Ошибка при создании счёта.")
        import logging
        logging.exception("Ошибка при создании инвойса")

# === Подтверждение оплаты ===
@router.pre_checkout_query()
async def checkout(pre_checkout_q: types.PreCheckoutQuery, bot: Bot):
    await bot.answer_pre_checkout_query(pre_checkout_q.id, ok=True)

# === Обработка успешного платежа ===
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

            payment_record = PaymentRecord(
                user_id=user.id,
                amount=amount_rub,
                payment_id=payment_id,
                status="succeeded"
            )
            session.add(payment_record)

            await session.commit()

            await message.answer(
                f"✅ Платёж прошёл успешно!\n"
                f"💸 Сумма: {amount_rub:.2f} {payment.currency}\n"
                f"🧾 ID платежа: {payment_id}\n"
                f"💰 Ваш текущий баланс: {user.balance:.2f} ₽"
            )

        except SQLAlchemyError:
            await session.rollback()
            await message.answer("⚠️ Ошибка при сохранении платежа. Попробуйте позже.")
            import logging
            logging.exception("Ошибка при сохранении платежа")
