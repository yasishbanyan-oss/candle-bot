import logging
import asyncio
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)

# --- سرور فرضی برای فعال نگه داشتن ربات روی پلن رایگان Render ---
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Candle Bot is running successfully!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

# تنظیمات لوگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

OWNER_ID = 6749949992
WAITING_FOR_CANDLE_COUNT = 1

# دیتابیس حافظه‌ای
user_data_db = {}

def get_user_data(user_id: int):
    is_new_user = user_id not in user_data_db
    if is_new_user:
        user_data_db[user_id] = {
            "worker": "👨‍🏭 حسین علوی (استادکار)",
            "slogans_count": 0,
            "last_slogan_time": None,
            "has_boost": False,
            "candles": 200,          # 🎁 ۲۰۰ شمع هدیه ورود اولیه!
            "total_extracted": 0,
            "is_extracting": False,
            "extraction_end_time": None,
            "pending_candles": 0,
            "ready_candles": 0,
            "worker_tired": False,
            "inventory_sholeh": 0,
            "last_msg_id": None,
            "chat_id": None,
            "username": None,
            "full_name": "",
            "claimed_welcome_gift": True
        }
    return user_data_db[user_id], is_new_user

def get_factory_level(total_candles: int) -> str:
    if total_candles < 100:
        return "🛠 کارگاه زیرزمینی"
    elif total_candles < 500:
        return "⚡ کارخونه خفن"
    elif total_candles < 2000:
        return "👑 ابرکارخونه پارافین"
    else:
        return "🔥 امپراطوری شمع‌سازی"

# --- ۱. دستور START ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    data, is_new = get_user_data(user_id)
    
    welcome_gift_msg = ""
    if is_new:
        welcome_gift_msg = "\n\n🎁 ۲۰۰ عدد شمع هدیه ورودی به انبار شما اضافه شد!"

    text = (
        "🔥 خوش اومدی به ابرکارخونه شمع‌سازی! 🕯"
        f"{welcome_gift_msg}\n\n"
        "📜 راهنمای دستورات بازی:\n"
        "🔹 کارخونه شمع سازی ➔ شروع استخراج و مدیریت کارگر\n"
        "🔹 جاوید حسین علوی ➔ حمایت و گرفتن بوست ۲ برابری\n"
        "🔹 شمع هام ➔ وضعیت حساب و انبار شمع‌ها\n"
        "🔹 خرید شله ➔ خرید غذا برای حسین علوی خسته\n"
        "🔹 اشپزخونه ➔ غذادهی به استادکار\n"
        "🔹 جدول برترین‌ها ➔ ۱۰ شمع‌ساز برتر\n\n"
        "📢 کانال ما: https://t.me/IR_Mafioso"
    )
    await update.message.reply_text(text, reply_to_message_id=update.message.message_id)

