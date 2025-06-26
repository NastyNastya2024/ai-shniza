import sys
import os

# Добавляем корень проекта в sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import SessionLocal, User

def main():
    db = SessionLocal()
    users = db.query(User).all()

    for user in users:
        print(f"ID: {user.id}, Telegram ID: {user.telegram_id}, Username: {user.username}, Баланс: {user.balance} руб.")

    db.close()

if __name__ == "__main__":
    main()
