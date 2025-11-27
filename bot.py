import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ---------- CONFIG ----------
BOT_TOKEN = "7688080597:AAGdZu38mxpqbBH3fWx_c3hspdPwjiiZKug"   # अपना असली Token डालें


# ---------- QUESTIONS LIST ----------
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
        "explanation": "बुद्ध का जन्म लुंबिनी (आधुनिक नेपाल) में हुआ था।"
    },

    {
        "question": "बुद्ध को ज्ञान कहाँ प्राप्त हुआ था?",
        "options": ["सारनाथ", "लुंबिनी", "बोधगया", "कुशीनगर"],
        "correct_index": 2,
        "explanation": "बुद्ध को ज्ञान बोधगया में बोधि वृक्ष के नीचे प्राप्त हुआ।"
    },

    # -------- बाकी सारे QUESTIONS उसी तरह कॉपी करो ----------
    # पूरा questions block तुमने जो भेजा है, उसे यहीं पेस्ट कर दो।
    # कोड बिल्कुल वैसे ही चलेगा।
]


# ---------- LOGGING ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------- SEND QUESTION ----------
async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE, q_index: int):
    question_data = QUESTIONS[q_index]
    context.user_data["q_index"] = q_index

    buttons = [
        [InlineKeyboardButton(text=opt, callback_data=f"answer_{i}")]
        for i, opt in enumerate(question_data["options"])
    ]

    markup = InlineKeyboardMarkup(buttons)

    text = f"Q{q_index + 1}: {question_data['question']}"

    if update.callback_query:
        await update.callback_query.message.reply_text(text=text, reply_markup=markup)
    else:
        await update.message.reply_text(text=text, reply_markup=markup)


# ---------- /start COMMAND ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["score"] = 0
    context.user_data["q_index"] = 0

    await update.message.reply_text(
        "नमस्ते! 👋\nमैं MCQ Quiz Bot हूँ.\n"
        "हर सवाल के सही विकल्प पर क्लिक करें।\nचलते हैं शुरू करते हैं!"
    )

    await send_question(update, context, 0)


# ---------- HANDLE ANSWER ----------
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected = int(query.data.split("_")[1])
    q_index = context.user_data.get("q_index", 0)

    question = QUESTIONS[q_index]
    correct = question["correct_index"]

    # सही/गलत चेक करें
    if selected == correct:
        context.user_data["score"] += 1
        feedback = "✅ सही जवाब!"
    else:
        feedback = f"❌ गलत.\nसही जवाब: {question['options'][correct]}"

    await query.message.reply_text(feedback)

    # व्याख्या भी भेजें
    explanation = question.get("explanation")
    if explanation:
        await query.message.reply_text(f"ℹ️ व्याख्या:\n{explanation}")

    # अगला प्रश्न
    next_q = q_index + 1
    if next_q < len(QUESTIONS):
        await send_question(update, context, next_q)
    else:
        score = context.user_data["score"]
        total = len(QUESTIONS)

        await query.message.reply_text(
            f"🎉 क्विज़ समाप्त!\n\nआपका स्कोर: {score}/{total}\n"
            "फिर से शुरू करने के लिए /start भेजें।"
        )
        context.user_data.clear()


# ---------- MAIN ----------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern=r"^answer_"))

    app.run_polling()


if __name__ == "__main__":
    main()
