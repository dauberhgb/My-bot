import json
import sqlite3

DB_NAME = "bot_settings.db"


def init_db():
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  # 1. جدول إعدادات السيرفر
  cursor.execute("""
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
            auto_nickname TEXT,
            ticket_category TEXT,
            ticket_support_role TEXT,
            xp_enabled INTEGER,
            xp_per_message INTEGER
            xp_role_5 TEXT,
            xp_role_10 TEXT,
            xp_role_20 TEXT,

        )
    """)

  # 2. جدول نظام المستويات (XP) الجديد
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_levels (
            guild_id TEXT,
            user_id TEXT,
            xp INTEGER,
            level INTEGER,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

  conn.commit()
  conn.close()


def get_settings(guild_id):
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute(
      "SELECT * FROM guild_settings WHERE guild_id = ?", (str(guild_id),)
  )
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
        "warning_msg_2": (
            row[9] or "تنبيه ثاني يا {user}، المخالفة القادمة ستعرضك للعقوبة!"
        ),
        "farewell_channel": row[10] or "",
        "farewell_title": row[11] or "وداعاً!",
        "farewell_desc": row[12] or "غادر العضو {user} السيرفر.",
        "farewell_img": row[13] or "",
        "farewell_action": row[14] or "none",
        "auto_responses": json.loads(row[15]) if row[15] else {},
        "auto_role": row[16] or "",
        "auto_nickname": row[17] or "",
        "ticket_category": row[18] or "",
        "ticket_support_role": row[19] or "",
        "xp_enabled": row[20] if row[20] is not None else 1,
        "xp_per_message": row[21] or 15,
        "xp_role_5": row[22] or "",
        "xp_role_10": row[23] or "",
        "xp_role_20": row[24] or "",
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
      "ticket_category": "",
      "ticket_support_role": "",
      "xp_enabled": 1,
      "xp_per_message": 15,
  }


def save_settings(guild_id, settings):
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute(
      """
        INSERT OR REPLACE INTO guild_settings VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """,
      (
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
          settings.get("auto_nickname", ""),
          settings.get("ticket_category", ""),
          settings.get("ticket_support_role", ""),
          int(settings.get("xp_enabled", 1)),
          int(settings.get("xp_per_message", 15)),
          str(settings.get("xp_role_5", "")),
          str(settings.get("xp_role_10", "")),
          str(settings.get("xp_role_20", "")),
      ),
  )
  conn.commit()
  conn.close()


# دوال إدارة نظام المستويات والخبرة (XP) الجديدة
def add_user_xp(guild_id, user_id, xp_amount=15):
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute(
      "SELECT xp, level FROM user_levels WHERE guild_id = ? AND user_id = ?",
      (str(guild_id), str(user_id)),
  )
  row = cursor.fetchone()

  if row:
    xp, level = row
  else:
    xp, level = 0, 1

  xp += xp_amount
  next_level_xp = level * 100 + 100
  leveled_up = False

  if xp >= next_level_xp:
    level += 1
    leveled_up = True

  cursor.execute(
      """
        INSERT OR REPLACE INTO user_levels (guild_id, user_id, xp, level)
        VALUES (?, ?, ?, ?)
    """,
      (str(guild_id), str(user_id), xp, level),
  )

  conn.commit()
  conn.close()
  return level, leveled_up


def get_user_level(guild_id, user_id):
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute(
      "SELECT xp, level FROM user_levels WHERE guild_id = ? AND user_id = ?",
      (str(guild_id), str(user_id)),
  )
  row = cursor.fetchone()
  conn.close()

  if row:
    return row[0], row[1]
  return 0, 1

def get_top_users(guild_id, limit=10):
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute(
      "SELECT user_id, xp, level FROM user_levels WHERE guild_id = ? ORDER BY"
      " xp DESC LIMIT ?",
      (str(guild_id), limit),
  )
  rows = cursor.fetchall()
  conn.close()
  return rows

init_db()
