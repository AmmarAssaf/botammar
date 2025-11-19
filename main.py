# ==============================
# 🤖 BOT: Telegram Registration Bot for Render
# 📦 نسخة مخففة للتجربة على Render
# 🐍 متوافق مع Python 3.13.4
# ==============================

import os
import logging
import re
import phonenumbers
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackContext, CallbackQueryHandler
import psycopg2
from psycopg2.extras import RealDictCursor
import random
import string

# ==============================
# 🔧 إعدادات التسجيل
# ==============================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==============================
# 🗄️ إعدادات قاعدة البيانات لـ Render
# ==============================
def get_database_config():
    """الحصول على إعدادات قاعدة البيانات من متغيرات البيئة"""
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Parse PostgreSQL URL
        import urllib.parse
        parsed_url = urllib.parse.urlparse(database_url)
        
        return {
            'dbname': parsed_url.path[1:],
            'user': parsed_url.username,
            'password': parsed_url.password,
            'host': parsed_url.hostname,
            'port': parsed_url.port,
            'environment': 'render'
        }
    else:
        # للاستخدام المحلي (إذا لزم الأمر)
        return {
            'dbname': 'telegram_bot',
            'user': 'postgres',
            'password': 'password',
            'host': 'localhost',
            'port': 5432,
            'environment': 'local'
        }

def create_connection():
    """إنشاء اتصال بقاعدة البيانات"""
    try:
        config = get_database_config()
        conn = psycopg2.connect(
            dbname=config['dbname'],
            user=config['user'],
            password=config['password'],
            host=config['host'],
            port=config['port']
        )
        return conn
    except Exception as e:
        logger.error(f"❌ خطأ في الاتصال بقاعدة البيانات: {e}")
        return None

# ==============================
# 🤖 إعدادات البوت
# ==============================
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8415474087:AAEDtwjvgogXfvpMzARe875svIEkSSDdNXk')
OWNER_USER_ID = 5425405664

# ==============================
# 🎯 تعريف مراحل المحادثة
# ==============================
(REFERRAL_STAGE, FULL_NAME, COUNTRY, GENDER, BIRTH_YEAR, PHONE, EMAIL) = range(7)

# ==============================
# 🌍 قائمة البلدان
# ==============================
COUNTRIES = {
    "السعودية": "+966", "مصر": "+20", "سوريا": "+963", "الأردن": "+962",
    "الإمارات": "+971", "الكويت": "+965", "قطر": "+974", "عمان": "+968"
}

# ==============================
# 🗃️ دوال قاعدة البيانات
# ==============================
def setup_database():
    """إنشاء الجداول المطلوبة في قاعدة البيانات"""
    try:
        conn = create_connection()
        if not conn:
            return False
            
        cursor = conn.cursor()
        
        # جدول المستخدمين
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id BIGINT PRIMARY KEY,
                telegram_username VARCHAR(100),
                email VARCHAR(255),
                referral_code VARCHAR(20) UNIQUE,
                invited_by VARCHAR(20),
                full_name VARCHAR(200),
                country VARCHAR(100),
                gender VARCHAR(10),
                birth_year INTEGER,
                phone_number VARCHAR(20),
                registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_referrals INTEGER DEFAULT 0,
                status VARCHAR(20) DEFAULT 'active'
            )
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info("✅ تم إعداد قاعدة البيانات بنجاح!")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في إعداد قاعدة البيانات: {e}")
        return False

def generate_referral_code():
    """إنشاء كود إحالة فريد"""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if check_referral_code_unique(code):
            return code

def check_referral_code_unique(code):
    """التحقق من أن كود الإحالة فريد"""
    try:
        conn = create_connection()
        if not conn:
            return False
            
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM user_profiles WHERE referral_code = %s", (code,))
        count = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        return count == 0
        
    except Exception as e:
        logger.error(f"❌ خطأ في التحقق من كود الإحالة: {e}")
        return False

async def check_user_registration(user_id: int) -> bool:
    """التحقق من تسجيل المستخدم مسبقاً"""
    try:
        conn = create_connection()
        if not conn:
            return False
            
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM user_profiles WHERE user_id = %s", (user_id,))
        count = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        return count > 0
        
    except Exception as e:
        logger.error(f"❌ خطأ في التحقق من تسجيل المستخدم: {e}")
        return False

# ==============================
# 🔍 دوال التحقق من الصحة
# ==============================
def validate_phone_with_country(phone_number, country_code):
    """التحقق من رقم الهاتف مع رمز الدولة"""
    try:
        phone_number = re.sub(r'[\s\-\(\)]', '', phone_number)
        
        if not phone_number.startswith('+'):
            phone_number = country_code + phone_number
        
        parsed_number = phonenumbers.parse(phone_number, None)
        
        if phonenumbers.is_valid_number(parsed_number):
            formatted_number = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
            return True, formatted_number, "✅ رقم الهاتف صحيح"
        else:
            return False, phone_number, "❌ رقم الهاتف غير صحيح"
            
    except Exception as e:
        return False, phone_number, f"❌ رقم الهاتف غير صحيح: {str(e)}"

