from sqlalchemy import Column, BigInteger, String, Date
from bot.db.database import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(BigInteger, primary_key=True, index=True)  # Telegram ID
    birthday = Column(Date, nullable=True)                      # дата рождения
    timezone = Column(String(100), nullable=True)               # строка с таймзоной
    name = Column(String(100), nullable=True)                   # имя пользователя
