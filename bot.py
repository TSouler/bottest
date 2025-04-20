import os
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    JobQueue
)
import sqlite3
from dotenv import load_dotenv
from datetime import datetime, time, timedelta

# Настройка логов
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = list(map(int, os.getenv('ADMIN_IDS', '').split(',')))
GROUP_ID = int(os.getenv('GROUP_ID', 0))
VK_LINK = os.getenv('VK_GROUP_LINK', 'https://vk.com/example')
TG_LINK = os.getenv('TG_CHANNEL_LINK', 'https://t.me/example')

if not BOT_TOKEN:
    logger.error("Не указан BOT_TOKEN в .env файле!")
    exit(1)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        points INTEGER DEFAULT 0,
        invited_count INTEGER DEFAULT 0,
        join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_month_points INTEGER DEFAULT 0
    )''')
    
    conn.commit()
    return conn

async def reset_monthly_points(context: ContextTypes.DEFAULT_TYPE):
    """Сброс очков в начале месяца"""
    conn = context.bot_data['conn']
    with conn:
        conn.execute('UPDATE users SET last_month_points = points, points = 0, invited_count = 0')
    logger.info("Ежемесячный сброс очков выполнен")
    await context.bot.send_message(
        chat_id=GROUP_ID,
        text="🎉 Очки за месяц сброшены! Новый конкурс начался!"
    )

async def send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие новых участников"""
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
            
        inviter = update.message.from_user
        conn = context.bot_data['conn']
        
        with conn:
            conn.execute(
                'INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
                (member.id, member.username, member.first_name)
            )
            
            if inviter and inviter.id != member.id and inviter.id not in ADMIN_IDS:
                conn.execute(
                    'UPDATE users SET points = points + 1, invited_count = invited_count + 1 WHERE user_id = ?',
                    (inviter.id,)
                )
        
        try:
            await context.bot.send_message(
                chat_id=member.id,
                text=f"👋 Привет, {member.first_name}!\n\n"
                     "Добро пожаловать! Напиши /start для участия в конкурсе!"
            )
        except Exception as e:
            logger.error(f"Ошибка приветствия: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    user = update.effective_user
    conn = context.bot_data['conn']
    
    with conn:
        conn.execute(
            'INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
            (user.id, user.username, user.first_name)
        )
    
    await update.message.reply_text(
        "✅ Ты зарегистрирован в конкурсе!\n\n"
        "Приглашай друзей и получай баллы!\n"
        "Твоя статистика: /me\n"
        "Топ участников: /top\n"
        "Правила: /info"
    )

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику (/me)"""
    user = update.effective_user
    conn = context.bot_data['conn']
    
    with conn:
        cursor = conn.execute(
            'SELECT points, invited_count, last_month_points FROM users WHERE user_id = ?',
            (user.id,)
        )
        result = cursor.fetchone()
    
    if result:
        points, invited, last_month = result
        now = datetime.now()
        next_month = now.replace(day=28) + timedelta(days=4)
        days_left = (next_month - now).days
        
        await update.message.reply_text(
            f"📊 Твоя статистика:\n\n"
            f"🏅 Баллы: {points}\n"
            f"👥 Приглашено: {invited}\n"
            f"🏆 Прошлый месяц: {last_month}\n\n"
            f"⏳ До сброса: {days_left} дней"
        )
    else:
        await update.message.reply_text("Напиши /start для регистрации")

async def show_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает топ участников (/top)"""
    conn = context.bot_data['conn']
    
    with conn:
        cursor = conn.execute(
            'SELECT first_name, username, points FROM users ORDER BY points DESC LIMIT 10'
        )
        top_users = cursor.fetchall()
    
    if top_users:
        response = "🏆 Топ участников:\n\n"
        for i, (first_name, username, points) in enumerate(top_users, 1):
            name = f"@{username}" if username else first_name
            response += f"{i}. {name} - {points} баллов\n"
        
        await update.message.reply_text(response)
    else:
        await update.message.reply_text("Пока нет данных")

async def show_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает информацию о конкурсе (/info)"""
    await update.message.reply_text(
        "🎁 Реферальный конкурс\n\n"
        "🔹 1 друг = 1 балл\n"
        "🔹 Очки сбрасываются 1 числа\n"
        "🔹 Топ-3 получают призы\n\n"
        f"📌 Наши ресурсы:\n{VK_LINK}\n{TG_LINK}"
    )

def main():
    """Запуск бота"""
    try:
        conn = init_db()
        
        # Создаем JobQueue отдельно
        job_queue = JobQueue()
        
        # Инициализируем приложение
        app = Application.builder().token(BOT_TOKEN).build()
        
        # Привязываем JobQueue к приложению
        job_queue.set_application(app)
        app.job_queue = job_queue
        
        app.bot_data['conn'] = conn
        
        # Обработчики
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("me", show_stats))
        app.add_handler(CommandHandler("top", show_top))
        app.add_handler(CommandHandler("info", show_info))
        app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, send_welcome))
        
        # Планировщик
        job_queue.run_monthly(
            reset_monthly_points,
            time=time(hour=0, minute=5),
            day=1,
            context=app
        )
        
        logger.info("Бот запущен с работающим JobQueue")
        app.run_polling()
        
    except Exception as e:
        logger.critical(f"Ошибка запуска: {e}", exc_info=True)
    finally:
        conn.close()
        logger.info("Бот остановлен")

if __name__ == '__main__':
    main()
