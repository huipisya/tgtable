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

# Имя директории для хранения файлов пользователей
# Используем переменную окружения для пути к постоянному хранилищу, по умолчанию 'user_data'
DATA_DIR = os.getenv('DATA_DIR', 'user_data')
# Убедимся, что директория существует
os.makedirs(DATA_DIR, exist_ok=True)

# ID чата для бэкапа (один на всех, или можно сделать индивидуально, если нужно)
BACKUP_CHAT_ID = os.getenv('BACKUP_CHAT_ID')

# Глобальная переменная для application
app = None

# --- ФУНКЦИИ РАБОТЫ С ИНДИВИДУАЛЬНЫМИ ФАЙЛАМИ ---

def get_user_excel_file(user_id: int) -> str:
    """Возвращает путь к Excel-файлу конкретного пользователя."""
    # Имя файла: user_{user_id}.xlsx
    return os.path.join(DATA_DIR, f'user_{user_id}.xlsx')

def init_user_excel(user_id: int):
    """Инициализирует Excel-файл для конкретного пользователя, если его нет."""
    excel_file = get_user_excel_file(user_id)
    
    if not os.path.exists(excel_file):
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
        
        wb.save(excel_file)
        logger.info(f"Создан новый Excel файл для пользователя {user_id}")

def send_backup_for_user(user_id: int):
    """Отправить бэкап индивидуального файла пользователя в указанный чат."""
    if BACKUP_CHAT_ID:
        excel_file = get_user_excel_file(user_id)
        if os.path.exists(excel_file):
            try:
                # Отправляем файл напрямую, используя file_id или file_path
                # В polling режиме нужно открыть файл для отправки
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

                # Создаём задачу для асинхронной отправки
                asyncio.create_task(_send())
            except Exception as e:
                logger.error(f"Ошибка подготовки бэкапа для пользователя {user_id}: {e}")
        else:
            logger.warning(f"Файл для бэкапа пользователя {user_id} не найден.")


# --- ОБНОВЛЁННЫЕ ФУНКЦИИ РАБОТЫ С EXCEL ---

# Получить следующий номер для поста (для конкретного пользователя)
def get_next_number(user_id: int):
    excel_file = get_user_excel_file(user_id)
    if not os.path.exists(excel_file):
        init_user_excel(user_id) # Убедимся, что файл существует

    wb = openpyxl.load_workbook(excel_file)
    ws = wb.active
    return ws.max_row  # Вернёт номер следующей строки

# Добавить пост в Excel (для конкретного пользователя)
def add_post_to_excel(user_id: int, link: str, status=None):
    from openpyxl.styles import Alignment, Border, Side
    
    excel_file = get_user_excel_file(user_id)
    if not os.path.exists(excel_file):
        init_user_excel(user_id) # Убедимся, что файл существует

    wb = openpyxl.load_workbook(excel_file)
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
    ws[f'B{row}'].style = "Hyperlink" # Note: openpyxl не сохраняет стиль Hyperlink в Excel, но значение и гиперссылка будут
    ws[f'B{row}'].border = thin_border
    
    ws[f'C{row}'] = status if status else ""
    ws[f'C{row}'].alignment = Alignment(horizontal="center", vertical="center")
    ws[f'C{row}'].border = thin_border
    
    ws[f'D{row}'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws[f'D{row}'].alignment = Alignment(horizontal="center", vertical="center")
    ws[f'D{row}'].border = thin_border
    
    wb.save(excel_file)
    
    # Отправляем бэкап после добавления
    send_backup_for_user(user_id)
    
    return number

# Удалить пост из Excel по ссылке (для конкретного пользователя)
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
            # Перенумеровать все посты после удаления
            for i in range(row, ws.max_row + 1):
                ws[f'A{i}'] = i - 1
            wb.save(excel_file)
            deleted = True
            break # Удаляем только первый найденный
            
    if deleted:
        # Отправляем бэкап после удаления
        send_backup_for_user(user_id)
    
    return deleted

# Обновить статус поста (для конкретного пользователя)
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

# Создать кнопку для отправки своей базы данных (для конкретного пользователя)
def get_export_button():
    keyboard = [[InlineKeyboardButton("📊 Отправить мою базу данных", callback_data='export_db')]]
    return InlineKeyboardMarkup(keyboard)

# --- ОБНОВЛЁННЫЕ ОБРАБОТЧИКИ ---

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user_excel(user_id) # Инициализируем файл при старте, если нужно
    await update.message.reply_text(
        f"👋 Привет, {update.effective_user.first_name}! Я бот для сохранения постов.\n\n"
        "Просто отправь мне ссылку на пост, и я сохраню её в *твою* персональную базу данных.\n\n"
        "Команды:\n"
        "/export - выгрузить *твою* базу данных в Excel\n"
        "/stats - статистика *твоих* постов"
    )

# Обработка ссылок
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
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
    
    user_id = query.from_user.id # Получаем ID пользователя из query

    # Обработка экспорта базы данных
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
        # Просто добавить пост без статуса
        number = add_post_to_excel(user_id, link)
        await query.edit_message_text(
            f"✅ Пост #{number} добавлен в *твою* базу данных!\n\n"
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

# Обработка текстовых сообщений (для статуса)
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user_excel(user_id) # Инициализируем файл при получении сообщения, если нужно

    if context.user_data.get('waiting_for_status'):
        status = update.message.text
        link = context.user_data.get('current_link')
        
        if link:
            number = add_post_to_excel(user_id, link, status)
            await update.message.reply_text(
                f"✅ Пост #{number} добавлен в *твою* базу данных!\n\n"
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

# Экспорт базы данных (для конкретного пользователя)
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

# Статистика (для конкретного пользователя)
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    excel_file = get_user_excel_file(user_id)
    if not os.path.exists(excel_file):
        await update.message.reply_text("📊 Твоя база данных пуста.")
        return
    
    wb = openpyxl.load_workbook(excel_file)
    ws = wb.active
    total = ws.max_row - 1  # Минус заголовок
    
    # Подсчёт статусов
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
    
    # Токен бота
    TOKEN = os.getenv("BOT_TOKEN")
    
    if not TOKEN:
        logger.error("Требуется переменная окружения BOT_TOKEN")
        return

    # Создание приложения (без job_queue чтобы избежать ошибки)
    app = Application.builder().token(TOKEN).job_queue(None).build()
    
    # Регистрация обработчиков
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("export", export_database))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запуск бота
    logger.info("Бот запущен с индивидуальными таблицами для пользователей!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()