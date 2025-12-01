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

# Negative marking rules
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


# ---------------- PERMISSION CHECK ----------------
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
        "🔹 Student commands:\n"
        "• /quiz short – 5 सवाल का छोटा क्विज़\n"
        "• /quiz full – बड़ा टेस्ट (max 25 सवाल)\n"
        "• /leaderboard – इस group का स्कोर\n\n"
        "🔹 Teacher/Admin commands:\n"
        "• /addq प्रश्न | A | B | C | D | सही (1-4) | व्याख्या\n"
        "• /bulkadd + कई /addq lines\n"
        "• /removeq <id>\n"
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


# ---------------- QUIZ START ----------------
def start_quiz(message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    if not is_admin(message):
        send_msg(chat_id, "केवल admin /quiz चला सकता है।")
        return

    mode = parse_quiz_mode(text)
    total_available = len(QUESTIONS)

    if total_available == 0:
        send_msg(chat_id, "अभी कोई सवाल मौजूद नहीं है। पहले /addq से सवाल जोड़ें।")
        return

    desired = 25 if mode == "full" else 5
    count = min(desired, total_available)

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
        f"🎯 Quiz शुरू!\nMode: {mode} | Questions: {count}\n"
        f"Time: {QUESTION_TIME}s | Correct: {MARK_CORRECT} | Wrong: {MARK_WRONG}\n"
        " आपका detailed result private chat में आएगा।"
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

    text = f"📝 सवाल {q_idx+1}/{len(order)} (⏱ {QUESTION_TIME}s)\n\n{q['question']}"

    send_msg(chat_id, text, reply_markup={"inline_keyboard": buttons})
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

    summary = (
        "⏰ समय समाप्त!\n"
        f"✅ सही उत्तर: {q['options'][q['correct']]}\n\n"
        f"ℹ️ व्याख्या:\n{q['explanation']}"
    )
    send_msg(chat_id, summary)

    st["q_index"] += 1

    if st["q_index"] < len(order):
        send_question(chat_id)
    else:
        send_msg(chat_id, "🎉 Quiz समाप्त! Leaderboard आ रहा है…")
        send_user_summaries(chat_id)
        send_leaderboard(chat_id)
        group_state.pop(chat_id, None)


# ---------------- ANSWER HANDLER ----------------
def handle_answer(cb):
    user = cb["from"]
    user_id = user["id"]
    chat_id = cb["message"]["chat"]["id"]
    data = cb.get("data")
    cb_id = cb["id"]

    st = group_state.get(chat_id)
    if not st:
        answer_callback(cb_id, "अभी कोई quiz active नहीं है।")
        return

    if time.time() - st["start"] > QUESTION_TIME:
        answer_callback(cb_id, "Time over!")
        finish_question(chat_id)
        return

    if user_id in st["answers"]:
        answer_callback(cb_id, "You already answered!")
        return

    selected = int(data.split("_")[1])

    q = QUESTIONS[st["order"][st["q_index"]]]
    correct = q["correct"]
    is_right = selected == correct

    stats = st["user_stats"].setdefault(user_id, {"correct": 0, "wrong": 0, "attempted": 0})
    stats["attempted"] += 1
    if is_right:
        stats["correct"] += 1
    else:
        stats["wrong"] += 1

    board = leaderboard.setdefault(chat_id, {})
    name = user.get("first_name", "") + " " + user.get("last_name", "")
    name = name.strip() or user.get("username") or str(user_id)

    udata = board.get(user_id, {"name": name, "score": 0})
    udata["score"] += MARK_CORRECT if is_right else MARK_WRONG
    board[user_id] = udata

    st["answers"][user_id] = True

    feedback = (
        f"सवाल: {q['question']}\n"
        f"आपका जवाब: {q['options'][selected]}\n"
        f"{'✔ सही' if is_right else '❌ गलत'}\n\n"
        f"व्याख्या:\n{q['explanation']}"
    )
    send_msg(user_id, feedback)
    answer_callback(cb_id, "जवाब दर्ज किया गया!")


# ---------------- SUMMARY + LEADERBOARD ----------------
def send_user_summaries(chat_id):
    st = group_state.get(chat_id)
    if not st:
        return

    stats = st["user_stats"]
    board = leaderboard.get(chat_id, {})
    total_q = len(st["order"])

    for uid, s in stats.items():
        correct = s["correct"]
        wrong = s["wrong"]
        attempted = s["attempted"]
        skipped = total_q - attempted
        score = board.get(uid, {}).get("score", 0.0)

        msg = (
            "📊 आपकी Summary:\n\n"
            f"कुल: {total_q}\n"
            f"सही: {correct}\n"
            f"गलत: {wrong}\n"
            f"छोड़े: {skipped}\n"
            f"Final Score: {score:.2f}"
        )
        send_msg(uid, msg)


def send_leaderboard(chat_id):
    board = leaderboard.get(chat_id, {})
    if not board:
        send_msg(chat_id, "अभी कोई स्कोर नहीं है।")
        return

    sorted_board = sorted(board.items(), key=lambda x: x[1]["score"], reverse=True)

    text = "🏆 *Leaderboard*\n\n"
    for rank, (uid, data) in enumerate(sorted_board, 1):
        text += f"{rank}. {data['name']} — {data['score']:.2f}\n"

    send_msg(chat_id, text, parse_mode="Markdown")


# ---------------- TEACHER COMMANDS ----------------

def handle_addq(message):
    if not teacher_allowed(message):
        send_msg(message["chat"]["id"], "आपको अनुमति नहीं है।")
        return

    text = message["text"][len("/addq"):].strip()
    parts = [p.strip() for p in text.split("|")]

    if len(parts) < 7:
        send_msg(message["chat"]["id"], "फॉर्मेट गलत है!")
        return

    q, A, B, C, D, corr, exp = parts[:7]

    corr = int(corr)
    if corr not in (1, 2, 3, 4):
        send_msg(message["chat"]["id"], "सही विकल्प 1-4 में होना चाहिए।")
        return

    QUESTIONS.append({
        "question": q,
        "options": [A, B, C, D],
        "correct": corr - 1,
        "explanation": exp,
    })

    send_msg(message["chat"]["id"], f"सवाल जोड़ दिया गया! (ID: {len(QUESTIONS)})")


def handle_bulkadd(message):
    if not teacher_allowed(message):
        send_msg(message["chat"]["id"], "अनुमति नहीं है।")
        return

    lines = message["text"].splitlines()[1:]
    added = 0

    for line in lines:
        if not line.strip():
            continue
        if line.startswith("/addq"):
            line = line[5:].strip()
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 7:
            continue
        q, A, B, C, D, corr, exp = parts[:7]
        corr = int(corr)
        if corr not in (1, 2, 3, 4):
            continue

        QUESTIONS.append({
            "question": q,
            "options": [A, B, C, D],
            "correct": corr - 1,
            "explanation": exp,
        })
        added += 1

    send_msg(message["chat"]["id"], f"{added} सवाल जोड़े गए।")


def handle_removeq(message):
    if not teacher_allowed(message):
        send_msg(message["chat"]["id"], "अनुमति नहीं है।")
        return

    parts = message["text"].split()
    if len(parts) < 2:
        send_msg(message["chat"]["id"], "Usage: /removeq <id>")
        return

    qid = int(parts[1]) - 1
    if qid < 0 or qid >= len(QUESTIONS):
        send_msg(message["chat"]["id"], "ID गलत है।")
        return

    removed = QUESTIONS.pop(qid)
    send_msg(message["chat"]["id"], f"सवाल हटाया गया: {removed['question']}")


def handle_resetboard(message):
    if not teacher_allowed(message):
        send_msg(message["chat"]["id"], "अनुमति नहीं है।")
        return

    leaderboard.pop(message["chat"]["id"], None)
    send_msg(message["chat"]["id"], "Leaderboard reset कर दिया गया।")


def handle_listq(message):
    if not teacher_allowed(message):
        send_msg(message["chat"]["id"], "अनुमति नहीं है।")
        return

    if not QUESTIONS:
        send_msg(message["chat"]["id"], "अभी कोई सवाल नहीं है।")
        return

    msg = ""
    for i, q in enumerate(QUESTIONS, start=1):
        msg += f"{i}. {q['question']}\n"
        if len(msg) > 3500:
            send_msg(message["chat"]["id"], msg)
            msg = ""

    if msg:
        send_msg(message["chat"]["id"], msg)


# ---------------- UPDATE DISPATCH ----------------
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
        log.exception("Webhook error: %s", e)
    return "ok"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
