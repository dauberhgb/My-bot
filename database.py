import os
import json
from pymongo import MongoClient

# الاتصال بقاعدة بيانات MongoDB باستخدام متغير البيئة
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client.get_database("bot_database")

# المجموعات (Collections) البديلة للجداول
settings_collection = db["guild_settings"]
levels_collection = db["user_levels"]

networks_collection = db["networks"]
network_guilds_collection = db["network_guilds"]

def init_db():
  try:
    # التحقق من الاتصال بقاعدة البيانات
    client.admin.command('ping')
    print("✅ تم الاتصال بقاعدة بيانات MongoDB بنجاح!")
  except Exception as e:
    print(f"❌ فشل الاتصال بقاعدة البيانات: {e}")


def get_settings(guild_id):
  guild_id_str = str(guild_id)
  row = settings_collection.find_one({"guild_id": guild_id_str})

  if row:
    row.pop("_id", None)
    return {
        "guild_id": row.get("guild_id", guild_id_str),
        "media_channels": row.get("media_channels", []),
        "media_warning": row.get("media_warning") or "عذراً {user}، هذه القناة مخصصة للميديا فقط!",
        "banned_words": row.get("banned_words", []),
        "max_violations": row.get("max_violations") or 3,
        "punishment_type": row.get("punishment_type") or "timeout",
        "timeout_minutes": row.get("timeout_minutes") or 10,
        "warning_title": row.get("warning_title") or "تحذير مخالفة",
        "warning_msg_1": row.get("warning_msg_1") or "تنبيه أول يا {user}، يرجى الالتزام بالقوانين.",
        "warning_msg_2": row.get("warning_msg_2") or "تنبيه ثاني يا {user}، المخالفة القادمة ستعرضك للعقوبة!",
        "farewell_channel": row.get("farewell_channel") or "",
        "farewell_title": row.get("farewell_title") or "وداعاً!",
        "farewell_desc": row.get("farewell_desc") or "غادر العضو {user} السيرفر.",
        "farewell_img": row.get("farewell_img") or "",
        "farewell_action": row.get("farewell_action") or "none",
        "auto_responses": row.get("auto_responses", {}),
        "auto_role": row.get("auto_role") or "",
        "auto_nickname": row.get("auto_nickname") or "",
        "ticket_category": row.get("ticket_category") or "",
        "ticket_support_role": row.get("ticket_support_role") or "",
        "xp_enabled": row.get("xp_enabled") if row.get("xp_enabled") is not None else 1,
        "xp_per_message": row.get("xp_per_message") or 15,
        "xp_role_5": row.get("xp_role_5") or "",
        "xp_role_10": row.get("xp_role_10") or "",
        "xp_role_20": row.get("xp_role_20") or "",
        "language": row.get("language") if row.get("language") else "ar",
        "welcome_enabled": row.get("welcome_enabled") if row.get("welcome_enabled") is not None else 1,
        "welcome_channel": row.get("welcome_channel") if row.get("welcome_channel") else "",
        "welcome_msg": row.get("welcome_msg") if row.get("welcome_msg") else "أهلاً بك يا {user} في السيرفر! 🎉",
        "welcome_img": row.get("welcome_img") if row.get("welcome_img") else "",
        "welcome_frame": row.get("welcome_frame") if row.get("welcome_frame") else "",
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
      "xp_role_5": "",
      "xp_role_10": "",
      "xp_role_20": "",
      "language": "ar",
      "welcome_enabled": 1,
      "welcome_channel": "",
      "welcome_msg": "أهلاً بك يا {user} في السيرفر! 🎉",
      "welcome_img": "",
      "welcome_frame": "",
  }


