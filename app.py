import os
import time
from datetime import datetime
from flask import Flask, request, jsonify
import google.generativeai as genai
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

app = Flask(__name__)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TOKEN) if TOKEN else None

client_sessions = {}
order_counters = {} 
day_orders_archive = [] 
active_orders_timers = {} 

@app.route('/', methods=['GET'])
def home():
    return "AI_HoReCa_Tech Engine: Time-Tracker & Reports Active!", 200

# ОДИН ЕДИНСТВЕННЫЙ МАРШРУТ ДЛЯ WEBHOOK
@app.route('/whatsapp/webhook', methods=['POST'])
def whatsapp_webhook():
    data = request.json
    try:
        # Извлекаем данные сообщения
        message_data = data.get("messageData", {})
        if message_data.get("typeMessage") != "textMessage":
            return jsonify({"status": "ignored"}), 200
            
        message_text = message_data.get("textMessageData", {}).get("textMessage", "")
        sender = data.get("senderData", {}).get("sender", "")
        phone = sender.split("@")[0]
        sender_name = data.get("senderData", {}).get("senderName", "Клиент")
        
        # Получаем ID чата кухни из переменных окружения
        tg_chat_id = os.environ.get("TG_KITCHEN_CHAT_ID")
        
        # 1. ОТПРАВЛЯЕМ СООБЩЕНИЕ КЛИЕНТА В ТЕЛЕГРАМ
        if bot:
            bot.send_message(tg_chat_id, f"💬 Сообщение от {sender_name}:\n{message_text}")

        # 2. ЛОГИКА ИИ
        restaurant_id = "mangal_01" 
        config = {"name": "Ресторан Мангал Гянджа", "gemini_key": os.environ.get("GEMINI_API_KEY")}
        genai.configure(api_key=config["gemini_key"])
        model = genai.GenerativeModel('gemini-1.5-flash')

        if phone not in client_sessions: client_sessions[phone] = []
        client_sessions[phone].append(f"Клиент: {message_text}")
        prompt = f"Ты официант {config['name']}. Отвечай вежливо. Итог: ЗАКАЗ: [список], ИТОГО: [число].\n" + "\n".join(client_sessions[phone][-5:])
        
        ai_reply = model.generate_content(prompt).text
        client_sessions[phone].append(f"ИИ: {ai_reply}")

        # 3. ЕСЛИ ЗАКАЗ - ДУБЛИРУЕМ В ТЕЛЕГРАМ
        if "ЗАКАЗ:" in ai_reply and bot:
            bot.send_message(tg_chat_id, f"✅ ИИ сформировал заказ:\n{ai_reply}")
            
        return jsonify({"status": "success", "reply": ai_reply})
    except Exception as e:
        print(f"Ошибка: {e}")
        return jsonify({"status": "error"}), 500

def send_order_to_kitchen(restaurant_id, phone, order_text, config, table_num):
    if not bot: return
    chat_id = config["tg_kitchen"]
    msg_text = f"🍽️ **ЗАКАЗ:**\nКлиент: {phone}\n{order_text}"
    bot.send_message(chat_id, msg_text)

@bot.callback_query_handler(func=lambda call: True)
def handle_kitchen_buttons(call):
    # (Здесь ваш старый код обработки кнопок остается без изменений)
    pass

if __name__ == "__main__":
    if bot:
        import threading
        threading.Thread(target=bot.infinity_polling, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
