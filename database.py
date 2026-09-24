import os
import re

from pymongo import MongoClient, ReturnDocument
from pymongo.errors import (
    PyMongoError,
    DuplicateKeyError,
    ServerSelectionTimeoutError,
)

# ============================================================
# CONFIGURATION
# ============================================================

MONGO_URI = os.getenv("MONGO_URI")

DATABASE_NAME = "bot_database"

MONGO_SERVER_SELECTION_TIMEOUT_MS = 5000
MONGO_CONNECT_TIMEOUT_MS = 5000
MONGO_SOCKET_TIMEOUT_MS = 10000

MAX_NETWORK_NAME_LENGTH = 80

MAX_SETTINGS_LIST_ITEMS = 500
MAX_BANNED_WORDS = 500
MAX_AUTO_RESPONSES = 500

MAX_TEXT_LENGTH = 2000
MAX_WARNING_LENGTH = 2000
MAX_URL_LENGTH = 2048

MAX_XP_AMOUNT = 100000
MAX_LIMIT = 100

NETWORK_ID_PATTERN = re.compile(r"^net_\d+$")

ALLOWED_LANGUAGES = {"ar", "en"}

ALLOWED_PUNISHMENTS = {
    "timeout",
    "kick",
    "ban",
    "none",
}

ALLOWED_FAREWELL_ACTIONS = {
    "none",
    "delete",
    "ban",
    "kick",
}

# ============================================================
# MONGODB CONNECTION
# ============================================================

if not MONGO_URI:
    print("❌ MONGO_URI غير موجود في متغيرات البيئة.")
    client = None
    db = None

    settings_collection = None
    levels_collection = None
    networks_collection = None
    network_guilds_collection = None
    shifts_collection = None

else:
    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=MONGO_SERVER_SELECTION_TIMEOUT_MS,
        connectTimeoutMS=MONGO_CONNECT_TIMEOUT_MS,
        socketTimeoutMS=MONGO_SOCKET_TIMEOUT_MS,
        retryWrites=True,
    )

    db = client.get_database(
        DATABASE_NAME
    )

    # ========================================================
    # COLLECTIONS
    # ========================================================

    settings_collection = db["guild_settings"]
    levels_collection = db["user_levels"]

    networks_collection = db["networks"]
    network_guilds_collection = db["network_guilds"]

    shifts_collection = db["staff_shifts"]


# ============================================================
# INTERNAL HELPERS
# ============================================================

def _require_db():
    if (
        client is None
        or db is None
        or settings_collection is None
    ):
        raise RuntimeError(
            "MongoDB غير مهيأة. تحقق من MONGO_URI."
        )


def _safe_int(
    value,
    default=0,
    minimum=None,
    maximum=None
):
    try:
        value = int(value)
    except (
        TypeError,
        ValueError,
        OverflowError
    ):
        value = default

    if minimum is not None and value < minimum:
        value = minimum

    if maximum is not None and value > maximum:
        value = maximum

    return value


def _safe_string(
    value,
    default="",
    maximum_length=None
):
    if value is None:
        value = default

    try:
        value = str(value)
    except Exception:
        return default

    value = value.strip()

    if maximum_length is not None:
        value = value[:maximum_length]

    return value


def _safe_bool_int(value, default=1):
    if isinstance(value, bool):
        return 1 if value else 0

    if value in (0, 1):
        return int(value)

    try:
        value = int(value)
        return 1 if value else 0
    except (
        TypeError,
        ValueError,
        OverflowError
    ):
        return default


def _clean_id(value):
    if value is None:
        return ""

    return str(value).strip()


def _sanitize_list(
    value,
    maximum_items=MAX_SETTINGS_LIST_ITEMS,
    maximum_item_length=200
):
    if not isinstance(value, list):
        return []

    result = []

    for item in value[:maximum_items]:

        if item is None:
            continue

        item = str(item).strip()

        if not item:
            continue

        result.append(
            item[:maximum_item_length]
        )

    return result


