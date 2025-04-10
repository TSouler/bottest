from telegram.ext import Updater, MessageHandler, Filters
from dotenv import load_dotenv
import os
import logging
from datetime import datetime

load_dotenv()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def get_greeting():
    hour = datetime.now().hour
    if 5 <= hour < 12: return "Доброе утро"
    elif 12 <= hour < 18: return "Добрый день"
    elif 18 <= hour < 23: return "Добрый вечер"
    else: return "Доброй ночи"

def welcome(update, context):
    for member in update.message.new_chat_members:
        greeting = f"{get_greeting()}, {member.mention_markdown()}!"
        message = f"""{greeting} 🎉

Добро пожаловать в наш канал!

📢 Присоединяйтесь к нашим сообществам:
- Telegram: {os.getenv('https://t.me/+n6v4XX-xFig5NDcy')}
- ВКонтакте: {os.getenv('https://vk.com/sevgarant')}

🎁 У нас регулярно проходят розыгрыши и конкурсы!"""
        
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=message,
            parse_mode='Markdown'
        )

def main():
    updater = Updater(os.getenv('7826072060:AAHKGnuJo-jq4tah7Le5q04rHwvFJv9h_iw'), use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.status_update.new_chat_members, welcome))
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()