# --- ۲. کارخونه شمع سازی ---
async def start_factory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    data, _ = get_user_data(user_id)
    data["chat_id"] = update.message.chat_id
    data["username"] = update.message.from_user.username
    data["full_name"] = update.message.from_user.full_name

    now = datetime.now()

    # ۱. اگر شمع آماده برداشت است
    if data["ready_candles"] > 0:
        keyboard = [[InlineKeyboardButton("📦 برداشت فوری شمع‌ها 🕯", callback_data="claim_candles")]]
        await update.message.reply_text(
            f"🎉 رئیس! بار جدید رسید!\n"
            f"📦 شمع‌های آماده برداشت: {data['ready_candles']} عدد\n\n"
            f"بزن رو دکمه زیر تا بریزیمشون تو انبارت 👇",
            reply_markup=InlineKeyboardMarkup(keyboard),
            reply_to_message_id=update.message.message_id
        )
        return

    # ۲. اگر در حال استخراج است
    if data["is_extracting"] and data["extraction_end_time"]:
        if now < data["extraction_end_time"]:
            remaining_sec = int((data["extraction_end_time"] - now).total_seconds())
            rem_min = max(1, remaining_sec // 60)
            
            keyboard = []
            if data["has_boost"]:
                keyboard.append([InlineKeyboardButton("🚀 استفاده از بوست ۲ برابر", callback_data="use_boost")])
            
            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            
            await update.message.reply_text(
                f"⚠️ رئیس! حسین علوی الان رو خطه داره کار میکنه!\n"
                f"⏳ زمان باقی‌مانده: حدود {rem_min} دقیقه\n"
                f"لطفاً شکیبا باشید تا کارش تموم شه...",
                reply_markup=reply_markup,
                reply_to_message_id=update.message.message_id
            )
            return

    # ۳. اگر کارگر خسته است
    if data["worker_tired"]:
        await update.message.reply_text(
            "🛑 رئیس! حسین علوی دست از کار کشیده!\n"
            "میگه: تا شله مشهدی نخورم دست به پارافین نمیزنم! 🍲\n\n"
            "🛒 با دستور (خرید شله) بخرش و بعد با (اشپزخونه) بده بخوره تا راه بیفته!",
            reply_to_message_id=update.message.message_id
        )
        return

    # ۴. انتخاب کارگر
    keyboard = [
        [InlineKeyboardButton("👨‍🏭 حسین علوی (استادکار پارافین)", callback_data="select_worker_alavi")],
        [InlineKeyboardButton("🔒 کارگر جدید (بزودی...)", callback_data="select_worker_soon")]
    ]
    await update.message.reply_text(
        "🏭 وارد کارخونه شمع‌سازی شدی!\nکارگرت رو انتخاب کن ببینم چه کاره‌ای:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        reply_to_message_id=update.message.message_id
    )

async def handle_worker_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "select_worker_soon":
        await query.answer("❌ این کارگر هنوز قفل است!", show_alert=True)
        return
        
    if query.data == "select_worker_alavi":
        await query.edit_message_text(
            "🕯 چندتا شمع میخوای واست استخراج کنه؟\n"
            "تعداد رو عدد بفرست برام:"
        )
        return WAITING_FOR_CANDLE_COUNT

async def get_candle_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("❌ داداش فقط عدد درست بفرست!", reply_to_message_id=update.message.message_id)
        return WAITING_FOR_CANDLE_COUNT
        
    count = int(text)
    user_id = update.message.from_user.id
    data, _ = get_user_data(user_id)
    data["pending_candles"] = count
    
    duration_minutes = max(1, count // 10)
    
    keyboard = [
        [
            InlineKeyboardButton("✅ بله، شروع کن", callback_data="confirm_extract_yes"),
            InlineKeyboardButton("❌ نه، بیخیال", callback_data="confirm_extract_no")
        ]
    ]
    await update.message.reply_text(
        f"⏱ زمان لازم برای استخراج {count} عدد شمع: حدود {duration_minutes} دقیقه\n"
        f"اوکیه؟ استخراج شروع بشه؟",
        reply_markup=InlineKeyboardMarkup(keyboard),
        reply_to_message_id=update.message.message_id
    )
    return ConversationHandler.END

async def handle_extraction_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data, _ = get_user_data(user_id)
    
    if query.data == "confirm_extract_no":
        await query.edit_message_text("❌ استخراج لغو شد.")
        return

    if query.data == "confirm_extract_yes":
        count = data["pending_candles"]
        duration_minutes = max(1, count // 10)
        
        data["is_extracting"] = True
        data["extraction_end_time"] = datetime.now() + timedelta(minutes=duration_minutes)
        
        await query.edit_message_text(
            f"🛠 حسین علوی پیش‌بندشو بست و رفت تو معدن! 🕯\n"
            f"در حال استخراج {count} عدد شمع...\n"
            f"⏳ حدود {duration_minutes} دقیقه دیگه تمومه!"
        )

        asyncio.create_task(wait_for_extraction_finish(context, user_id, duration_minutes * 60))

async def wait_for_extraction_finish(context: ContextTypes.DEFAULT_TYPE, user_id: int, wait_seconds: int):
    await asyncio.sleep(wait_seconds)
    data, _ = get_user_data(user_id)
    
    if data["is_extracting"]:
        data["is_extracting"] = False
        data["ready_candles"] = data["pending_candles"]
        data["pending_candles"] = 0
        
        user_mention = f"[{data['full_name']}](tg://user?id={user_id})"
        await context.bot.send_message(
            chat_id=data["chat_id"],
            text=f"🔔 رئیس {user_mention}!\n"
                 f"حسین علوی بار شمع‌ها رو آورد دم کارخونه! 🕯🎉\n"
                 f"با دستور (کارخونه شمع سازی) بارت رو بزن تو انبار!"
        )

# --- ۳. سیستم بوست ---
async def ask_use_boost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [
            InlineKeyboardButton("⚡ بله، زمان نصف بشه", callback_data="boost_confirm_yes"),
            InlineKeyboardButton("🔴 نه، بعداً", callback_data="boost_confirm_no")
        ]
    ]
    await query.message.reply_text(
        "🚀 میخوای نیترو بزنی و زمان استخراج رو نصف کنی؟",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_boost_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data, _ = get_user_data(user_id)
    
    if query.data == "boost_confirm_yes" and data["is_extracting"]:
        data["has_boost"] = False
        now = datetime.now()
        rem_seconds = (data["extraction_end_time"] - now).total_seconds()
        
        new_rem_seconds = max(5, rem_seconds / 2)
        data["extraction_end_time"] = now + timedelta(seconds=new_rem_seconds)
        
        new_min = max(1, int(new_rem_seconds // 60))
        await query.edit_message_text(
            f"🔥 بوست فعال شد! سرعت استخراج دو برابر شد!\n"
            f"⏱ زمان باقی‌مانده به {new_min} دقیقه کاهش یافت!"
        )
    else:
        await query.edit_message_text("❌ فعلاً از بوست استفاده نشد.")

# --- ۴. برداشت محصول ---
async def handle_claim_candles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data, _ = get_user_data(user_id)
    
    claimed = data["ready_candles"]
    data["candles"] += claimed
    data["total_extracted"] += claimed
    data["ready_candles"] = 0
    data["worker_tired"] = True 
    
    await query.edit_message_text(
        f"✨ دمت گرم! {claimed} عدد شمع اومد تو انبارت! 🕯📦\n\n"
        f"😴 حسین علوی خسته شد و افتاد گوشه کارخونه... میگه تا شله مشهدی برام نخری دیگه جاشمعی رو هم جابه‌جا نمیکنم!"
    )

# --- ۵. خرید شله و آشپزخانه ---
async def start_buy_sholeh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    data, _ = get_user_data(user_id)
    cost = 20
    
    if data["candles"] < cost:
        await update.message.reply_text(
            f"❌ جیبت خالیه رئیس!\nبرای خرید شله مشهدی حداقل {cost} عدد شمع لازمه.",
            reply_to_message_id=update.message.message_id
        )
        return

    keyboard = [
        [
            InlineKeyboardButton("🍲 آره، ۲۰ تا شمع بده شله بخر", callback_data="buy_sholeh_yes"),
            InlineKeyboardButton("❌ نه، پشیمون شدم", callback_data="buy_sholeh_no")
        ]
    ]
    await update.message.reply_text(
        f"🍲 قیمت یک کاسه شله مشهدی مشتی: ۲۰ عدد شمع\nموافقی کسر بشه؟",
        reply_markup=InlineKeyboardMarkup(keyboard),
        reply_to_message_id=update.message.message_id
    )

async def handle_sholeh_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data, _ = get_user_data(user_id)
    cost = 20

    if query.data == "buy_sholeh_yes":
        if data["candles"] >= cost:
            data["candles"] -= cost
            data["inventory_sholeh"] += 1
            await query.edit_message_text(
                "🍲 شله مشهدی داغ با قیمه فراوان خریداری شد!\n"
                "حالا با دستور (اشپزخونه) بده حسین علوی بزنه بر بدن!"
            )
        else:
            await query.edit_message_text("❌ شمع کافی نداری!")
    else:
        await query.edit_message_text("❌ خرید شله لغو شد.")

async def open_kitchen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    data, _ = get_user_data(user_id)

    if data["inventory_sholeh"] <= 0:
        await update.message.reply_text(
            "❌ تو انبارت هیچ شله‌ای نداری!\nاول با دستور (خرید شله) یکی بخر بعد بیا اینجا.",
            reply_to_message_id=update.message.message_id
        )
        return

    keyboard = [
        [InlineKeyboardButton("👨‍🏭 حسین علوی", callback_data="kitchen_feed_alavi")]
    ]
    await update.message.reply_text(
        "🍳 به آشپزخونه کارخونه خوش اومدی!\nغذا رو می‌خوای بدی به کدوم کارگر؟",
        reply_markup=InlineKeyboardMarkup(keyboard),
        reply_to_message_id=update.message.message_id
    )

async def handle_kitchen_feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "kitchen_feed_alavi":
        keyboard = [
            [InlineKeyboardButton("🍲 شله مشهدی پر قیمه", callback_data="feed_sholeh_confirm")]
        ]
        await query.edit_message_text(
            "چی میخوای بدی حسین علوی بخوره؟",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_feed_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data, _ = get_user_data(user_id)

    if data["inventory_sholeh"] > 0:
        data["inventory_sholeh"] -= 1
        data["worker_tired"] = False
        await query.edit_message_text(
            "😋 به به! حسین علوی شله رو زد بر بدن و مشتی قبراط شد!\n"
            "میگه: رئیس امر بفرما بریم برای استخراج بعدی! 🚀"
        )

# --- ۶. شعار و بوست ---
async def handle_slogan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    data, _ = get_user_data(user_id)
    now = datetime.now()
    
    if data["last_slogan_time"] and (now - data["last_slogan_time"]) < timedelta(minutes=10):
        await update.message.reply_text(
            "✋ فرزندم! شما دقایقی قبل حمایت خود را اعلام کردید!\n"
            "لطفاً صبر کنید تا تایم ربات برای حمایت ثانویه به اتمام برسد!",
            reply_to_message_id=update.message.message_id
        )
        return

    data["last_slogan_time"] = now
    data["slogans_count"] += 1
    data["has_boost"] = True
    
    await update.message.reply_text(
        "🎉 ایول! به دلیل حمایت از حقوق کارگران معدن شمع، برنده‌ی یک بوست سرعت شدی! ⚡",
        reply_to_message_id=update.message.message_id
    )

# --- ۷. جدول برترین‌ها ---
async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sorted_users = sorted(user_data_db.items(), key=lambda x: x[1]["total_extracted"], reverse=True)[:10]
    
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    text = "⚔️ جدول سراسری نفرات برتر شمع‌سازی :\n\n"
    
    if not sorted_users:
        text += "هنوز هیچ شمع‌سازی ثبت نام نکرده!"
    else:
        for idx, (uid, udata) in enumerate(sorted_users):
            uname = f"@{udata['username']}" if udata['username'] else udata['full_name']
            text += f"{medals[idx]} - {udata['full_name']} - {uname} - {udata['total_extracted']} 🕯\n\n"

    await update.message.reply_text(text, reply_to_message_id=update.message.message_id)

# --- ۸. پروفایل (شمع هام) ---
async def show_my_candles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    data, _ = get_user_data(user.id)
    
    boost_status = "⚡ دارد" if data["has_boost"] else "❌ ندارد"
    factory_lvl = get_factory_level(data["total_extracted"])
    
    caption_text = (
        f"👤 نام شما: {user.full_name}\n"
        f"🆔 آیدی عددی شما: {user.id}\n"
        f"📢 تعداد شعارهای شما: {data['slogans_count']}\n"
        f"👨‍🏭 کارگر انتخاب شده: {data['worker']}\n"
        f"🕯 شمع‌های موجود در انبار: {data['candles']} عدد\n"
        f"📊 کل شمع‌های استخراج شده: {data['total_extracted']} عدد\n"
        f"🏭 لول کارخونه شما: {factory_lvl}\n"
        f"🚀 وضعیت بوست: {boost_status}\n\n"
        f"📣 کانال رسمی ما: https://t.me/IR_Mafioso"
    )
    
    user_photos = await context.bot.get_user_profile_photos(user.id, limit=1)
    if user_photos.total_count > 0:
        await update.message.reply_photo(
            photo=user_photos.photos[0][-1].file_id,
            caption=caption_text,
            reply_to_message_id=update.message.message_id
        )
    else:
        await update.message.reply_text(
            caption_text,
            reply_to_message_id=update.message.message_id
        )

# --- ۹. اجرا ---
def main():
    # روشن کردن سرور وب فرضی در پس‌زمینه برای Render
    threading.Thread(target=run_dummy_server, daemon=True).start()

    TOKEN = "8998529794:AAGIbI-TB9PesR3XepE8IFlpmTzbtoCZXFE"
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^کارخونه شمع سازی$"), start_factory),
            CallbackQueryHandler(handle_worker_selection, pattern="^select_worker_")
        ],
        states={
            WAITING_FOR_CANDLE_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_candle_count)
            ]
        },
        fallbacks=[]
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(handle_extraction_confirmation, pattern="^confirm_extract_"))
    app.add_handler(CallbackQueryHandler(ask_use_boost, pattern="^use_boost$"))
    app.add_handler(CallbackQueryHandler(handle_boost_decision, pattern="^boost_confirm_"))
    app.add_handler(CallbackQueryHandler(handle_claim_candles, pattern="^claim_candles$"))
    
    # غذادهی
    app.add_handler(MessageHandler(filters.Regex("^خرید شله$"), start_buy_sholeh))
    app.add_handler(CallbackQueryHandler(handle_sholeh_purchase, pattern="^buy_sholeh_"))
    app.add_handler(MessageHandler(filters.Regex("^اشپزخونه$"), open_kitchen))
    app.add_handler(CallbackQueryHandler(handle_kitchen_feed, pattern="^kitchen_feed_"))
    app.add_handler(CallbackQueryHandler(handle_feed_confirm, pattern="^feed_sholeh_confirm$"))

    # بقیه دستورات
    app.add_handler(MessageHandler(filters.Regex("^جاوید حسین علوی$"), handle_slogan))
    app.add_handler(MessageHandler(filters.Regex("^شمع هام$"), show_my_candles))
    app.add_handler(MessageHandler(filters.Regex("^جدول برترین‌ها$"), show_leaderboard))

    print("ربات آماده آپلود است...")
    app.run_polling()

if __name__ == "__main__":
    main()