def _sanitize_auto_responses(value):
    if not isinstance(value, dict):
        return {}

    result = {}

    for key, response in list(
        value.items()
    )[:MAX_AUTO_RESPONSES]:

        key = _safe_string(
            key,
            maximum_length=200
        )

        response = _safe_string(
            response,
            maximum_length=MAX_TEXT_LENGTH
        )

        if not key:
            continue

        result[key] = response

    return result


def _sanitize_network_id(network_id):
    network_id = _clean_id(network_id)

    if not NETWORK_ID_PATTERN.fullmatch(
        network_id
    ):
        return None

    return network_id


def _sanitize_network_name(network_name):
    network_name = _safe_string(
        network_name,
        maximum_length=MAX_NETWORK_NAME_LENGTH
    )

    if not network_name:
        return None

    return network_name


def _strip_mongo_id(document):
    if not document:
        return document

    document.pop("_id", None)

    return document


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():

    _require_db()

    try:

        # ----------------------------------------------------
        # Connection test
        # ----------------------------------------------------

        client.admin.command("ping")

        # ----------------------------------------------------
        # Guild settings
        # ----------------------------------------------------

        settings_collection.create_index(
            "guild_id",
            unique=True,
            name="guild_settings_guild_id_unique"
        )

        # ----------------------------------------------------
        # XP
        # ----------------------------------------------------

        levels_collection.create_index(
            [
                ("guild_id", 1),
                ("user_id", 1)
            ],
            unique=True,
            name="user_levels_guild_user_unique"
        )

        levels_collection.create_index(
            [
                ("guild_id", 1),
                ("xp", -1)
            ],
            name="user_levels_guild_xp"
        )

        # ----------------------------------------------------
        # Networks
        # ----------------------------------------------------

        networks_collection.create_index(
            "network_id",
            unique=True,
            name="networks_network_id_unique"
        )

        # ----------------------------------------------------
        # Network guild links
        # IMPORTANT: UNIQUE
        # ----------------------------------------------------

        network_guilds_collection.create_index(
            [
                ("guild_id", 1),
                ("network_id", 1)
            ],
            unique=True,
            name="network_guild_unique"
        )

        network_guilds_collection.create_index(
            "network_id",
            name="network_id_lookup"
        )

        network_guilds_collection.create_index(
            [
                ("network_id", 1),
                ("guild_id", 1)
            ],
            name="network_guild_guild_lookup"
        )

        # ----------------------------------------------------
        # Staff shifts
        # ----------------------------------------------------

        shifts_collection.create_index(
            [
                ("guild_id", 1),
                ("user_id", 1)
            ],
            unique=True,
            name="staff_shift_guild_user_unique"
        )

        shifts_collection.create_index(
            [
                ("guild_id", 1),
                ("total_seconds", -1)
            ],
            name="staff_shift_guild_seconds"
        )

        print(
            "✅ تم الاتصال بقاعدة بيانات MongoDB "
            "وإنشاء/التحقق من الـ Indexes بنجاح!"
        )

        return True

    except ServerSelectionTimeoutError as e:

        print(
            f"❌ تعذر الوصول إلى MongoDB خلال المهلة المحددة: {e}"
        )

        return False

    except PyMongoError as e:

        print(
            f"❌ خطأ في MongoDB أثناء تهيئة قاعدة البيانات: {e}"
        )

        return False

    except Exception as e:

        print(
            f"❌ خطأ غير متوقع أثناء تهيئة قاعدة البيانات: {e}"
        )

        return False


# ============================================================
# GUILD SETTINGS
# ============================================================

