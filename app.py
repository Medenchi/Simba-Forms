import telebot
from flask import Flask, request
import sqlite3
import matplotlib.pyplot as plt
import os
import random
import string
import config

# База данных
conn = sqlite3.connect('database.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS responses (
        user_id INTEGER,
        username TEXT,
        question_number INTEGER,
        answer TEXT
    )
''')
conn.commit()

bot = telebot.TeleBot(config.BOT_TOKEN)
app = Flask(__name__)

# Вопросы
questions = [
    "Как вам интерфейс?",
    "Удобно ли было пользоваться?",
    "Что можно улучшить?",
    "Оцените скорость работы",
    "Нравится ли вам дизайн?",
    "Есть ли баги?",
    "Как часто вы будете использовать это приложение?",
    "Что бы вы добавили?",
    "Ваш возраст?",
    "Другие комментарии?"
]

user_states = {}  # Хранение прогресса пользователя

# --- Команды ---
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    user_states[user_id] = 0
    bot.send_message(user_id, "Привет! Мы начинаем опрос. Готовы?")
    ask_question(message.from_user)

@bot.message_handler(commands=['analytics'])
def analytics(message):
    if message.chat.id != config.ADMIN_CHAT_ID:
        bot.reply_to(message, "Вы не администратор.")
        return

    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM responses")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM responses")
    total_answers = cursor.fetchone()[0]

    question_stats = []
    for i in range(1, len(questions)+1):
        cursor.execute("SELECT COUNT(*) FROM responses WHERE question_number=?", (i,))
        count = cursor.fetchone()[0]
        question_stats.append((i, questions[i-1], count))

    text = f"📊 Аналитика:\n\nПользователей прошло опрос: {total_users}\nВсего ответов: {total_answers}\n\nОтветы по вопросам:\n"
    for i, q, count in question_stats:
        text += f"{i}. {q} — {count} {'ответ' if count % 10 == 1 and count != 11 else 'ответа' if count % 10 in [2,3,4] and count not in [12,13,14] else 'ответов'}\n"

    bot.send_message(config.ADMIN_CHAT_ID, text)
    generate_and_send_charts(bot, config.ADMIN_CHAT_ID, question_stats)

# --- Логика опроса ---
@bot.message_handler(func=lambda message: message.from_user.id in user_states)
def handle_answer(message):
    user = message.from_user
    user_id = user.id
    answer = message.text

    current_q = user_states[user_id]

    if current_q < len(questions):
        save_answer(user, current_q, answer)
        user_states[user_id] += 1
        ask_question(user)
    else:
        bot.send_message(user_id, "Спасибо за прохождение опроса!")
        send_to_group(user)
        del user_states[user_id]

def ask_question(user):
    q_index = user_states[user.id]
    if q_index < len(questions):
        bot.send_message(user.id, questions[q_index])
    else:
        bot.send_message(user.id, "Спасибо!")

def save_answer(user, q_index, answer):
    cursor.execute(
        "INSERT INTO responses (user_id, username, question_number, answer) VALUES (?, ?, ?, ?)",
        (user.id, user.username, q_index + 1, answer)
    )
    conn.commit()

def send_to_group(user):
    cursor.execute("SELECT * FROM responses WHERE user_id=?", (user.id,))
    answers = cursor.fetchall()
    text = f"👤 Ответы пользователя @{user.username} ({user.id}):\n\n"
    for row in answers:
        text += f"{row[2]}. {row[3]}\n"
    bot.send_message(config.ADMIN_CHAT_ID, text)

# --- Генерация графиков ---
def generate_chart(question_num, question_text, answer_count):
    plt.figure(figsize=(6, 3))
    plt.bar(['Ответы'], [answer_count], color='skyblue')
    plt.title(f"Вопрос {question_num}: {question_text[:30]}...")
    plt.ylabel("Количество")
    plt.tight_layout()
    filename = ''.join(random.choices(string.ascii_lowercase, k=10)) + ".png"
    plt.savefig(filename)
    plt.close()
    return filename

def generate_and_send_charts(bot, chat_id, stats):
    for i, q, count in stats:
        file_path = generate_chart(i, q, count)
        with open(file_path, 'rb') as photo:
            bot.send_photo(chat_id, photo, caption=f"Вопрос {i}: {q}")
        os.remove(file_path)

# --- Вебхук ---
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('X-Telegram-Bot-Api-Secret-Token') == config.SECRET_TOKEN:
        update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
        bot.process_new_updates([update])
        return '', 200
    else:
        return 'Forbidden', 403

@app.route('/')
def index():
    return "Бот работает!"

if __name__ == '__main__':
    from waitress import serve
    bot.remove_webhook()
    bot.set_webhook(url=config.WEBHOOK_URL, secret_token=config.SECRET_TOKEN)
    print("Запуск сервера...")
    serve(app, host='0.0.0.0', port=config.PORT)
