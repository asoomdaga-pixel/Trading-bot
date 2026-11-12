import asyncio
import logging
import sqlite3
import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# === التوكن الخاص بك ===
TOKEN = "9098302700:AAE_F4b9PKUkQxAZNePcKZztKG1ly469RXI"

logging.basicConfig(level=logging.INFO)
router = Router()


# === إعداد قاعدة البيانات للتنبيهات ===
def init_db():
  conn = sqlite3.connect("market_bot.db")
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            target_price REAL
        )
    """)
  conn.commit()
  conn.close()


init_db()


# === حالات FSM لضبط التنبيهات والبحث ===
class AlertState(StatesGroup):
  waiting_for_symbol = State()
  waiting_for_price = State()


# === دالة جلب أسعار العملات الرقمية ===
async def get_crypto_price(symbol: str):
  url = f"https://api.coingecko.com/api/v3/simple/price?ids={symbol.lower()}&vs_currencies=usd"
  try:
    async with aiohttp.ClientSession() as session:
      async with session.get(url) as response:
        if response.status == 200:
          data = await response.json()
          return data.get(symbol.lower(), {}).get("usd")
  except Exception:
    pass
  return None


# === أزرار القائمة الرئيسية ===
def main_menu_keyboard():
  return InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🔍 بحث عن عملة / أصل", callback_data="search_asset"
              ),
              InlineKeyboardButton(
                  text="⏰ ضبط تنبيه سعر", callback_data="set_alert"
              ),
          ],
          [InlineKeyboardButton(text="📋 تنبيهاتي النشطة", callback_data="my_alerts")],
      ]
  )


@router.message(Command("start"))
async def cmd_start(message: Message):
  await message.answer(
      "📊 **مرحباً بك في بوت مراقبة الأسواق والذكاء المالي**\n\nاختر ما يناسبك:",
      reply_markup=main_menu_keyboard(),
  )


@router.callback_query(F.data == "back_home")
async def back_home(callback: CallbackQuery):
  await callback.message.edit_text(
      "📊 **القائمة الرئيسية:**", reply_markup=main_menu_keyboard()
  )
  await callback.answer()


# === 1. ميزة البحث الشامل ===
@router.callback_query(F.data == "search_asset")
async def search_start(callback: CallbackQuery, state: FSMContext):
  await callback.message.answer(
      "🔍 أرسل اسم أو رمز الأصل باللغة الإنجليزية (مثلاً: `bitcoin`,"
      " `solana`, `ethereum`):"
  )
  await state.set_state(AlertState.waiting_for_symbol)
  await callback.answer()


@router.message(AlertState.waiting_for_symbol)
async def process_search(message: Message, state: FSMContext):
  symbol = message.text.strip().lower()
  price = await get_crypto_price(symbol)

  if price is not None:
    await message.answer(
        f"✅ **نتيجة البحث:**\n- الأصل: `{symbol.upper()}`\n- السعر الحالي:"
        f" **{price} $**"
    )
  else:
    await message.answer(
        "❌ لم يتم العثور على هذا الأصل. تأكد من كتابة الرمز الصحيح (مثال:"
        " `bitcoin`)."
    )

  await state.clear()
  await message.answer("القائمة الرئيسية:", reply_markup=main_menu_keyboard())


# === 2. نظام التنبيهات التلقائية ===
@router.callback_query(F.data == "set_alert")
async def alert_start(callback: CallbackQuery, state: FSMContext):
  await callback.message.answer(
      "⏰ أرسل رمز العملة التي تريد مراقبتها (مثال: `bitcoin` أو `solana`):"
  )
  await state.set_state(AlertState.waiting_for_symbol)
  await callback.answer()


@router.message(AlertState.waiting_for_symbol)
async def alert_get_symbol(message: Message, state: FSMContext):
  await state.update_data(symbol=message.text.strip().lower())
  await message.answer("💰 أرسل السعر المستهدف بالدولار (أرقام فقط، مثال: 150):")
  await state.set_state(AlertState.waiting_for_price)


@router.message(AlertState.waiting_for_price)
async def alert_save(message: Message, state: FSMContext):
  try:
    target_price = float(message.text)
    data = await state.get_data()
    symbol = data["symbol"]

    conn = sqlite3.connect("market_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO alerts (user_id, symbol, target_price) VALUES (?, ?, ?)",
        (message.from_user.id, symbol, target_price),
    )
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(
        f"✅ **تم حفظ التنبيه بنجاح!**\nسننبهك فور وصول `{symbol.upper()}` إلى"
        f" السعر المستهدف: `{target_price}$`",
        reply_markup=main_menu_keyboard(),
    )
  except ValueError:
    await message.answer("❌ يرجى إدخال رقم صحيح للسعر:")


@router.callback_query(F.data == "my_alerts")
async def show_my_alerts(callback: CallbackQuery):
  conn = sqlite3.connect("market_bot.db")
  cursor = conn.cursor()
  cursor.execute(
      "SELECT alert_id, symbol, target_price FROM alerts WHERE user_id = ?",
      (callback.from_user.id,),
  )
  alerts = cursor.fetchall()
  conn.close()

  if not alerts:
    await callback.message.edit_text(
        "📭 ليس لديك أي تنبيهات نشطة حالياً.", reply_markup=main_menu_keyboard()
    )
    return

  text = "📋 **تنبيهاتك النشطة:**\n\n"
  for alert_id, symbol, target in alerts:
    text += (
        f"🆔 رقم ({alert_id}) | الأصل: **{symbol.upper()}** | الهدف:"
        f" **{target}$**\n"
    )

  await callback.message.edit_text(text, reply_markup=main_menu_keyboard())
  await callback.answer()


# === مهمة الخلفية لفحص الأسعار وإرسال التنبيهات تلقائياً ===
async def check_market_alerts(bot: Bot):
  while True:
    try:
      conn = sqlite3.connect("market_bot.db")
      cursor = conn.cursor()
      cursor.execute("SELECT alert_id, user_id, symbol, target_price FROM alerts")
      alerts = cursor.fetchall()

      for alert_id, user_id, symbol, target_price in alerts:
        current_price = await get_crypto_price(symbol)
        if current_price is not None:
          if current_price >= target_price:
            try:
              await bot.send_message(
                  user_id,
                  f"🚨 **تنبيه السعر المستهدف!**\nالأصل `{symbol.upper()}` وصل"
                  f" إلى السعر الحالي: **{current_price}$** (الهدف كان:"
                  f" `{target_price}$`)",
              )
              cursor.execute("DELETE FROM alerts WHERE alert_id = ?", (alert_id,))
              conn.commit()
            except Exception:
              pass
      conn.close()
    except Exception as e:
      logging.error(f"Alert background task error: {e}")

    await asyncio.sleep(60)


async def main():
  bot = Bot(token=TOKEN)
  dp = Dispatcher(storage=MemoryStorage())
  dp.include_router(router)

  # تشغيل فاحص الأسعار في الخلفية
  asyncio.create_task(check_market_alerts(bot))

  print("🚀 Market Tracking Bot is active and running!")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
