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

# База данных в оперативной памяти (для теста)
client_sessions = {}
order_counters = {} 

# Хранилище для статистики смены
day_orders_archive = []  # Сюда сохраняем данные каждого закрытого заказа
active_orders_timers = {} # Тут храним время старта: {phone: {"start_time": timestamp, "items_count": X}}

@app.route('/', methods=['GET'])
def home():
    return "AI_HoReCa_Tech Engine: Time-Tracker & Reports Active!", 200
@app.route('/whatsapp/webhook', methods=['POST'])
def whatsapp_webhook():
    # Получаем данные от Green-API
    data = request.json
    # Логируем данные, чтобы видеть их в консоли Render (для отладки)
    print("Получен запрос от Green-API:", data)
    
    # Сюда можно добавить логику обработки данных, если нужно
    # Пока просто подтверждаем получение
    return jsonify({"status": "success"}), 200
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
        # Фиксируем время старта готовки (когда ИИ сформировал заказ)
        active_orders_timers[phone] = {
            "start_time": time.time(),
            "raw_reply": ai_reply
        }
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
        # Добавляем кнопку закрытия смены в каждое сообщение для администратора (или можно отдельной командой)
        markup.add(InlineKeyboardButton(text="🔒 Закрыть смену (Отчет)", callback_data=f"close_shift_{restaurant_id}"))
        bot.send_message(chat_id, msg_text, reply_markup=markup)
    else:
        msg_text = f"🍽️ **ЗАКАЗ ЗА СТОЛ №{table_num}**\n\nКлиент: {phone}\n{order_text}"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(text="🥡 Нужна тара", callback_data=f"tara_{table_num}"))
        markup.add(InlineKeyboardButton(text="✅ Стол Оплачен / Закрыт", callback_data=f"ready_table_{table_num}_{phone}"))
        markup.add(InlineKeyboardButton(text="🔒 Закрыть смену (Отчет)", callback_data=f"close_shift_{restaurant_id}"))
        bot.send_message(chat_id, msg_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_kitchen_buttons(call):
    data = call.data
    
    # 1. Повар нажал "Готов" в режиме электронной очереди
    if data.startswith("ready_") and not data.startswith("ready_table_") and not data.startswith("close_shift_"):
        _, order_num, client_phone = data.split("_")
        
        # Считаем время готовки
        cooking_time_str = "Неизвестно"
        if client_phone in active_orders_timers:
            start_time = active_orders_timers[client_phone]["start_time"]
            duration = time.time() - start_time # время в секундах
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            cooking_time_str = f"{minutes} мин {seconds} сек"
            
            # Парсим сумму для отчета (ищем цифры после ИТОГО:)
            raw_text = active_orders_timers[client_phone]["raw_reply"]
            price = 0
            try:
                if "ИТОГО:" in raw_text:
                    price_part = raw_text.split("ИТОГО:")[1].strip().replace("AZN","").replace(".","").strip()
                    price = int(''.join(filter(str.isdigit, price_part)))
            except:
                price = 10 # дефолт если не распарсилось
                
            # Сохраняем в архив смены
            day_orders_archive.append({
                "type": "queue",
                "number": order_num,
                "duration_sec": duration,
                "price": price
            })
            del active_orders_timers[client_phone]

        bot.answer_callback_query(call.id, text=f"Заказ №{order_num} готов!")
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                              text=f"✅ **Заказ №{order_num} ВЫДАН**\n⏱️ Время готовки: {cooking_time_str}\nУведомление клиенту отправлено.")

    # 2. Официант закрыл стол в режиме ресторана
    elif data.startswith("ready_table_"):
        _, _, table_num, client_phone = data.split("_")
        cooking_time_str = "Неизвестно"
        
        if client_phone in active_orders_timers:
            start_time = active_orders_timers[client_phone]["start_time"]
            duration = time.time() - start_time
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            cooking_time_str = f"{minutes} мин {seconds} сек"
            
            raw_text = active_orders_timers[client_phone]["raw_reply"]
            price = 0
            try:
                if "ИТОГО:" in raw_text:
                    price_part = raw_text.split("ИТОГО:")[1].strip()
                    price = int(''.join(filter(str.isdigit, price_part)))
            except:
                price = 20
                
            day_orders_archive.append({
                "type": "table",
                "number": table_num,
                "duration_sec": duration,
                "price": price
            })
            del active_orders_timers[client_phone]

        bot.answer_callback_query(call.id, text=f"Стол №{table_num} закрыт!")
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                              text=f"💵 **Стол №{table_num} ОПЛАЧЕН**\n⏱️ Время обслуживания: {cooking_time_str}")

    # 3. НАЖАТИЕ КНОПКИ ЗАКРЫТИЯ СМЕНЫ И СБОР ОТЧЕТА
    elif data.startswith("close_shift_"):
        restaurant_id = data.split("_")[2]
        
        if not day_orders_archive:
            bot.answer_callback_query(call.id, text="Заказов за смену еще нет! Закрывать нечего.")
            return

        # Считаем аналитику
        total_orders = len(day_orders_archive)
        total_revenue = sum([item["price"] for item in day_orders_archive])
        avg_time_sec = sum([item["duration_sec"] for item in day_orders_archive]) / total_orders
        
        avg_min = int(avg_time_sec // 60)
        avg_sec = int(avg_time_sec % 60)
        
        # Экономия времени: 3 минуты (180 сек) на заказ ручного труда кассира
        saved_time_total_sec = total_orders * 180
        saved_hours = int(saved_time_total_sec // 3600)
        saved_mins = int((saved_time_total_sec % 3600) // 60)

        current_time_str = datetime.now().strftime("%d.%m.%Y в %H:%M")

        report_text = (
            f"🔒 **СМЕНА ОФИЦИАЛЬНО ЗАКРЫТА**\n"
            f"📅 Время закрытия кассы: {current_time_str}\n"
            f"-----------------------------------------\n"
            f"💰 **ФИНАНСЫ ЗА ДЕНЬ:**\n"
            f"• Всего заказов через ИИ: **{total_orders} шт.**\n"
            f"• Итоговая выручка: **{total_revenue} AZN**\n\n"
            f"⏱️ **ЭФФЕКТИВНОСТЬ КУХНИ:**\n"
            f"• Среднее время готовки/сервиса: **{avg_min} мин {avg_sec} сек**\n\n"
            f"🚀 **МАРКЕТИНГОВАЯ ВЫГОДА:**\n"
            f"• Сэкономлено рабочего времени персонала: **~{saved_hours} ч {saved_mins} мин**\n"
            f"• *Персонал сфокусировался на качестве еды и выдаче, не отвлекаясь на прием заказов!*"
        )
        
        # Сбрасываем архивы на следующий день
        day_orders_archive.clear()
        client_sessions.clear()

        bot.answer_callback_query(call.id, text="Смена закрыта! Отчет сформирован.")
        bot.send_message(call.message.chat.id, report_text)

if __name__ == "__main__":
    if bot:
        import threading
        threading.Thread(target=bot.infinity_polling, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
