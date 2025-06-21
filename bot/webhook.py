import os
import hmac
import hashlib
import json
from aiohttp import web
from sqlalchemy import func
from database import SessionLocal
from database.models import User, PaymentRecord
from yookassa import Configuration

Configuration.account_id = os.getenv("YOOKASSA_SHOP_ID")
Configuration.secret_key = os.getenv("YOOKASSA_API_KEY")

YOOKASSA_WEBHOOK_SECRET = os.getenv("YOOKASSA_WEBHOOK_SECRET")

def update_user_balance(db_session, user_id: int):
    total_paid = db_session.query(func.sum(PaymentRecord.amount))\
        .filter(PaymentRecord.telegram_id == user_id, PaymentRecord.status == "succeeded")\
        .scalar() or 0.0
    user = db_session.query(User).filter(User.telegram_id == user_id).first()
    if user:
        user.balance = total_paid
        db_session.commit()

async def yookassa_webhook_handler(request):
    body = await request.text()
    signature = request.headers.get("Content-HMAC")

    computed_signature = hmac.new(
        YOOKASSA_WEBHOOK_SECRET.encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_signature, signature):
        return web.Response(status=403, text="Invalid signature")

    data = json.loads(body)
    payment_id = data["object"]["id"]
    status = data["object"]["status"]
    amount = float(data["object"]["amount"]["value"])
    metadata = data["object"].get("metadata", {})
    telegram_id = metadata.get("telegram_id")

    db = SessionLocal()
    try:
        payment_record = db.query(PaymentRecord).filter(PaymentRecord.payment_id == payment_id).first()

        if not payment_record:
            payment_record = PaymentRecord(
                payment_id=payment_id,
                telegram_id=telegram_id,
                amount=amount,
                status=status
            )
            db.add(payment_record)
        else:
            payment_record.status = status

        db.commit()

        # Обновляем баланс пользователя, если платеж успешен и есть telegram_id
        if status == "succeeded" and telegram_id:
            update_user_balance(db, telegram_id)
    finally:
        db.close()

    return web.Response(status=200, text="OK")


def setup_webhook_routes(app: web.Application):
    app.router.add_post("/yookassa_webhook", yookassa_webhook_handler)
