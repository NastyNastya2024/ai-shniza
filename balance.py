# bot/handlers/balance.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import PRICE_PER_GENERATION, PAYMENT_LINK
from database import SessionLocal, User
from bot.payments import create_payment

balance_router = Router()

def balance_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="topup")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])

def payment_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пополнить баланс", url=PAYMENT_LINK)],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])

async def get_or_create_user(user_id: int, username: str):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == user_id).first()
    if not user:
        user = User(telegram_id=user_id, username=username, balance=0)
        db.add(user)
        db.commit()
        db.refresh(user)
    db.close()
    return user

@balance_router.message(F.text == "📊 Баланс")
async def cmd_balance(message: Message):
    user = await get_or_create_user(message.from_user.id, message.from_user.username)
    await message.answer(
        f"Ваш баланс: {user.balance} руб.\nОдна генерация — {PRICE_PER_GENERATION} руб.",
        reply_markup=balance_keyboard()
    )

@balance_router.callback_query(F.data == "topup")
async def handle_topup(callback: CallbackQuery):
    user_id = callback.from_user.id
    return_url = f"https://yourdomain.com/payment_success?user_id={user_id}"

    payment = create_payment(amount=199, return_url=return_url, description="Пополнение баланса")
    payment_url = payment.get("confirmation", {}).get("confirmation_url")

    if payment_url:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить", url=payment_url)],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
        ])
        await callback.message.answer("Нажмите кнопку ниже для оплаты:", reply_markup=keyboard)
    else:
        await callback.message.answer("Ошибка при создании платежа. Повторите позже.")
    await callback.answer()
