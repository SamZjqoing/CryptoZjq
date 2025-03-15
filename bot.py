# bot.py

import logging
import requests
import time
import datetime
from datetime import time as dtime

import pandas as pd
import ta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext

import config  # config.py must contain TELEGRAM_TOKEN

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global variables
user_chat_id = None
cache = {}
# Define coins: key = coin_id in CoinGecko, display = Persian name with symbol
COINS = {
    "cardano": "کاردانو (ADA)",
    "ripple": "ریپل (XRP)",
    "ethereum": "اتریوم (ETH)",
    "bitcoin": "بیت کوین (BTC)"
}

def fetch_candlestick_data(coin_id, days=7):
    """
    Fetch OHLC data from CoinGecko for a given coin.
    Returns data as a list of lists: [timestamp, open, high, low, close]
    """
    cache_key = f"{coin_id}_{days}"
    current_time = time.time()
    if cache_key in cache:
        cached_data, timestamp = cache[cache_key]
        if current_time - timestamp < 60:
            return cached_data
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {"vs_currency": "usd", "days": days}
    response = requests.get(url, params=params)
    data = response.json()
    cache[cache_key] = (data, current_time)
    return data

def analyze_coin_advanced(coin_id, coin_display):
    """
    Analyze coin data using technical indicators to calculate:
      - Current price (USD)
      - Weekly percentage change (based on price from Saturday)
      - Final signal: "سیگنال خرید"، "سیگنال فروش" یا "خنثی"
    """
    data = fetch_candlestick_data(coin_id, days=7)
    if not data or len(data) < 20:
        return f"{coin_display}: داده کافی موجود نیست.", "خنثی", 0.0

    df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close"])
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.sort_values("timestamp", inplace=True)
    
    # فرض کنید اولین داده هفته شنبه است
    starting_price = df["close"].iloc[0]
    current_price = df["close"].iloc[-1]
    weekly_change = (current_price - starting_price) / starting_price * 100

    # محاسبه برخی شاخص‌های فنی ساده (برای اطلاع‌رسانی)
    rsi = ta.momentum.rsi(df["close"], window=14).iloc[-1]
    sma20 = df["close"].rolling(window=20).mean().iloc[-1]
    macd = ta.trend.macd(df["close"]).iloc[-1]
    macd_signal = ta.trend.macd_signal(df["close"]).iloc[-1]
    macd_diff = macd - macd_signal

    # منطق سیگنال نهایی ساده:
    # اگر درصد تغییر مثبت و RSI کمتر از 40 باشد → سیگنال خرید
    # اگر درصد تغییر منفی و RSI بالای 60 باشد → سیگنال فروش
    # در غیر این صورت → خنثی
    if weekly_change > 0 and rsi < 40:
        signal = "سیگنال خرید"
    elif weekly_change < 0 and rsi > 60:
        signal = "سیگنال فروش"
    else:
        signal = "خنثی"

    message = f"{coin_display}:\n"
    message += f"قیمت فعلی: {current_price:.2f} USD\n"
    message += f"تغییرات هفتگی: {weekly_change:.2f}%\n"
    message += f"سیگنال: {signal}"
    return message, signal, weekly_change

def analyze_market_advanced():
    """
    Generate a weekly summary for all coins.
    """
    messages = []
    for coin_id, coin_display in COINS.items():
        msg, signal, change = analyze_coin_advanced(coin_id, coin_display)
        messages.append(msg)
    overall_message = "\n\n".join(messages)
    return overall_message

def ada_command(update: Update, context: CallbackContext):
    msg, signal, change = analyze_coin_advanced("cardano", COINS["cardano"])
    update.message.reply_text(msg, parse_mode="Markdown")

def btc_command(update: Update, context: CallbackContext):
    msg, signal, change = analyze_coin_advanced("bitcoin", COINS["bitcoin"])
    update.message.reply_text(msg, parse_mode="Markdown")

def eth_command(update: Update, context: CallbackContext):
    msg, signal, change = analyze_coin_advanced("ethereum", COINS["ethereum"])
    update.message.reply_text(msg, parse_mode="Markdown")

def xrp_command(update: Update, context: CallbackContext):
    msg, signal, change = analyze_coin_advanced("ripple", COINS["ripple"])
    update.message.reply_text(msg, parse_mode="Markdown")

def menu_command(update: Update, context: CallbackContext):
    """
    Send a main menu with buttons for each coin.
    """
    keyboard = [
        [InlineKeyboardButton("کاردانو (ADA)", callback_data="ada")],
        [InlineKeyboardButton("بیت کوین (BTC)", callback_data="btc")],
        [InlineKeyboardButton("اتریوم (ETH)", callback_data="eth")],
        [InlineKeyboardButton("ریپل (XRP)", callback_data="xrp")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("لطفاً یکی از ارزها را انتخاب کنید:", reply_markup=reply_markup)

def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data
    if data == "ada":
        msg, _, _ = analyze_coin_advanced("cardano", COINS["cardano"])
    elif data == "btc":
        msg, _, _ = analyze_coin_advanced("bitcoin", COINS["bitcoin"])
    elif data == "eth":
        msg, _, _ = analyze_coin_advanced("ethereum", COINS["ethereum"])
    elif data == "xrp":
        msg, _, _ = analyze_coin_advanced("ripple", COINS["ripple"])
    else:
        msg = "دستور نامعتبر است."
    query.edit_message_text(text=msg, parse_mode="Markdown")

def start_command(update: Update, context: CallbackContext):
    global user_chat_id
    user_chat_id = update.effective_chat.id
    # ارسال پیام اولیه هفتگی
    weekly_msg = analyze_market_advanced()
    update.message.reply_text("پیام هفتگی:\n" + weekly_msg, parse_mode="Markdown")
    # ارسال منوی اصلی
    menu_command(update, context)

def signal_command(update: Update, context: CallbackContext):
    # در هر زمان درخواست کاربر، تحلیل لحظه‌ای (قیمت لحظه‌ای) ارسال می‌شود
    overall_msg = analyze_market_advanced()
    update.message.reply_text(overall_msg, parse_mode="Markdown")

def scheduled_signal(context: CallbackContext):
    """
    Scheduled job to send weekly summary every Saturday at 8 AM Tehran time.
    """
    global user_chat_id
    if user_chat_id:
        msg = analyze_market_advanced()
        context.bot.send_message(chat_id=user_chat_id, text="پیام هفتگی:\n" + msg, parse_mode="Markdown")

def main():
    updater = Updater(config.TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Command handlers
    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CommandHandler("signal", signal_command))
    dp.add_handler(CommandHandler("menu", menu_command))
    dp.add_handler(CommandHandler("ada", ada_command))
    dp.add_handler(CommandHandler("btc", btc_command))
    dp.add_handler(CommandHandler("eth", eth_command))
    dp.add_handler(CommandHandler("xrp", xrp_command))
    dp.add_handler(CallbackQueryHandler(button_callback))

    # Schedule weekly job: every Saturday at 4:30 UTC (8:00 Tehran assuming UTC+3:30)
    # run_daily(callback, time, days) : Saturday is weekday 5 (Monday=0,...,Sunday=6)
    schedule_time = dtime(4, 30, 0)
    dp.job_queue.run_daily(scheduled_signal, schedule_time, days=(5,))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
