import logging
import asyncio
import os
from datetime import datetime, timedelta
from aiohttp import web
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

# تنظیمات لوگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

OWNER_ID = 6749949992

# وضعیت‌های گفتگو (States)
WAITING_FOR_DRUG_COUNT = 1
WAITING_FOR_WORKER_NAME = 2

# دیتابیس حافظه‌ای
user_data_db = {}

# لیست شعارهای مجاز
ALLOWED_SLOGANS = [
    "سلامتی ساقی خسته",
    "نوید پیوی رو سین کن",
    "درود بر کارگران معدن",
    "جاویدان باد کارگر زحمتکش",
    "جاویدان باد کارگر زحمت کش",
    "جاویدان باد کارگر زحمت‌کش"
]

def get_user_data(user_id: int):
    is_new_user = user_id not in user_data_db
    if is_new_user:
        user_data_db[user_id] = {
            "workers": [],             # لیست کارگران ساخته شده
            "selected_worker": None,   # کارگر انتخاب شده فعلی
            "slogans_count": 0,
            "last_slogan_time": None,
            "has_boost": False,
            "drugs": 200,              # 🎁 ۲۰۰ بسته شیشه هدیه ورودی
            "total_extracted": 0,
            "is_extracting": False,
            "extraction_end_time": None,
            "pending_drugs": 0,
            "ready_drugs": 0,
            "worker_tired": False,
            "inventory_energy": 0,     # تعداد پک انرژی برای رفع خستگی
            "chat_id": None,
            "username": None,
            "full_name": ""
        }
    return user_data_db[user_id], is_new_user

def get_empire_level(total_drugs: int) -> str:
    if total_drugs < 100:
        return "🏚 ساقیه خرده‌پا"
    elif total_drugs < 500:
        return "⚡ توزیع‌کننده منطقه‌ای"
    elif total_drugs < 2000:
        return "👑 کارتل بزرگ"
    else:
        return "🔥 امپراطوری قاچاق"

# --- ۱. دستور START ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    data, is_new = get_user_data(user_id)
    
    welcome_gift_msg = ""
    if is_new:
        welcome_gift_msg = "\n\n🎁 ۲۰۰ بسته شیشه هدیه ورودی به انبار مخفی شما اضافه شد!"

    text = (
        "💀 به بازی قاچاق‌گیم خوش آمدید! ❄️"
        f"{welcome_gift_msg}\n\n"
        "📜 راهنمای دستورات امپراطوری:\n"
        "🏭 مقر قاچاق ➔ شروع تولید و تولید بسته‌ها\n"
        "🔨 ساختن کارگر ➔ استخدام کارگر جدید با اسم دلخواه\n"
        "📢 ارسال یکی از شعارها ➔ گرفتن بوست سرعت ۲ برابری\n"
        "📦 جنس هام ➔ وضعیت انبار و کارتل شما\n"
        "🛒 خرید انرژی ➔ خرید پک انرژی برای کارگر خسته\n"
        "🍲 اشپزخونه ➔ تجدید قوا و سوخت‌رسانی به کارگر\n"
        "🏆 برترین ‌های قاچاق ➔ ۱۰ قاچاقچی برتر\n\n"
        "📢 کانال ما: https://t.me/IR_Mafioso"
    )
    await update.message.reply_text(text, reply_to_message_id=update.message.message_id)

# --- ۲. ساختن کارگر اختصاصی ---
async def start_create_worker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 اسم کارگر جدیدت رو بفرست تا برات استخدامش کنم:",
        reply_to_message_id=update.message.message_id
    )
    return WAITING_FOR_WORKER_NAME

