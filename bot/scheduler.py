import logging
from datetime import datetime, time
import pytz
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from bot.db.database import Session
from bot.db.users.models import User

logger = logging.getLogger(__name__)

async def send_birthday_countdown(bot: Bot):
    session = Session()
    try:
        users = session.query(User).filter(User.birthday != None, User.timezone != None).all()
    finally:
        session.close()

    for user in users:
        try:
            tz = pytz.timezone(user.timezone)
            now = datetime.now(tz)
            birthday = user.birthday
            next_birthday = birthday.replace(year=now.year)
            if next_birthday < now.date():
                next_birthday = next_birthday.replace(year=now.year + 1)
            days_left = (next_birthday - now.date()).days
            if time(0, 0) <= now.time() < time(0, 5):
                await bot.send_message(
                    user.user_id,
                    f'🎉 До вашего дня рождения осталось <b>{days_left}</b> дней!',
                    parse_mode='HTML'
                )
                logger.info(f'Уведомление отправлено user_id={user.user_id}, days_left={days_left}')
        except Exception as e:
            logger.error(f'Ошибка при отправке уведомления user_id={user.user_id}: {e}', exc_info=True)

def setup_scheduler(bot: Bot):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_birthday_countdown, CronTrigger(minute='0,5', hour='*'), args=[bot])
    scheduler.start()
    logger.info('Планировщик ежедневных уведомлений запущен.')
