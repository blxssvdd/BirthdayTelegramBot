from sqlalchemy import Column, BigInteger, String, Date, Boolean
from bot.db.database import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(BigInteger, primary_key=True, index=True)  # Telegram ID
    birthday = Column(Date, nullable=True)                      # дата рождения
    timezone = Column(String(100), nullable=True)               # строка с таймзоной
    city = Column(String(100), nullable=True)                   # город
    notifications_enabled = Column(Boolean, default=True)       # включены ли уведомления
