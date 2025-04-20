import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import sqlite3
from dotenv import load_dotenv

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
VK_LINK = os.getenv('VK_GROUP_LINK')
TG_LINK = os.getenv('TG_CHANNEL_LINK')

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        points INTEGER DEFAULT 0,
        invited_count INTEGER DEFAULT 0,
        join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    return conn

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    user = update.effective_user
    conn = context.bot_data['conn']
    
    # Добавляем пользователя в БД
    with conn:
        conn.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name) 
        VALUES (?, ?, ?)
        ''', (user.id, user.username, user.first_name))
    
    # Приветственное сообщение с ссылками
    welcome_text = (
        f"Привет, {user.first_name}! 👋\n\n"
        "Я бот для учета рефералов и активности в группе!\n\n"
        "Присоединяйся к нашим сообществам:\n"
        f"🔹 ВКонтакте: {VK_LINK}\n"
        f"🔹 Telegram: {TG_LINK}\n\n"
        "Используй команды:\n"
        "/me - твоя статистика\n"
        "/top - лучшие участники"
    )
    
    await update.message.reply_text(welcome_text)

async def handle_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка новых участников группы"""
    conn = context.bot_data['conn']
    
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
            
        inviter = update.message.from_user
        
        with conn:
            # Добавляем нового пользователя
            conn.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name) 
            VALUES (?, ?, ?)
            ''', (member.id, member.username, member.first_name))
            
            # Начисляем баллы пригласившему
            if inviter.id != member.id and inviter.id not in ADMIN_IDS:
                conn.execute('''
                UPDATE users 
                SET points = points + 1, 
                    invited_count = invited_count + 1 
                WHERE user_id = ?
                ''', (inviter.id,))
        
        # Приветственное сообщение с ссылками
        welcome_text = (
            f"Добро пожаловать, {member.first_name}! 🎉\n\n"
            f"Вас пригласил @{inviter.username if inviter.username else 'участник'}\n\n"
            "Подпишись на наши ресурсы:\n"
            f"🔹 ВКонтакте: {VK_LINK}\n"
            f"🔹 Telegram: {TG_LINK}\n\n"
            "Используй /me для просмотра своей статистики"
        )
        
        try:
            await context.bot.send_message(
                chat_id=member.id,
                text=welcome_text
            )
        except Exception as e:
            logger.error(f"Не удалось отправить приветствие: {e}")

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику пользователя (/me)"""
    user = update.effective_user
    conn = context.bot_data['conn']
    
    with conn:
        cursor = conn.execute('''
        SELECT points, invited_count 
        FROM users 
        WHERE user_id = ?
        ''', (user.id,))
        result = cursor.fetchone()
    
    if result:
        points, invited = result
        response = (
            f"📊 Статистика {user.first_name}:\n\n"
            f"• 🏅 Ваши баллы: {points}\n"
            f"• 👥 Приглашено друзей: {invited}\n\n"
            "Приглашайте друзей и получайте баллы!\n"
            f"Наши ресурсы:\n{VK_LINK}\n{TG_LINK}"
        )
        await update.message.reply_text(response)
    else:
        await update.message.reply_text("Вы не зарегистрированы. Напишите /start")

async def show_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает топ пользователей (/top)"""
    conn = context.bot_data['conn']
    
    with conn:
        cursor = conn.execute('''
        SELECT first_name, username, points 
        FROM users 
        ORDER BY points DESC 
        LIMIT 10
        ''')
        top_users = cursor.fetchall()
    
    if top_users:
        response = "🏆 Топ участников:\n\n"
        for i, (first_name, username, points) in enumerate(top_users, 1):
            name = f"@{username}" if username else first_name
            response += f"{i}. {name} - {points} баллов\n"
        
        response += f"\nНаши ресурсы:\n{VK_LINK}\n{TG_LINK}"
        await update.message.reply_text(response)
    else:
        await update.message.reply_text("Пока нет данных для топа")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ошибок"""
    logger.error("Ошибка при обработке запроса:", exc_info=context.error)
    
    if update and hasattr(update, 'message'):
        try:
            await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")
        except:
            pass

def main():
    """Запуск бота"""
    # Инициализация базы данных
    conn = init_db()
    
    try:
        # Создаем приложение
        app = Application.builder().token(BOT_TOKEN).build()
        
        # Сохраняем соединение с БД
        app.bot_data['conn'] = conn
        
        # Обработчики команд
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("me", show_stats))
        app.add_handler(CommandHandler("top", show_top))
        
        # Обработчик новых участников
        app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members))
        
        # Обработчик ошибок
        app.add_error_handler(error_handler)
        
        logger.info("Бот запущен...")
        app.run_polling()
        
    except Exception as e:
        logger.error("Ошибка при запуске бота:", exc_info=True)
    finally:
        conn.close()
        logger.info("Бот остановлен")

if __name__ == '__main__':
    main()
