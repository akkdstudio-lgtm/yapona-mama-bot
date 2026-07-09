import logging
import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)
from datetime import datetime
import json

# Включаем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния диалога
MAIN_MENU, VIEWING_MENU, CART_VIEW, CHECKOUT, PAYMENT, ORDERS = range(6)

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('food_bot.db', check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS menu (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            category TEXT
        )''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            items TEXT,
            total REAL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS carts (
            user_id INTEGER PRIMARY KEY,
            items TEXT
        )''')

        self.conn.commit()
        self.add_default_menu()

    def add_default_menu(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM menu")
        if cursor.fetchone()[0] == 0:
            menu_items = [
                ("Манты", "Мясные пельмени по-узбекски", 15000, "Основные блюда"),
                ("Плов", "Классический узбекский плов", 20000, "Основные блюда"),
                ("Шашлык", "Мясо на гриле", 18000, "Основные блюда"),
                ("Суп лапша", "Традиционный суп", 12000, "Супы"),
                ("Хаш", "Узбекский согревающий суп", 14000, "Супы"),
                ("Самса", "Жареные треугольники с мясом", 8000, "Закуски"),
                ("Чай", "Черный узбекский чай", 2000, "Напитки"),
                ("Компот", "Свежий компот", 3000, "Напитки"),
            ]
            cursor.executemany(
                "INSERT INTO menu (name, description, price, category) VALUES (?, ?, ?, ?)",
                menu_items
            )
            self.conn.commit()

    def get_menu_by_category(self, category=None):
        cursor = self.conn.cursor()
        if category:
            cursor.execute("SELECT id, name, price FROM menu WHERE category = ?", (category,))
        else:
            cursor.execute("SELECT id, name, price FROM menu")
        return cursor.fetchall()

    def get_categories(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM menu")
        return [row[0] for row in cursor.fetchall()]

    def get_item(self, item_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM menu WHERE id = ?", (item_id,))
        return cursor.fetchone()

    def get_cart(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT items FROM carts WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if result:
            return json.loads(result[0])
        return {}

    def save_cart(self, user_id, items):
        cursor = self.conn.cursor()
        items_json = json.dumps(items)
        cursor.execute("INSERT OR REPLACE INTO carts (user_id, items) VALUES (?, ?)",
                      (user_id, items_json))
        self.conn.commit()

    def clear_cart(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM carts WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def create_order(self, user_id, items, total):
        cursor = self.conn.cursor()
        items_json = json.dumps(items)
        cursor.execute("INSERT INTO orders (user_id, items, total, status) VALUES (?, ?, ?, ?)",
                      (user_id, items_json, total, 'Принят'))
        self.conn.commit()
        cursor.execute("SELECT last_insert_rowid()")
        return cursor.fetchone()[0]

    def get_user_orders(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        return cursor.fetchall()

db = Database()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    await update.message.reply_text(
        "Добро пожаловать в 🍜 Япона Мама!\n"
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("📋 Меню")],
            [KeyboardButton("🛒 Корзина")],
            [KeyboardButton("📦 Мои заказы")]
        ], resize_keyboard=True)
    )
    return MAIN_MENU

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню"""
    text = update.message.text

    if "📋 Меню" in text:
        categories = db.get_categories()
        buttons = [[InlineKeyboardButton(cat, callback_data=f"cat_{cat}")] for cat in categories]
        buttons.append([InlineKeyboardButton("← Назад", callback_data="back_menu")])

        await update.message.reply_text(
            "Выберите категорию:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return VIEWING_MENU

    elif "🛒 Корзина" in text:
        cart = db.get_cart(update.effective_user.id)
        if not cart:
            await update.message.reply_text("Ваша корзина пуста")
            return MAIN_MENU

        total = sum(item['price'] * item['quantity'] for item in cart.values())
        cart_text = "🛒 Ваша корзина:\n\n"
        for item_id, item in cart.items():
            cart_text += f"{item['name']}\n{item['quantity']}x {item['price']} = {item['quantity'] * item['price']} сум\n\n"

        cart_text += f"Итого: {total} сум"

        buttons = [
            [InlineKeyboardButton("✅ Оформить", callback_data="checkout")],
            [InlineKeyboardButton("🗑️ Очистить", callback_data="clear_cart")],
            [InlineKeyboardButton("← Назад", callback_data="back_menu")]
        ]

        await update.message.reply_text(cart_text, reply_markup=InlineKeyboardMarkup(buttons))
        return CART_VIEW

    elif "📦 Мои заказы" in text:
        orders = db.get_user_orders(update.effective_user.id)
        if not orders:
            await update.message.reply_text("У вас нет заказов")
            return MAIN_MENU

        orders_text = "📦 Ваши заказы:\n\n"
        for order in orders:
            order_id, user_id, items, total, status, created_at = order
            orders_text += f"Заказ #{order_id}\nСумма: {total} сум\nСтатус: {status}\nВремя: {created_at}\n\n"

        await update.message.reply_text(orders_text)
        return MAIN_MENU

    return MAIN_MENU

async def handle_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вывод блюд категории"""
    query = update.callback_query
    await query.answer()

    if "back" in query.data:
        await query.edit_message_text(
            "Выберите действие:",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("📋 Меню")],
                [KeyboardButton("🛒 Корзина")],
                [KeyboardButton("📦 Мои заказы")]
            ], resize_keyboard=True)
        )
        return MAIN_MENU

    category = query.data.replace("cat_", "")
    items = db.get_menu_by_category(category)

    buttons = []
    for item_id, name, price in items:
        buttons.append([InlineKeyboardButton(f"{name} ({price} сум)", callback_data=f"item_{item_id}")])
    buttons.append([InlineKeyboardButton("← Назад к категориям", callback_data="back_menu")])

    await query.edit_message_text(
        f"Категория: {category}\n\nВыберите блюдо:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return VIEWING_MENU

async def handle_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр блюда и добавление в корзину"""
    query = update.callback_query
    await query.answer()

    item_id = int(query.data.replace("item_", ""))
    item = db.get_item(item_id)

    if item:
        item_id, name, description, price, category = item
        text = f"🍜 {name}\n\n{description}\n\nЦена: {price} сум"

        buttons = [
            [InlineKeyboardButton("➕ Добавить в корзину", callback_data=f"add_{item_id}")],
            [InlineKeyboardButton("← Назад", callback_data=f"cat_{category}")]
        ]

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

    return VIEWING_MENU

async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавление товара в корзину"""
    query = update.callback_query
    await query.answer()

    item_id = int(query.data.replace("add_", ""))
    item = db.get_item(item_id)

    if item:
        item_id, name, description, price, category = item
        cart = db.get_cart(update.effective_user.id)

        if str(item_id) in cart:
            cart[str(item_id)]['quantity'] += 1
        else:
            cart[str(item_id)] = {'name': name, 'price': price, 'quantity': 1}

        db.save_cart(update.effective_user.id, cart)

        await query.answer(f"✅ {name} добавлен в корзину!", show_alert=True)

        buttons = [[InlineKeyboardButton("← Назад", callback_data=f"cat_{category}")]]
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))

    return VIEWING_MENU

async def checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оформление заказа"""
    query = update.callback_query
    await query.answer()

    cart = db.get_cart(update.effective_user.id)
    total = sum(item['price'] * item['quantity'] for item in cart.values())

    buttons = [
        [InlineKeyboardButton("💳 Оплатить", callback_data="pay")],
        [InlineKeyboardButton("← Назад в корзину", callback_data="back_cart")]
    ]

    await query.edit_message_text(
        f"Ваш заказ:\n\nОбщая сумма: {total} сум\n\nПодтвердите оплату:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return CHECKOUT

async def payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка платежа"""
    query = update.callback_query
    await query.answer()

    if query.data == "pay":
        cart = db.get_cart(update.effective_user.id)
        total = sum(item['price'] * item['quantity'] for item in cart.values())

        order_id = db.create_order(update.effective_user.id, cart, total)
        db.clear_cart(update.effective_user.id)

        await query.edit_message_text(
            f"✅ Заказ #{order_id} успешно создан!\n\n"
            f"Сумма: {total} сум\n"
            f"Статус: Принят\n\n"
            f"Мы свяжемся с вами для подтверждения адреса доставки.\n"
            f"+998 (90) 123-45-67"
        )
        return PAYMENT

    elif query.data == "back_cart":
        cart = db.get_cart(update.effective_user.id)
        if not cart:
            await query.edit_message_text("Ваша корзина пуста")
            return MAIN_MENU

        total = sum(item['price'] * item['quantity'] for item in cart.values())
        cart_text = "🛒 Ваша корзина:\n\n"
        for item_id, item in cart.items():
            cart_text += f"{item['name']}\n{item['quantity']}x {item['price']} = {item['quantity'] * item['price']} сум\n\n"

        cart_text += f"Итого: {total} сум"

        buttons = [
            [InlineKeyboardButton("✅ Оформить", callback_data="checkout")],
            [InlineKeyboardButton("🗑️ Очистить", callback_data="clear_cart")],
            [InlineKeyboardButton("← Назад", callback_data="back_menu")]
        ]

        await query.edit_message_text(cart_text, reply_markup=InlineKeyboardMarkup(buttons))
        return CART_VIEW

    return CHECKOUT

async def clear_cart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистка корзины"""
    query = update.callback_query
    await query.answer()

    db.clear_cart(update.effective_user.id)
    await query.edit_message_text("🗑️ Корзина очищена")

    return MAIN_MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена"""
    await update.message.reply_text("Операция отменена")
    return ConversationHandler.END

def main():
    """Запуск бота"""
    # Замените TOKEN на ваш токен от @BotFather
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu),
            ],
            VIEWING_MENU: [
                CallbackQueryHandler(handle_category),
                CallbackQueryHandler(handle_item),
                CallbackQueryHandler(add_to_cart),
            ],
            CART_VIEW: [
                CallbackQueryHandler(checkout),
                CallbackQueryHandler(clear_cart_handler),
            ],
            CHECKOUT: [
                CallbackQueryHandler(payment),
            ],
            PAYMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)

    # Запуск бота
    print("🤖 Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()
