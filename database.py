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
    
    conn.commit()
    conn.close()

def get_settings(guild_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (str(guild_id),))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "guild_id": row[0],
            "media_channels": json.loads(row[1]) if row[1] else [],
            "media_warning": row[2] or "عذراً {user}، هذه القناة مخصصة للميديا فقط!",
            "banned_words": json.loads(row[3]) if row[3] else [],
            "max_violations": row[4] or 3,
            "punishment_type": row[5] or "timeout",
            "timeout_minutes": row[6] or 10,
            "warning_title": row[7] or "تحذير مخالفة",
            "warning_msg_1": row[8] or "تنبيه أول يا {user}، يرجى الالتزام بالقوانين.",
            "warning_msg_2": row[9] or "تنبيه ثاني يا {user}، المخالفة القادمة ستعرضك للعقوبة!",
            "farewell_channel": row[10] or "",
            "farewell_title": row[11] or "وداعاً!",
            "farewell_desc": row[12] or "غادر العضو {user} السيرفر.",
            "farewell_img": row[13] or "",
            "farewell_action": row[14] or "none",
            "auto_responses": json.loads(row[15]) if row[15] else {},
            "auto_role": row[16] or "",
            "auto_nickname": row[17] or ""
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
        "auto_nickname": ""
    }

def save_settings(guild_id, settings):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO guild_settings VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    ''', (
        str(guild_id),
        json.dumps(settings.get("media_channels", [])),
        settings.get("media_warning", ""),
        json.dumps(settings.get("banned_words", [])),
        settings.get("max_violations", 3),
        settings.get("punishment_type", "timeout"),
        settings.get("timeout_minutes", 10),
        settings.get("warning_title", ""),
        settings.get("warning_msg_1", ""),
        settings.get("warning_msg_2", ""),
        settings.get("farewell_channel", ""),
        settings.get("farewell_title", ""),
        settings.get("farewell_desc", ""),
        settings.get("farewell_img", ""),
        settings.get("farewell_action", "none"),
        json.dumps(settings.get("auto_responses", {})),
        settings.get("auto_role", ""),
        settings.get("auto_nickname", "")
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