def get_settings(guild_id):

    _require_db()

    guild_id_str = _clean_id(
        guild_id
    )

    if not guild_id_str:
        guild_id_str = "0"

    row = settings_collection.find_one(
        {
            "guild_id": guild_id_str
        }
    )

    if row:

        _strip_mongo_id(row)

        return {
            "guild_id": row.get(
                "guild_id",
                guild_id_str
            ),

            "media_channels": _sanitize_list(
                row.get("media_channels", [])
            ),

            "media_warning": _safe_string(
                row.get("media_warning"),
                "عذراً {user}، هذه القناة مخصصة للميديا فقط!",
                MAX_WARNING_LENGTH
            ),

            "banned_words": _sanitize_list(
                row.get("banned_words", []),
                MAX_BANNED_WORDS
            ),

            "max_violations": _safe_int(
                row.get("max_violations"),
                3,
                1,
                100
            ),

            "punishment_type": (
                row.get("punishment_type")
                if row.get("punishment_type")
                in ALLOWED_PUNISHMENTS
                else "timeout"
            ),

            "timeout_minutes": _safe_int(
                row.get("timeout_minutes"),
                10,
                1,
                10080
            ),

            "warning_title": _safe_string(
                row.get("warning_title"),
                "تحذير مخالفة",
                MAX_TEXT_LENGTH
            ),

            "warning_msg_1": _safe_string(
                row.get("warning_msg_1"),
                "تنبيه أول يا {user}، يرجى الالتزام بالقوانين.",
                MAX_WARNING_LENGTH
            ),

            "warning_msg_2": _safe_string(
                row.get("warning_msg_2"),
                "تنبيه ثاني يا {user}، المخالفة القادمة ستعرضك للعقوبة!",
                MAX_WARNING_LENGTH
            ),

            "farewell_channel": _safe_string(
                row.get("farewell_channel"),
                "",
                32
            ),

            "farewell_title": _safe_string(
                row.get("farewell_title"),
                "وداعاً!",
                MAX_TEXT_LENGTH
            ),

            "farewell_desc": _safe_string(
                row.get("farewell_desc"),
                "غادر العضو {user} السيرفر.",
                MAX_TEXT_LENGTH
            ),

            "farewell_img": _safe_string(
                row.get("farewell_img"),
                "",
                MAX_URL_LENGTH
            ),

            "farewell_action": (
                row.get("farewell_action")
                if row.get("farewell_action")
                in ALLOWED_FAREWELL_ACTIONS
                else "none"
            ),

            "auto_responses": _sanitize_auto_responses(
                row.get("auto_responses", {})
            ),

            "auto_role": _safe_string(
                row.get("auto_role"),
                "",
                32
            ),

            "auto_nickname": _safe_string(
                row.get("auto_nickname"),
                "",
                32
            ),

            "ticket_status": _safe_string(
                row.get("ticket_status"),
                "enabled",
                32
            ),

            "ticket_category": _safe_string(
                row.get("ticket_category"),
                "",
                32
            ),

            "ticket_support_role": _safe_string(
                row.get(
                    "ticket_support_role",
                    row.get(
                        "support_role",
                        ""
                    )
                ),
                "",
                32
            ),

            "ticket_archive_channel": _safe_string(
                row.get("ticket_archive_channel"),
                "",
                32
            ),

            "xp_enabled": _safe_bool_int(
                row.get("xp_enabled"),
                1
            ),

            "xp_per_message": _safe_int(
                row.get("xp_per_message"),
                15,
                0,
                MAX_XP_AMOUNT
            ),

            "xp_role_5": _safe_string(
                row.get("xp_role_5"),
                "",
                32
            ),

            "xp_role_10": _safe_string(
                row.get("xp_role_10"),
                "",
                32
            ),

            "xp_role_20": _safe_string(
                row.get("xp_role_20"),
                "",
                32
            ),

            "language": (
                row.get("language")
                if row.get("language")
                in ALLOWED_LANGUAGES
                else "ar"
            ),

            "welcome_enabled": _safe_bool_int(
                row.get("welcome_enabled"),
                1
            ),

            "welcome_channel": _safe_string(
                row.get("welcome_channel"),
                "",
                32
            ),

            "welcome_msg": _safe_string(
                row.get("welcome_msg"),
                "أهلاً بك يا {user} في السيرفر! 🎉",
                MAX_TEXT_LENGTH
            ),

            "welcome_img": _safe_string(
                row.get("welcome_img"),
                "",
                MAX_URL_LENGTH
            ),

            "welcome_frame": _safe_string(
                row.get("welcome_frame"),
                "",
                100
            ),

            "text_1": _safe_string(
                row.get("text_1"),
                "",
                MAX_TEXT_LENGTH
            ),

            "text_2": _safe_string(
                row.get("text_2"),
                "",
                MAX_TEXT_LENGTH
            ),

            "text_3": _safe_string(
                row.get("text_3"),
                "",
                MAX_TEXT_LENGTH
            ),

            "color_1": _safe_string(
                row.get("color_1"),
                "#FFFFFF",
                20
            ),

            "color_2": _safe_string(
                row.get("color_2"),
                "#FFD700",
                20
            ),

            "color_3": _safe_string(
                row.get("color_3"),
                "#FFFFFF",
                20
            ),
        }

    # ========================================================
    # DEFAULT SETTINGS
    # ========================================================

    return {
        "guild_id": guild_id_str,

        "media_channels": [],

        "media_warning":
            "عذراً {user}، هذه القناة مخصصة للميديا فقط!",

        "banned_words": [],

        "max_violations": 3,

        "punishment_type":
            "timeout",

        "timeout_minutes":
            10,

        "warning_title":
            "⚠️ تحذير نظام الحماية",

        "warning_msg_1":
            "تنبيه أول يا {user}، يرجى الالتزام بالقوانين.",

        "warning_msg_2":
            "تنبيه ثاني يا {user}، المخالفة القادمة ستعرضك للعقوبة!",

        "farewell_channel":
            "",

        "farewell_title":
            "وداعاً!",

        "farewell_desc":
            "غادر العضو {user} السيرفر نتمنى له التوفيق.",

        "farewell_img":
            "",

        "farewell_action":
            "none",

        "auto_responses":
            {},

        "auto_role":
            "",

        "auto_nickname":
            "",

        "ticket_status":
            "enabled",

        "ticket_category":
            "",

        "ticket_support_role":
            "",

        "ticket_archive_channel":
            "",

        "xp_enabled":
            1,

        "xp_per_message":
            15,

        "xp_role_5":
            "",

        "xp_role_10":
            "",

        "xp_role_20":
            "",

        "language":
            "ar",

        "welcome_enabled":
            1,

        "welcome_channel":
            "",

        "welcome_msg":
            "أهلاً بك يا {user} في السيرفر! 🎉",

        "welcome_img":
            "",

        "welcome_frame":
            "",

        "text_1":
            "",

        "text_2":
            "",

        "text_3":
            "",

        "color_1":
            "#FFFFFF",

        "color_2":
            "#FFD700",

        "color_3":
            "#FFFFFF",
    }


