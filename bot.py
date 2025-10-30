import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import openpyxl
from openpyxl import Workbook
import os
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Имя файла Excel
# Используем переменную окружения для пути к постоянному хранилищу
DATA_DIR = os.getenv('DATA_DIR', '.')
EXCEL_FILE = os.path.join(DATA_DIR, 'posts_database.xlsx')

# ID чата для бэкапа
BACKUP_CHAT_ID = os.getenv('BACKUP_CHAT_ID')

# Глобальная переменная для application
app = None

# Инициализация Excel файла
def init_excel():
    # Создаем директорию если её нет
    os.makedirs(DATA_DIR, exist_ok=True)
    
    if not os.path.exists(EXCEL_FILE):
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Посты"
        
        # Заголовки
        headers = ['№', 'Ссылка', 'Статус', 'Дата добавления']
        ws.append(headers)
        
        # Стиль для заголовков
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=12)
        alignment_center = Alignment(horizontal="center", vertical="center")
        
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        # Применяем стиль к заголовкам
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = alignment_center
            cell.border = thin_border
        
        # Устанавливаем ширину столбцов
        ws.column_dimensions['A'].width = 8   # №
        ws.column_dimensions['B'].width = 60  # Ссылка
        ws.column_dimensions['C'].width = 20  # Статус
        ws.column_dimensions['D'].width = 22  # Дата
        
        wb.save(EXCEL_FILE)
        logger.info("Создан новый Excel файл")

# Отправить бэкап в указанный чат
async def send_backup():
    if BACKUP_CHAT_ID and os.path.exists(EXCEL_FILE):
        try:
            with open(EXCEL_FILE, 'rb') as f:
                await app.bot.send_document(
                    chat_id=BACKUP_CHAT_ID,
                    document=f,
                    filename=f'backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
                )
            logger.info("Бэкап отправлен успешно")
        except Exception as e:
            logger.error(f"Ошибка отправки бэкапа: {e}")

# Получить следующий номер для поста
def get_next_number():
    wb = openpyxl.load_workbook(EXCEL_FILE)
    ws = wb.active
    return ws.max_row  # Вернёт номер следующей строки

# Добавить пост в Excel
def add_post_to_excel(link, status=None):
    from openpyxl.styles import Alignment, Border, Side
    
    wb = openpyxl.load_workbook(EXCEL_FILE)
    ws = wb.active
    row = ws.max_row + 1
    number = row - 1  # Минус заголовок
    
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    ws[f'A{row}'] = number
    ws[f'A{row}'].alignment = Alignment(horizontal="center", vertical="center")
    ws[f'A{row}'].border = thin_border
    
    # Добавляем ссылку как гиперссылку
    ws[f'B{row}'].hyperlink = link
    ws[f'B{row}'].value = link
    ws[f'B{row}'].style = "Hyperlink"
    ws[f'B{row}'].border = thin_border
    
    ws[f'C{row}'] = status if status else ""
    ws[f'C{row}'].alignment = Alignment(horizontal="center", vertical="center")
    ws[f'C{row}'].border = thin_border
    
    ws[f'D{row}'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws[f'D{row}'].alignment = Alignment(horizontal="center", vertical="center")
    ws[f'D{row}'].border = thin_border
    
    wb.save(EXCEL_FILE)
    
    # Отправляем бэкап после добавления
    import asyncio
    asyncio.create_task(send_backup())
    
    return number

# Удалить пост из Excel по ссылке
def delete_post_from_excel(link):
    wb = openpyxl.load_workbook(EXCEL_FILE)
    ws = wb.active
    
    for row in range(2, ws.max_row + 1):
        if ws[f'B{row}'].value == link:
            ws.delete_rows(row)
            # Перенумеровать все посты после удаления
            for i in range(row, ws.max_row + 1):
                ws[f'A{i}'] = i - 1
            wb.save(EXCEL_FILE)
            
            # Отправляем бэкап после удаления
            import asyncio
            asyncio.create_task(send_backup())
            
            return True
    return False

# Обновить статус поста
def update_post_status(link, status):
    wb = openpyxl.load_workbook(EXCEL_FILE)
    ws = wb.active
    
    for row in range(2, ws.max_row + 1):
        if ws[f'B{row}'].value == link:
            ws[f'C{row}'] = status
            wb.save(EXCEL_FILE)
            return True
    return False

# Создать кнопку для отправки базы данных
def get_export_button():
    keyboard = [[InlineKeyboardButton("📊 Отправить актуальную базу данных", callback_data='export_db')]]
    return InlineKeyboardMarkup(keyboard)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для сохранения постов.\n\n"
        "Просто отправь мне ссылку на пост, и я сохраню её в базу данных.\n\n"
        "Команды:\n"
        "/export - выгрузить базу данных в Excel\n"
        "/stats - статистика"
    )

