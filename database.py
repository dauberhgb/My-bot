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
    
    # جدول إحصائيات التحليلات
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
    
    # التأكد من إضافة الأعمدة في حال كان الجدول قديم دون فقدان البيانات
    try:
        cursor.execute("ALTER TABLE guild_analytics ADD COLUMN timeout_count INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE guild_analytics ADD COLUMN ban_count INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # ==========================================
    # إضافة حقول الميزات الجديدة (تضمين قناة أرشيف التذاكر)
    # ==========================================
    new_columns = [
        ("welcome_channel", "TEXT DEFAULT ''"),
        ("welcome_title", "TEXT DEFAULT ''"),
        ("welcome_desc", "TEXT DEFAULT ''"),
        ("welcome_img", "TEXT DEFAULT ''"),
        ("log_channel", "TEXT DEFAULT ''"),
        ("ticket_channel", "TEXT DEFAULT ''"),
        ("ticket_archive_channel", "TEXT DEFAULT ''")
    ]

    for col_name, col_type in new_columns:
        try:
            cursor.execute(f"ALTER TABLE guild_settings ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass

    # ==========================================
    # الخيار 24: نظام الـ Embed Builder الخارق
    # ==========================================
    # 1. جدول القوالب والرسائل المخصصة (Visual Construction & Logic)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS embed_templates (
            template_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT,
            template_name TEXT,
            embed_data TEXT,
            components_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 2. جدول الرسائل المجدولة (Scheduled Embeds)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scheduled_embeds (
            schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT,
            channel_id TEXT,
            template_id INTEGER,
            send_at TEXT,
            mention_type TEXT DEFAULT 'none',
            status TEXT DEFAULT 'pending',
            FOREIGN KEY (template_id) REFERENCES embed_templates (template_id)
        )
    ''')

    # 3. جدول التفاعلات الحية للأزرار والقوائم والـ Modals
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS embed_interactions (
            custom_id TEXT PRIMARY KEY,
            guild_id TEXT,
            action_type TEXT,
            action_data TEXT
        )
    ''')

    # 4. جدول إعدادات القوائم المنسدلة الذكية (Smart Dropdowns)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS embed_dropdowns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT,
            custom_id TEXT UNIQUE,
            placeholder TEXT,
            min_values INTEGER DEFAULT 1,
            max_values INTEGER DEFAULT 1,
            options_json TEXT
        )
    ''')

    # 5. جدول إعدادات نوافذ الإدخال المنبثقة (Modals)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS embed_modals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT,
            custom_id TEXT UNIQUE,
            title TEXT,
            inputs_json TEXT,
            target_channel_id TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def get_settings(guild_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (str(guild_id),))
    row = cursor.fetchone()
    
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
            "welcome_channel": data.get("welcome_channel") or "",
            "welcome_title": data.get("welcome_title") or "مرحباً بك!",
            "welcome_desc": data.get("welcome_desc") or "أهلاً بك يا {user} في السيرفر!",
            "welcome_img": data.get("welcome_img") or "",
            "log_channel": data.get("log_channel") or "",
            "ticket_channel": data.get("ticket_channel") or "",
            "ticket_archive_channel": data.get("ticket_archive_channel") or ""
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
        "welcome_channel": "",
        "welcome_title": "أهلاً وسهلاً بك! 🎉",
        "welcome_desc": "مرحباً بك يا {user} في سيرفرنا، نتمنى لك وقتاً ممتعاً!",
        "welcome_img": "",
        "log_channel": "",
        "ticket_channel": "",
        "ticket_archive_channel": ""
    }

def save_settings(guild_id, settings):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    current = get_settings(guild_id)
    updated = {**current, **settings}
    
    cursor.execute('''
        INSERT OR REPLACE INTO guild_settings (
            guild_id, media_channels, media_warning, banned_words, max_violations,
            punishment_type, timeout_minutes, warning_title, warning_msg_1, warning_msg_2,
            farewell_channel, farewell_title, farewell_desc, farewell_img, farewell_action,
            auto_responses, auto_role, auto_nickname,
            welcome_channel, welcome_title, welcome_desc, welcome_img,
            log_channel, ticket_channel, ticket_archive_channel
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
        updated.get("ticket_archive_channel", "")
    ))
    conn.commit()
    conn.close()

def increment_stat(guild_id, stat_name):
    allowed_stats = ['banned_blocked', 'media_deleted', 'auto_replies', 'timeout_count', 'ban_count']
    if stat_name not in allowed_stats:
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("INSERT OR IGNORE INTO guild_analytics (guild_id, banned_blocked, media_deleted, auto_replies, timeout_count, ban_count) VALUES (?, 0, 0, 0, 0, 0)", (str(guild_id),))
    cursor.execute(f"UPDATE guild_analytics SET {stat_name} = {stat_name} + 1 WHERE guild_id = ?", (str(guild_id),))
    
    conn.commit()
    conn.close()