# ============================================================
# SAVE SETTINGS
# ============================================================

def save_settings(
    guild_id,
    settings
):

    _require_db()

    if not isinstance(
        settings,
        dict
    ):
        raise TypeError(
            "settings يجب أن يكون Dictionary."
        )

    guild_id_str = _clean_id(
        guild_id
    )

    if not guild_id_str:
        raise ValueError(
            "guild_id غير صالح."
        )

    data_to_save = {

        "guild_id":
            guild_id_str,

        "media_channels":
            _sanitize_list(
                settings.get(
                    "media_channels",
                    []
                )
            ),

        "media_warning":
            _safe_string(
                settings.get(
                    "media_warning",
                    ""
                ),
                "",
                MAX_WARNING_LENGTH
            ),

        "banned_words":
            _sanitize_list(
                settings.get(
                    "banned_words",
                    []
                ),
                MAX_BANNED_WORDS
            ),

        "max_violations":
            _safe_int(
                settings.get(
                    "max_violations",
                    3
                ),
                3,
                1,
                100
            ),

        "punishment_type":
            (
                settings.get(
                    "punishment_type",
                    "timeout"
                )
                if settings.get(
                    "punishment_type",
                    "timeout"
                )
                in ALLOWED_PUNISHMENTS
                else "timeout"
            ),

        "timeout_minutes":
            _safe_int(
                settings.get(
                    "timeout_minutes",
                    10
                ),
                10,
                1,
                10080
            ),

        "warning_title":
            _safe_string(
                settings.get(
                    "warning_title",
                    ""
                ),
                "",
                MAX_TEXT_LENGTH
            ),

        "warning_msg_1":
            _safe_string(
                settings.get(
                    "warning_msg_1",
                    ""
                ),
                "",
                MAX_WARNING_LENGTH
            ),

        "warning_msg_2":
            _safe_string(
                settings.get(
                    "warning_msg_2",
                    ""
                ),
                "",
                MAX_WARNING_LENGTH
            ),

        "farewell_channel":
            _safe_string(
                settings.get(
                    "farewell_channel",
                    ""
                ),
                "",
                32
            ),

        "farewell_title":
            _safe_string(
                settings.get(
                    "farewell_title",
                    ""
                ),
                "",
                MAX_TEXT_LENGTH
            ),

        "farewell_desc":
            _safe_string(
                settings.get(
                    "farewell_desc",
                    ""
                ),
                "",
                MAX_TEXT_LENGTH
            ),

        "farewell_img":
            _safe_string(
                settings.get(
                    "farewell_img",
                    ""
                ),
                "",
                MAX_URL_LENGTH
            ),

        "farewell_action":
            (
                settings.get(
                    "farewell_action",
                    "none"
                )
                if settings.get(
                    "farewell_action",
                    "none"
                )
                in ALLOWED_FAREWELL_ACTIONS
                else "none"
            ),

        "auto_responses":
            _sanitize_auto_responses(
                settings.get(
                    "auto_responses",
                    {}
                )
            ),

        "auto_role":
            _safe_string(
                settings.get(
                    "auto_role",
                    ""
                ),
                "",
                32
            ),

        "auto_nickname":
            _safe_string(
                settings.get(
                    "auto_nickname",
                    ""
                ),
                "",
                32
            ),

        "ticket_status":
            _safe_string(
                settings.get(
                    "ticket_status",
                    "enabled"
                ),
                "enabled",
                32
            ),

        "ticket_category":
            _safe_string(
                settings.get(
                    "ticket_category",
                    ""
                ),
                "",
                32
            ),

        "ticket_support_role":
            _safe_string(
                settings.get(
                    "ticket_support_role",
                    ""
                ),
                "",
                32
            ),

        "ticket_archive_channel":
            _safe_string(
                settings.get(
                    "ticket_archive_channel",
                    ""
                ),
                "",
                32
            ),

        "xp_enabled":
            _safe_bool_int(
                settings.get(
                    "xp_enabled",
                    1
                ),
                1
            ),

        "xp_per_message":
            _safe_int(
                settings.get(
                    "xp_per_message",
                    15
                ),
                15,
                0,
                MAX_XP_AMOUNT
            ),

        "xp_role_5":
            _safe_string(
                settings.get(
                    "xp_role_5",
                    ""
                ),
                "",
                32
            ),

        "xp_role_10":
            _safe_string(
                settings.get(
                    "xp_role_10",
                    ""
                ),
                "",
                32
            ),

        "xp_role_20":
            _safe_string(
                settings.get(
                    "xp_role_20",
                    ""
                ),
                "",
                32
            ),

        "language":
            (
                settings.get(
                    "language",
                    "ar"
                )
                if settings.get(
                    "language",
                    "ar"
                )
                in ALLOWED_LANGUAGES
                else "ar"
            ),

        "welcome_enabled":
            _safe_bool_int(
                settings.get(
                    "welcome_enabled",
                    1
                ),
                1
            ),

        "welcome_channel":
            _safe_string(
                settings.get(
                    "welcome_channel",
                    ""
                ),
                "",
                32
            ),

        "welcome_msg":
            _safe_string(
                settings.get(
                    "welcome_msg",
                    ""
                ),
                "",
                MAX_TEXT_LENGTH
            ),

        "welcome_img":
            _safe_string(
                settings.get(
                    "welcome_img",
                    ""
                ),
                "",
                MAX_URL_LENGTH
            ),

        "welcome_frame":
            _safe_string(
                settings.get(
                    "welcome_frame",
                    ""
                ),
                "",
                100
            ),

        "text_1":
            _safe_string(
                settings.get(
                    "text_1",
                    ""
                ),
                "",
                MAX_TEXT_LENGTH
            ),

        "text_2":
            _safe_string(
                settings.get(
                    "text_2",
                    ""
                ),
                "",
                MAX_TEXT_LENGTH
            ),

        "text_3":
            _safe_string(
                settings.get(
                    "text_3",
                    ""
                ),
                "",
                MAX_TEXT_LENGTH
            ),

        "color_1":
            _safe_string(
                settings.get(
                    "color_1",
                    "#FFFFFF"
                ),
                "#FFFFFF",
                20
            ),

        "color_2":
            _safe_string(
                settings.get(
                    "color_2",
                    "#FFD700"
                ),
                "#FFD700",
                20
            ),

        "color_3":
            _safe_string(
                settings.get(
                    "color_3",
                    "#FFFFFF"
                ),
                "#FFFFFF",
                20
            ),
    }

    settings_collection.update_one(
        {
            "guild_id":
                guild_id_str
        },
        {
            "$set":
                data_to_save
        },
        upsert=True
    )

    return True


