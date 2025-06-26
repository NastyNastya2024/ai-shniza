import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import SessionLocal, User

def change_user_balance(telegram_id: int, amount: float):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == telegram_id).first()

    if not user:
        print(f"Пользователь с telegram_id={telegram_id} не найден.")
        db.close()
        return

    user.balance += amount
    db.commit()
    print(f"Баланс пользователя {user.username} ({telegram_id}) изменён на {amount}. Новый баланс: {user.balance}")

    db.close()

if __name__ == "__main__":
    # Пример: добавить 100 рублей пользователю с telegram_id=123456789
    change_user_balance(679030923, 1010000)