async def save_worker_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    worker_name = update.message.text.strip()
    user_id = update.message.from_user.id
    data, _ = get_user_data(user_id)
    
    if len(worker_name) > 30:
        await update.message.reply_text("❌ اسم کارگر خیلی طولانیه! یه اسم کوتاه‌تر بفرست:", reply_to_message_id=update.message.message_id)
        return WAITING_FOR_WORKER_NAME

    data["workers"].append(worker_name)
    data["selected_worker"] = worker_name
    
    await update.message.reply_text(
        f"✅ کارگر جدید با نام (👨‍🏭 {worker_name}) با موفقیت استخدام شد و رو خط قرار گرفت!\n"
        f"حالا با دستور (مقر قاچاق) کارش رو شروع کن.",
        reply_to_message_id=update.message.message_id
    )
    return ConversationHandler.END

# --- ۳. مقر قاچاق (مدیریت تولید) ---
async def start_headquarters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    data, _ = get_user_data(user_id)
    data["chat_id"] = update.message.chat_id
    data["username"] = update.message.from_user.username
    data["full_name"] = update.message.from_user.full_name

    now = datetime.now()

    if not data["workers"]:
        await update.message.reply_text(
            "⚠️ شما هنوز هیچ کارگری ندارید!\n"
            "ابتدا با ارسال دستور (ساختن کارگر) یک کارگر برای خود بسازید.",
            reply_to_message_id=update.message.message_id
        )
        return

    if data["ready_drugs"] > 0:
        keyboard = [[InlineKeyboardButton("📦 انبار کردن جنس‌ها ❄️", callback_data="claim_drugs")]]
        await update.message.reply_text(
            f"🎉 رئیس! محموله آماده شد!\n"
            f"📦 بسته‌های آماده تحویل: {data['ready_drugs']} عدد شیشه\n\n"
            f"برای انتقال به انبار دکمه زیر رو بزن 👇",
            reply_markup=InlineKeyboardMarkup(keyboard),
            reply_to_message_id=update.message.message_id
        )
        return

    if data["is_extracting"] and data["extraction_end_time"]:
        if now < data["extraction_end_time"]:
            remaining_sec = int((data["extraction_end_time"] - now).total_seconds())
            rem_min = max(1, remaining_sec // 60)
            
            keyboard = []
            if data["has_boost"]:
                keyboard.append([InlineKeyboardButton("🚀 استفاده از بوست ۲ برابر", callback_data="use_boost")])
            
            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            
            await update.message.reply_text(
                f"⚠️ رئیس! کارگر ({data['selected_worker']}) الان مشغول بسته‌بندی جنس‌هاست!\n"
                f"⏳ زمان باقی‌مانده: حدود {rem_min} دقیقه\n"
                f"لطفاً شکیبا باشید...",
                reply_markup=reply_markup,
                reply_to_message_id=update.message.message_id
            )
            return

    if data["worker_tired"]:
        await update.message.reply_text(
            f"🛑 رئیس! کارگر ({data['selected_worker']}) خسته شده و افتاده گوشه لابراتوار!\n"
            "میگه تا پک انرژی نگیرم دست به آزمایشگاه نمیزنم! 🧪\n\n"
            "🛒 با دستور (خرید انرژی) بخر و بعد با (اشپزخونه) بده بهش تا راه بیفته!",
            reply_to_message_id=update.message.message_id
        )
        return

    keyboard = []
    for worker in data["workers"]:
        keyboard.append([InlineKeyboardButton(f"👨‍🏭 {worker}", callback_data=f"select_worker:{worker}")])
    
    await update.message.reply_text(
        "🏭 وارد مقر قاچاق شدید!\nکارگر مورد نظر برای پخت محموله را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        reply_to_message_id=update.message.message_id
    )

async def handle_worker_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    worker_name = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    data, _ = get_user_data(user_id)
    data["selected_worker"] = worker_name
    
    await query.edit_message_text(
        f"❄️ چند بسته شیشه می‌خواهید کارگر ({worker_name}) تولید کند؟\n"
        "تعداد را به عدد بفرستید:"
    )
    return WAITING_FOR_DRUG_COUNT

async def get_drug_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("❌ لطفاً یک عدد معتبر بفرستید!", reply_to_message_id=update.message.message_id)
        return WAITING_FOR_DRUG_COUNT
        
    count = int(text)
    user_id = update.message.from_user.id
    data, _ = get_user_data(user_id)
    data["pending_drugs"] = count
    
    duration_minutes = max(1, count // 10)
    
    keyboard = [
        [
            InlineKeyboardButton("✅ بله، شروع پخت", callback_data="confirm_extract_yes"),
            InlineKeyboardButton("❌ نه، بیخیال", callback_data="confirm_extract_no")
        ]
    ]
    await update.message.reply_text(
        f"⏱ زمان لازم برای پخت {count} بسته شیشه: حدود {duration_minutes} دقیقه\n"
        f"تولید محموله شروع شود؟",
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
        await query.edit_message_text("❌ ساخت محموله لغو شد.")
        return

    if query.data == "confirm_extract_yes":
        count = data["pending_drugs"]
        duration_minutes = max(1, count // 10)
        
        data["is_extracting"] = True
        data["extraction_end_time"] = datetime.now() + timedelta(minutes=duration_minutes)
        
        await query.edit_message_text(
            f"🛠 کارگر ({data['selected_worker']}) رفت تو لابراتوار! ❄️\n"
            f"در حال تولید {count} بسته شیشه...\n"
            f"⏳ حدود {duration_minutes} دقیقه دیگه تمومه!"
        )

        asyncio.create_task(wait_for_extraction_finish(context, user_id, duration_minutes * 60))

async def wait_for_extraction_finish(context: ContextTypes.DEFAULT_TYPE, user_id: int, wait_seconds: int):
    await asyncio.sleep(wait_seconds)
    data, _ = get_user_data(user_id)
    
    if data["is_extracting"]:
        data["is_extracting"] = False
        data["ready_drugs"] = data["pending_drugs"]
        data["pending_drugs"] = 0
        
        user_mention = f"[{data['full_name']}](tg://user?id={user_id})"
        await context.bot.send_message(
            chat_id=data["chat_id"],
            text=f"🔔 رئیس {user_mention}!\n"
                 f"کارگر ({data['selected_worker']}) محموله شیشه‌ها رو آماده کرد! ❄️🎉\n"
                 f"با دستور (مقر قاچاق) بارت رو بزن تو انبار!"
        )

# --- ۴. سیستم بوست ---
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
        "🚀 می‌خواهی نیترو بزنی و زمان پخت محموله را نصف کنی؟",
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
            f"🔥 بوست فعال شد! سرعت پخت دو برابر شد!\n"
            f"⏱ زمان باقی‌مانده به {new_min} دقیقه کاهش یافت!"
        )
    else:
        await query.edit_message_text("❌ فعلاً از بوست استفاده نشد.")

# --- ۵. انبار کردن محصول ---
async def handle_claim_drugs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data, _ = get_user_data(user_id)
    
    claimed = data["ready_drugs"]
    data["drugs"] += claimed
    data["total_extracted"] += claimed
    data["ready_drugs"] = 0
    data["worker_tired"] = True 
    
    await query.edit_message_text(
        f"✨ عالیه! {claimed} بسته شیشه اومد تو انبار مخفیت! 📦❄️\n\n"
        f"😴 کارگر ({data['selected_worker']}) خسته شده و افتاده گوشه لابراتوار... تا پک انرژی براش نخری دیگه کار نمیکنه!"
    )

# --- ۶. خرید انرژی و آشپزخانه ---
async def start_buy_energy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    data, _ = get_user_data(user_id)
    cost = 20
    
    if data["drugs"] < cost:
        await update.message.reply_text(
            f"❌ جیبت خالیه رئیس!\nبرای خرید پک انرژی حداقل به {cost} بسته شیشه نیاز داری.",
            reply_to_message_id=update.message.message_id
        )
        return

    keyboard = [
        [
            InlineKeyboardButton("🧪 آره، ۲۰ تا شیشه بده انرژی بخر", callback_data="buy_energy_yes"),
            InlineKeyboardButton("❌ نه، بیخیال", callback_data="buy_energy_no")
        ]
    ]
    await update.message.reply_text(
        f"🧪 قیمت یک پک انرژی مخصوص کارگر: ۲۰ بسته شیشه\nموافقی کسر بشه؟",
        reply_markup=InlineKeyboardMarkup(keyboard),
        reply_to_message_id=update.message.message_id
    )

async def handle_energy_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data, _ = get_user_data(user_id)
    cost = 20

    if query.data == "buy_energy_yes":
        if data["drugs"] >= cost:
            data["drugs"] -= cost
            data["inventory_energy"] += 1
            await query.edit_message_text(
                "🧪 پک انرژی با موفقیت خریداری شد!\n"
                "حالا با دستور (اشپزخونه) بده به کارگرت."
            )
        else:
            await query.edit_message_text("❌ جنس کافی نداری!")
    else:
        await query.edit_message_text("❌ خرید لغو شد.")

async def open_kitchen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    data, _ = get_user_data(user_id)

    if data["inventory_energy"] <= 0:
        await update.message.reply_text(
            "❌ تو انبارت هیچ پک انرژی نداری!\nاول با دستور (خرید انرژی) یکی بخر بعد بیا اینجا.",
            reply_to_message_id=update.message.message_id
        )
        return

    if not data["workers"]:
        await update.message.reply_text("❌ ابتدا یک کارگر بسازید!", reply_to_message_id=update.message.message_id)
        return

    keyboard = []
    for worker in data["workers"]:
        keyboard.append([InlineKeyboardButton(f"👨‍🏭 {worker}", callback_data=f"kitchen_feed:{worker}")])

    await update.message.reply_text(
        "🍳 به بخش تجدید قوا خوش آمدید!\nپک انرژی را می‌خواهید به کدام کارگر بدهید؟",
        reply_markup=InlineKeyboardMarkup(keyboard),
        reply_to_message_id=update.message.message_id
    )

async def handle_kitchen_feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    worker_name = query.data.split(":", 1)[1]
    keyboard = [
        [InlineKeyboardButton("🧪 سوخت‌رسانی و تزریق انرژی", callback_data=f"feed_confirm:{worker_name}")]
    ]
    await query.edit_message_text(
        f"تزریق پک انرژی به کارگر ({worker_name})؟",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_feed_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data, _ = get_user_data(user_id)
    
    worker_name = query.data.split(":", 1)[1]

    if data["inventory_energy"] > 0:
        data["inventory_energy"] -= 1
        data["worker_tired"] = False
        await query.edit_message_text(
            f"😋 عالی شد! کارگر ({worker_name}) پر انرژی شد و قبراق آماده به کاره!\n"
            "میگه: رئیس امر بفرما بریم برای محموله بعدی! 🚀"
        )

# --- ۷. بخش شعارها ---
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
        "🎉 ایول! به دلیل حمایت از حقوق ساقی‌ها و کارگران، برنده‌ی یک بوست سرعت شدی! ⚡",
        reply_to_message_id=update.message.message_id
    )

# --- ۸. برترین‌های قاچاق (لیدربورد) ---
async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sorted_users = sorted(user_data_db.items(), key=lambda x: x[1]["total_extracted"], reverse=True)[:10]
    
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    text = "⚔️ **جدول سراسری برترین ‌های قاچاق :**\n\n"
    
    if not sorted_users:
        text += "هنوز هیچ قاچاقچی ثبت نام نکرده!"
    else:
        for idx, (uid, udata) in enumerate(sorted_users):
            uname = f"@{udata['username']}" if udata['username'] else udata['full_name']
            text += f"{medals[idx]} - {udata['full_name']} - {uname} - {udata['total_extracted']} ❄️\n\n"

    await update.message.reply_text(text, reply_to_message_id=update.message.message_id, parse_mode="Markdown")

# --- ۹. جنس هام (پروفایل) ---
async def show_my_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    data, _ = get_user_data(user.id)
    
    boost_status = "⚡ دارد" if data["has_boost"] else "❌ ندارد"
    empire_lvl = get_empire_level(data["total_extracted"])
    
    workers_list_str = ", ".join(data["workers"]) if data["workers"] else "بدون کارگر"
    current_worker = data["selected_worker"] if data["selected_worker"] else "انتخاب نشده"
    
    caption_text = (
        f"👤 نام شما: {user.full_name}\n"
        f"🆔 آیدی عددی شما: {user.id}\n"
        f"📢 تعداد شعارهای شما: {data['slogans_count']}\n"
        f"👨‍🏭 کارگران شما: {workers_list_str}\n"
        f"🎯 کارگر فعال: {current_worker}\n"
        f"❄️ بسته‌های موجود در انبار: {data['drugs']} عدد\n"
        f"📊 کل بسته‌های تولید شده: {data['total_extracted']} عدد\n"
        f"🏭 سطح امپراطوری شما: {empire_lvl}\n"
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

# --- وب‌سرور استاندارد aiohttp برای Render ---
async def handle_ping(request):
    return web.Response(text="Bot is online!")

async def main():
    TOKEN = "8998529794:AAGIbI-TB9PesR3XepE8IFlpmTzbtoCZXFE"
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))

    # گفتگو برای ساخت کارگر
    worker_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^ساختن کارگر$"), start_create_worker)],
        states={
            WAITING_FOR_WORKER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_worker_name)]
        },
        fallbacks=[]
    )
    app.add_handler(worker_conv_handler)

    # گفتگو برای تولید محموله
    hq_conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^مقر قاچاق$"), start_headquarters),
            CallbackQueryHandler(handle_worker_selection, pattern="^select_worker:")
        ],
        states={
            WAITING_FOR_DRUG_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_drug_count)
            ]
        },
        fallbacks=[]
    )
    app.add_handler(hq_conv_handler)

    app.add_handler(CallbackQueryHandler(handle_extraction_confirmation, pattern="^confirm_extract_"))
    app.add_handler(CallbackQueryHandler(ask_use_boost, pattern="^use_boost$"))
    app.add_handler(CallbackQueryHandler(handle_boost_decision, pattern="^boost_confirm_"))
    app.add_handler(CallbackQueryHandler(handle_claim_drugs, pattern="^claim_drugs$"))
    
    # غذادهی / انرژی
    app.add_handler(MessageHandler(filters.Regex("^خرید انرژی$"), start_buy_energy))
    app.add_handler(CallbackQueryHandler(handle_energy_purchase, pattern="^buy_energy_"))
    app.add_handler(MessageHandler(filters.Regex("^اشپزخونه$"), open_kitchen))
    app.add_handler(CallbackQueryHandler(handle_kitchen_feed, pattern="^kitchen_feed:"))
    app.add_handler(CallbackQueryHandler(handle_feed_confirm, pattern="^feed_confirm:"))

    # شعارها
    slogan_filter = filters.Regex(f"^({'|'.join(ALLOWED_SLOGANS)})$")
    app.add_handler(MessageHandler(slogan_filter, handle_slogan))

    # بقیه دستورات
    app.add_handler(MessageHandler(filters.Regex("^جنس هام$"), show_my_status))
    app.add_handler(MessageHandler(filters.Regex("^برترین ‌های قاچاق$"), show_leaderboard))

    # راه‌اندازی سرور وب aiohttp در کنار ربات بدون بلاک کردن
    web_app = web.Application()
    web_app.router.add_get('/', handle_ping)
    runner = web.AppRunner(web_app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    print("ربات قاچاق‌گیم آنلاین شد...")
    
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        # نگه‌داشتن برنامه در حال اجرا
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