def get_analytics(guild_id):
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

# ==========================================
# دوال الخيار 24 (Embed Builder الخارق)
# ==========================================

def save_embed_template(guild_id, template_name, embed_data, components_data):
    """حفظ أو تحديث قالب Embed كامل مع أزراره ومكوناته التفاعلية"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO embed_templates (guild_id, template_name, embed_data, components_data)
        VALUES (?, ?, ?, ?)
    ''', (str(guild_id), template_name, json.dumps(embed_data), json.dumps(components_data)))
    template_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return template_id

def get_embed_templates(guild_id):
    """جلب جميع القوالب المحفوظة لسيرفر معين"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT template_id, template_name, embed_data, components_data, created_at FROM embed_templates WHERE guild_id = ?", (str(guild_id),))
    rows = cursor.fetchall()
    conn.close()
    templates = []
    for r in rows:
        templates.append({
            "template_id": r[0],
            "template_name": r[1],
            "embed_data": json.loads(r[2]) if r[2] else {},
            "components_data": json.loads(r[3]) if r[3] else [],
            "created_at": r[4]
        })
    return templates

def register_interaction(custom_id, guild_id, action_type, action_data):
    """تسجيل تفاعل زر أو قائمة منسدلة أو Modal في قاعدة البيانات ليربطه البوت تلقائياً"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO embed_interactions (custom_id, guild_id, action_type, action_data)
        VALUES (?, ?, ?, ?)
    ''', (custom_id, str(guild_id), action_type, json.dumps(action_data)))
    conn.commit()
    conn.close()

def get_interaction(custom_id):
    """جلب بيانات التفاعل عند ضغط المستخدم على أي زر أو خيار في ديسكورد"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT guild_id, action_type, action_data FROM embed_interactions WHERE custom_id = ?", (custom_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "guild_id": row[0],
            "action_type": row[1],
            "action_data": json.loads(row[2]) if row[2] else {}
        }
    return None

def add_scheduled_embed(guild_id, channel_id, template_id, send_at, mention_type="none"):
    """جدولة رسالة Embed للإرسال التلقائي في وقت لاحق"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO scheduled_embeds (guild_id, channel_id, template_id, send_at, mention_type, status)
        VALUES (?, ?, ?, ?, ?, 'pending')
    ''', (str(guild_id), str(channel_id), template_id, str(send_at), mention_type))
    conn.commit()
    conn.close()

def get_pending_scheduled_embeds():
    """جلب الرسائل المجدولة المستحقة للإرسال الآن"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.schedule_id, s.guild_id, s.channel_id, s.mention_type, t.embed_data, t.components_data
        FROM scheduled_embeds s
        JOIN embed_templates t ON s.template_id = t.template_id
        WHERE s.status = 'pending' AND datetime(s.send_at) <= datetime('now')
    ''')
    rows = cursor.fetchall()
    conn.close()
    return rows

def mark_schedule_completed(schedule_id):
    """تحديث حالة الرسالة المجدولة بعد الإرسال بنجاح"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE scheduled_embeds SET status = 'completed' WHERE schedule_id = ?", (schedule_id,))
    conn.commit()
    conn.close()

def save_dropdown_config(guild_id, custom_id, placeholder, min_val, max_val, options):
    """حفظ إعدادات القوائم المنسدلة الذكية"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO embed_dropdowns (guild_id, custom_id, placeholder, min_values, max_values, options_json)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (str(guild_id), custom_id, placeholder, min_val, max_val, json.dumps(options)))
    conn.commit()
    conn.close()

def get_dropdown_config(custom_id):
    """جلب إعدادات قائمة منسدلة بحسب custom_id"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT guild_id, placeholder, min_values, max_values, options_json FROM embed_dropdowns WHERE custom_id = ?', (custom_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            'guild_id': row[0],
            'placeholder': row[1],
            'min_values': row[2],
            'max_values': row[3],
            'options': json.loads(row[4]) if row[4] else []
        }
    return None

def save_modal_config(guild_id, custom_id, title, inputs, target_channel_id):
    """حفظ إعدادات النوافذ المنبثقة Modals"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO embed_modals (guild_id, custom_id, title, inputs_json, target_channel_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (str(guild_id), custom_id, title, json.dumps(inputs), str(target_channel_id)))
    conn.commit()
    conn.close()

def get_modal_config(custom_id):
    """جلب إعدادات نافذة منبثقة Modal بحسب custom_id"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT guild_id, title, inputs_json, target_channel_id FROM embed_modals WHERE custom_id = ?', (custom_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            'guild_id': row[0],
            'title': row[1],
            'inputs': json.loads(row[2]) if row[2] else [],
            'target_channel_id': row[3]
        }
    return None

init_db()