# ============================================================
# XP SYSTEM
# ============================================================

def add_user_xp(
    guild_id,
    user_id,
    xp_amount=15
):

    _require_db()

    g_id = _clean_id(
        guild_id
    )

    u_id = _clean_id(
        user_id
    )

    if not g_id or not u_id:
        raise ValueError(
            "guild_id أو user_id غير صالح."
        )

    xp_amount = _safe_int(
        xp_amount,
        15,
        0,
        MAX_XP_AMOUNT
    )

    if xp_amount <= 0:
        return get_user_level(
            g_id,
            u_id
        )[1], False

    # --------------------------------------------------------
    # Atomic XP update
    #
    # Instead of:
    #
    # find -> calculate -> update
    #
    # MongoDB performs the update atomically.
    # --------------------------------------------------------

    old_row = levels_collection.find_one(
        {
            "guild_id": g_id,
            "user_id": u_id
        },
        {
            "level": 1,
            "xp": 1
        }
    )

    old_level = _safe_int(
        old_row.get("level", 1)
        if old_row
        else 1,
        1,
        1,
        1000000000
    )

    updated_row = levels_collection.find_one_and_update(
        {
            "guild_id": g_id,
            "user_id": u_id
        },
        [
            {
                "$set": {
                    "xp": {
                        "$add": [
                            {
                                "$ifNull": [
                                    "$xp",
                                    0
                                ]
                            },
                            xp_amount
                        ]
                    }
                }
            },
            {
                "$set": {
                    "level": {
                        "$max": [
                            1,
                            {
                                "$floor": {
                                    "$divide": [
                                        "$xp",
                                        100
                                    ]
                                }
                            }
                        ]
                    }
                }
            }
        ],
        upsert=True,
        return_document=ReturnDocument.AFTER
    )

    if not updated_row:
        return old_level, False

    new_xp = _safe_int(
        updated_row.get(
            "xp",
            0
        ),
        0,
        0
    )

    new_level = _safe_int(
        updated_row.get(
            "level",
            1
        ),
        1,
        1
    )

    leveled_up = (
        new_level > old_level
    )

    return new_level, leveled_up


