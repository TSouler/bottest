import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import sqlite3
from dotenv import load_dotenv
from datetime import datetime, time

# Настройка логов
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Конфигурация
try:
    BOT_TOKEN = os.environ['BOT_TOKEN']
    ADMIN_IDS = [int(id) for id in os.environ['ADMIN_IDS'].split(',')]
    GROUP_ID = int(os.environ.get('GROUP_ID', 0))
    VK_LINK = os.environ.get('VK_GROUP_LINK', '')
    TG_LINK = os.environ.get('TG_CHANNEL_LINK', '')
except KeyError as e:
    logger.error(f"Ошибка загрузки конфигурации: {e}")
    exit(1)

# Инициализация базы данных
def init_db():
    try:
        conn = sqlite3.connect('bot.db')
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
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных: {e}")
        raise

async def reset_monthly_points(context: ContextTypes.DEFAULT_TYPE):
    """Сброс очков в начале месяца"""
    try:
        conn = context.bot_data['conn']
        with conn:
            conn.execute('UPDATE users SET last_month_points = points, points = 0, invited_count = 0')
        logger.info("Ежемесячный сброс очков выполнен")
        await context.bot.send_message(
            chat_id=GROUP_ID,
            text="🎉 Произведён сброс очков за новый месяц! Удачи в конкурсе!"
        )
    except Exception as e:
        logger.error(f"Ошибка при сбросе очков: {e}")

async def send_welcome(context: ContextTypes.DEFAULT_TYPE, user_id: int, first_name: str, inviter: str = None):
    """Отправка приветственного сообщения"""
    try:
        text = (
            f"👋 Добро пожаловать, {first_name}!\n\n"
            "📢 Для участия в реферальном конкурсе:\n"
            "1. Напишите /start\n"
            "2. Приглашайте друзей\n"
            "3. Получайте баллы!\n\n"
            f"🎁 Вас пригласил: @{inviter}" if inviter else ""
        )
        await context.bot.send_message(chat_id=user_id, text=text)
    except Exception as e:
        logger.error(f"Ошибка приветствия: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    try:
        user = update.effective_user
        conn = context.bot_data['conn']
        
        with conn:
            conn.execute(
                'INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
                (user.id, user.username, user.first_name)
            )
        
        await update.message.reply_text(
            "✅ Вы зарегистрированы!\n"
            "Теперь приглашайте друзей и получайте баллы.\n\n"
            "ℹ️ Подробнее: /info"
        )
    except Exception as e:
        logger.error(f"Ошибка в /start: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка новых участников"""
    try:
        for member in update.message.new_chat_members:
            if member.is_bot:
                continue
                
            inviter = update.message.from_user
            conn = context.bot_data['conn']
            
            with conn:
                # Добавление пользователя
                conn.execute(
                    'INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
                    (member.id, member.username, member.first_name)
                )
                
                # Начисление баллов пригласившему
                if inviter and inviter.id != member.id and inviter.id not in ADMIN_IDS:
                    conn.execute(
                        'UPDATE users SET points = points + 1, invited_count = invited_count + 1 WHERE user_id = ?',
                        (inviter.id,)
                    )
            
            # Отправка приветствия
            await send_welcome(
                context,
                member.id,
                member.first_name,
                inviter.username if inviter else None
            )
    except Exception as e:
        logger.error(f"Ошибка при обработке нового участника: {e}")

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о конкурсе"""
    await update.message.reply_text(
        "🏆 Реферальный конкурс 🏆\n\n"
        "🔹 1 приглашённый = 1 балл\n"
        "🔹 Очки сбрасываются 1 числа каждого месяца\n"
        "🔹 Топ-3 участника получают призы!\n\n"
        "📊 Ваша статистика: /me\n"
        "🏆 Топ участников: /top\n\n"
        f"📌 Наши ресурсы:\n{VK_LINK}\n{TG_LINK}"
    )

def main():
    """Запуск бота"""
    try:
        conn = init_db()
        app = Application.builder().token(BOT_TOKEN).build()
        app.bot_data['conn'] = conn
        
        # Обработчики
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("info", info))
        app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))
        
        # Планировщик сброса очков
        app.job_queue.run_monthly(
            reset_monthly_points,
            time=time(hour=0, minute=0),
            day=1,
            context=app
        )
        
        logger.info("Бот запущен")
        app.run_polling()
        
    except Exception as e:
        logger.critical(f"Фатальная ошибка: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == '__main__':
    main()
