#!/usr/bin/env python3
import logging
import os
import json
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

MAIN_MENU, VIEWING_MENU, CART_VIEW, CHECKOUT, PAYMENT = range(5)

class FoodDB:
    def __init__(self, db_name='food_bot.db'):
        self.db_name = db_name
        self.init_db()

    def get_conn(self):
        return sqlite3.connect(self.db_name, check_same_thread=False)

    def init_db(self):
        conn = self.get_conn()
        c = conn.cursor()

        c.execute('''CREATE TABLE IF NOT EXISTS menu (
            id INTEGER PRIMARY KEY, name TEXT, description TEXT, price REAL, category TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY, user_id INTEGER, items TEXT, total REAL, status TEXT, created_at TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS carts (user_id INTEGER PRIMARY KEY, items TEXT)''')

        # Add default menu
        c.execute("SELECT COUNT(*) FROM menu")
        if c.fetchone()[0] == 0:
            menu_data = [
                ("Манты", "Мясные пельмени", 15000, "Основные"),
                ("Плов", "Узбекский плов", 20000, "Основные"),
                ("Шашлык", "Мясо на гриле", 18000, "Основные"),
                ("Суп лапша", "Традиционный суп", 12000, "Супы"),
                ("Хаш", "Согревающий суп", 14000, "Супы"),
                ("Самса", "Жареные треугольники", 8000, "Закуски"),
                ("Чай", "Узбекский чай", 2000, "Напитки"),
                ("Компот", "Свежий компот", 3000, "Напитки"),
            ]
            c.executemany("INSERT INTO menu (name, description, price, category) VALUES (?, ?, ?, ?)", menu_data)

        conn.commit()
        conn.close()

    def get_categories(self):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT DISTINCT category FROM menu ORDER BY category")
        result = [row[0] for row in c.fetchall()]
        conn.close()
        return result

    def get_menu_items(self, category):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT id, name, price FROM menu WHERE category = ?", (category,))
        result = c.fetchall()
        conn.close()
        return result

    def get_item(self, item_id):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM menu WHERE id = ?", (item_id,))
        result = c.fetchone()
        conn.close()
        return result

    def get_cart(self, user_id):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT items FROM carts WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        return json.loads(row[0]) if row else {}

    def save_cart(self, user_id, items):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO carts (user_id, items) VALUES (?, ?)", (user_id, json.dumps(items)))
        conn.commit()
        conn.close()

    def clear_cart(self, user_id):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM carts WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    def create_order(self, user_id, items, total):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("INSERT INTO orders (user_id, items, total, status, created_at) VALUES (?, ?, ?, ?, ?)",
                  (user_id, json.dumps(items), total, "Принят", datetime.now().isoformat()))
        conn.commit()
        order_id = c.lastrowid
        conn.close()
        return order_id

    def get_orders(self, user_id):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        result = c.fetchall()
        conn.close()
        return result

