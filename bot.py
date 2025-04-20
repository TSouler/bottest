import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import sqlite3
from dotenv import load_dotenv
from datetime import datetime

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
        join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_month_points INTEGER DEFAULT 0
    )''')
    
    conn.commit()
    return conn

async def reset_monthly_points(context: ContextTypes.DEFAULT_TYPE):
    """Сброс очков в начале месяца"""
    conn = context.bot_data['conn']
    with conn:
        # Сохраняем текущие очки в last_month_points
        conn.execute('''
        UPDATE users 
        SET last_month_points = points,
            points = 0,
            invited_count = 0
        ''')
    logger.info("Ежемесячный сброс очков выполнен")

async def check_monthly_reset(app: Application):
    """Проверка необходимости сброса очков"""
    now = datetime.now()
    if now.day == 1:
        await reset_monthly_points(app)

def format_contest_info():
    """Форматирование информации о конкурсе"""
    return (
        "🎉 <b>Реферальный конкурс</b> 🎉\n\n"
        "🔹 <b>Как участвовать?</b>\n"
        "1. Приглашайте друзей в чат\n"
        "2. За каждого приглашенного друга вы получаете 1 балл\n"
        "3. В начале месяца подводятся итоги\n"
        "4. Лучшие участники получают призы!\n\n"
        "🔹 <b>Важно!</b>\n"
        "• Для участия нужно активировать бота командой /start\n"
        "• Очки сбрасываются 1 числа каждого месяца\n"
        "• Чем больше друзей вы пригласите, тем выше шанс на победу!\n\n"
        "🏆 <b>Призы:</b>\n"
        "• 1 место: Премиум-статус на месяц\n"
        "• 2 место: 500 рублей на баланс\n"
        "• 3 место: Стикерпак\n\n"
        "📌 Наши ресурсы:\n"
        f"ВКонтакте: {VK_LINK}\n"
        f"Telegram: {TG_LINK}"
    )

async def send_welcome_message(context: ContextTypes.DEFAULT_TYPE, user_id: int, first_name: str, inviter_username: str = None):
    """Отправка приветственного сообщения новому участнику"""
    welcome_text = (
        f"👋 <b>Добро пожаловать, {first_name}!</b>\n\n"
        "Мы рады видеть вас в нашем сообществе!\n\n"
        "🎁 У нас проходит <b>реферальный конкурс</b>!\n"
        "Приглашайте друзей и получайте баллы.\n"
        "1 друг = 1 балл\n\n"
        "🔹 <b>Чтобы участвовать:</b>\n"
        "1. Напишите команду /start\n"
        "2. Приглашайте друзей в этот чат\n"
        "3. Следите за своим прогрессом по команде /me\n\n"
        "📌 Подробнее: /info\n\n"
        f"📢 Вас пригласил: @{inviter_username}" if inviter_username else ""
    )
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=welcome_text,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Не удалось отправить приветствие: {e}")

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
    
    await update.message.reply_text(
        "✅ Вы успешно зарегистрированы в реферальной системе!\n\n"
        "Теперь вы можете приглашать друзей и получать баллы.\n"
        "Используйте команды:\n"
        "/me - ваша статистика\n"
        "/top - топ участников\n"
        "/info - правила конкурса",
        parse_mode='HTML'
    )

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
        
        # Отправляем приветственное сообщение
        await send_welcome_message(
            context,
            member.id,
            member.first_name,
            inviter.username if inviter else None
        )

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику пользователя (/me)"""
    user = update.effective_user
    conn = context.bot_data['conn']
    
    with conn:
        cursor = conn.execute('''
        SELECT points, invited_count, last_month_points 
        FROM users 
        WHERE user_id = ?
        ''', (user.id,))
        result = cursor.fetchone()
    
    if result:
        points, invited, last_month = result
        now = datetime.now()
        days_left = (datetime(now.year, now.month % 12 + 1, 1) - now
        
        response = (
            f"📊 <b>Ваша статистика</b>\n\n"
            f"🏅 <b>Текущие баллы:</b> {points}\n"
            f"👥 <b>Приглашено друзей:</b> {invited}\n"
            f"🏆 <b>Баллов в прошлом месяце:</b> {last_month}\n\n"
            f"⏳ <b>До сброса очков:</b> {days_left.days} дней\n\n"
            "Приглашайте друзей командой /info и получайте баллы!"
        )
        await update.message.reply_text(response, parse_mode='HTML')
    else:
        await update.message.reply_text(
            "Вы не зарегистрированы. Напишите /start для участия",
            parse_mode='HTML'
        )

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
        response = "🏆 <b>Топ участников этого месяца</b>\n\n"
        for i, (first_name, username, points) in enumerate(top_users, 1):
            name = f"@{username}" if username else first_name
            response += f"{i}. {name} - {points} баллов\n"
        
        response += (
            "\n🎁 <b>Призы:</b>\n"
            "1 место: Премиум-статус\n"
            "2 место: 500 рублей\n"
            "3 место: Стикерпак\n\n"
            "Подробнее: /info"
        )
        await update.message.reply_text(response, parse_mode='HTML')
    else:
        await update.message.reply_text("Пока нет данных для топа", parse_mode='HTML')

async def show_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает информацию о конкурсе (/info)"""
    await update.message.reply_text(
        format_contest_info(),
        parse_mode='HTML'
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ошибок"""
    logger.error("Ошибка при обработке запроса:", exc_info=context.error)
    
    if update and hasattr(update, 'message'):
        try:
            await update.message.reply_text(
                "❌ Произошла ошибка. Попробуйте позже.",
                parse_mode='HTML'
            )
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
        app.add_handler(CommandHandler("info", show_info))
        
        # Обработчик новых участников
        app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members))
        
        # Обработчик ошибок
        app.add_error_handler(error_handler)
        
        # Планировщик для сброса очков
        job_queue = app.job_queue
        job_queue.run_monthly(
            callback=reset_monthly_points,
            when=datetime.time(hour=0, minute=0),
            day=1,
            context=app
        )
        
        logger.info("Бот запущен...")
        app.run_polling()
        
    except Exception as e:
        logger.error("Ошибка при запуске бота:", exc_info=True)
    finally:
        conn.close()
        logger.info("Бот остановлен")

if __name__ == '__main__':
    main()
