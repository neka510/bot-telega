import logging
import os
import sqlite3
from telegram import Update, Message
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.helpers import escape_markdown

# --- НАСТРОЙКИ ---
TOKEN = "8279354110:AAFkY5C2nELbeVby2SmGXM0hUykzUHsgQfw"
DB_NAME = "audio_database.db"
ADMIN_ID = 1127227960  # ЗАМЕНИТЕ НА ВАШ ID
# --- КОНЕЦ НАСТРОЕК ---

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

def initialize_db():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS audio_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title_lower TEXT NOT NULL UNIQUE,
            original_title TEXT NOT NULL,
            added_by_username TEXT,
            added_by_first_name TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()
        conn.close()
        logger.info(f"База данных '{DB_NAME}' успешно инициализирована.")
    except sqlite3.Error as e:
        logger.error(f"Критическая ошибка при инициализации БД: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        f"Привет, {user.mention_html()}!\n\nЧтобы добавить аудиофайл в базу, используйте команду /add."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Как добавить трек в базу:\n"
        "1. Отправьте аудиофайл и в подписи к нему напишите команду `/add`.\n"
        "   *ИЛИ*\n"
        "2. Сначала отправьте аудиофайл, а затем ответьте на его сообщение командой `/add`.\n\n"
        "Команды:\n"
        "/start, /help, /add, /list, /reset (только для админа)"
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        logger.warning(f"Пользователь {user_id} попытался использовать команду /reset без прав доступа.")
        await update.message.reply_text("⛔️ Эта команда доступна только администратору бота.")
        return

    try:
        if os.path.exists(DB_NAME):
            os.remove(DB_NAME)
        initialize_db()
        await update.message.reply_text("✅ База данных аудиофайлов была полностью очищена администратором!")
        logger.warning(f"База данных очищена администратором (ID: {user_id}).")
    except Exception as e:
        await update.message.reply_text(f"Произошла ошибка при очистке базы данных: {e}")

# ИСПРАВЛЕННАЯ ВЕРСИЯ
async def list_songs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT original_title FROM audio_files ORDER BY original_title ASC")
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            await update.message.reply_text("База данных пока пуста.")
            return
            
        # ИСПРАВЛЕНО: Экранируем спецсимволы в заголовке
        header = f"🎧 *Список всех треков в базе \\({len(results)} шт\\.\\):*\n\n"
        message_chunks = []
        current_chunk = header
        
        for index, row in enumerate(results):
            # escape_markdown защищает название трека
            safe_title = escape_markdown(row[0], version=2)
            line = f"{index + 1}\\. {safe_title}\n"
            if len(current_chunk) + len(line) > 4096:
                message_chunks.append(current_chunk)
                current_chunk = ""
            current_chunk += line
        
        message_chunks.append(current_chunk)
        
        for chunk in message_chunks:
            await update.message.reply_text(chunk, parse_mode="MarkdownV2")

    except Exception as e:
        logger.error(f"Ошибка в list_songs: {e}")
        await update.message.reply_text(f"Произошла ошибка при получении списка песен.")

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    
    audio_to_process = None
    if message.audio:
        audio_to_process = message.audio
    elif message.reply_to_message and message.reply_to_message.audio:
        audio_to_process = message.reply_to_message.audio
    
    if not audio_to_process:
        await message.reply_text("Чтобы добавить трек, используйте /add вместе с аудиофайлом.")
        return

    title = audio_to_process.title
    if not title:
        safe_filename = escape_markdown(audio_to_process.file_name, version=2)
        await message.reply_text(f"У файла `{safe_filename}` нет названия в мета\\-тегах\\.", parse_mode="MarkdownV2")
        return
        
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        title_lower = title.lower()
        
        cursor.execute("SELECT added_by_first_name, added_by_username FROM audio_files WHERE title_lower = ?", (title_lower,))
        result = cursor.fetchone()

        safe_title = escape_markdown(title, version=2)
        safe_first_name = escape_markdown(user.first_name, version=2)
        safe_username = escape_markdown(user.username or "N/A", version=2)

        response_text = ""
        if result:
            original_sender_name, original_sender_username = result
            safe_orig_name = escape_markdown(original_sender_name, version=2)
            safe_orig_user = escape_markdown(original_sender_username or "N/A", version=2)
            response_text = (
                f"⚠️ *Найден дубликат\\!* \n\n"
                f"*Название:* `{safe_title}`\n\n"
                f"Этот трек уже был добавлен *{safe_orig_name}* \\(@{safe_orig_user}\\)\\."
            )
        else:
            cursor.execute(
                "INSERT INTO audio_files (title_lower, original_title, added_by_username, added_by_first_name) VALUES (?, ?, ?, ?)",
                (title_lower, title, user.username or 'N/A', user.first_name)
            )
            conn.commit()
            response_text = (
                f"✅ *Уведомление: Трек успешно добавлен в базу\\!* \n\n"
                f"🎧 *Название:* `{safe_title}`\n"
                f"*Добавил:* {safe_first_name} \\(@{safe_username}\\)"
            )
        
        conn.close()
        await message.reply_text(response_text, parse_mode="MarkdownV2")

    except Exception as e:
        logger.error(f"Ошибка в add_command: {e}")
        await message.reply_text(f"Произошла ошибка при работе с базой данных.")

def main() -> None:
    initialize_db()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("list", list_songs))
    application.add_handler(CommandHandler("add", add_command))
    print("Бот запущен. Команда /reset доступна только для админа.")
    application.run_polling()

if __name__ == "__main__":
    main()