db = FoodDB()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🍜 Добро пожаловать в Япона Мама!\n\nВыберите действие:",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("📋 Меню")],
            [KeyboardButton("🛒 Корзина")],
            [KeyboardButton("📦 Заказы")]
        ], resize_keyboard=True)
    )
    return MAIN_MENU

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if "📋 Меню" in text:
        cats = db.get_categories()
        btns = [[InlineKeyboardButton(c, callback_data=f"cat:{c}")] for c in cats]
        await update.message.reply_text("Выберите категорию:", reply_markup=InlineKeyboardMarkup(btns))
        return VIEWING_MENU

    elif "🛒 Корзина" in text:
        cart = db.get_cart(update.effective_user.id)
        if not cart:
            await update.message.reply_text("Корзина пуста")
            return MAIN_MENU

        total = sum(v['price'] * v['qty'] for v in cart.values())
        txt = "🛒 Корзина:\n\n"
        for k, v in cart.items():
            txt += f"{v['name']} x{v['qty']} = {v['price'] * v['qty']} сум\n"
        txt += f"\nИтого: {total} сум"

        btns = [
            [InlineKeyboardButton("✅ Оформить", callback_data="checkout")],
            [InlineKeyboardButton("🗑️ Очистить", callback_data="clear")]
        ]
        await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(btns))
        return CART_VIEW

    elif "📦 Заказы" in text:
        orders = db.get_orders(update.effective_user.id)
        if not orders:
            await update.message.reply_text("У вас нет заказов")
        else:
            txt = "📦 Ваши заказы:\n\n"
            for o in orders:
                txt += f"Заказ #{o[0]}: {o[4]} | {o[3]} сум | {o[5]}\n"
            await update.message.reply_text(txt)
        return MAIN_MENU

    return MAIN_MENU

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data.startswith("cat:"):
        cat = data.split(":", 1)[1]
        items = db.get_menu_items(cat)
        btns = [[InlineKeyboardButton(f"{i[1]} ({i[2]} сум)", callback_data=f"item:{i[0]}")] for i in items]
        btns.append([InlineKeyboardButton("← Назад", callback_data="back")])
        await query.edit_message_text(f"Категория: {cat}", reply_markup=InlineKeyboardMarkup(btns))
        return VIEWING_MENU

    elif data.startswith("item:"):
        item_id = int(data.split(":", 1)[1])
        item = db.get_item(item_id)
        if item:
            txt = f"🍜 {item[1]}\n\n{item[2]}\n\nЦена: {item[3]} сум"
            btns = [
                [InlineKeyboardButton("➕ В корзину", callback_data=f"add:{item_id}")],
                [InlineKeyboardButton("← Назад", callback_data=f"cat:{item[4]}")]
            ]
            await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(btns))
        return VIEWING_MENU

    elif data.startswith("add:"):
        item_id = int(data.split(":", 1)[1])
        item = db.get_item(item_id)
        if item:
            cart = db.get_cart(user_id)
            key = str(item_id)
            if key in cart:
                cart[key]['qty'] += 1
            else:
                cart[key] = {'name': item[1], 'price': item[3], 'qty': 1}
            db.save_cart(user_id, cart)
            await query.answer("✅ Добавлено в корзину", show_alert=True)
        return VIEWING_MENU

    elif data == "checkout":
        cart = db.get_cart(user_id)
        if not cart:
            await query.edit_message_text("Корзина пуста")
            return CART_VIEW

        total = sum(v['price'] * v['qty'] for v in cart.values())
        context.user_data['total'] = total

        btns = [
            [InlineKeyboardButton("💳 Оплатить", callback_data="pay")],
            [InlineKeyboardButton("← Назад", callback_data="back_cart")]
        ]
        await query.edit_message_text(f"Сумма заказа: {total} сум\n\nПодтвердить оплату?",
                                     reply_markup=InlineKeyboardMarkup(btns))
        return CHECKOUT

    elif data == "pay":
        cart = db.get_cart(user_id)
        total = sum(v['price'] * v['qty'] for v in cart.values())
        order_id = db.create_order(user_id, cart, total)
        db.clear_cart(user_id)

        await query.edit_message_text(
            f"✅ Заказ #{order_id} создан!\n"
            f"Сумма: {total} сум\n"
            f"Статус: Принят\n\n"
            f"Свяжемся с вами: +998 (90) 123-45-67"
        )
        return PAYMENT

    elif data == "clear":
        db.clear_cart(user_id)
        await query.edit_message_text("🗑️ Корзина очищена")
        return MAIN_MENU

    elif data == "back":
        cats = db.get_categories()
        btns = [[InlineKeyboardButton(c, callback_data=f"cat:{c}")] for c in cats]
        await query.edit_message_text("Выберите категорию:", reply_markup=InlineKeyboardMarkup(btns))
        return VIEWING_MENU

    elif data == "back_cart":
        cart = db.get_cart(user_id)
        if not cart:
            await query.edit_message_text("Корзина пуста")
            return MAIN_MENU

        total = sum(v['price'] * v['qty'] for v in cart.values())
        txt = "🛒 Корзина:\n\n"
        for k, v in cart.items():
            txt += f"{v['name']} x{v['qty']} = {v['price'] * v['qty']} сум\n"
        txt += f"\nИтого: {total} сум"

        btns = [
            [InlineKeyboardButton("✅ Оформить", callback_data="checkout")],
            [InlineKeyboardButton("🗑️ Очистить", callback_data="clear")]
        ]
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(btns))
        return CART_VIEW

    return MAIN_MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено")
    return ConversationHandler.END

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ Ошибка: TELEGRAM_BOT_TOKEN не установлен")
        return

    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [MessageHandler(filters.TEXT, main_menu_handler)],
            VIEWING_MENU: [CallbackQueryHandler(callback_handler)],
            CART_VIEW: [CallbackQueryHandler(callback_handler)],
            CHECKOUT: [CallbackQueryHandler(callback_handler)],
            PAYMENT: [CallbackQueryHandler(callback_handler), MessageHandler(filters.TEXT, main_menu_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    print("✅ Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
