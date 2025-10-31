import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import openpyxl
from openpyxl import Workbook
import os
import re
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Имя директории для хранения файлов пользователей
DATA_DIR = os.getenv('DATA_DIR', 'user_data')
os.makedirs(DATA_DIR, exist_ok=True)

# ID чата для бэкапа
BACKUP_CHAT_ID = os.getenv('BACKUP_CHAT_ID')

# Глобальная переменная для application
app = None

# --- ФУНКЦИИ РАБОТЫ С ИНДИВИДУАЛЬНЫМИ ФАЙЛАМИ ---
def get_user_excel_file(user_id: int) -> str:
    return os.path.join(DATA_DIR, f'user_{user_id}.xlsx')

def init_user_excel(user_id: int):
    excel_file = get_user_excel_file(user_id)
    
    if not os.path.exists(excel_file):
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Посты"
        
        headers = ['№', 'Ссылка', 'Статус', 'Дата добавления']
        ws.append(headers)
        
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=12)
        alignment_center = Alignment(horizontal="center", vertical="center")
        
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = alignment_center
            cell.border = thin_border
        
        ws.column_dimensions['A'].width = 8
        ws.column_dimensions['B'].width = 60
        ws.column_dimensions['C'].width = 20
        ws.column_dimensions['D'].width = 22
        
        wb.save(excel_file)
        logger.info(f"Создан новый Excel файл для пользователя {user_id}")

def send_backup_for_user(user_id: int):
    if BACKUP_CHAT_ID:
        excel_file = get_user_excel_file(user_id)
        if os.path.exists(excel_file):
            try:
                import asyncio
                async def _send():
                    try:
                        with open(excel_file, 'rb') as f:
                            await app.bot.send_document(
                                chat_id=BACKUP_CHAT_ID,
                                document=f,
                                filename=f'backup_user_{user_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
                            )
                        logger.info(f"Бэкап для пользователя {user_id} отправлен успешно")
                    except Exception as e:
                        logger.error(f"Ошибка отправки бэкапа для пользователя {user_id}: {e}")

                asyncio.create_task(_send())
            except Exception as e:
                logger.error(f"Ошибка подготовки бэкапа для пользователя {user_id}: {e}")
        else:
            logger.warning(f"Файл для бэкапа пользователя {user_id} не найден.")

# --- ОБНОВЛЁННЫЕ ФУНКЦИИ РАБОТЫ С EXCEL ---
def get_next_number(user_id: int):
    excel_file = get_user_excel_file(user_id)
    if not os.path.exists(excel_file):
        init_user_excel(user_id)
    wb = openpyxl.load_workbook(excel_file)
    ws = wb.active
    return ws.max_row

