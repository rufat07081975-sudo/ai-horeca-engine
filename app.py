import os
import time
from flask import Flask, request, jsonify
import google.generativeai as genai
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# 1. Инициализация веб-сервера и Telegram-бота
app = Flask(__name__)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TOKEN) if TOKEN else None

client_sessions = {}
order_counters = {} 

@app.route('/', methods=['GET'])
def home():
    return "AI_HoReCa_Tech Engine is Running Sub-Partner Network Active!", 200

# 2. Имитация вебхука входящих сообщений WhatsApp
@app.route('/whatsapp/webhook', methods=['POST'])
def whatsapp_webhook():
    data = request.json
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
    )
    if config["flag_delivery"]:
        system_instruction += "У нас доступна ДОСТАВКА. Если клиент хочет доставку, вежливо спроси его адрес и имя.\n"
    if config["flag_tara"]:
        system_instruction += f"Мы можем упаковать еду с собой. Пластиковая тара стоит {config['price_tara']}.\n"
    
    system_instruction += "Когда клиент четко определился с заказом, сформируй финальный список в формате: 'ЗАКАЗ: [список блюд], ИТОГО: [сумма]'."

    client_sessions[phone].append(f"Клиент: {message}")
    prompt = system_instruction + "\n" + "\n".join(client_sessions[phone])
    
    try:
        response = model.generate_content(prompt)
        ai_reply = response.text
        client_sessions[phone].append(f"ИИ: {ai_reply}")
    except Exception as e:
        ai_reply = "Salam! Извините, технический сбой, повторите через минуту."

    if "ЗАКАЗ:" in ai_reply:
        send_order_to_kitchen(restaurant_id, phone, ai_reply, config, table_num)

    return jsonify({"status": "success", "reply": ai_reply})

def send_order_to_kitchen(restaurant_id, phone, order_text, config, table_num):
    if not bot:
        return
    chat_id = config["tg_kitchen"]
    
    if config["mode"] == "queue":
        if restaurant_id not in order_counters:
            order_counters[restaurant_id] = 40 
        order_counters[restaurant_id] += 1
        current_num = order_counters[restaurant_id]
        
        msg_text = f"📦 **НОВЫЙ ЗАКАЗ В ОЧЕРЕДЬ (№{current_num})**\n\nКлиент: {phone}\n{order_text}"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(text=f"✅ Заказ №{current_num} Готов", callback_data=f"ready_{current_num}_{phone}"))
        bot.send_message(chat_id, msg_text, reply_markup=markup)
    else:
        msg_text = f"🍽️ **ЗАКАЗ ЗА СТОЛ №{table_num}**\n\nКлиент: {phone}\n{order_text}"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(text="💵 Разделить чек на компанию", callback_data=f"split_{table_num}"))
        markup.add(InlineKeyboardButton(text="🥡 Требуется пластиковая тара", callback_data=f"tara_{table_num}"))
        markup.add(InlineKeyboardButton(text="❌ Закрыть стол / Оплачено", callback_data=f"close_{table_num}"))
        bot.send_message(chat_id, msg_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_kitchen_buttons(call):
    data = call.data
    if data.startswith("ready_"):
        _, order_num, client_phone = data.split("_")
        bot.answer_callback_query(call.id, text=f"Заказ №{order_num} закрыт!")
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                              text=f"✅ **Заказ №{order_num} ВЫДАН**\nУведомление клиенту отправлено.")
    elif data.startswith("tara_"):
        table = data.split("_")[1]
        bot.answer_callback_query(call.id, text="Уведомление: Тара будет собрана.")
        bot.send_message(call.message.chat.id, f"🥡 Повару отправлен сигнал: Собрать пластиковую тару для стола №{table}")

if __name__ == "__main__":
    if bot:
        import threading
        threading.Thread(target=bot.infinity_polling, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