def get_user_level(
    guild_id,
    user_id
):

    _require_db()

    row = levels_collection.find_one(
        {
            "guild_id":
                _clean_id(guild_id),

            "user_id":
                _clean_id(user_id)
        }
    )

    if row:

        return (
            _safe_int(
                row.get("xp", 0),
                0,
                0
            ),

            _safe_int(
                row.get("level", 1),
                1,
                1
            )
        )

    return 0, 1


def get_top_users(
    guild_id,
    limit=10
):

    _require_db()

    limit = _safe_int(
        limit,
        10,
        1,
        MAX_LIMIT
    )

    cursor = (
        levels_collection
        .find(
            {
                "guild_id":
                    _clean_id(guild_id)
            }
        )
        .sort(
            "xp",
            -1
        )
        .limit(limit)
    )

    rows = []

    for doc in cursor:

        rows.append(
            (
                doc.get(
                    "user_id"
                ),

                _safe_int(
                    doc.get("xp", 0),
                    0,
                    0
                ),

                _safe_int(
                    doc.get("level", 1),
                    1,
                    1
                )
            )
        )

    return rows


# ============================================================
# NETWORK SYSTEM
# ============================================================

def create_network(
    network_id,
    network_name,
    owner_id
):

    _require_db()

    network_id = _sanitize_network_id(
        network_id
    )

    network_name = _sanitize_network_name(
        network_name
    )

    owner_id = _clean_id(
        owner_id
    )

    if not network_id:
        raise ValueError(
            "network_id غير صالح."
        )

    if not network_name:
        raise ValueError(
            "network_name غير صالح."
        )

    if not owner_id:
        raise ValueError(
            "owner_id غير صالح."
        )

    # --------------------------------------------------------
    # IMPORTANT:
    # This function no longer silently overwrites the owner
    # of an existing network.
    #
    # Authorization must still be checked by the Cog.
    # --------------------------------------------------------

    try:

        result = networks_collection.update_one(
            {
                "network_id":
                    network_id
            },
            {
                "$setOnInsert": {
                    "network_id":
                        network_id,

                    "network_name":
                        network_name,

                    "owner_id":
                        owner_id,
                }
            },
            upsert=True
        )

        return result

    except DuplicateKeyError:

        # Another process created the network
        # simultaneously.

        return None


