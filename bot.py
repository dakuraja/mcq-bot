import os
import time
import requests
import logging
import random

from flask import Flask, request

# ---------------- CONFIG ----------------
BOT_TOKEN = os.environ["BOT_TOKEN"]
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

QUESTION_TIME = 45
MARK_CORRECT = 1.0
MARK_WRONG = -0.33

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("BOT")

# ---------------- QUESTIONS ----------------
QUESTIONS = [
    {
        "question": "1. मौर्य साम्राज्य की स्थापना किसने की?",
        "options": ["A) बिन्दुसार", "B) चंद्रगुप्त मौर्य", "C) अशोक", "D) पुष्यमित्र शुंग"],
        "correct": 1,
        "explanation": "चंद्रगुप्त मौर्य ने 322 ई.पू. में मौर्य साम्राज्य की स्थापना की।"
    },
]

# ---------------- GLOBAL STATE ----------------
group_state = {}
leaderboard = {}


# ---------------- BASIC TELEGRAM FUNCTIONS ----------------
def api_call(method, params=None):
    try:
        r = requests.get(f"{API_URL}/{method}", params=params, timeout=15)
        return r.json()
    except Exception as e:
        log.error("API error: %s", e)
        return None


def send_msg(chat_id, text, reply_markup=None, parse_mode=None):
    import json
    params = {"chat_id": chat_id, "text": text}
    if reply_markup:
        params["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    if parse_mode:
        params["parse_mode"] = parse_mode
    return api_call("sendMessage", params)


def answer_callback(cb_id, text=""):
    api_call("answerCallbackQuery", {"callback_query_id": cb_id, "text": text})


def get_chat_member(chat_id, user_id):
    data = api_call("getChatMember", {"chat_id": chat_id, "user_id": user_id})
    if data and data.get("ok"):
        return data["result"]
    return None


# ---------------- PERMISSIONS ----------------
def is_admin(message):
    chat_type = message["chat"]["type"]
    user = message["from"]

    if chat_type == "private":
        return True

    member = get_chat_member(message["chat"]["id"], user["id"])
    return member and member["status"] in ("administrator", "creator")


def teacher_allowed(message):
    chat_type = message["chat"]["type"]
    if chat_type == "private":
        return True
    return is_admin(message)


# ---------------- BASIC COMMANDS ----------------
def start_command(message):
    chat_id = message["chat"]["id"]
    text = (
        "नमस्ते! 👋\n"
        "मैं Mauryan Quiz Bot हूँ.\n\n"
        "Student Commands:\n"
        "• /quiz short – 5 सवाल\n"
        "• /quiz full – 25 सवाल\n"
        "• /leaderboard – group स्कोर\n\n"
        "Admin Commands:\n"
        "• /addq प्रश्न | A | B | C | D | सही | व्याख्या\n"
        "• /bulkadd\n"
        "• /removeq id\n"
        "• /resetboard\n"
        "• /listq\n"
    )
    send_msg(chat_id, text)


def parse_quiz_mode(text):
    parts = text.split()
    if len(parts) > 1:
        mode = parts[1].lower()
        if mode in ("short", "full"):
            return mode
    return "short"


# ---------------- QUIZ START/FLOW ----------------
def start_quiz(message):
    chat_id = message["chat"]["id"]

    if not is_admin(message):
        send_msg(chat_id, "केवल admin /quiz चला सकता है।")
        return

    mode = parse_quiz_mode(message.get("text", ""))
    total_available = len(QUESTIONS)

    if total_available == 0:
        send_msg(chat_id, "पहले /addq से सवाल जोड़ें।")
        return

    count = 25 if mode == "full" else 5
    count = min(count, total_available)

    order = list(range(total_available))
    random.shuffle(order)
    order = order[:count]

    group_state[chat_id] = {
        "order": order,
        "q_index": 0,
        "start": time.time(),
        "answers": {},
        "user_stats": {},
    }

    send_msg(
        chat_id,
        f"Quiz शुरू! ({count} सवाल)\n"
        f"समय: {QUESTION_TIME}s\n"
        f"Correct: {MARK_CORRECT}, Wrong: {MARK_WRONG}"
    )

    send_question(chat_id)


def send_question(chat_id):
    st = group_state.get(chat_id)
    if not st:
        return

    order = st["order"]
    q_idx = st["q_index"]

    if q_idx >= len(order):
        return

    q = QUESTIONS[order[q_idx]]

    buttons = [
        [{"text": opt, "callback_data": f"ans_{i}"}]
        for i, opt in enumerate(q["options"])
    ]
    markup = {"inline_keyboard": buttons}

    send_msg(
        chat_id,
        f"Q {q_idx+1}/{len(order)} (⏱ {QUESTION_TIME}s)\n\n{q['question']}",
        reply_markup=markup,
    )

    st["start"] = time.time()
    st["answers"] = {}


def timeout_check():
    now = time.time()
    for chat_id, st in list(group_state.items()):
        if now - st.get("start", now) >= QUESTION_TIME:
            finish_question(chat_id)


def finish_question(chat_id):
    st = group_state.get(chat_id)
    if not st:
        return

    order = st["order"]
    q_idx = st["q_index"]
    q = QUESTIONS[order[q_idx]]
    correct = q["correct"]

    send_msg(
        chat_id,
        f"⏰ समय समाप्त!\n"
        f"सही उत्तर: {q['options'][correct]}\n\n"
        f"{q['explanation']}"
    )

    st["q_index"] += 1

    if st["q_index"] < len(order):
        send_question(chat_id)
    else:
        send_msg(chat_id, "Quiz समाप्त! Summary भेजी जा रही है…")
        send_user_summaries(chat_id)
        send_leaderboard(chat_id)
        group_state.pop(chat_id, None)


# ---------------- ANSWERS ----------------
def handle_answer(cb):
    user = cb["from"]
    user_id = user["id"]
    chat_id = cb["message"]["chat"]["id"]
    cb_id = cb["id"]

    st = group_state.get(chat_id)
    if not st:
        answer_callback(cb_id, "कोई quiz चालू नहीं है।")
        return

    if time.time() - st["start"] > QUESTION_TIME:
        answer_callback(cb_id, "समय समाप्त!")
        finish_question(chat_id)
        return

    if user_id in st["answers"]:
        answer_callback(cb_id, "आप पहले जवाब दे चुके हैं।")
        return

    try:
        selected = int(cb["data"].split("_")[1])
    except:
        answer_callback(cb_id, "Error.")
        return

    order = st["order"]
    q_idx = st["q_index"]
    q = QUESTIONS[order[q_idx]]

    correct = q["correct"]
    is_right = selected == correct

    stats = st["user_stats"].setdefault(user_id, {"correct": 0, "wrong": 0, "attempted": 0})
    stats["attempted"] += 1
    stats["correct" if is_right else "wrong"] += 1

    board = leaderboard.setdefault(chat_id, {})
    name = (user.get("first_name") or "") + " " + (user.get("last_name") or "")
    name = name.strip() or user.get("username") or str(user_id)

    prev = board.get(user_id, {"name": name, "score": 0.0})
    prev["score"] += MARK_CORRECT if is_right else MARK_WRONG
    prev["name"] = name
    board[user_id] = prev

    st["answers"][user_id] = True

    send_msg(
        user_id,
        f"सवाल: {q['question']}\n"
        f"आपका जवाब: {q['options'][selected]}\n"
        f"{'✔ सही' if is_right else '❌ गलत'}\n\n"
        f"{q['explanation']}"
    )

    answer_callback(cb_id, "जवाब दर्ज हुआ।")


# ---------------- SUMMARY & LEADERBOARD ----------------
def send_user_summaries(chat_id):
    st = group_state.get(chat_id)
    if not st:
        return

    stats = st["user_stats"]
    total_q = len(st["order"])
    board = leaderboard.get(chat_id, {})

    for uid, u in stats.items():
        summary = (
            f"📊 आपका Summary\n\n"
            f"कुल प्रश्न: {total_q}\n"
            f"सही: {u['correct']}\n"
            f"गलत: {u['wrong']}\n"
            f"स्कोर: {board.get(uid, {}).get('score', 0):.2f}"
        )
        send_msg(uid, summary)


def send_leaderboard(chat_id):
    board = leaderboard.get(chat_id, {})
    if not board:
        send_msg(chat_id, "कोई स्कोर नहीं मिला।")
        return

    sorted_board = sorted(board.items(), key=lambda x: x[1]["score"], reverse=True)

    text = "🏆 Leaderboard\n\n"
    for i, (uid, data) in enumerate(sorted_board, 1):
        text += f"{i}. {data['name']} — {data['score']:.2f}\n"

    send_msg(chat_id, text)


# ---------------- UPDATE HANDLER ----------------
def process_update(upd):
    timeout_check()

    if "message" in upd:
        msg = upd["message"]
        text = msg.get("text", "")

        if text.startswith("/start"):
            start_command(msg)
        elif text.startswith("/quiz"):
            start_quiz(msg)
        elif text.startswith("/leaderboard"):
            send_leaderboard(msg["chat"]["id"])
        elif text.startswith("/addq"):
            handle_addq(msg)
        elif text.startswith("/bulkadd"):
            handle_bulkadd(msg)
        elif text.startswith("/removeq"):
            handle_removeq(msg)
        elif text.startswith("/resetboard"):
            handle_resetboard(msg)
        elif text.startswith("/listq"):
            handle_listq(msg)

    if "callback_query" in upd:
        handle_answer(upd["callback_query"])


# ---------------- FLASK APP ----------------
app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    return "Mauryan Quiz Bot is running."


@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    try:
        upd = request.get_json(force=True, silent=True) or {}
        process_update(upd)
    except Exception as e:
        log.exception("Error: %s", e)
    return "ok"


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
