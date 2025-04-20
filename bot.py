import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
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
    VK_LINK = os.environ.get('VK_GROUP_LINK', 'ссылка_не_указана')
    TG_LINK = os.environ.get('TG_CHANNEL_LINK', 'ссылка_не_указана')
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

async def send_welcome_message(user_id: int, first_name: str, context: ContextTypes.DEFAULT_TYPE, inviter_username: str = None):
    """Отправка приветственного сообщения новому участнику"""
    try:
        welcome_text = (
            f"👋 Добро пожаловать, {first_name}!\n\n"
            "🎁 У нас проходит реферальный конкурс:\n"
            "1. Напишите /start для регистрации\n"
            "2. Приглашайте друзей в этот чат\n"
            "3. Получайте 1 балл за каждого приглашённого\n\n"
            f"📢 Вас пригласил: @{inviter_username}\n\n" if inviter_username else ""
            "🏆 Лучшие участники получают призы каждый месяц!\n"
            "ℹ️ Подробнее: /info"
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=welcome_text
        )
    except Exception as e:
        logger.error(f"Не удалось отправить приветствие: {e}")

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
            "✅ Вы успешно зарегистрированы в реферальной системе!\n\n"
            "Теперь вы можете:\n"
            "• Приглашать друзей в чат\n"
            "• Получать баллы за приглашённых\n"
            "• Следить за своим прогрессом (/me)\n\n"
            "🏆 Топ участников: /top\n"
            "ℹ️ Правила конкурса: /info"
        )
    except Exception as e:
        logger.error(f"Ошибка в /start: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка новых участников группы"""
    try:
        for member in update.message.new_chat_members:
            if member.is_bot:
                continue
                
            inviter = update.message.from_user
            conn = context.bot_data['conn']
            
            with conn:
                # Добавляем нового пользователя
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
            await send_welcome_message(
                member.id,
                member.first_name,
                context,
                inviter.username if inviter else None
            )
    except Exception as e:
        logger.error(f"Ошибка при обработке нового участника: {e}")

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику пользователя (/me)"""
    try:
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
            next_month = now.replace(day=28) + timedelta(days=4)  # Первое число след. месяца
            days_left = (next_month - now).days
            
            response = (
                f"📊 Ваша статистика:\n\n"
                f"🏅 Текущие баллы: {points}\n"
                f"👥 Приглашено друзей: {invited}\n"
                f"🏆 Баллов в прошлом месяце: {last_month}\n\n"
                f"⏳ До сброса очков: {days_left} дней\n\n"
                "Приглашайте друзей и получайте больше баллов!"
            )
            await update.message.reply_text(response)
        else:
            await update.message.reply_text("Вы не зарегистрированы. Напишите /start")
    except Exception as e:
        logger.error(f"Ошибка в /me: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")

async def show_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает топ участников (/top)"""
    try:
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
    except Exception as e:
        logger.error(f"Ошибка в /top: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")

async def show_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает информацию о конкурсе (/info)"""
    try:
        info_text = (
            "🎁 Реферальный конкурс 🎁\n\n"
            "🔹 Как участвовать:\n"
            "1. Напишите /start для регистрации\n"
            "2. Приглашайте друзей в этот чат\n"
            "3. Получайте 1 балл за каждого друга\n\n"
            "🔹 Правила:\n"
            "• Очки сбрасываются 1 числа каждого месяца\n"
            "• Призы разыгрываются среди топ-3 участников\n"
            "• Администраторы не участвуют в конкурсе\n\n"
            "🏆 Призы:\n"
            "• 1 место: Премиум-статус (1 месяц)\n"
            "• 2 место: 500 рублей\n"
            "• 3 место: Эксклюзивный стикерпак\n\n"
            f"📌 Наши ресурсы:\n{VK_LINK}\n{TG_LINK}"
        )
        await update.message.reply_text(info_text)
    except Exception as e:
        logger.error(f"Ошибка в /info: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")

def main():
    """Запуск бота"""
    try:
        conn = init_db()
        
        app = ApplicationBuilder() \
            .token(BOT_TOKEN) \
            .job_queue(None) \
            .build()
            
        app.bot_data['conn'] = conn
        
        # Обработчики команд
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("me", show_stats))
        app.add_handler(CommandHandler("top", show_top))
        app.add_handler(CommandHandler("info", show_info))
        
        # Обработчик новых участников
        app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))
        
        # Планировщик сброса очков
        app.job_queue.run_monthly(
            reset_monthly_points,
            time=time(hour=0, minute=0),
            day=1,
            context=app
        )
        
        logger.info("Бот успешно запущен")
        app.run_polling()
        
    except Exception as e:
        logger.critical(f"Фатальная ошибка при запуске: {e}", exc_info=True)
    finally:
        if 'conn' in locals():
            conn.close()
            logger.info("Соединение с базой данных закрыто")

if __name__ == '__main__':
    from datetime import timedelta  # Добавлено для корректной работы days_left
    main()