# Обработка ссылок
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text
    
    # Сохраняем ссылку в контексте пользователя
    context.user_data['current_link'] = link
    
    # Создаём кнопки
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

# Обработка нажатий на кнопки
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Обработка экспорта базы данных
    if query.data == 'export_db':
        if os.path.exists(EXCEL_FILE):
            await query.message.reply_document(
                document=open(EXCEL_FILE, 'rb'),
                filename=f'posts_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
        else:
            await query.edit_message_text("❌ База данных пуста. Добавь хотя бы один пост.")
        return
    
    link = context.user_data.get('current_link')
    
    if not link:
        await query.edit_message_text("❌ Ошибка: ссылка не найдена. Отправь ссылку заново.")
        return
    
    if query.data == 'add_simple':
        # Просто добавить пост без статуса
        number = add_post_to_excel(link)
        await query.edit_message_text(
            f"✅ Пост #{number} добавлен в базу данных!\n\n"
            f"Ссылка: {link}",
            reply_markup=get_export_button()
        )
        context.user_data.clear()
        
    elif query.data == 'add_with_status':
        # Просим ввести статус
        context.user_data['waiting_for_status'] = True
        await query.edit_message_text(
            f"📝 Введи статус для поста:\n\n{link}\n\n"
            "Например: Одобрено, На проверке, Отклонено и т.д."
        )
        
    elif query.data == 'delete_post':
        # Удалить пост
        delete_post_from_excel(link)
        await query.edit_message_text(
            f"🗑️ Пост удалён из базы данных!\n\n"
            f"Ссылка: {link}",
            reply_markup=get_export_button()
        )
        context.user_data.clear()

# Обработка текстовых сообщений (для статуса)
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_status'):
        status = update.message.text
        link = context.user_data.get('current_link')
        
        if link:
            number = add_post_to_excel(link, status)
            await update.message.reply_text(
                f"✅ Пост #{number} добавлен в базу данных!\n\n"
                f"Ссылка: {link}\n"
                f"Статус: {status}",
                reply_markup=get_export_button()
            )
            context.user_data.clear()
        else:
            await update.message.reply_text("❌ Ошибка: ссылка не найдена.")
    else:
        # Обрабатываем как ссылку
        await handle_link(update, context)

# Экспорт базы данных
async def export_database(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if os.path.exists(EXCEL_FILE):
        await update.message.reply_document(
            document=open(EXCEL_FILE, 'rb'),
            filename=f'posts_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
    else:
        await update.message.reply_text("❌ База данных пуста. Добавь хотя бы один пост.")

# Статистика
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.exists(EXCEL_FILE):
        await update.message.reply_text("📊 База данных пуста.")
        return
    
    wb = openpyxl.load_workbook(EXCEL_FILE)
    ws = wb.active
    total = ws.max_row - 1  # Минус заголовок
    
    # Подсчёт статусов
    statuses = {}
    for row in range(2, ws.max_row + 1):
        status = ws[f'C{row}'].value
        if status:
            statuses[status] = statuses.get(status, 0) + 1
    
    message = f"📊 Статистика базы данных:\n\n"
    message += f"Всего постов: {total}\n\n"
    
    if statuses:
        message += "По статусам:\n"
        for status, count in statuses.items():
            message += f"• {status}: {count}\n"
    
    await update.message.reply_text(message)

# Основная функция
def main():
    global app
    
    # Инициализация Excel
    init_excel()
    
    # Токен бота
    TOKEN = os.getenv("BOT_TOKEN")
    
    # Создание приложения (без job_queue  чтобы избежать ошибки)
    app = Application.builder().token(TOKEN).job_queue(None).build()
    
    # Регистрация обработчиков
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("export", export_database))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запуск бота
    logger.info("Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()