def get_network(
    network_id
):

    _require_db()

    network_id = _sanitize_network_id(
        network_id
    )

    if not network_id:
        return None

    row = networks_collection.find_one(
        {
            "network_id":
                network_id
        }
    )

    if not row:
        return None

    return _strip_mongo_id(
        row
    )


def join_network(
    guild_id,
    network_id,
    bound_channel_id
):

    _require_db()

    guild_id = _clean_id(
        guild_id
    )

    network_id = _sanitize_network_id(
        network_id
    )

    bound_channel_id = _clean_id(
        bound_channel_id
    )

    if not guild_id:
        raise ValueError(
            "guild_id غير صالح."
        )

    if not network_id:
        raise ValueError(
            "network_id غير صالح."
        )

    if not bound_channel_id:
        raise ValueError(
            "bound_channel_id غير صالح."
        )

    # --------------------------------------------------------
    # Prevent links to deleted/non-existing networks.
    # --------------------------------------------------------

    network_exists = networks_collection.find_one(
        {
            "network_id":
                network_id
        },
        {
            "_id": 1
        }
    )

    if not network_exists:
        raise ValueError(
            "لا يمكن ربط السيرفر بشبكة غير موجودة."
        )

    try:

        return network_guilds_collection.update_one(
            {
                "guild_id":
                    guild_id,

                "network_id":
                    network_id
            },
            {
                "$set": {
                    "guild_id":
                        guild_id,

                    "network_id":
                        network_id,

                    "bound_channel_id":
                        bound_channel_id
                }
            },
            upsert=True
        )

    except DuplicateKeyError:

        return None


def get_guild_networks(
    guild_id
):

    _require_db()

    rows = network_guilds_collection.find(
        {
            "guild_id":
                _clean_id(guild_id)
        }
    )

    result = []

    for row in rows:

        result.append(
            _strip_mongo_id(
                row
            )
        )

    return result


def get_network_guilds(
    network_id
):

    _require_db()

    network_id = _sanitize_network_id(
        network_id
    )

    if not network_id:
        return []

    rows = network_guilds_collection.find(
        {
            "network_id":
                network_id
        }
    )

    result = []

    for row in rows:

        result.append(
            _strip_mongo_id(
                row
            )
        )

    return result