def validate_email(email: str) -> bool:
    """التحقق من صحة البريد الإلكتروني"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_birth_year(year):
    """التحقق من سنة الولادة"""
    try:
        year_int = int(year)
        current_year = datetime.now().year
        if 1920 <= year_int <= current_year - 13:
            return True, year_int
        return False, year_int
    except:
        return False, None

# ==============================
# 🚀 دوال المحادثة الرئيسية
# ==============================
async def start(update: Update, context: CallbackContext) -> int:
    """بدء عملية التسجيل - نسخة مبسطة"""
    user = update.message.from_user
    
    logger.info(f"محاولة دخول من: {user.id} - {user.first_name}")
    
    # التحقق من التسجيل المسبق
    if await check_user_registration(user.id):
        await update.message.reply_text(
            f"🎉 **مرحباً بعودتك {user.first_name}!**\n\n"
            "✅ **أنت مسجل مسبقاً في النظام**\n\n"
            "🔧 **الأوامر المتاحة:**\n"
            "/profile - عرض ملفك الشخصي\n"
            "/invite - عرض كود الدعوة\n"
            "/support - الدعم الفني"
        )
        return ConversationHandler.END
    
    # بدء تسجيل جديد
    context.user_data.clear()
    context.user_data['telegram_username'] = user.username
    context.user_data['user_id'] = user.id
    
    await update.message.reply_text(
        f"🆕 **مرحباً {user.first_name}!** 👋\n\n"
        "🏢 **أهلاً بك في نظام التسجيل**\n\n"
        "🆔 **الآن، ما هو اسمك الثلاثي الكامل؟**\n"
        "(مثال: أحمد محمد علي)"
    )
    return FULL_NAME

async def get_full_name(update: Update, context: CallbackContext) -> int:
    """استقبال الاسم الثلاثي الكامل من المستخدم"""
    full_name = update.message.text.strip()

    name_parts = full_name.split()
    if len(name_parts) < 3:
        await update.message.reply_text(
            "❌ الرجاء إدخال الاسم الثلاثي الكامل (الاسم الأول + الأب + الكنية)\n"
            "(مثال: أحمد محمد علي)"
        )
        return FULL_NAME

    if len(full_name) > 50:
        await update.message.reply_text(
            "❌ الاسم طويل جداً! الحد الأقصى هو 50 حرف\n\n"
            f"📏 عدد أحرف الاسم الذي أدخلته: {len(full_name)}\n"
            "✂️ الرجاء اختصار الاسم وإعادة إدخاله"
        )
        return FULL_NAME
    
    context.user_data['full_name'] = full_name
    
    country_buttons = [list(COUNTRIES.keys())[i:i+2] for i in range(0, len(COUNTRIES), 2)]
    reply_markup = ReplyKeyboardMarkup(country_buttons, one_time_keyboard=True)
    
    await update.message.reply_text(
        f"✅ تم حفظ الاسم: {full_name}\n\n"
        "🌍 **الآن، اختر بلدك من القائمة:**",
        reply_markup=reply_markup
    )
    return COUNTRY

async def get_country(update: Update, context: CallbackContext) -> int:
    """استقبال البلد المختار من المستخدم"""
    country = update.message.text

    if country not in COUNTRIES:
        await update.message.reply_text("❌ الرجاء اختيار بلد من القائمة المحددة.")
        return COUNTRY
    
    context.user_data['country'] = country
    context.user_data['country_code'] = COUNTRIES[country]
    
    gender_keyboard = [['ذكر', 'أنثى']]
    reply_markup = ReplyKeyboardMarkup(gender_keyboard, one_time_keyboard=True)
    
    await update.message.reply_text(
        f"🌍 تم اختيار البلد: {country}\n\n"
        "🚻 **الآن، اختر جنسك:**",
        reply_markup=reply_markup
    )
    return GENDER

async def get_gender(update: Update, context: CallbackContext) -> int:
    """استقبال الجنس المختار من المستخدم"""
    gender = update.message.text
    if gender not in ['ذكر', 'أنثى']:
        await update.message.reply_text("❌ الرجاء اختيار 'ذكر' أو 'أنثى'.")
        return GENDER
    
    context.user_data['gender'] = gender
    
    await update.message.reply_text(
        f"🚻 تم التسجيل كـ: {gender}\n\n"
        "🎂 **الآن، ما هو عام ولادتك؟**\n"
        "(أدخل السنة بأربعة أرقام، مثال: 1990)"
    )
    return BIRTH_YEAR

async def get_birth_year(update: Update, context: CallbackContext) -> int:
    """استقبال عام الولادة من المستخدم"""
    year = update.message.text
    is_valid, year_int = validate_birth_year(year)
    
    if not is_valid:
        await update.message.reply_text(
            "❌ سنة الولادة غير صحيحة!\n"
            "الرجاء إدخال سنة صحيحة (مثال: 1990)"
        )
        return BIRTH_YEAR
    
    context.user_data['birth_year'] = year_int
    
    country_code = context.user_data.get('country_code', '+966')
    await update.message.reply_text(
        f"🎂 تم حفظ سنة الولادة: {year_int}\n\n"
        f"📞 **الآن، ما هو رقم هاتفك؟**\n"
        f"سيتم إضافة رمز الدولة {country_code} تلقائياً\n"
        f"(أدخل الرقم فقط، مثال: 512345678)"
    )
    return PHONE

async def get_phone(update: Update, context: CallbackContext) -> int:
    """استقبال رقم الهاتف من المستخدم"""
    phone_input = update.message.text
    country_code = context.user_data.get('country_code', '+966')
    
    is_valid, formatted_phone, message = validate_phone_with_country(phone_input, country_code)
    
    if not is_valid:
        await update.message.reply_text(
            f"{message}\n\n"
            f"📞 الرجاء إدخال رقم هاتف صحيح لبلدك:\n"
            f"(أدخل الرقم فقط، مثال: 512345678)"
        )
        return PHONE
    
    context.user_data['phone_number'] = formatted_phone
    
    await update.message.reply_text(
        f"{message}\n\n"
        "📧 **الآن، أدخل بريدك الإلكتروني:**\n"
        "(مثال: yourname@example.com)"
    )
    return EMAIL

async def get_email(update: Update, context: CallbackContext) -> int:
    """استقبال البريد الإلكتروني من المستخدم"""
    email = update.message.text.strip()
    
    if not validate_email(email):
        await update.message.reply_text(
            "❌ البريد الإلكتروني غير صحيح!\n"
            "الرجاء إدخال بريد إلكتروني صالح (مثال: user@example.com)\n\n"
            "📧 أدخل بريدك الإلكتروني:"
        )
        return EMAIL
    
    context.user_data['email'] = email
    
    # حفظ البيانات في قاعدة البيانات
    await save_user_data(update.effective_user.id, context.user_data)
    
    # عرض الملخص النهائي
    return await show_final_summary(update, context)

async def save_user_data(user_id: int, user_data: dict):
    """حفظ بيانات المستخدم في قاعدة البيانات"""
    try:
        conn = create_connection()
        if not conn:
            return False
            
        cursor = conn.cursor()
        
        # إنشاء كود إحالة فريد
        referral_code = generate_referral_code()
        
        cursor.execute('''
            INSERT INTO user_profiles 
            (user_id, telegram_username, email, referral_code, full_name, country, gender, birth_year, phone_number)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            user_id,
            user_data.get('telegram_username'),
            user_data.get('email'),
            referral_code,
            user_data.get('full_name'),
            user_data.get('country'),
            user_data.get('gender'),
            user_data.get('birth_year'),
            user_data.get('phone_number')
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        user_data['referral_code'] = referral_code
        logger.info(f"✅ تم حفظ بيانات المستخدم {user_id} بنجاح")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في حفظ البيانات: {e}")
        return False

async def show_final_summary(update: Update, context: CallbackContext) -> int:
    """عرض الملخص النهائي بعد اكتمال التسجيل"""
    user_data = context.user_data
    referral_code = user_data.get('referral_code', 'غير متوفر')
    
    summary = f"""
