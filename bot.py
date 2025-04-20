import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
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
        
        # Добавляем пользователя в БД
        with conn:
            conn.execute(
                'INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
                (member.id, member.username, member.first_name)
            )
            
            # Начисляем баллы пригласившему
            if inviter and inviter.id != member.id and inviter.id not in ADMIN_IDS:
                conn.execute(
                    'UPDATE users SET points = points + 1, invited_count = invited_count + 1 WHERE user_id = ?',
                    (inviter.id,)
                )
        
        # Отправляем приветственное сообщение
        try:
            welcome_text = (
                f"👋 Привет, {member.first_name}!\n\n"
                "Добро пожаловать в наше сообщество!\n\n"
                "🎁 У нас проходит реферальный конкурс:\n"
                "1. Напиши /start для регистрации\n"
                "2. Приглашай друзей\n"
                "3. Получай баллы за каждого друга\n\n"
                f"📢 Тебя пригласил: @{inviter.username}\n\n" if inviter else ""
                "🏆 Топ участников: /top\n"
                "ℹ️ Подробнее: /info"
            )
            await context.bot.send_message(
                chat_id=member.id,
                text=welcome_text
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке приветствия: {e}")

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
        "Теперь ты можешь:\n"
        "• Приглашать друзей в чат\n"
        "• Получать 1 балл за каждого друга\n"
        "• Следить за своим прогрессом (/me)\n\n"
        "🏆 Топ участников: /top\n"
        "ℹ️ Правила конкурса: /info"
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
        
        response = (
            f"📊 Твоя статистика:\n\n"
            f"🏅 Текущие баллы: {points}\n"
            f"👥 Приглашено друзей: {invited}\n"
            f"🏆 Баллов в прошлом месяце: {last_month}\n\n"
            f"⏳ До сброса очков: {days_left} дней\n\n"
            "Приглашай друзей и получай больше баллов!"
        )
        await update.message.reply_text(response)
    else:
        await update.message.reply_text("Ты не зарегистрирован. Напиши /start")

async def show_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает топ участников (/top)"""
    conn = context.bot_data['conn']
    
    with conn:
        cursor = conn.execute(
            'SELECT first_name, username, points FROM users ORDER BY points DESC LIMIT 10'
        )
        top_users = cursor.fetchall()
    
    if top_users:
        response = "🏆 Топ участников этого месяца:\n\n"
        for i, (first_name, username, points) in enumerate(top_users, 1):
            name = f"@{username}" if username else first_name
            response += f"{i}. {name} - {points} баллов\n"
        
        response += (
            "\n🎁 Призы:\n"
            "🥇 1 место: Премиум-статус\n"
            "🥈 2 место: 500 рублей\n"
            "🥉 3 место: Стикерпак\n\n"
            "ℹ️ Подробнее: /info"
        )
        await update.message.reply_text(response)
    else:
        await update.message.reply_text("Пока нет данных для топа")

async def show_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает информацию о конкурсе (/info)"""
    info_text = (
        "🎁 Реферальный конкурс 🎁\n\n"
        "🔹 Как участвовать:\n"
        "1. Напиши /start\n"
        "2. Приглашай друзей в этот чат\n"
        "3. Получай 1 балл за каждого друга\n\n"
        "🔹 Правила:\n"
        "• Очки сбрасываются 1 числа каждого месяца\n"
        "• Призы разыгрываются среди топ-3\n"
        "• Админы не участвуют\n\n"
        "🏆 Призы:\n"
        "• 1 место: Премиум на 1 месяц\n"
        "• 2 место: 500 рублей\n"
        "• 3 место: Стикерпак\n\n"
        f"📌 Наши ресурсы:\n{VK_LINK}\n{TG_LINK}"
    )
    await update.message.reply_text(info_text)

def main():
    """Запуск бота"""
    try:
        conn = init_db()
        
        # Создаем приложение с работающим JobQueue
        app = (
            ApplicationBuilder()
            .token(BOT_TOKEN)
            .job_queue(None)  # Важно: явная инициализация
            .build()
        )
        
        app.bot_data['conn'] = conn
        
        # Обработчики команд
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("me", show_stats))
        app.add_handler(CommandHandler("top", show_top))
        app.add_handler(CommandHandler("info", show_info))
        
        # Обработчик новых участников
        app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, send_welcome))
        
        # Планировщик сброса очков (теперь точно работает)
        app.job_queue.run_monthly(
            reset_monthly_points,
            time=time(hour=0, minute=5),  # В 00:05
            day=1,
            context=app
        )
        
        logger.info("Бот успешно запущен!")
        app.run_polling()
        
    except Exception as e:
        logger.critical(f"Ошибка запуска: {e}", exc_info=True)
    finally:
        conn.close()
        logger.info("Бот остановлен")

if __name__ == '__main__':
    main()