def delete_network(
    network_id
):

    _require_db()

    network_id = _sanitize_network_id(
        network_id
    )

    if not network_id:
        raise ValueError(
            "network_id غير صالح."
        )

    # --------------------------------------------------------
    # We intentionally remove links first.
    #
    # If the second operation fails, the network remains but
    # without links, which is safer than leaving orphaned
    # network_guilds pointing to a deleted network.
    # --------------------------------------------------------

    network_guilds_collection.delete_many(
        {
            "network_id":
                network_id
        }
    )

    result = networks_collection.delete_one(
        {
            "network_id":
                network_id
        }
    )

    return result.deleted_count > 0


def leave_network(
    guild_id,
    network_id
):

    _require_db()

    guild_id = _clean_id(
        guild_id
    )

    network_id = _sanitize_network_id(
        network_id
    )

    if not guild_id:
        raise ValueError(
            "guild_id غير صالح."
        )

    if not network_id:
        raise ValueError(
            "network_id غير صالح."
        )

    result = network_guilds_collection.delete_one(
        {
            "guild_id":
                guild_id,

            "network_id":
                network_id
        }
    )

    return result.deleted_count > 0


# ============================================================
# STAFF SHIFTS
# ============================================================

def get_staff_shift_stats(
    guild_id,
    user_id
):

    _require_db()

    g_id = _clean_id(
        guild_id
    )

    u_id = _clean_id(
        user_id
    )

    row = shifts_collection.find_one(
        {
            "guild_id":
                g_id,

            "user_id":
                u_id
        }
    )

    if row:

        return {
            "total_seconds":
                _safe_int(
                    row.get(
                        "total_seconds",
                        0
                    ),
                    0,
                    0
                ),

            "shifts_count":
                _safe_int(
                    row.get(
                        "shifts_count",
                        0
                    ),
                    0,
                    0
                ),

            "points":
                _safe_int(
                    row.get(
                        "points",
                        100
                    ),
                    100,
                    0
                )
        }

    return {
        "total_seconds":
            0,

        "shifts_count":
            0,

        "points":
            100
    }


def update_staff_shift_stats(
    guild_id,
    user_id,
    add_seconds,
    add_shifts,
    new_points
):

    _require_db()

    g_id = _clean_id(
        guild_id
    )

    u_id = _clean_id(
        user_id
    )

    add_seconds = _safe_int(
        add_seconds,
        0,
        0
    )

    add_shifts = _safe_int(
        add_shifts,
        0,
        0
    )

    new_points = _safe_int(
        new_points,
        100,
        0
    )

    return shifts_collection.update_one(
        {
            "guild_id":
                g_id,

            "user_id":
                u_id
        },
        {
            "$inc": {
                "total_seconds":
                    add_seconds,

                "shifts_count":
                    add_shifts
            },

            "$set": {
                "points":
                    new_points
            }
        },
        upsert=True
    )


def get_top_staff_shifts(
    guild_id,
    limit=10
):

    _require_db()

    limit = _safe_int(
        limit,
        10,
        1,
        MAX_LIMIT
    )

    cursor = (
        shifts_collection
        .find(
            {
                "guild_id":
                    _clean_id(guild_id)
            }
        )
        .sort(
            "total_seconds",
            -1
        )
        .limit(limit)
    )

    rows = []

    for doc in cursor:

        rows.append(
            (
                doc.get(
                    "user_id"
                ),

                _safe_int(
                    doc.get(
                        "total_seconds",
                        0
                    ),
                    0,
                    0
                ),

                _safe_int(
                    doc.get(
                        "shifts_count",
                        0
                    ),
                    0,
                    0
                ),

                _safe_int(
                    doc.get(
                        "points",
                        100
                    ),
                    100,
                    0
                )
            )
        )

    return rows


# ============================================================
# INITIALIZE DATABASE
# ============================================================

if client is not None:

    init_db()