def add_post_to_excel(user_id: int, link: str, status=None):
    from openpyxl.styles import Alignment, Border, Side
    
    excel_file = get_user_excel_file(user_id)
    if not os.path.exists(excel_file):
        init_user_excel(user_id)

    wb = openpyxl.load_workbook(excel_file)
    ws = wb.active
    row = ws.max_row + 1
    number = row - 1
    
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    ws[f'A{row}'] = number
    ws[f'A{row}'].alignment = Alignment(horizontal="center", vertical="center")
    ws[f'A{row}'].border = thin_border
    
    ws[f'B{row}'].hyperlink = link
    ws[f'B{row}'].value = link
    ws[f'B{row}'].border = thin_border
    
    ws[f'C{row}'] = status if status else ""
    ws[f'C{row}'].alignment = Alignment(horizontal="center", vertical="center")
    ws[f'C{row}'].border = thin_border
    
    ws[f'D{row}'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws[f'D{row}'].alignment = Alignment(horizontal="center", vertical="center")
    ws[f'D{row}'].border = thin_border
    
    wb.save(excel_file)
    send_backup_for_user(user_id)
    return number

def delete_post_from_excel(user_id: int, link: str):
    excel_file = get_user_excel_file(user_id)
    if not os.path.exists(excel_file):
        logger.warning(f"Попытка удаления из несуществующего файла для пользователя {user_id}")
        return False

    wb = openpyxl.load_workbook(excel_file)
    ws = wb.active
    deleted = False
    
    for row in range(2, ws.max_row + 1):
        if ws[f'B{row}'].value == link:
            ws.delete_rows(row)
            for i in range(row, ws.max_row + 1):
                ws[f'A{i}'] = i - 1
            wb.save(excel_file)
            deleted = True
            break
            
    if deleted:
        send_backup_for_user(user_id)
    
    return deleted

def update_post_status(user_id: int, link: str, status: str):
    excel_file = get_user_excel_file(user_id)
    if not os.path.exists(excel_file):
        logger.warning(f"Попытка обновления статуса в несуществующем файле для пользователя {user_id}")
        return False

    wb = openpyxl.load_workbook(excel_file)
    ws = wb.active
    
    for row in range(2, ws.max_row + 1):
        if ws[f'B{row}'].value == link:
            ws[f'C{row}'] = status
            wb.save(excel_file)
            return True
    return False

def get_export_button():
    keyboard = [[InlineKeyboardButton("📊 Отправить мою базу данных", callback_data='export_db')]]
    return InlineKeyboardMarkup(keyboard)

# --- НОВАЯ ФУНКЦИЯ ДЛЯ ИЗВЛЕЧЕНИЯ ССЫЛОК ---
def extract_telegram_link(text: str) -> str:
    pattern = r'https?://(?:t\.me|telegram\.me)/(?:[a-zA-Z0-9_]+)(?:/[0-9]+)?(?:/[a-zA-Z0-9_]+)?'
    match = re.search(pattern, text)
    if match:
        return match.group(0)
    return ""

# --- ОБНОВЛЁННЫЕ ОБРАБОТЧИКИ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user_excel(user_id)
    await update.message.reply_text(
        f"👋 Привет, {update.effective_user.first_name}! Я бот для сохранения постов.\n\n"
        "Ты можешь:\n"
        "1. *Переслать* мне пост из Telegram (если он содержит или добавляется с комментарием содержащим ссылку).\n"
        "2. Отправить мне *ссылку* на пост в Telegram.\n"
        "3. Отправить *медиафайл* с подписью, содержащей ссылку.\n\n"
        "Я сохраню её в *твою* персональную базу данных.\n\n"
        "Команды:\n"
        "/export - выгрузить *твою* базу данных в Excel\n"
        "/stats - статистика *твоих* постов"
    )

# Обработка сообщений (любых, кроме команд)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user_excel(user_id)

    # Проверяем текст или подпись текущего сообщения
    text = update.message.text or update.message.caption or ""
    if text:
        link = extract_telegram_link(text)
        if link:
            # Сохраняем ссылку в контексте пользователя
            context.user_data['current_link'] = link
            await _present_link_options(update, context, link)
            return # Обработали, выходим

    # Если ссылка не найдена
    await update.message.reply_text("❌ Я не нашёл действительную ссылку на пост в Telegram в твоём сообщении. Отправь ссылку, перешли пост с комментарием или отправь медиа с подписью содержащей ссылку.")

# Вспомогательная функция для представления опций после извлечения ссылки
async def _present_link_options(update: Update, context: ContextTypes.DEFAULT_TYPE, link: str):
    keyboard = [
        [InlineKeyboardButton("📝 Добавить пост + статус", callback_data='add_with_status')],
        [InlineKeyboardButton("🗑️ Удалить пост", callback_data='delete_post')],
        [InlineKeyboardButton("✅ Просто добавить пост", callback_data='add_simple')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📌 Пост получен!\n\nСсылка: {link}\n\nВыбери действие:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id

    if query.data == 'export_db':
        excel_file = get_user_excel_file(user_id)
        if os.path.exists(excel_file):
            await query.message.reply_document(
                document=open(excel_file, 'rb'),
                filename=f'my_posts_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
        else:
            await query.edit_message_text("❌ Твоя база данных пуста. Добавь хотя бы один пост.")
        return
    
    link = context.user_data.get('current_link')
    
    if not link:
        await query.edit_message_text("❌ Ошибка: ссылка не найдена. Отправь ссылку заново.")
        return
    
    if query.data == 'add_simple':
        number = add_post_to_excel(user_id, link)
        await query.edit_message_text(
            f"✅ Пост #{number} добавлен в *твою* базу данных!\n\n"
            f"Ссылка: {link}",
            reply_markup=get_export_button()
        )
        context.user_data.clear()
        
    elif query.data == 'add_with_status':
        context.user_data['waiting_for_status'] = True
        await query.edit_message_text(
            f"📝 Введи статус для поста:\n\n{link}\n\n"
            "Например: Одобрено, На проверке, Отклонено и т.д."
        )
        
    elif query.data == 'delete_post':
        success = delete_post_from_excel(user_id, link)
        if success:
            await query.edit_message_text(
                f"🗑️ Пост удалён из *твоей* базы данных!\n\n"
                f"Ссылка: {link}",
                reply_markup=get_export_button()
            )
        else:
            await query.edit_message_text(
                f"❌ Не удалось удалить пост. Возможно, его уже нет в базе.\n\n"
                f"Ссылка: {link}",
                reply_markup=get_export_button()
            )
        context.user_data.clear()

async def export_database(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    excel_file = get_user_excel_file(user_id)
    if os.path.exists(excel_file):
        await update.message.reply_document(
            document=open(excel_file, 'rb'),
            filename=f'my_posts_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
    else:
        await update.message.reply_text("❌ Твоя база данных пуста. Добавь хотя бы один пост.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    excel_file = get_user_excel_file(user_id)
    if not os.path.exists(excel_file):
        await update.message.reply_text("📊 Твоя база данных пуста.")
        return
    
    wb = openpyxl.load_workbook(excel_file)
    ws = wb.active
    total = ws.max_row - 1
    
    statuses = {}
    for row in range(2, ws.max_row + 1):
        status = ws[f'C{row}'].value
        if status:
            statuses[status] = statuses.get(status, 0) + 1
    
    message = f"📊 Статистика *твоих* постов:\n\n"
    message += f"Всего постов: {total}\n\n"
    
    if statuses:
        message += "По статусам:\n"
        for status, count in statuses.items():
            message += f"• {status}: {count}\n"
    
    await update.message.reply_text(message)

# Основная функция
def main():
    global app

    TOKEN = os.getenv("BOT_TOKEN")
    
    if not TOKEN:
        logger.error("Требуется переменная окружения BOT_TOKEN")
        return

    app = Application.builder().token(TOKEN).job_queue(None).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("export", export_database))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(button_handler))
    # Обработчик для всех сообщений, кроме команд
    app.add_handler(MessageHandler(~filters.COMMAND, handle_message))
    
    logger.info("Бот запущен с поддержкой пересланных сообщений (если они содержат ссылку)!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()