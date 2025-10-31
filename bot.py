import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
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
        ws.column_dimensions['C'].width = 30 # Увеличено для длинных статусов
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
    
    # --- ИЗМЕНЕНИЕ: Добавляем кликабельную ссылку ---
    ws[f'B{row}'].value = link
    ws[f'B{row}'].hyperlink = link
    ws[f'B{row}'].font = Font(color="0563C1", underline="single")
    ws[f'B{row}'].border = thin_border
    # --- /ИЗМЕНЕНИЕ ---
    
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

# --- ПРОВЕРКА НАЛИЧИЯ ССЫЛКИ ---
def link_exists_in_excel(user_id: int, link: str) -> bool:
    excel_file = get_user_excel_file(user_id)
    if not os.path.exists(excel_file):
        return False

    wb = openpyxl.load_workbook(excel_file)
    ws = wb.active

    for row in range(2, ws.max_row + 1):
        if ws[f'B{row}'].value == link:
            return True
    return False

# --- ФУНКЦИИ ДЛЯ СОЗДАНИЯ КНОПОК ---
def get_time_options_keyboard():
    keyboard = [
        [InlineKeyboardButton("Вышли первыми", callback_data='status_1')],
        [InlineKeyboardButton("Вышли в течение часа", callback_data='status_2')],
        [InlineKeyboardButton("Вышли в течение 2-3 часов", callback_data='status_3')],
        [InlineKeyboardButton("Вышли больше, чем через 3 часа", callback_data='status_4')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_new_link_or_delete_keyboard():
    keyboard = [
        [InlineKeyboardButton("Отправить новую ссылку", callback_data='new_link')],
        [InlineKeyboardButton("Удалить этот пост", callback_data='delete_current')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_delete_or_new_link_keyboard():
    keyboard = [
        [InlineKeyboardButton("Удалить", callback_data='delete_current')],
        [InlineKeyboardButton("Отправить новую ссылку", callback_data='new_link')]
    ]
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
        "Просто *перешли* мне пост из Telegram или отправь ссылку.\n\n"
        "Команды:\n"
        "/export - выгрузить *твою* базу данных в Excel\n"
        "/stats - статистика *твоих* постов"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user_excel(user_id)

    # Проверяем, есть ли пересланное сообщение из канала/супергруппы с username
    if update.message.forward_from_chat:
        chat = update.message.forward_from_chat
        message_id = update.message.forward_from_message_id

        if chat.username and message_id:
            link = f"https://t.me/{chat.username}/{message_id}"
            context.user_data['current_link'] = link
            if link_exists_in_excel(user_id, link):
                reply_markup = get_delete_or_new_link_keyboard()
                await update.message.reply_text(
                    f"⚠️ Ссылка уже есть в базе данных!\n\nСсылка: {link}\n\nВыбери действие:",
                    reply_markup=reply_markup
                )
            else:
                reply_markup = get_time_options_keyboard()
                await update.message.reply_text(
                    f"📌 Пост получен!\n\nСсылка: {link}\n\nКогда он вышел?",
                    reply_markup=reply_markup
                )
            return

    # Если не переслано из чата с username, проверяем текст
    text = update.message.text or update.message.caption or ""
    if text:
        link = extract_telegram_link(text)
        if link:
            if link_exists_in_excel(user_id, link):
                context.user_data['current_link'] = link
                reply_markup = get_delete_or_new_link_keyboard()
                await update.message.reply_text(
                    f"⚠️ Ссылка уже есть в базе данных!\n\nСсылка: {link}\n\nВыбери действие:",
                    reply_markup=reply_markup
                )
            else:
                context.user_data['current_link'] = link
                reply_markup = get_time_options_keyboard()
                await update.message.reply_text(
                    f"📌 Пост получен!\n\nСсылка: {link}\n\nКогда он вышел?",
                    reply_markup=reply_markup
                )
        else:
            await update.message.reply_text(
                "❌ Я не нашёл действительную ссылку на пост в Telegram в твоём сообщении.\n\n"
                "Отправь ссылку, перешли пост из канала/группы (с username) или отправь медиа с подписью содержащей ссылку."
            )
    else:
        await update.message.reply_text(
            "❌ Я не нашёл действительную ссылку на пост в Telegram в твоём сообщении.\n\n"
            "Отправь ссылку, перешли пост из канала/группы (с username) или отправь медиа с подписью содержащей ссылку."
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

    if query.data == 'new_link':
        context.user_data.pop('current_link', None)
        await query.edit_message_text("✅ Готов принять новую ссылку. Отправь её сюда.")
        return

    if query.data == 'delete_current':
        link = context.user_data.get('current_link')
        if link:
            success = delete_post_from_excel(user_id, link)
            if success:
                excel_file = get_user_excel_file(user_id)
                if os.path.exists(excel_file):
                    await query.message.reply_document(
                        document=open(excel_file, 'rb'),
                        filename=f'my_posts_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
                    )
                else:
                    await query.edit_message_text("❌ Твоя база данных пуста.")
            else:
                await query.edit_message_text("❌ Не удалось удалить пост. Возможно, его уже нет.")
        else:
            await query.edit_message_text("❌ Ошибка: ссылка не найдена для удаления.")
        context.user_data.pop('current_link', None)
        return

    link = context.user_data.get('current_link')

    if not link:
        await query.edit_message_text("❌ Ошибка: ссылка не найдена. Отправь ссылку заново.")
        return

    status_mapping = {
        'status_1': "Вышли первыми",
        'status_2': "Вышли в течение часа",
        'status_3': "Вышли в течение 2-3 часов",
        'status_4': "Вышли больше, чем через 3 часа"
    }

    selected_status = status_mapping.get(query.data)
    if selected_status:
        try:
            number = add_post_to_excel(user_id, link, selected_status)
            excel_file = get_user_excel_file(user_id)
            if os.path.exists(excel_file):
                await query.message.reply_document(
                    document=open(excel_file, 'rb'),
                    filename=f'my_posts_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
                )
            else:
                await query.edit_message_text("❌ Твоя база данных пуста.")
            
            reply_markup = get_new_link_or_delete_keyboard()
            await query.message.reply_text(
                f"✅ Пост #{number} добавлен в *твою* базу данных!\n\n"
                f"Ссылка: {link}\n"
                f"Статус: {selected_status}",
                reply_markup=reply_markup
            )
            context.user_data.pop('current_link', None)
        except Exception as e:
            logger.error(f"Ошибка при добавлении поста для пользователя {user_id}: {e}")
            await query.edit_message_text("❌ Произошла ошибка при добавлении поста. Попробуй ещё раз.")
            context.user_data.pop('current_link', None)
    else:
        await query.edit_message_text("❌ Неизвестная команда. Попробуй снова.")
        context.user_data.pop('current_link', None)

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

# --- ОСНОВНАЯ ФУНКЦИЯ ---
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
    app.add_handler(MessageHandler(~filters.COMMAND, handle_message))
    
    logger.info("Бот запущен с новой логикой обработки !")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()