def save_settings(guild_id, settings):
  guild_id_str = str(guild_id)
  data_to_save = {
      "guild_id": guild_id_str,
      "media_channels": settings.get("media_channels", []),
      "media_warning": settings.get("media_warning", ""),
      "banned_words": settings.get("banned_words", []),
      "max_violations": settings.get("max_violations", 3),
      "punishment_type": settings.get("punishment_type", "timeout"),
      "timeout_minutes": settings.get("timeout_minutes", 10),
      "warning_title": settings.get("warning_title", ""),
      "warning_msg_1": settings.get("warning_msg_1", ""),
      "warning_msg_2": settings.get("warning_msg_2", ""),
      "farewell_channel": settings.get("farewell_channel", ""),
      "farewell_title": settings.get("farewell_title", ""),
      "farewell_desc": settings.get("farewell_desc", ""),
      "farewell_img": settings.get("farewell_img", ""),
      "farewell_action": settings.get("farewell_action", "none"),
      "auto_responses": settings.get("auto_responses", {}),
      "auto_role": settings.get("auto_role", ""),
      "auto_nickname": settings.get("auto_nickname", ""),
      "ticket_category": settings.get("ticket_category", ""),
      "ticket_support_role": settings.get("ticket_support_role", ""),
      "xp_enabled": int(settings.get("xp_enabled", 1)),
      "xp_per_message": int(settings.get("xp_per_message", 15)),
      "xp_role_5": str(settings.get("xp_role_5", "")),
      "xp_role_10": str(settings.get("xp_role_10", "")),
      "xp_role_20": str(settings.get("xp_role_20", "")),
      "language": str(settings.get("language", "ar")),
      "welcome_enabled": int(settings.get("welcome_enabled", 1)),
      "welcome_channel": str(settings.get("welcome_channel", "")),
      "welcome_msg": str(settings.get("welcome_msg", "")),
      "welcome_img": str(settings.get("welcome_img", "")),
      "welcome_frame": str(settings.get("welcome_frame", "")),
  }
  
  settings_collection.update_one(
      {"guild_id": guild_id_str},
      {"$set": data_to_save},
      upsert=True
  )


# دوال إدارة نظام المستويات والخبرة (XP)
def add_user_xp(guild_id, user_id, xp_amount=15):
  g_id, u_id = str(guild_id), str(user_id)
  row = levels_collection.find_one({"guild_id": g_id, "user_id": u_id})

  if row:
    xp = row.get("xp", 0)
    level = row.get("level", 1)
  else:
    xp, level = 0, 1

  xp += xp_amount
  next_level_xp = level * 100 + 100
  leveled_up = False

  if xp >= next_level_xp:
    level += 1
    leveled_up = True

  levels_collection.update_one(
      {"guild_id": g_id, "user_id": u_id},
      {"$set": {"xp": xp, "level": level}},
      upsert=True
  )
  return level, leveled_up


def get_user_level(guild_id, user_id):
  row = levels_collection.find_one({"guild_id": str(guild_id), "user_id": str(user_id)})

  if row:
    return row.get("xp", 0), row.get("level", 1)
  return 0, 1


def get_top_users(guild_id, limit=10):
  cursor = levels_collection.find({"guild_id": str(guild_id)}).sort("xp", -1).limit(limit)
  rows = []
  for doc in cursor:
    rows.append((doc.get("user_id"), doc.get("xp", 0), doc.get("level", 1)))
  return rows

# --- دوال نظام النسخ المتطابق والشبكات ---
def create_network(network_id, network_name, owner_id):
    networks_collection.insert_one({
        "network_id": network_id,
        "network_name": network_name,
        "owner_id": str(owner_id)
    })

def get_network(network_id):
    return networks_collection.find_one({"network_id": network_id})

def join_network(guild_id, network_id, bound_channel_id):
    network_guilds_collection.update_one(
        {"guild_id": str(guild_id)},
        {
            "$set": {
                "network_id": network_id,
                "bound_channel_id": str(bound_channel_id),
                "is_banned_sync_enabled": True
            }
        },
        upsert=True
    )

def get_guild_network(guild_id):
    return network_guilds_collection.find_one({"guild_id": str(guild_id)})

def get_network_guilds(network_id):
    return list(network_guilds_collection.find({"network_id": network_id}))

def delete_network(network_id):
    # حذف الشبكة نفسها
    networks_collection.delete_one({"network_id": network_id})
    # حذف جميع السيرفرات المرتبطة بهذه الشبكة
    network_guilds_collection.delete_many({"network_id": network_id})
  

init_db()
