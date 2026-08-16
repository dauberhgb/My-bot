import sqlite3
import json

DB_NAME = "bot_settings.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # جدول إعدادات السيرفر
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id TEXT PRIMARY KEY,
            media_channels TEXT,
            media_warning TEXT,
            banned_words TEXT,
            max_violations INTEGER,
            punishment_type TEXT,
            timeout_minutes INTEGER,
            warning_title TEXT,
            warning_msg_1 TEXT,
            warning_msg_2 TEXT,
            farewell_channel TEXT,
            farewell_title TEXT,
            farewell_desc TEXT,
            farewell_img TEXT,
            farewell_action TEXT,
            auto_responses TEXT,
            auto_role TEXT,
            auto_nickname TEXT
        )
    ''')
    
    # جدول إحصائيات التحليلات (مُحدّث ليشمل حالات التايم أوت والحظر)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS guild_analytics (
            guild_id TEXT PRIMARY KEY,
            banned_blocked INTEGER DEFAULT 0,
            media_deleted INTEGER DEFAULT 0,
            auto_replies INTEGER DEFAULT 0,
            timeout_count INTEGER DEFAULT 0,
            ban_count INTEGER DEFAULT 0
        )
    ''')
    
    # التأكد من إضافة الأعمدة الجديدة في حال كان الجدول قديم بدون فقدان البيانات
    try:
        cursor.execute("ALTER TABLE guild_analytics ADD COLUMN timeout_count INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE guild_analytics ADD COLUMN ban_count INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # ==========================================
    # إضافة حقول الميزات الجديدة (بدون المساس بالقديم)
    # ==========================================
    new_columns = [
        ("welcome_channel", "TEXT DEFAULT ''"),
        ("welcome_title", "TEXT DEFAULT ''"),
        ("welcome_desc", "TEXT DEFAULT ''"),
        ("welcome_img", "TEXT DEFAULT ''"),
        ("log_channel", "TEXT DEFAULT ''"),
        ("ticket_channel", "TEXT DEFAULT ''"),
        ("ticket_category", "TEXT DEFAULT ''")
    ]

    for col_name, col_type in new_columns:
        try:
            cursor.execute(f"ALTER TABLE guild_settings ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass
    
    conn.commit()
    conn.close()

def get_settings(guild_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (str(guild_id),))
    row = cursor.fetchone()
    
    # جلب أسماء الأعمدة ديناميكياً لضمان التوافق وقراءة الميزات الجديدة
    colnames = [desc[0] for desc in cursor.description]
    conn.close()
    
    if row:
        data = dict(zip(colnames, row))
        return {
            "guild_id": data.get("guild_id"),
            "media_channels": json.loads(data.get("media_channels")) if data.get("media_channels") else [],
            "media_warning": data.get("media_warning") or "عذراً {user}، هذه القناة مخصصة للميديا فقط!",
            "banned_words": json.loads(data.get("banned_words")) if data.get("banned_words") else [],
            "max_violations": data.get("max_violations") or 3,
            "punishment_type": data.get("punishment_type") or "timeout",
            "timeout_minutes": data.get("timeout_minutes") or 10,
            "warning_title": data.get("warning_title") or "تحذير مخالفة",
            "warning_msg_1": data.get("warning_msg_1") or "تنبيه أول يا {user}، يرجى الالتزام بالقوانين.",
            "warning_msg_2": data.get("warning_msg_2") or "تنبيه ثاني يا {user}، المخالفة القادمة ستعرضك للعقوبة!",
            "farewell_channel": data.get("farewell_channel") or "",
            "farewell_title": data.get("farewell_title") or "وداعاً!",
            "farewell_desc": data.get("farewell_desc") or "غادر العضو {user} السيرفر.",
            "farewell_img": data.get("farewell_img") or "",
            "farewell_action": data.get("farewell_action") or "none",
            "auto_responses": json.loads(data.get("auto_responses")) if data.get("auto_responses") else {},
            "auto_role": data.get("auto_role") or "",
            "auto_nickname": data.get("auto_nickname") or "",
            # الميزات الجديدة
            "welcome_channel": data.get("welcome_channel") or "",
            "welcome_title": data.get("welcome_title") or "مرحباً بك!",
            "welcome_desc": data.get("welcome_desc") or "أهلاً بك يا {user} في السيرفر!",
            "welcome_img": data.get("welcome_img") or "",
            "log_channel": data.get("log_channel") or "",
            "ticket_channel": data.get("ticket_channel") or "",
            "ticket_category": data.get("ticket_category") or ""
        }
    return {
        "guild_id": str(guild_id),
        "media_channels": [],
        "media_warning": "عذراً {user}، هذه القناة مخصصة للميديا فقط!",
        "banned_words": [],
        "max_violations": 3,
        "punishment_type": "timeout",
        "timeout_minutes": 10,
        "warning_title": "⚠️ تحذير نظام الحماية",
        "warning_msg_1": "تنبيه أول يا {user}، يرجى الالتزام بالقوانين.",
        "warning_msg_2": "تنبيه ثاني يا {user}، المخالفة القادمة ستعرضك للعقوبة!",
        "farewell_channel": "",
        "farewell_title": "وداعاً!",
        "farewell_desc": "غادر العضو {user} السيرفر نتمنى له التوفيق.",
        "farewell_img": "",
        "farewell_action": "none",
        "auto_responses": {},
        "auto_role": "",
        "auto_nickname": "",
        # الميزات الجديدة الافتراضية
        "welcome_channel": "",
        "welcome_title": "أهلاً وسهلاً بك! 🎉",
        "welcome_desc": "مرحباً بك يا {user} في سيرفرنا، نتمنى لك وقتاً ممتعاً!",
        "welcome_img": "",
        "log_channel": "",
        "ticket_channel": "",
        "ticket_category": ""
    }

def save_settings(guild_id, settings):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # الحصول على الإعدادات الحالية لعدم مسح أي بيانات سابقة
    current = get_settings(guild_id)
    
    # دمج البيانات
    updated = {**current, **settings}
    
    cursor.execute('''
        INSERT OR REPLACE INTO guild_settings (
            guild_id, media_channels, media_warning, banned_words, max_violations,
            punishment_type, timeout_minutes, warning_title, warning_msg_1, warning_msg_2,
            farewell_channel, farewell_title, farewell_desc, farewell_img, farewell_action,
            auto_responses, auto_role, auto_nickname,
            welcome_channel, welcome_title, welcome_desc, welcome_img,
            log_channel, ticket_channel, ticket_category
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    ''', (
        str(guild_id),
        json.dumps(updated.get("media_channels", [])),
        updated.get("media_warning", ""),
        json.dumps(updated.get("banned_words", [])),
        updated.get("max_violations", 3),
        updated.get("punishment_type", "timeout"),
        updated.get("timeout_minutes", 10),
        updated.get("warning_title", ""),
        updated.get("warning_msg_1", ""),
        updated.get("warning_msg_2", ""),
        updated.get("farewell_channel", ""),
        updated.get("farewell_title", ""),
        updated.get("farewell_desc", ""),
        updated.get("farewell_img", ""),
        updated.get("farewell_action", "none"),
        json.dumps(updated.get("auto_responses", {})),
        updated.get("auto_role", ""),
        updated.get("auto_nickname", ""),
        updated.get("welcome_channel", ""),
        updated.get("welcome_title", ""),
        updated.get("welcome_desc", ""),
        updated.get("welcome_img", ""),
        updated.get("log_channel", ""),
        updated.get("ticket_channel", ""),
        updated.get("ticket_category", "")
    ))
    conn.commit()
    conn.close()

# ==========================================
# دوال ميزة التحليلات (Analytics) المحدثة
# ==========================================

def increment_stat(guild_id, stat_name):
    """زيادة العداد لميزة معينة (banned_blocked / media_deleted / auto_replies / timeout_count / ban_count)"""
    allowed_stats = ['banned_blocked', 'media_deleted', 'auto_replies', 'timeout_count', 'ban_count']
    if stat_name not in allowed_stats:
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # التأكد من وجود سجل للسيرفر
    cursor.execute("INSERT OR IGNORE INTO guild_analytics (guild_id, banned_blocked, media_deleted, auto_replies, timeout_count, ban_count) VALUES (?, 0, 0, 0, 0, 0)", (str(guild_id),))
    
    # زيادة العداد بمقدار 1
    cursor.execute(f"UPDATE guild_analytics SET {stat_name} = {stat_name} + 1 WHERE guild_id = ?", (str(guild_id),))
    
    conn.commit()
    conn.close()

def get_analytics(guild_id):
    """جلب إحصائيات التحليلات للسيرفر"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT banned_blocked, media_deleted, auto_replies, timeout_count, ban_count FROM guild_analytics WHERE guild_id = ?", (str(guild_id),))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "banned_blocked": row[0],
            "media_deleted": row[1],
            "auto_replies": row[2],
            "timeout_count": row[3],
            "ban_count": row[4]
        }
    return {
        "banned_blocked": 0,
        "media_deleted": 0,
        "auto_replies": 0,
        "timeout_count": 0,
        "ban_count": 0
    }

init_db()