🎉 **تم تسجيل بياناتك بنجاح!** ✅

📋 **البيانات المسجلة:**
👤 الاسم: {user_data.get('full_name')}
🚻 الجنس: {user_data.get('gender')}
🌍 البلد: {user_data.get('country')}
🎂 سنة الولادة: {user_data.get('birth_year')}
📞 الهاتف: {user_data.get('phone_number')}
📧 البريد الإلكتروني: {user_data.get('email')}

📢 **كود دعوتك الشخصي:** `{referral_code}`
👥 شارك هذا الكود مع أصدقائك!

💡 **الأوامر المتاحة:**
/profile - عرض ملفك الشخصي  
/invite - عرض كود الدعوة والإحصائيات
/support - التواصل مع الدعم الفني
"""

    await update.message.reply_text(summary, parse_mode='Markdown')
    return ConversationHandler.END

# ==============================
# 🔧 الأوامر الإضافية
# ==============================
async def show_profile(update: Update, context: CallbackContext):
    """عرض الملف الشخصي للمستخدم"""
    try:
        user_id = update.effective_user.id
        if not await check_user_registration(user_id):
            await update.message.reply_text("❌ لم يتم العثور على ملفك الشخصي")
            return
        
        conn = create_connection()
        if not conn:
            await update.message.reply_text("❌ خطأ في الاتصال بقاعدة البيانات")
            return
            
        cursor = conn.cursor()
        cursor.execute('''
            SELECT referral_code, full_name, country, gender, birth_year, phone_number, email, total_referrals, registration_date
            FROM user_profiles WHERE user_id = %s
        ''', (user_id,))
        
        profile = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not profile:
            await update.message.reply_text("❌ لم يتم العثور على ملفك الشخصي!")
            return
        
        message = f"""
