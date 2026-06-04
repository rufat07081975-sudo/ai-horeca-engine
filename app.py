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
    print("Получен запрос от Green-API:", data) # Это будет видно в логах Render
    
    # Извлекаем данные из структуры Green-API
    # Обратите внимание: Green-API часто шлет данные внутри ключа 'messageData'
    try:
        sender = data.get("senderData", {}).get("sender", "")
        message_text = data.get("messageData", {}).get("textMessageData", {}).get("textMessage", "")
        phone = sender.split("@")[0]
        
        # Если это не текстовое сообщение, игнорируем
        if not message_text:
            return jsonify({"status": "ignored"}), 200
    except Exception as e:
        return jsonify({"status": "error", "details": str(e)}), 400

    # Ваши настройки
    restaurant_id = "mangal_01" 
    qr_context = "hall"
    table_num = "1" 
    
    restaurant_settings = {
        "mangal_01": {
            "name": "Ресторан Мангал Гянджа",
            "gemini_key": os.environ.get("GEMINI_API_KEY"),
            "tg_kitchen": os.environ.get("TG_KITCHEN_CHAT_ID"),
            "mode": qr_context
        }
    }
    
    config = restaurant_settings.get(restaurant_id, {})
    genai.configure(api_key=config["gemini_key"])
    model = genai.GenerativeModel('gemini-1.5-flash')

    if phone not in client_sessions:
        client_sessions[phone] = []

    system_instruction = (
        f"Ты — умный ИИ-официант ресторана '{config['name']}'. Отвечай вежливо. "
        "Когда клиент определился, сформируй список в формате: 'ЗАКАЗ: [список], ИТОГО: [число]'."
    )

    client_sessions[phone].append(f"Клиент: {message_text}")
    prompt = system_instruction + "\n" + "\n".join(client_sessions[phone][-5:])
    
    try:
        response = model.generate_content(prompt)
        ai_reply = response.text
        client_sessions[phone].append(f"ИИ: {ai_reply}")
    except:
        ai_reply = "Извините, технический сбой."

    if "ЗАКАЗ:" in ai_reply:
        active_orders_timers[phone] = {"start_time": time.time(), "raw_reply": ai_reply}
        send_order_to_kitchen(restaurant_id, phone, ai_reply, config, table_num)

    return jsonify({"status": "success", "reply": ai_reply})

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
