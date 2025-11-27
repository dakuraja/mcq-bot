import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ---------- CONFIG ----------
BOT_TOKEN = "XYZ"   # yahan apna asli token daalna hai

QUESTIONS = [
    {
        "question": "बौद्ध धर्म के संस्थापक कौन थे?",
        "options": ["महावीर", "बुद्ध", "मख्खलि गोसाल", "पाणिनि"],
        "correct_index": 1,
        "explanation": "बौद्ध धर्म की स्थापना सिद्धार्थ गौतम (बुद्ध) ने की थी, जिन्होंने बौद्ध मत के मूल सिद्धांत दिए।"
    },
    {
        "question": "बुद्ध का जन्म किस स्थान पर हुआ था?",
        "options": ["वैशाली", "लुंबिनी", "कुशीनगर", "श्रावस्ती"],
        "correct_index": 1,
        "explanation": "बुद्ध का जन्म लुंबिनी (आधुनिक नेपाल) में हुआ था। इसे 'लुम्बिनी वन' भी कहा जाता था।"
    },
    # ... बाकी सारे questions वैसे ही रहने दो ...
    # आखिरी वाला question यहाँ तक
    {
        "question": "बुद्ध का मुख्य ध्येय क्या था?",
        "options": ["शक्ति", "भोग-विलास", "दुखों से मुक्ति", "धन"],
        "correct_index": 2,
        "explanation": "बुद्ध का ध्येय मनुष्य को दुख, तृष्णा और मोह से मुक्त कर निर्वाण की ओर ले जाना था।"
    }
]

# ---------- LOGGING ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------- HELPER: SEND ONE QUESTION ----------
async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE, q_index: int):
    question_data = QUESTIONS[q_index]

    context.user_data["q_index"] = q_index

    buttons = []
    for i, option in enumerate(question_data["options"]):
        buttons.append(
            [InlineKeyboardButton(text=option, callback_data=f"answer_{i}")]
        )

    reply_markup = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        await update.callback_query.message.reply_text(
            text=f"Q{q_index + 1}: {question_data['question']}",
            reply_markup=reply_markup,
        )
    else:
        await update.message.reply_text(
            text=f"Q{q_index + 1}: {question_data['question']}",
            reply_markup=reply_markup,
        )


# ---------- /start COMMAND ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["score"] = 0
    await update.message.reply_text(
        "नमस्ते! 👋\nमैं MCQ Quiz Bot हूँ.\n\n"
        "हर सवाल का सही विकल्प चुनिए.\n"
        "शुरू करते हैं!"
    )
    await send_question(update, context, q_index=0)


# ---------- HANDLE ANSWERS (एक ही बार, explanation सहित) ----------
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_index = int(query.data.split("_")[1])

    q_index = context.user_data.get("q_index", 0)
    question_data = QUESTIONS[q_index]
    correct_index = question_data["correct_index"]

    # सही / गलत check
    if selected_index == correct_index:
        context.user_data["score"] = context.user_data.get("score", 0) + 1
        feedback = "✅ सही जवाब!"
    else:
        correct_text = question_data["options"][correct_index]
        feedback = f"❌ गलत.\nसही जवाब: {correct_text}"

    # Feedback भेजो
    await query.message.reply_text(feedback)

    # Explanation भेजो
    explanation = question_data.get("explanation")
    if explanation:
        await query.message.reply_text(f"ℹ️ व्याख्या:\n{explanation}")

    # अगला सवाल या क्विज़ खत्म
    next_q = q_index + 1
    if next_q < len(QUESTIONS):
        await send_question(update, context, q_index=next_q)
    else:
        score = context.user_data.get("score", 0)
        total = len(QUESTIONS)
        await query.message.reply_text(
            f"क्विज़ समाप्त! 🎉\nआपका स्कोर: {score}/{total}\n"
            "फिर से शुरू करने के लिए /start टाइप करें."
        )


# ---------- MAIN FUNCTION ----------
def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_answer, pattern=r"^answer_"))

    application.run_polling()


if __name__ == "__main__":
    main()
