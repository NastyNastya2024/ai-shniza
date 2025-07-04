import sys
import os
import asyncio
from sqlalchemy import select

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.db import async_session
from database.models import User  # импортируем из bot.models, как у вас

async def change_user_balance(telegram_id: int, amount: float):
    async with async_session() as session:
        async with session.begin():
            result = await session.execute(select(User).where(User.telegram_id == telegram_id))
            user = result.scalars().first()

            if not user:
                print(f"Пользователь с telegram_id={telegram_id} не найден.")
                return

            user.balance += amount

            # session.begin() автоматически коммитит изменения,
            # но если нужно, можно вызвать await session.commit()

            print(f"Баланс пользователя {user.username} ({telegram_id}) изменён на {amount}. Новый баланс: {user.balance}")

if __name__ == "__main__":
    telegram_id = 679030923
    amount = -1008520  # задайте нужное значение
    asyncio.run(change_user_balance(telegram_id, amount))
