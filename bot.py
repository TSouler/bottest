import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

TOKEN = os.getenv('BOT_TOKEN')
VK_LINK = os.getenv('VK_GROUP_LINK')
TG_LINK = os.getenv('TG_CHANNEL_LINK')

async def start(update: Update, context):
    user = update.effective_user
    welcome_text = (
        f"Привет, {user.first_name}! 👋\n\n"
        "Мы рады видеть тебя здесь!\n\n"
        f"Присоединяйся к нашим сообществам:\n"
        f"🔹 ВКонтакте: {VK_LINK}\n"
        f"🔹 Telegram: {TG_LINK}\n\n"
        "У нас регулярно проходят крутые розыгрыши! 🎁"
    )
    
    await update.message.reply_text(welcome_text)

async def handle_new_members(update: Update, context):
    for member in update.message.new_chat_members:
        welcome_text = (
            f"Добро пожаловать, {member.first_name}! 🎉\n\n"
            "Мы очень рады видеть тебя в нашем чате!\n"
            f"Не забудь подписаться на наши ресурсы:\n"
            f"🔹 ВКонтакте: {VK_LINK}\n"
            f"🔹 Telegram: {TG_LINK}\n\n"
            "Там мы проводим розыгрыши призов! 🚀"
        )
        await update.message.reply_text(welcome_text)

def main():
    app = Application.builder().token(TOKEN).build()
    
    # Обработчики команд
    app.add_handler(CommandHandler("start", start))
    
    # Приветствие новых участников
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members))
    
    # Запуск бота
    app.run_polling()

if __name__ == '__main__':
    main()
