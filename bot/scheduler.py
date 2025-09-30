import logging
from datetime import datetime, time
import pytz
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from bot.db.database import Session
from bot.db.users.models import User
from sqlalchemy import select

logger = logging.getLogger(__name__)

async def send_birthday_countdown(bot: Bot):
    async with Session() as session:
        try:
            result = await session.execute(
                select(User).where(User.birthday != None, User.timezone != None)
            )
            users = result.scalars().all()
            
            for user in users:
                try:
                    tz = pytz.timezone(user.timezone)
                    now = datetime.now(tz)
                    birthday = user.birthday
                    next_birthday = birthday.replace(year=now.year)
                    if next_birthday < now.date():
                        next_birthday = next_birthday.replace(year=now.year + 1)
                    days_left = (next_birthday - now.date()).days

                    # Отправка ровно в 00:00 по локальному времени пользователя
                    if now.hour == 0 and now.minute < 5:
                        await bot.send_message(
                            user.user_id,
                            f'🎉 До вашего дня рождения осталось <b>{days_left}</b> дней!',
                            parse_mode='HTML'
                        )
                        logger.info(f'Уведомление отправлено user_id={user.user_id}, days_left={days_left}')
                except Exception as e:
                    logger.error(f'Ошибка при отправке уведомления user_id={user.user_id}: {e}', exc_info=True)
        except Exception as e:
            logger.error(f'Ошибка при выборке пользователей: {e}', exc_info=True)

def setup_scheduler(bot: Bot):
    scheduler = AsyncIOScheduler()
    # Запуск каждые 5 минут, чтобы не пропустить 00:00 в любом часовом поясе
    scheduler.add_job(send_birthday_countdown, CronTrigger(minute='*/5', hour='*'), args=[bot])
    scheduler.start()
    logger.info('Планировщик ежедневных уведомлений запущен.')
