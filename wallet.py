import sqlite3
from aiogram.types import LabeledPrice
import os
from dotenv import load_dotenv

load_dotenv()

PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")

def init_db():
    conn = sqlite3.connect('wallet.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS wallet (
            user_id INTEGER PRIMARY KEY,
            balance REAL NOT NULL DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def get_balance(user_id):
    conn = sqlite3.connect('wallet.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM wallet WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def update_balance(user_id, amount):
    conn = sqlite3.connect('wallet.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO wallet (user_id, balance) VALUES (?, ?)', (user_id, 0))
    cursor.execute('UPDATE wallet SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

async def send_invoice(bot, chat_id, price_rubles: float):
    prices = [LabeledPrice(label="Пополнение кошелька", amount=int(price_rubles * 100))]
    await bot.send_invoice(
        chat_id,
        title="Пополнение кошелька",
        description=f"Пополнение на сумму: {price_rubles:.2f} RUB",
        provider_token=PAYMENT_TOKEN,
        currency="RUB",
        prices=prices,
        start_parameter="wallet_funding",
        payload="wallet_funding_payload"
    )