📋 **ملفك الشخصي**

👤 **المعلومات الشخصية:**
🆔 كود الدعوة: `{profile[0]}`
📛 الاسم: {profile[1]}
🌍 البلد: {profile[2]}
🚻 الجنس: {profile[3]}
🎂 سنة الولادة: {profile[4]}
📞 الهاتف: {profile[5]}
📧 البريد الإلكتروني: {profile[6]}
👥 عدد المُحالين: {profile[7]}
📅 تاريخ التسجيل: {profile[8].strftime('%Y-%m-%d')}
"""
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text("❌ حدث خطأ في عرض الملف الشخصي")
        logger.error(f"Error: {e}")

async def show_invite(update: Update, context: CallbackContext):
    """عرض كود الدعوة والإحصائيات"""
    try:
        user_id = update.effective_user.id
        
        conn = create_connection()
        if not conn:
            await update.message.reply_text("❌ خطأ في الاتصال بقاعدة البيانات")
            return
            
        cursor = conn.cursor()
        cursor.execute('SELECT referral_code, total_referrals FROM user_profiles WHERE user_id = %s', (user_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not result:
            await update.message.reply_text("❌ لم يتم العثور على بياناتك!")
            return
        
        referral_code, total_referrals = result
        
        message = f"""
📢 **نظام الدعوة والإحالة**

🆔 **كود دعوتك الشخصي:** `{referral_code}`

👥 **عدد الأشخاص الذين دعوتهم:** {total_referrals}

🔗 **كيفية استخدام كود الدعوة:**
شارك هذا الرابط مع أصدقائك:
https://t.me/{(await context.bot.get_me()).username}?start={referral_code}
"""
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text("❌ حدث خطأ في عرض معلومات الدعوة")
        logger.error(f"Error: {e}")

async def support_command(update: Update, context: CallbackContext):
    """عرض معلومات الدعم الفني"""
    support_text = """
🆘 **الدعم الفني**

📞 للاستفسارات والمشاكل التقنية:

💬 **طرق التواصل:**
• عبر البوت: اكتب رسالتك وسيتم الرد عليك
• البريد الإلكتروني: support@example.com

⏰ **أوقات العمل:**
• الأحد - الخميس: 9:00 ص - 5:00 م

🔧 **نحن هنا لمساعدتك في:**
• مشاكل التسجيل
• استفسارات حول المكافآت
• أي استفسارات أخرى
"""
    
    await update.message.reply_text(support_text)

async def cancel(update: Update, context: CallbackContext) -> int:
    """إلغاء عملية التسجيل"""
    await update.message.reply_text(
        "❌ **تم إلغاء التسجيل**\n\n"
        "يمكنك البدء من جديد باستخدام /start\n\n"
        "💡 للاستفسارات، استخدم /support"
    )
    return ConversationHandler.END

# ==============================
# 🎪 الدالة الرئيسية
# ==============================
def main():
    """الدالة الرئيسية لتشغيل البوت"""
    
    print("🚀 بدء إعداد البوت للتجربة على Render...")
    
    # التحقق من إعدادات قاعدة البيانات
    if not setup_database():
        print("❌ لا يمكن تشغيل البوت بسبب مشكلة في قاعدة البيانات")
        return
    
    # التحقق من توكن البوت
    if not BOT_TOKEN:
        print("❌ لم يتم تعيين BOT_TOKEN")
        return
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # إعداد نظام المحادثات
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_full_name)],
            COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_country)],
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_gender)],
            BIRTH_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_birth_year)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    application.add_handler(conv_handler)
    
    # إضافة الأوامر الإضافية
    application.add_handler(CommandHandler("profile", show_profile))
    application.add_handler(CommandHandler("invite", show_invite))
    application.add_handler(CommandHandler("support", support_command))
    
    print("🤖 البوت يعمل الآن...")
    print("📍 يمكنك تجربته في تلغرام!")
    print("💡 الأوامر المتاحة:")
    print("   /start - بدء التسجيل")
    print("   /profile - عرض الملف الشخصي")
    print("   /invite - عرض كود الدعوة")
    print("   /support - الدعم الفني")
    
    application.run_polling()

if __name__ == '__main__':
    main()
