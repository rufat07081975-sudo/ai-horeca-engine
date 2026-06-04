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

# ЕДИНСТВЕННЫЙ И ПРАВИЛЬНЫЙ МАРШРУТ
@app.route('/whatsapp/webhook', methods=['POST'])
def whatsapp_webhook():
    data = request.json
    print("Получен запрос от Green-API:", data)
    
    phone = data.get("phone")        
    message = data.get("message")   
    qr_context = data.get("context", "hall") 
    table_num = data.get("table", "0")        
    restaurant_id = data.get("restaurant_id") 
    
    restaurant_settings = {
        "mangal_01": {
            "name": "Ресторан Мангал Гянджа",
            "gemini_key": os.environ.get("GEMINI_API_KEY"),
            "tg_kitchen": os.environ.get("TG_KITCHEN_CHAT_ID"),
            "flag_delivery": True,
            "flag_tara": True,
            "price_tara": "0.50 AZN",
            "mode": qr_context
        }
    }
    
    config = restaurant_settings.get(restaurant_id, {})
    if not config:
        return jsonify({"status": "error", "message": "Restaurant not found"}), 404

    genai.configure(api_key=config["gemini_key"])
    model = genai.GenerativeModel('gemini-1.5-flash')

    if phone not in client_sessions:
        client_sessions[phone] = []

    system_instruction = (
        f"Ты — умный ИИ-официант ресторана '{config['name']}'. Отвечай вежливо, кратко, на языке клиента.\n"
        f"Текущий режим работы: {config['mode']}. Стол клиента: {table_num}.\n"
        "Когда клиент четко определился с заказом, сформируй финальный список в формате: 'ЗАКАЗ: [список блюд], ИТОГО: [сумма без букв, только число, например 25]'."
    )

    client_sessions[phone].append(f"Клиент: {message}")
    prompt = system_instruction + "\n" + "\n".join(client_sessions[phone])
    
    try:
        response = model.generate_content(prompt)
        ai_reply = response.text
        client_sessions[phone].append(f"ИИ: {ai_reply}")
    except Exception as e:
        ai_reply = "Salam! Извините, технический сбой, повторите через минуту."

    if "ЗАКАЗ:" in ai_reply:
        active_orders_timers[phone] = {
            "start_time": time.time(),
            "raw_reply": ai_reply
        }
        send_order_to_kitchen(restaurant_id, phone, ai_reply, config, table_num)

    return jsonify({"status": "success", "reply": ai_reply})

# ... (далее функции send_order_to_kitchen и handle_kitchen_buttons как были у вас) ...
# ОСТАВЬТЕ ВСЁ ОСТАЛЬНОЕ БЕЗ ИЗМЕНЕНИЙ ДО САМОГО КОНЦА ФАЙЛА
