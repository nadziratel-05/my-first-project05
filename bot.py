import os
import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
DB_PATH = "reactions.sqlite3"

# --- База данных ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS reactions (
            chat_id INTEGER,
            message_id INTEGER,
            user_id INTEGER,
            user_name TEXT,
            emoji TEXT,
            PRIMARY KEY (chat_id, message_id, user_id)
        )
        """)
        await db.commit()

# --- Эмодзи ---
emojis = ["😂", "❤️", "🔥", "😢", "👍", "👎"]

def build_keyboard(counts):
    buttons = []
    for e in emojis:
        text = f"{e} {counts.get(e, 0)}" if counts.get(e, 0) > 0 else e
        buttons.append(InlineKeyboardButton(text=text, callback_data=f"react:{e}"))
    rows = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(inline_keyboard=rows)

# --- Добавление под постами ---
@dp.channel_post(F.content_type.in_({"text", "photo", "video", "document"}))
async def add_reactions(msg: types.Message):
    keyboard = build_keyboard({})
    await msg.edit_reply_markup(reply_markup=keyboard)
    print(f"✅ Реакции добавлены под постом {msg.message_id}")

# --- Обработка нажатий ---
@dp.callback_query(F.data.startswith("react:"))
async def on_reaction(call: types.CallbackQuery):
    emoji = call.data.split(":")[1]
    user = call.from_user
    msg = call.message

    async with aiosqlite.connect(DB_PATH) as db:
        existing = await db.execute_fetchone(
            "SELECT emoji FROM reactions WHERE chat_id=? AND message_id=? AND user_id=?",
            (msg.chat.id, msg.message_id, user.id)
        )

        if existing:
            if existing[0] == emoji:
                await db.execute(
                    "DELETE FROM reactions WHERE chat_id=? AND message_id=? AND user_id=?",
                    (msg.chat.id, msg.message_id, user.id)
                )
                await call.answer("Реакция снята")
            else:
                await db.execute(
                    "UPDATE reactions SET emoji=? WHERE chat_id=? AND message_id=? AND user_id=?",
                    (emoji, msg.chat.id, msg.message_id, user.id)
                )
                await call.answer(f"Изменено на {emoji}")
        else:
            await db.execute(
                "INSERT INTO reactions VALUES (?, ?, ?, ?, ?)",
                (msg.chat.id, msg.message_id, user.id, user.full_name, emoji)
            )
            await call.answer(f"Ты выбрал {emoji}")

        await db.commit()

        rows = await db.execute_fetchall(
            "SELECT emoji, COUNT(*) FROM reactions WHERE chat_id=? AND message_id=? GROUP BY emoji",
            (msg.chat.id, msg.message_id)
        )
        counts = {emoji: count for emoji, count in rows}

    kb = build_keyboard(counts)
    await msg.edit_reply_markup(reply_markup=kb)

# --- Просмотр статистики ---
@dp.message(Command("stats"))
async def stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🚫 Только админ может просматривать статистику.")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Используй: /stats ID_сообщения")
        return
    msg_id = args[1]
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            "SELECT user_name, emoji FROM reactions WHERE message_id=?",
            (msg_id,)
        )
    if not rows:
        await message.answer("📭 Нет реакций на это сообщение.")
        return
    text = "📊 <b>Реакции:</b>\n\n"
    for name, emoji in rows:
        text += f"{emoji} — {name}\n"
    await message.answer(text)

# --- Запуск ---
async def main():
    await init_db()
    print("🤖 Бот запущен и ждёт посты...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
