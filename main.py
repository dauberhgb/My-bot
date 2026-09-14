# ============================================================
# Discord Bot + Flask Dashboard
# Secure / Organized Main File
# ============================================================

import os
import secrets
import threading
import logging
import time
from datetime import timedelta
from functools import wraps
from io import BytesIO
from urllib.parse import urlencode
from collections import defaultdict

import static_ffmpeg
static_ffmpeg.add_paths()

import aiohttp
from aiohttp_socks import ProxyConnector
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

import discord
from discord import app_commands
from discord.ext import commands

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
)

import requests

import database
from translations import _


# ============================================================
# 1. LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("discord_bot")


# ============================================================
# 2. ENVIRONMENT / SECURITY CONFIGURATION
# ============================================================

TOKEN = os.getenv("TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "").strip()

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "").strip().rstrip("/")
REDIRECT_URI = os.getenv("REDIRECT_URI", "").strip()

OWNER_ID = 1462429084377157832

PORT = int(os.getenv("PORT", "8080"))

# يجب وضع FLASK_SECRET_KEY حقيقية في Environment Variables
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")

if not FLASK_SECRET_KEY:
    logger.warning(
        "FLASK_SECRET_KEY غير موجودة. "
        "قم بتعيينها في Environment Variables قبل استخدام Dashboard."
    )
    # لا نستخدم قيمة ثابتة ضعيفة.
    FLASK_SECRET_KEY = secrets.token_hex(32)


if not TOKEN:
    logger.error("TOKEN غير موجود في Environment Variables.")

if not CLIENT_ID or not CLIENT_SECRET:
    logger.warning(
        "CLIENT_ID أو CLIENT_SECRET غير موجودين. "
        "Discord OAuth2 لن يعمل حتى يتم ضبطهما."
    )


# ============================================================
# 3. DISCORD BOT
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
)

# منع تراكم المخالفات بلا حدود
violations = defaultdict(dict)

# سيتم تهيئة HTTP session عند تشغيل البوت
http_session: aiohttp.ClientSession | None = None

# لمنع تحميل Cogs عدة مرات عند reconnect
cogs_loaded = False


# ============================================================
# 4. AVAILABLE FRAMES
# ============================================================

AVAILABLE_FRAMES = {
    "admin_gold": {
        "en_name": "Admin Gold Luxury",
        "ar_name": "إطار الإدارة الذهبي الفاخر",
        "en_file": "frames/admin_gold.png",
        "ar_file": "frames/admin_gold_ar.png",
    },
    "cyberpunk": {
        "en_name": "Cyberpunk Neon",
        "ar_name": "إطار السايبر بانك و النيون",
        "en_file": "frames/cyberpunk.png",
        "ar_file": "frames/cyberpunk_ar.png",
    },
    "galaxy_space": {
        "en_name": "Deep Space Galaxy",
        "ar_name": "إطار الفضاء والمجرات",
        "en_file": "frames/galaxy_space.png",
        "ar_file": "frames/galaxy_space_ar.png",
    },
    "mafia_gangs": {
        "en_name": "Mafia & Gangs",
        "ar_name": "إطار العصابات والمافيا",
        "en_file": "frames/mafia_gangs.png",
        "ar_file": "frames/mafia_gangs_ar.png",
    },
    "royal_blue": {
        "en_name": "Royal Blue Classic",
        "ar_name": "إطار ملكي كلاسيكي",
        "en_file": "frames/royal_blue.png",
        "ar_file": "frames/royal_blue_ar.png",
    },
}


# ============================================================
# 5. GENERAL HELPERS
# ============================================================

ALLOWED_LANGUAGES = {"ar", "en"}

ALLOWED_PUNISHMENTS = {
    "timeout",
    "kick",
    "mute",
}

MAX_BANNED_WORDS = 100
MAX_AUTO_RESPONSES = 3

MAX_TIMEOUT_MINUTES = 40320  # 28 days
MAX_XP_PER_MESSAGE = 1000

MAX_TEXT_LENGTH = 1000
MAX_LONG_TEXT_LENGTH = 4000

MAX_IMAGE_BYTES = 8 * 1024 * 1024

ALLOWED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}


def get_base_url():
    """
    الحصول على عنوان لوحة التحكم.
    """

    if DASHBOARD_URL:
        return DASHBOARD_URL

    render_name = os.getenv("RENDER_SERVICE_NAME", "app")
    return f"https://{render_name}.onrender.com"


def get_redirect_uri():
    """
    URI الخاص بـ Discord OAuth2.
    """

    if REDIRECT_URI:
        return REDIRECT_URI

    return f"{get_base_url()}/auth/callback"


def get_guild_lang(guild_id):
    """
    الحصول على لغة السيرفر بشكل آمن.
    """

    if not guild_id:
        return "ar"

    try:
        settings = database.get_settings(str(guild_id)) or {}
        language = str(settings.get("language", "ar")).lower()

        if language not in ALLOWED_LANGUAGES:
            return "ar"

        return language

    except Exception:
        logger.exception("فشل الحصول على لغة السيرفر")
        return "ar"


def safe_int(value, default, minimum=None, maximum=None):
    """
    تحويل رقم من input بدون التسبب في 500.
    """

    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default

    if minimum is not None:
        result = max(result, minimum)

    if maximum is not None:
        result = min(result, maximum)

    return result


def clean_text(value, maximum=MAX_TEXT_LENGTH):
    """
    تنظيف النص وتحديد حجمه.
    """

    if value is None:
        return ""

    return str(value).strip()[:maximum]


def valid_discord_id(value):
    """
    التحقق من Discord Snowflake.
    """

    if value is None:
        return False

    value = str(value).strip()

    return value.isdigit() and 17 <= len(value) <= 20


def valid_hex_color(value, default="#FFFFFF"):
    """
    التحقق من لون Hex.
    """

    if not value:
        return default

    value = str(value).strip()

    if len(value) == 7 and value.startswith("#"):
        try:
            int(value[1:], 16)
            return value.upper()
        except ValueError:
            pass

    return default


def is_safe_image_url(url):
    """
    حماية أساسية من SSRF.

    نسمح فقط بـ HTTPS.
    """

    if not url:
        return False

    url = str(url).strip().lower()

    if not url.startswith("https://"):
        return False

    # منع localhost والعناوين المحلية الواضحة
    blocked = (
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "169.254.",
        "[::1]",
    )

    if any(item in url for item in blocked):
        return False

    return True


# ============================================================
# 6. FLASK DASHBOARD
# ============================================================

app = Flask(__name__)

app.secret_key = FLASK_SECRET_KEY

# إعدادات Cookie الآمنة
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "1") == "1",
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)


# ============================================================
# 7. CSRF
# ============================================================

def get_csrf_token():
    """
    إنشاء CSRF token خاص بالجلسة.
    """

    token = session.get("csrf_token")

    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token

    return token


def validate_csrf():
    """
    التحقق من CSRF في POST requests.
    """

    expected = session.get("csrf_token")

    supplied = (
        request.headers.get("X-CSRF-Token")
        or request.form.get("csrf_token")
    )

    if not expected or not supplied:
        return False

    return secrets.compare_digest(
        str(expected),
        str(supplied),
    )


@app.context_processor
def inject_security_context():
    return {
        "csrf_token": get_csrf_token(),
    }


# ============================================================
# 8. ADMIN AUTHORIZATION
# ============================================================

def admin_required(view_function):
    """
    حماية لوحة التحكم.

    مهم جداً:
    لا نثق أبداً بـ user_id القادم من:
    - query string
    - headers
    - form

    الهوية تؤخذ فقط من Flask session بعد OAuth.
    """

    @wraps(view_function)
    def decorated_function(guild_id, *args, **kwargs):

        if not valid_discord_id(guild_id):
            return jsonify({
                "status": "error",
                "message": "معرف السيرفر غير صالح.",
            }), 400

        try:
            guild = bot.get_guild(int(guild_id))
        except Exception:
            guild = None

        if not guild:
            if request.method == "POST":
                return jsonify({
                    "status": "error",
                    "message": "السيرفر غير موجود أو البوت ليس عضواً فيه.",
                }), 404

            return (
                "السيرفر غير موجود أو البوت ليس عضواً فيه.",
                404,
            )

        user_id = session.get("user_id")

        if not valid_discord_id(user_id):
            if request.method == "POST":
                return jsonify({
                    "status": "error",
                    "message": "جلسة تسجيل الدخول غير صالحة.",
                }), 401

            return redirect(url_for("login"))

        try:
            user_id_int = int(user_id)
        except ValueError:
            return jsonify({
                "status": "error",
                "message": "معرف المستخدم غير صالح.",
            }), 400

        is_authorized = False

        # صاحب البوت
        if user_id_int == OWNER_ID:
            is_authorized = True

        # مالك السيرفر
        elif user_id_int == guild.owner_id:
            is_authorized = True

        else:
            member = guild.get_member(user_id_int)

            if member:
                permissions = member.guild_permissions

                if (
                    permissions.administrator
                    or permissions.manage_guild
                ):
                    is_authorized = True

        if not is_authorized:
            if request.method == "POST":
                return jsonify({
                    "status": "error",
                    "message": (
                        "عذراً، لا تملك صلاحية إدارة هذا السيرفر."
                    ),
                }), 403

            return (
                "عذراً، لا تملك صلاحية إدارة هذا السيرفر.",
                403,
            )

        # CSRF للطلبات التي تغيّر البيانات
        if request.method == "POST":
            if not validate_csrf():
                return jsonify({
                    "status": "error",
                    "message": "طلب غير صالح: فشل التحقق الأمني CSRF.",
                }), 403

        return view_function(guild_id, *args, **kwargs)

    return decorated_function


# ============================================================
# 9. LOGIN
# ============================================================

@app.route("/")
def home():

    if session.get("user_id"):
        return redirect(url_for("guild_list"))

    return redirect(url_for("login"))


@app.route("/login")
def login():

    if not CLIENT_ID or not CLIENT_SECRET:
        return (
            "Discord OAuth2 غير مهيأ. تحقق من CLIENT_ID و CLIENT_SECRET.",
            500,
        )

    # State لمنع OAuth CSRF
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    session.permanent = True

    redirect_uri = get_redirect_uri()

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "identify guilds",
        "state": state,
    }

    discord_login_url = (
        "https://discord.com/api/oauth2/authorize?"
        + urlencode(params)
    )

    return redirect(discord_login_url)


# ============================================================
# 10. OAUTH CALLBACK
# ============================================================

@app.route("/auth/callback")
def auth_callback():

    code = request.args.get("code")
    state = request.args.get("state")

    expected_state = session.pop("oauth_state", None)

    if not code:
        return (
            "فشل تسجيل الدخول: لم يتم استلام رمز المصادقة.",
            400,
        )

    if (
        not state
        or not expected_state
        or not secrets.compare_digest(
            str(state),
            str(expected_state),
        )
    ):
        return (
            "فشل التحقق الأمني من تسجيل الدخول.",
            403,
        )

    redirect_uri = get_redirect_uri()

    token_data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:

        token_response = requests.post(
            "https://discord.com/api/oauth2/token",
            data=token_data,
            headers=headers,
            timeout=10,
        )

        if token_response.status_code != 200:
            logger.warning(
                "Discord OAuth token request failed: %s",
                token_response.status_code,
            )
            return (
                "فشل تسجيل الدخول عبر Discord.",
                400,
            )

        token_json = token_response.json()

        access_token = token_json.get("access_token")

        if not access_token:
            return (
                "فشل الحصول على رمز الوصول.",
                400,
            )

        user_headers = {
            "Authorization": f"Bearer {access_token}",
        }

        # معلومات المستخدم
        user_response = requests.get(
            "https://discord.com/api/users/@me",
            headers=user_headers,
            timeout=10,
        )

        if user_response.status_code != 200:
            return (
                "تعذر التحقق من حساب Discord.",
                400,
            )

        user_data = user_response.json()

        discord_user_id = user_data.get("id")

        if not valid_discord_id(discord_user_id):
            return (
                "استجابة Discord غير صالحة.",
                400,
            )

        # السيرفرات
        guilds_response = requests.get(
            "https://discord.com/api/users/@me/guilds",
            headers=user_headers,
            timeout=10,
        )

        if guilds_response.status_code != 200:
            return (
                "تعذر الحصول على سيرفرات Discord.",
                400,
            )

        guilds = guilds_response.json()

        admin_guilds = []

        for guild_data in guilds:

            guild_id = guild_data.get("id")

            if not valid_discord_id(guild_id):
                continue

            permissions = safe_int(
                guild_data.get("permissions"),
                0,
            )

            is_owner = bool(
                guild_data.get("owner", False)
            )

            has_admin = bool(
                permissions & 0x8
            )

            has_manage_guild = bool(
                permissions & 0x20
            )

            if (
                is_owner
                or has_admin
                or has_manage_guild
                or str(discord_user_id) == str(OWNER_ID)
            ):
                admin_guilds.append(str(guild_id))

        # تجديد الجلسة
        session.clear()

        session["user_id"] = str(discord_user_id)
        session["admin_guilds"] = admin_guilds
        session["csrf_token"] = secrets.token_urlsafe(32)
        session.permanent = True

        return redirect(url_for("guild_list"))

    except requests.RequestException:
        logger.exception("OAuth network error")
        return (
            "تعذر الاتصال بخدمات Discord. حاول مرة أخرى.",
            502,
        )

    except Exception:
        logger.exception("OAuth callback error")
        return (
            "حدث خطأ أثناء تسجيل الدخول.",
            500,
        )


# ============================================================
# 11. LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# ============================================================
# 12. GUILD LIST
# ============================================================

@app.route("/guilds")
def guild_list():

    user_id = session.get("user_id")

    if not valid_discord_id(user_id):
        return redirect(url_for("login"))

    bot_guilds = []

    for guild in bot.guilds:

        member = guild.get_member(int(user_id))

        authorized = False

        if int(user_id) == OWNER_ID:
            authorized = True

        elif int(user_id) == guild.owner_id:
            authorized = True

        elif member:
            authorized = (
                member.guild_permissions.administrator
                or member.guild_permissions.manage_guild
            )

        if not authorized:
            continue

        bot_guilds.append({
            "id": str(guild.id),
            "name": guild.name,
            "icon": (
                guild.icon.url
                if guild.icon
                else None
            ),
        })

    current_lang = "ar"

    if bot_guilds:
        try:
            settings = database.get_settings(
                bot_guilds[0]["id"]
            ) or {}

            current_lang = settings.get(
                "language",
                "ar",
            )
        except Exception:
            pass

    return render_template(
        "guilds.html",
        guilds=bot_guilds,
        user_id=user_id,
        current_lang=current_lang,
    )


# ============================================================
# 13. DASHBOARD
# ============================================================

@app.route("/dashboard/<guild_id>")
@admin_required
def dashboard(guild_id):

    guild = bot.get_guild(int(guild_id))

    if not guild:
        return "السيرفر غير موجود.", 404

    channels = [
        {
            "id": str(channel.id),
            "name": channel.name,
        }
        for channel in guild.text_channels
    ]

    roles = [
        {
            "id": str(role.id),
            "name": role.name,
        }
        for role in guild.roles
        if not role.is_default()
    ]

    categories = [
        {
            "id": str(category.id),
            "name": category.name,
        }
        for category in guild.categories
    ]

    settings = database.get_settings(
        guild_id
    ) or {}

    icon_url = (
        guild.icon.url
        if guild.icon
        else None
    )

    current_lang = settings.get(
        "language",
        "ar",
    )

    user_id = session.get("user_id")

    is_admin = False

    if user_id:

        uid = int(user_id)

        if uid == OWNER_ID:
            is_admin = True

        elif uid == guild.owner_id:
            is_admin = True

        else:
            member = guild.get_member(uid)

            if member:
                is_admin = (
                    member.guild_permissions.administrator
                    or member.guild_permissions.manage_guild
                )

    return render_template(
        "index.html",
        guild=guild,
        channels=channels,
        roles=roles,
        categories=categories,
        settings=settings,
        icon_url=icon_url,
        current_lang=current_lang,
        is_admin=is_admin,
        csrf_token=get_csrf_token(),
        **{
            "_": lambda text: text
        },
    )


# ============================================================
# 14. UPDATE LANGUAGE
# ============================================================

@app.route("/update_language/<guild_id>", methods=["POST"])
@admin_required
def update_language(guild_id):

    new_lang = clean_text(
        request.form.get("language"),
        10,
    ).lower()

    if new_lang not in ALLOWED_LANGUAGES:
        return jsonify({
            "status": "error",
            "message": "اللغة غير مدعومة.",
        }), 400

    settings = database.get_settings(
        guild_id
    ) or {}

    settings["language"] = new_lang

    database.save_settings(
        guild_id,
        settings,
    )

    return jsonify({
        "status": "success",
        "message": "تم تحديث اللغة بنجاح.",
    })


# ============================================================
# 15. SAVE DASHBOARD SETTINGS
# ============================================================

@app.route("/save/<guild_id>", methods=["POST"])
@admin_required
def save(guild_id):

    guild = bot.get_guild(int(guild_id))

    if not guild:
        return jsonify({
            "status": "error",
            "message": "السيرفر غير موجود.",
        }), 404

    # --------------------------------------------------------
    # Basic settings
    # --------------------------------------------------------

    language = clean_text(
        request.form.get("language", "ar"),
        10,
    ).lower()

    if language not in ALLOWED_LANGUAGES:
        language = "ar"

    media_enabled = (
        request.form.get("media_enabled") == "on"
    )

    banned_enabled = (
        request.form.get("banned_enabled") == "on"
    )

    farewell_enabled = (
        request.form.get("farewell_enabled") == "on"
    )

    raw_welcome = (
        str(
            request.form.get(
                "welcome_enabled",
                "",
            )
        )
        .strip()
        .lower()
    )

    welcome_enabled = raw_welcome not in {
        "0",
        "false",
        "off",
        "disabled",
        "معطل",
    }

    # --------------------------------------------------------
    # Media channels
    # --------------------------------------------------------

    media_channels = []

    for channel_id in request.form.getlist(
        "media_channels"
    ):

        channel_id = str(channel_id).strip()

        if not valid_discord_id(channel_id):
            continue

        channel = guild.get_channel(
            int(channel_id)
        )

        if isinstance(
            channel,
            discord.TextChannel,
        ):
            media_channels.append(
                channel_id
            )

    media_channels = list(
        dict.fromkeys(media_channels)
    )

    # --------------------------------------------------------
    # Banned words
    # --------------------------------------------------------

    banned_words_raw = request.form.get(
        "banned_words",
        "",
    )

    banned_words = []

    for word in banned_words_raw.split(","):

        word = clean_text(
            word,
            100,
        ).lower()

        if word:
            banned_words.append(word)

        if len(banned_words) >= MAX_BANNED_WORDS:
            break

    banned_words = list(
        dict.fromkeys(banned_words)
    )

    # --------------------------------------------------------
    # Auto responses
    # --------------------------------------------------------

    auto_responses = {}

    for i in range(1, MAX_AUTO_RESPONSES + 1):

        word = clean_text(
            request.form.get(
                f"word{i}",
                "",
            ),
            100,
        ).lower()

        response = clean_text(
            request.form.get(
                f"resp{i}",
                "",
            ),
            MAX_TEXT_LENGTH,
        )

        if word and response:
            auto_responses[word] = response

    # --------------------------------------------------------
    # Numeric validation
    # --------------------------------------------------------

    max_violations = safe_int(
        request.form.get("max_violations"),
        3,
        minimum=1,
        maximum=20,
    )

    timeout_minutes = safe_int(
        request.form.get("timeout_minutes"),
        10,
        minimum=1,
        maximum=MAX_TIMEOUT_MINUTES,
    )

    xp_enabled = safe_int(
        request.form.get("xp_enabled"),
        1,
        minimum=0,
        maximum=1,
    )

    xp_per_message = safe_int(
        request.form.get("xp_per_message"),
        15,
        minimum=0,
        maximum=MAX_XP_PER_MESSAGE,
    )

    # --------------------------------------------------------
    # Discord IDs
    # --------------------------------------------------------

    def get_valid_channel_id(field_name):
        value = str(
            request.form.get(
                field_name,
                "",
            )
        ).strip()

        if not valid_discord_id(value):
            return ""

        channel = guild.get_channel(
            int(value)
        )

        if isinstance(
            channel,
            (
                discord.TextChannel,
                discord.VoiceChannel,
                discord.CategoryChannel,
            ),
        ):
            return value

        return ""

    welcome_channel = get_valid_channel_id(
        "welcome_channel"
    )

    farewell_channel = get_valid_channel_id(
        "farewell_channel"
    )

    ticket_category = get_valid_channel_id(
        "ticket_category"
    )

    ticket_archive_channel = get_valid_channel_id(
        "ticket_archive_channel"
    )

    # --------------------------------------------------------
    # Role validation
    # --------------------------------------------------------

    def get_valid_role_id(field_name):
        value = str(
            request.form.get(
                field_name,
                "",
            )
        ).strip()

        if not valid_discord_id(value):
            return ""

        role = guild.get_role(
            int(value)
        )

        if not role:
            return ""

        return value

    xp_role_5 = get_valid_role_id(
        "xp_role_5"
    )

    xp_role_10 = get_valid_role_id(
        "xp_role_10"
    )

    xp_role_20 = get_valid_role_id(
        "xp_role_20"
    )

    ticket_support_role = get_valid_role_id(
        "ticket_support_role"
    )

    auto_role = get_valid_role_id(
        "auto_role"
    )

    # --------------------------------------------------------
    # Frame validation
    # --------------------------------------------------------

    welcome_frame = clean_text(
        request.form.get(
            "welcome_frame",
            "",
        ),
        50,
    )

    if welcome_frame not in AVAILABLE_FRAMES:
        welcome_frame = ""

    # --------------------------------------------------------
    # Settings
    # --------------------------------------------------------

    settings = {
        "guild_id": str(guild.id),

        "language": language,

        "media_enabled": media_enabled,
        "media_channels": media_channels,
        "media_warning": clean_text(
            request.form.get("media_warning", ""),
            MAX_TEXT_LENGTH,
        ),

        "banned_enabled": banned_enabled,
        "banned_words": banned_words,

        "max_violations": max_violations,

        "punishment_type": (
            request.form.get(
                "punishment_type",
                "timeout",
            )
            if request.form.get(
                "punishment_type",
                "timeout",
            )
            in ALLOWED_PUNISHMENTS
            else "timeout"
        ),

        "timeout_minutes": timeout_minutes,

        "warning_title": clean_text(
            request.form.get("warning_title", ""),
            256,
        ),

        "warning_msg_1": clean_text(
            request.form.get("warning_msg_1", ""),
            MAX_TEXT_LENGTH,
        ),

        "warning_msg_2": clean_text(
            request.form.get("warning_msg_2", ""),
            MAX_TEXT_LENGTH,
        ),

        "welcome_enabled": welcome_enabled,

        "welcome_channel": welcome_channel,

        "welcome_msg": clean_text(
            request.form.get("welcome_msg", ""),
            MAX_TEXT_LENGTH,
        ),

        "welcome_img": clean_text(
            request.form.get("welcome_img", ""),
            1000,
        ),

        "welcome_frame": welcome_frame,

        "farewell_enabled": farewell_enabled,

        "farewell_channel": farewell_channel,

        "farewell_title": clean_text(
            request.form.get("farewell_title", ""),
            256,
        ),

        "farewell_desc": clean_text(
            request.form.get("farewell_desc", ""),
            MAX_TEXT_LENGTH,
        ),

        "farewell_img": clean_text(
            request.form.get("farewell_img", ""),
            1000,
        ),

        "farewell_action": (
            request.form.get(
                "farewell_action",
                "none",
            )
            if request.form.get(
                "farewell_action",
                "none",
            )
            in {"none", "ban", "timeout"}
            else "none"
        ),

        "auto_responses": auto_responses,

        "auto_role": auto_role,

        "auto_nickname": clean_text(
            request.form.get("auto_nickname", ""),
            100,
        ),

        "ticket_status": (
            "enabled"
            if request.form.get(
                "ticket_status"
            ) == "1"
            else "disabled"
        ),

        "ticket_category": ticket_category,

        "ticket_support_role": ticket_support_role,

        "ticket_archive_channel":
            ticket_archive_channel,

        "xp_enabled": xp_enabled,

        "xp_per_message": xp_per_message,

        "xp_role_5": xp_role_5,
        "xp_role_10": xp_role_10,
        "xp_role_20": xp_role_20,

        "text_1": clean_text(
            request.form.get("text_1", ""),
            200,
        ),

        "text_2": clean_text(
            request.form.get("text_2", ""),
            200,
        ),

        "text_3": clean_text(
            request.form.get("text_3", ""),
            200,
        ),

        "color_1": valid_hex_color(
            request.form.get("color_1"),
            "#FFFFFF",
        ),

        "color_2": valid_hex_color(
            request.form.get("color_2"),
            "#FFD700",
        ),

        "color_3": valid_hex_color(
            request.form.get("color_3"),
            "#FFFFFF",
        ),
    }

    try:

        database.save_settings(
            str(guild.id),
            settings,
        )

    except Exception:
        logger.exception(
            "فشل حفظ إعدادات السيرفر %s",
            guild.id,
        )

        return jsonify({
            "status": "error",
            "message": "تعذر حفظ الإعدادات.",
        }), 500

    return jsonify({
        "status": "success",
        "message": (
            f"تم حفظ إعدادات السيرفر "
            f"({guild.name}) بنجاح!"
        ),
    }), 200


# ============================================================
# 16. HTTP IMAGE DOWNLOAD
# ============================================================

async def download_image(url):
    """
    تحميل صورة بأمان مع:
    - HTTPS فقط
    - timeout
    - حد أقصى للحجم
    - فحص Content-Type
    """

    global http_session

    if not is_safe_image_url(url):
        return None

    if http_session is None:
        return None

    try:

        timeout = aiohttp.ClientTimeout(
            total=10,
            connect=5,
            sock_read=8,
        )

        async with http_session.get(
            url,
            timeout=timeout,
            allow_redirects=False,
        ) as response:

            if response.status != 200:
                return None

            content_type = (
                response.headers
                .get("Content-Type", "")
                .split(";")[0]
                .lower()
            )

            if content_type not in ALLOWED_IMAGE_TYPES:
                return None

            content_length = response.headers.get(
                "Content-Length"
            )

            if content_length:

                try:
                    if int(content_length) > MAX_IMAGE_BYTES:
                        return None
                except ValueError:
                    pass

            data = bytearray()

            while True:

                chunk = await response.content.read(
                    64 * 1024
                )

                if not chunk:
                    break

                data.extend(chunk)

                if len(data) > MAX_IMAGE_BYTES:
                    return None

            return bytes(data)

    except (
        aiohttp.ClientError,
        asyncio.TimeoutError,
    ):
        return None

    except Exception:
        logger.exception(
            "فشل تحميل الصورة"
        )
        return None


# ============================================================
# 17. FONT MANAGEMENT
# ============================================================

FONT_PATH = "Cairo-Bold.ttf"


async def ensure_font():
    """
    تحميل الخط مرة واحدة فقط.

    يفضل وضع Cairo-Bold.ttf داخل المشروع بدلاً
    من تنزيله في كل عملية.
    """

    if os.path.exists(FONT_PATH):
        return FONT_PATH

    if http_session is None:
        return None

    font_url = (
        "https://github.com/google/fonts/raw/"
        "main/ofl/cairo/Cairo-Bold.ttf"
    )

    try:

        timeout = aiohttp.ClientTimeout(
            total=15
        )

        async with http_session.get(
            font_url,
            timeout=timeout,
        ) as response:

            if response.status != 200:
                return None

            data = await response.read()

            if len(data) > 5 * 1024 * 1024:
                return None

            with open(
                FONT_PATH,
                "wb",
            ) as file:
                file.write(data)

            return FONT_PATH

    except Exception:
        logger.exception(
            "فشل تحميل الخط"
        )
        return None


# ============================================================
# 18. WELCOME CARD
# ============================================================

async def generate_welcome_card(
    member,
    bg_url=None,
    lang="ar",
    frame_key=None,
    guild_id=None,
):
    """
    إنشاء بطاقة الترحيب.
    """

    try:

        width = 1536
        height = 1024

        base = Image.new(
            "RGBA",
            (width, height),
            (0, 0, 0, 0),
        )

        settings = {}

        if guild_id:
            settings = (
                database.get_settings(
                    str(guild_id)
                )
                or {}
            )

        raw_t1 = settings.get(
            "text_1",
            "WELCOME TO THE SERVER",
        )

        raw_t2 = settings.get(
            "text_2",
            "{user_name}",
        )

        raw_t3 = settings.get(
            "text_3",
            "MEMBER #{count}",
        )

        c1 = valid_hex_color(
            settings.get("color_1"),
            "#FFFFFF",
        )

        c2 = valid_hex_color(
            settings.get("color_2"),
            "#93C5FD",
        )

        c3 = valid_hex_color(
            settings.get("color_3"),
            "#D1D5DB",
        )

        # ----------------------------------------------------
        # Text replacements
        # ----------------------------------------------------

        server_name = clean_text(
            member.guild.name,
            100,
        )

        display_name_raw = clean_text(
            member.display_name,
            100,
        )

        t1_text = raw_t1.replace(
            "{server}",
            server_name,
        )

        t2_text = (
            raw_t2
            .replace(
                "{user_name}",
                display_name_raw,
            )
            .replace(
                "{user}",
                display_name_raw,
            )
        )

        t3_text = raw_t3.replace(
            "{count}",
            str(member.guild.member_count or 0),
        )

        # ----------------------------------------------------
        # Background
        # ----------------------------------------------------

        if bg_url and is_safe_image_url(bg_url):

            bg_data = await download_image(
                bg_url
            )

            if bg_data:

                try:

                    custom_bg = Image.open(
                        BytesIO(bg_data)
                    ).convert("RGBA")

                    custom_bg.thumbnail(
                        (width, height),
                        Image.Resampling.LANCZOS,
                    )

                    background = Image.new(
                        "RGBA",
                        (width, height),
                        (0, 0, 0, 0),
                    )

                    x = (
                        width
                        - custom_bg.width
                    ) // 2

                    y = (
                        height
                        - custom_bg.height
                    ) // 2

                    background.paste(
                        custom_bg,
                        (x, y),
                    )

                    base = Image.alpha_composite(
                        base,
                        background,
                    )

                except Exception:
                    logger.exception(
                        "خطأ في معالجة خلفية الترحيب"
                    )

        # ----------------------------------------------------
        # Frame
        # ----------------------------------------------------

        user_lang = str(
            lang
        ).lower().strip()

        if user_lang not in ALLOWED_LANGUAGES:
            user_lang = "ar"

        if (
            frame_key
            and frame_key in AVAILABLE_FRAMES
        ):

            frame_info = AVAILABLE_FRAMES[
                frame_key
            ]

            frame_path = (
                frame_info["ar_file"]
                if user_lang == "ar"
                else frame_info["en_file"]
            )

            if os.path.isfile(frame_path):

                try:

                    with Image.open(
                        frame_path
                    ) as frame_source:

                        frame_img = (
                            frame_source
                            .convert("RGBA")
                            .resize(
                                (width, height),
                                Image.Resampling.LANCZOS,
                            )
                        )

                    base = Image.alpha_composite(
                        base,
                        frame_img,
                    )

                except Exception:
                    logger.exception(
                        "خطأ أثناء دمج الإطار"
                    )

        # ----------------------------------------------------
        # Fonts
        # ----------------------------------------------------

        font_path = await ensure_font()

        try:

            if font_path:
                font_title = ImageFont.truetype(
                    font_path,
                    41,
                )

                font_name = ImageFont.truetype(
                    font_path,
                    55,
                )

                font_sub = ImageFont.truetype(
                    font_path,
                    30,
                )

            else:
                raise OSError(
                    "Font unavailable"
                )

        except Exception:

            font_title = (
                font_name
            ) = (
                font_sub
            ) = ImageFont.load_default()

        # ----------------------------------------------------
        # Positions
        # ----------------------------------------------------

        avatar_size = 440

        avatar_y = (
            (height - avatar_size)
            // 2
            - 20
        )

        if user_lang == "ar":

            avatar_x = (
                width
                - avatar_size
                - 96
            )

            title_x = width - 780
            name_x = width - 870
            sub_x = width - 870

            title_y = 529
            name_y = 305
            sub_y = 731

            welcome_title = (
                get_display(
                    arabic_reshaper.reshape(
                        t1_text
                    )
                )
            )

            member_count_text = (
                get_display(
                    arabic_reshaper.reshape(
                        t3_text
                    )
                )
            )

            display_name = (
                get_display(
                    arabic_reshaper.reshape(
                        t2_text[:18]
                    )
                )
            )

        else:

            avatar_x = 96

            title_x = 775
            name_x = 870
            sub_x = 870

            title_y = 550
            name_y = 330
            sub_y = 750

            welcome_title = t1_text
            member_count_text = t3_text
            display_name = t2_text[:18]

        draw = ImageDraw.Draw(base)

        # ----------------------------------------------------
        # Avatar
        # ----------------------------------------------------

        avatar_url = str(
            member.display_avatar.url
        )

        avatar_data = await download_image(
            avatar_url
        )

        if avatar_data:

            try:

                avatar = Image.open(
                    BytesIO(avatar_data)
                ).convert("RGBA")

                avatar = avatar.resize(
                    (
                        avatar_size,
                        avatar_size,
                    ),
                    Image.Resampling.LANCZOS,
                )

                mask = Image.new(
                    "L",
                    (
                        avatar_size,
                        avatar_size,
                    ),
                    0,
                )

                mask_draw = ImageDraw.Draw(
                    mask
                )

                mask_draw.ellipse(
                    (
                        0,
                        0,
                        avatar_size,
                        avatar_size,
                    ),
                    fill=255,
                )

                draw.ellipse(
                    (
                        avatar_x - 5,
                        avatar_y - 5,
                        avatar_x
                        + avatar_size
                        + 5,
                        avatar_y
                        + avatar_size
                        + 5,
                    ),
                    outline=(
                        59,
                        130,
                        246,
                        255,
                    ),
                    width=5,
                )

                base.paste(
                    avatar,
                    (
                        avatar_x,
                        avatar_y,
                    ),
                    mask,
                )

            except Exception:
                logger.exception(
                    "خطأ في معالجة Avatar"
                )

        # ----------------------------------------------------
        # Text
        # ----------------------------------------------------

        if user_lang == "ar":

            draw.text(
                (
                    title_x,
                    title_y,
                ),
                welcome_title,
                fill=c1,
                font=font_title,
                anchor="ra",
            )

            draw.text(
                (
                    name_x,
                    name_y,
                ),
                display_name,
                fill=c2,
                font=font_name,
                anchor="ra",
            )

            draw.text(
                (
                    sub_x,
                    sub_y,
                ),
                member_count_text,
                fill=c3,
                font=font_sub,
                anchor="ra",
            )

        else:

            draw.text(
                (
                    title_x,
                    title_y,
                ),
                welcome_title,
                fill=c1,
                font=font_title,
                anchor="lm",
            )

            draw.text(
                (
                    name_x,
                    name_y,
                ),
                display_name,
                fill=c2,
                font=font_name,
                anchor="lm",
            )

            draw.text(
                (
                    sub_x,
                    sub_y,
                ),
                member_count_text,
                fill=c3,
                font=font_sub,
                anchor="lm",
            )

        # ----------------------------------------------------
        # Final PNG
        # ----------------------------------------------------

        final_buffer = BytesIO()

        base.save(
            final_buffer,
            format="PNG",
            optimize=True,
        )

        final_buffer.seek(0)

        return discord.File(
            final_buffer,
            filename="welcome_card.png",
        )

    except Exception:
        logger.exception(
            "خطأ عام في توليد بطاقة الترحيب"
        )
        return None


# ============================================================
# 19. DISCORD ERROR HANDLER
# ============================================================

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):

    lang = "ar"

    if interaction.guild_id:
        lang = get_guild_lang(
            interaction.guild_id
        )

    if isinstance(
        error,
        app_commands.MissingPermissions,
    ):

        msg = (
            "❌ Sorry! This command requires "
            "**Manage Server** permission."
            if lang == "en"
            else
            "❌ عذراً! هذا الأمر يتطلب "
            "صلاحية **إدارة السيرفر**."
        )

    elif isinstance(
        error,
        app_commands.CommandOnCooldown,
    ):

        remaining = round(
            error.retry_after,
            1,
        )

        msg = (
            f"⏳ Please wait {remaining} seconds."
            if lang == "en"
            else
            f"⏳ يرجى الانتظار {remaining} ثانية."
        )

    elif isinstance(
        error,
        app_commands.CommandNotFound,
    ):

        return

    else:

        logger.exception(
            "Slash command error",
            exc_info=error,
        )

        msg = (
            "❌ An unexpected error occurred."
            if lang == "en"
            else
            "❌ حدث خطأ غير متوقع أثناء تنفيذ الأمر."
        )

    try:

        if interaction.response.is_done():

            await interaction.followup.send(
                msg,
                ephemeral=True,
            )

        else:

            await interaction.response.send_message(
                msg,
                ephemeral=True,
            )

    except Exception:
        logger.exception(
            "Failed to send error response"
        )


# ============================================================
# 20. READY EVENT
# ============================================================

@bot.event
async def on_ready():

    global http_session
    global cogs_loaded

    logger.info(
        "تم تسجيل الدخول بنجاح باسم %s",
        bot.user,
    )

    # --------------------------------------------------------
    # HTTP session
    # --------------------------------------------------------

    if (
        http_session is None
        or http_session.closed
    ):

        timeout = aiohttp.ClientTimeout(
            total=15,
            connect=5,
            sock_read=10,
        )

        http_session = aiohttp.ClientSession(
            timeout=timeout,
            headers={
                "User-Agent": "DiscordBot/1.0"
            },
        )

    # --------------------------------------------------------
    # Load Cogs only once
    # --------------------------------------------------------

    if not cogs_loaded:

        cogs_path = "./cogs"

        if os.path.isdir(cogs_path):

            for filename in sorted(
                os.listdir(cogs_path)
            ):

                if not filename.endswith(
                    ".py"
                ):
                    continue

                if filename.startswith(
                    "_"
                ):
                    continue

                extension_name = (
                    f"cogs.{filename[:-3]}"
                )

                if (
                    extension_name
                    in bot.extensions
                ):
                    continue

                try:

                    await bot.load_extension(
                        extension_name
                    )

                    logger.info(
                        "تم تحميل Cog: %s",
                        filename[:-3],
                    )

                except Exception:

                    logger.exception(
                        "فشل تحميل Cog: %s",
                        filename[:-3],
                    )

            cogs_loaded = True

        else:

            logger.warning(
                "مجلد cogs غير موجود."
            )


# ============================================================
# 21. LANGUAGE COMMAND
# ============================================================

@bot.tree.command(
    name="language",
    description="تغيير لغة ردود البوت",
)
@app_commands.describe(
    lang="اختر اللغة المفضلة"
)
@app_commands.choices(
    lang=[
        app_commands.Choice(
            name="العربية (Arabic)",
            value="ar",
        ),
        app_commands.Choice(
            name="English (الإنجليزية)",
            value="en",
        ),
    ]
)
@app_commands.checks.has_permissions(
    manage_guild=True
)
@app_commands.checks.cooldown(
    1,
    5.0,
    key=lambda i: (
        i.guild_id,
        i.user.id,
    ),
)
async def language_command(
    interaction: discord.Interaction,
    lang: app_commands.Choice[str],
):

    guild_id = interaction.guild.id

    settings = (
        database.get_settings(
            guild_id
        )
        or {}
    )

    settings["language"] = lang.value

    database.save_settings(
        guild_id,
        settings,
    )

    if lang.value == "en":

        message = (
            "✅ Successfully changed the "
            "bot language to **English**!"
        )

    else:

        message = (
            "✅ تم تغيير لغة البوت إلى "
            "**العربية** بنجاح!"
        )

    await interaction.response.send_message(
        message,
        ephemeral=True,
    )


# ============================================================
# 22. SETUP COMMAND
# ============================================================

@bot.tree.command(
    name="setup",
    description="فتح لوحة التحكم الآمنة",
)
@app_commands.checks.has_permissions(
    manage_guild=True
)
@app_commands.checks.cooldown(
    1,
    5.0,
    key=lambda i: (
        i.guild_id,
        i.user.id,
    ),
)
async def setup(
    interaction: discord.Interaction,
):

    lang = get_guild_lang(
        interaction.guild.id
    )

    login_link = (
        f"{get_base_url()}/login"
    )

    view = discord.ui.View()

    button = discord.ui.Button(
        label=(
            "Open Control Panel ⚙️"
            if lang == "en"
            else "فتح لوحة التحكم ⚙️"
        ),
        url=login_link,
        style=discord.ButtonStyle.link,
    )

    view.add_item(button)

    if lang == "en":

        embed = discord.Embed(
            title="🛠️ Bot Control Panel",
            description=(
                "Click the button below to log in "
                "securely with Discord and manage "
                "your server."
            ),
            color=discord.Color.blue(),
        )

    else:

        embed = discord.Embed(
            title="🛠️ لوحة تحكم البوت",
            description=(
                "اضغط على الزر أدناه لتسجيل الدخول "
                "بشكل آمن عبر Discord وإدارة سيرفرك."
            ),
            color=discord.Color.blue(),
        )

    await interaction.response.send_message(
        embed=embed,
        view=view,
        ephemeral=True,
    )


# ============================================================
# 23. MEMBER JOIN
# ============================================================

@bot.event
async def on_member_join(member):

    try:

        settings = (
            database.get_settings(
                member.guild.id
            )
            or {}
        )

        if not settings:
            return

        if not settings.get(
            "welcome_enabled",
            True,
        ):
            return

        # ----------------------------------------------------
        # Auto role
        # ----------------------------------------------------

        role_id = str(
            settings.get(
                "auto_role",
                "",
            )
        )

        if valid_discord_id(role_id):

            role = member.guild.get_role(
                int(role_id)
            )

            if role:

                try:

                    await member.add_roles(
                        role,
                        reason="Automatic welcome role",
                    )

                except discord.Forbidden:
                    logger.warning(
                        "لا يمكن إعطاء الرول %s",
                        role.id,
                    )

                except discord.HTTPException:
                    logger.exception(
                        "Discord error while adding role"
                    )

        # ----------------------------------------------------
        # Auto nickname
        # ----------------------------------------------------

        auto_nick = clean_text(
            settings.get(
                "auto_nickname",
                "",
            ),
            100,
        )

        if auto_nick:

            try:

                if "{user}" in auto_nick:

                    new_nick = auto_nick.replace(
                        "{user}",
                        member.display_name,
                    )

                else:

                    new_nick = (
                        f"{auto_nick} "
                        f"{member.display_name}"
                    )

                await member.edit(
                    nick=new_nick[:32],
                    reason="Automatic welcome nickname",
                )

            except (
                discord.Forbidden,
                discord.HTTPException,
            ):

                logger.warning(
                    "تعذر تغيير لقب العضو %s",
                    member.id,
                )

        # ----------------------------------------------------
        # Welcome channel
        # ----------------------------------------------------

        welcome_channel_id = str(
            settings.get(
                "welcome_channel",
                "",
            )
        )

        if not valid_discord_id(
            welcome_channel_id
        ):
            return

        channel = member.guild.get_channel(
            int(welcome_channel_id)
        )

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            return

        lang = settings.get(
            "language",
            "ar",
        )

        frame_key = settings.get(
            "welcome_frame"
        )

        bg_url = settings.get(
            "welcome_img"
        )

        card_file = await generate_welcome_card(
            member,
            bg_url,
            lang=lang,
            frame_key=frame_key,
            guild_id=member.guild.id,
        )

        custom_msg = clean_text(
            settings.get(
                "welcome_msg",
                "",
            ),
            MAX_TEXT_LENGTH,
        )

        if custom_msg:

            welcome_text = (
                custom_msg
                .replace(
                    "{user}",
                    member.mention,
                )
                .replace(
                    "{server}",
                    member.guild.name,
                )
            )

        elif lang == "en":

            welcome_text = (
                f"Welcome {member.mention} "
                f"to {member.guild.name}! 🎉"
            )

        else:

            welcome_text = (
                f"أهلاً بك يا {member.mention} "
                f"في سيرفر {member.guild.name}! 🎉"
            )

        if card_file:

            await channel.send(
                content=welcome_text,
                file=card_file,
            )

        else:

            await channel.send(
                content=welcome_text,
            )

    except Exception:

        logger.exception(
            "خطأ في on_member_join"
        )


# ============================================================
# 24. MEMBER REMOVE
# ============================================================

@bot.event
async def on_member_remove(member):

    try:

        settings = (
            database.get_settings(
                member.guild.id
            )
            or {}
        )

        if not settings:
            return

        if not settings.get(
            "farewell_enabled",
            True,
        ):
            return

        channel_id = str(
            settings.get(
                "farewell_channel",
                "",
            )
        )

        if not valid_discord_id(
            channel_id
        ):
            return

        channel = member.guild.get_channel(
            int(channel_id)
        )

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            return

        lang = settings.get(
            "language",
            "ar",
        )

        default_title = (
            "Goodbye"
            if lang == "en"
            else "وداعاً"
        )

        farewell_title = clean_text(
            settings.get(
                "farewell_title",
                default_title,
            ),
            256,
        )

        farewell_desc = clean_text(
            settings.get(
                "farewell_desc",
                "",
            ),
            MAX_TEXT_LENGTH,
        ).replace(
            "{user}",
            member.mention,
        )

        embed = discord.Embed(
            title=farewell_title,
            description=farewell_desc,
            color=discord.Color.red(),
        )

        farewell_img = str(
            settings.get(
                "farewell_img",
                "",
            )
        )

        if is_safe_image_url(
            farewell_img
        ):
            embed.set_image(
                url=farewell_img
            )

        action = settings.get(
            "farewell_action",
            "none",
        )

        view = None

        if action in {
            "ban",
            "timeout",
        }:

            class FarewellView(
                discord.ui.View
            ):

                def __init__(
                    self,
                    selected_action,
                    selected_lang,
                ):

                    super().__init__(
                        timeout=300
                    )

                    self.selected_action = (
                        selected_action
                    )

                    self.selected_lang = (
                        selected_lang
                    )

                @discord.ui.button(
                    label="Apply",
                    style=discord.ButtonStyle.danger,
                )
                async def btn_callback(
                    self,
                    interaction,
                    button,
                ):

                    # تحديث اسم الزر حسب اللغة
                    if (
                        self.selected_lang
                        == "en"
                    ):

                        action_text = (
                            self.selected_action.upper()
                        )

                    else:

                        action_text = (
                            self.selected_action.upper()
                        )

                    # يجب أن يكون المتفاعل لديه صلاحية
                    if not interaction.guild:

                        await interaction.response.send_message(
                            "غير متاح هنا.",
                            ephemeral=True,
                        )
                        return

                    actor = interaction.guild.get_member(
                        interaction.user.id
                    )

                    if not actor:

                        await interaction.response.send_message(
                            "تعذر التحقق من صلاحياتك.",
                            ephemeral=True,
                        )
                        return

                    if not (
                        actor.guild_permissions.administrator
                        or actor.guild_permissions.manage_guild
                    ):

                        await interaction.response.send_message(
                            (
                                "You need Manage Server permission."
                                if self.selected_lang == "en"
                                else
                                "تحتاج إلى صلاحية إدارة السيرفر."
                            ),
                            ephemeral=True,
                        )
                        return

                    try:

                        if (
                            self.selected_action
                            == "ban"
                        ):

                            await member.ban(
                                reason=(
                                    "Farewell button action"
                                    if self.selected_lang
                                    == "en"
                                    else
                                    "عن طريق زر الوداع"
                                )
                            )

                            msg = (
                                "Member banned."
                                if self.selected_lang
                                == "en"
                                else
                                "تم حظر العضو."
                            )

                        else:

                            await member.timeout(
                                timedelta(
                                    minutes=10
                                ),
                                reason=(
                                    "Farewell button action"
                                    if self.selected_lang
                                    == "en"
                                    else
                                    "عن طريق زر الوداع"
                                ),
                            )

                            msg = (
                                "Member timed out."
                                if self.selected_lang
                                == "en"
                                else
                                "تم إعطاء تايم أوت."
                            )

                        await interaction.response.send_message(
                            msg,
                            ephemeral=True,
                        )

                    except discord.Forbidden:

                        await interaction.response.send_message(
                            (
                                "Discord denied this action."
                                if self.selected_lang
                                == "en"
                                else
                                "Discord رفض تنفيذ هذا الإجراء."
                            ),
                            ephemeral=True,
                        )

                    except discord.HTTPException:

                        logger.exception(
                            "Farewell action failed"
                        )

                        await interaction.response.send_message(
                            (
                                "Failed to execute action."
                                if self.selected_lang
                                == "en"
                                else
                                "فشل تنفيذ الإجراء."
                            ),
                            ephemeral=True,
                        )

            view = FarewellView(
                action,
                lang,
            )

            if lang == "en":
                view.children[0].label = (
                    f"Apply {action.upper()}"
                )
            else:
                view.children[0].label = (
                    f"تطبيق {action.upper()}"
                )

        await channel.send(
            embed=embed,
            view=view,
        )

    except Exception:

        logger.exception(
            "خطأ في on_member_remove"
        )


# ============================================================
# 25. MESSAGE HANDLER
# ============================================================

@bot.event
async def on_message(message):

    if (
        message.author.bot
        or not message.guild
    ):
        return

    try:

        settings = (
            database.get_settings(
                message.guild.id
            )
            or {}
        )

        if not settings:

            await bot.process_commands(
                message
            )
            return

        lang = settings.get(
            "language",
            "ar",
        )

        # ----------------------------------------------------
        # XP
        # ----------------------------------------------------

        if (
            settings.get(
                "xp_enabled",
                1,
            )
            == 1
        ):

            xp_gain = safe_int(
                settings.get(
                    "xp_per_message",
                    15,
                ),
                15,
                minimum=0,
                maximum=MAX_XP_PER_MESSAGE,
            )

            if hasattr(
                database,
                "add_user_xp",
            ):

                try:

                    new_level, leveled_up = (
                        database.add_user_xp(
                            message.guild.id,
                            message.author.id,
                            xp_gain,
                        )
                    )

                except Exception:

                    logger.exception(
                        "XP database error"
                    )

                    new_level = None
                    leveled_up = False

                if leveled_up:

                    try:

                        if lang == "en":

                            await message.channel.send(
                                f"🎉 Congratulations "
                                f"{message.author.mention}! "
                                f"You leveled up to "
                                f"**{new_level}** 🚀"
                            )

                        else:

                            await message.channel.send(
                                f"🎉 مبروك "
                                f"{message.author.mention}! "
                                f"لقد ترقيت إلى المستوى "
                                f"**{new_level}** 🚀"
                            )

                        role_id_to_give = None

                        if new_level == 5:

                            role_id_to_give = (
                                settings.get(
                                    "xp_role_5"
                                )
                            )

                        elif new_level == 10:

                            role_id_to_give = (
                                settings.get(
                                    "xp_role_10"
                                )
                            )

                        elif new_level == 20:

                            role_id_to_give = (
                                settings.get(
                                    "xp_role_20"
                                )
                            )

                        if valid_discord_id(
                            role_id_to_give
                        ):

                            target_role = (
                                message.guild.get_role(
                                    int(
                                        role_id_to_give
                                    )
                                )
                            )

                            if target_role:

                                await message.author.add_roles(
                                    target_role,
                                    reason="XP level reward",
                                )

                                if lang == "en":

                                    await message.channel.send(
                                        f"🎁 You received "
                                        f"the role: "
                                        f"**{target_role.name}**!"
                                    )

                                else:

                                    await message.channel.send(
                                        f"🎁 لقد حصلت على "
                                        f"رول التميز: "
                                        f"**{target_role.name}**!"
                                    )

                    except (
                        discord.Forbidden,
                        discord.HTTPException,
                    ):

                        logger.warning(
                            "تعذر منح XP role"
                        )

        # ----------------------------------------------------
        # Media-only channels
        # ----------------------------------------------------

        if settings.get(
            "media_enabled",
            True,
        ):

            media_channels = {
                str(x)
                for x in settings.get(
                    "media_channels",
                    [],
                )
            }

            if (
                str(message.channel.id)
                in media_channels
            ):

                has_media = bool(
                    message.attachments
                )

                if not has_media:

                    lowered = (
                        message.content.lower()
                    )

                    allowed_extensions = (
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".gif",
                        ".webp",
                        ".mp4",
                        ".mov",
                        ".webm",
                    )

                    has_media = (
                        any(
                            ext in lowered
                            for ext in allowed_extensions
                        )
                        or "https://" in lowered
                    )

                if not has_media:

                    try:
                        await message.delete()
                    except discord.HTTPException:
                        pass

                    default_warn = (
                        "Sorry, this channel is "
                        "for media only!"
                        if lang == "en"
                        else
                        "عذراً هذه القناة للميديا فقط!"
                    )

                    warn_msg = clean_text(
                        settings.get(
                            "media_warning",
                            default_warn,
                        ),
                        MAX_TEXT_LENGTH,
                    ).replace(
                        "{user}",
                        message.author.mention,
                    )

                    await message.channel.send(
                        warn_msg,
                        delete_after=5,
                    )

                    return

        # ----------------------------------------------------
        # Banned words
        # ----------------------------------------------------

        if settings.get(
            "banned_enabled",
            True,
        ):

            banned_words = [
                str(word).strip().lower()
                for word in settings.get(
                    "banned_words",
                    [],
                )
                if str(word).strip()
            ][:MAX_BANNED_WORDS]

            msg_content = (
                message.content.lower()
            )

            matched_word = next(
                (
                    word
                    for word in banned_words
                    if word in msg_content
                ),
                None,
            )

            if matched_word:

                try:
                    await message.delete()
                except discord.HTTPException:
                    pass

                guild_id = str(
                    message.guild.id
                )

                user_id = str(
                    message.author.id
                )

                violations[
                    guild_id
                ][user_id] = (
                    violations[
                        guild_id
                    ].get(
                        user_id,
                        0,
                    )
                    + 1
                )

                count = violations[
                    guild_id
                ][user_id]

                max_v = safe_int(
                    settings.get(
                        "max_violations",
                        3,
                    ),
                    3,
                    minimum=1,
                    maximum=20,
                )

                if count < max_v:

                    default_title = (
                        "Warning"
                        if lang == "en"
                        else "تحذير"
                    )

                    title = clean_text(
                        settings.get(
                            "warning_title",
                            default_title,
                        ),
                        256,
                    )

                    if count == 1:

                        msg_text = settings.get(
                            "warning_msg_1"
                        )

                    else:

                        msg_text = settings.get(
                            "warning_msg_2"
                        )

                    if not msg_text:

                        msg_text = (
                            "Please follow the rules!"
                            if lang == "en"
                            else
                            "يرجى الالتزام بالقوانين!"
                        )

                    msg_text = clean_text(
                        msg_text,
                        MAX_TEXT_LENGTH,
                    ).replace(
                        "{user}",
                        message.author.mention,
                    )

                    embed = discord.Embed(
                        title=title,
                        description=msg_text,
                        color=discord.Color.gold(),
                    )

                    await message.channel.send(
                        embed=embed,
                        delete_after=10,
                    )

                else:

                    punishment = settings.get(
                        "punishment_type",
                        "timeout",
                    )

                    if punishment not in ALLOWED_PUNISHMENTS:
                        punishment = "timeout"

                    timeout_minutes = safe_int(
                        settings.get(
                            "timeout_minutes",
                            10,
                        ),
                        10,
                        minimum=1,
                        maximum=MAX_TIMEOUT_MINUTES,
                    )

                    try:

                        if punishment == "timeout":

                            await message.author.timeout(
                                timedelta(
                                    minutes=timeout_minutes
                                ),
                                reason=(
                                    "Rule violation"
                                    if lang == "en"
                                    else
                                    "مخالفة القوانين"
                                ),
                            )

                        elif punishment == "kick":

                            await message.author.kick(
                                reason=(
                                    "Rule violation"
                                    if lang == "en"
                                    else
                                    "مخالفة القوانين"
                                )
                            )

                        elif punishment == "mute":

                            await message.author.timeout(
                                timedelta(
                                    days=7
                                ),
                                reason=(
                                    "Full mute"
                                    if lang == "en"
                                    else
                                    "كتم كامل"
                                ),
                            )

                        punishment_msg = (
                            f"Applied ({punishment}) "
                            f"to {message.author.mention}."
                            if lang == "en"
                            else
                            f"تم تطبيق ({punishment}) "
                            f"على {message.author.mention}."
                        )

                        await message.channel.send(
                            punishment_msg,
                            delete_after=10,
                        )

                    except discord.Forbidden:

                        logger.warning(
                            "Discord denied punishment"
                        )

                    except discord.HTTPException:

                        logger.exception(
                            "Punishment failed"
                        )

                    # إعادة العداد للصفر
                    violations[
                        guild_id
                    ].pop(
                        user_id,
                        None,
                    )

                return

        # ----------------------------------------------------
        # Auto responses
        # ----------------------------------------------------

        auto_resp = settings.get(
            "auto_responses",
            {},
        )

        msg_content = (
            message.content.lower().strip()
        )

        if (
            isinstance(
                auto_resp,
                dict,
            )
            and msg_content in auto_resp
        ):

            response_text = clean_text(
                auto_resp[msg_content],
                MAX_TEXT_LENGTH,
            )

            await message.channel.send(
                response_text
            )

            return

        # ----------------------------------------------------
        # Network Cog
        # ----------------------------------------------------

        network_cog = bot.get_cog(
            "NetworkCog"
        )

        if network_cog:

            try:
                await network_cog.on_message(
                    message
                )
            except Exception:
                logger.exception(
                    "NetworkCog on_message failed"
                )

        await bot.process_commands(
            message
        )

    except Exception:

        logger.exception(
            "Unhandled on_message error"
        )

        # لا نرسل تفاصيل الخطأ للمستخدم.


# ============================================================
# 26. OWNER-ONLY SYNC
# ============================================================

@bot.command(
    name="sync"
)
async def sync_commands(ctx):

    if ctx.author.id != OWNER_ID:
        return

    msg = await ctx.send(
        "⏳ جاري مزامنة أوامر البوت..."
    )

    try:

        # لا نمسح Global commands.
        # مزامنة Global فقط.
        synced = await bot.tree.sync()

        await msg.edit(
            content=(
                f"✅ تمت مزامنة "
                f"**{len(synced)}** "
                f"أمر سلاش بنجاح!"
            )
        )

    except Exception:

        logger.exception(
            "Global command sync failed"
        )

        await msg.edit(
            content=(
                "❌ حدث خطأ أثناء مزامنة الأوامر."
            )
        )


# ============================================================
# 27. OWNER-ONLY SERVER LIST
# ============================================================

@bot.command(
    name="servers"
)
async def list_servers(ctx):

    if ctx.author.id != OWNER_ID:
        return

    servers_list = []

    for guild in bot.guilds:

        servers_list.append(
            f"• **{guild.name}** "
            f"(`{guild.id}`) - "
            f"الأعضاء: `{guild.member_count}`"
        )

    desc = (
        "\n".join(servers_list)
        if servers_list
        else
        "لا توجد سيرفرات مرتبطة."
    )

    # Discord embed description limit
    if len(desc) > 4000:
        desc = (
            desc[:3900]
            + "\n\n... القائمة طويلة جداً."
        )

    embed = discord.Embed(
        title=(
            f"📊 السيرفرات المرتبطة "
            f"بالبوت ({len(bot.guilds)})"
        ),
        description=desc,
        color=discord.Color.blue(),
    )

    try:

        await ctx.author.send(
            embed=embed
        )

        if ctx.guild:

            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

    except discord.Forbidden:

        await ctx.send(
            embed=embed,
            delete_after=10,
        )


# ============================================================
# 28. USER INFO
# ============================================================

@bot.tree.command(
    name="userinfo",
    description="عرض معلومات العضو",
)
@app_commands.describe(
    member="العضو المراد عرض معلوماته"
)
@app_commands.checks.has_permissions(
    manage_guild=True
)
@app_commands.checks.cooldown(
    1,
    5.0,
    key=lambda i: (
        i.guild_id,
        i.user.id,
    ),
)
async def userinfo(
    interaction: discord.Interaction,
    member: discord.Member | None = None,
):

    target = (
        member
        or interaction.user
    )

    lang = get_guild_lang(
        interaction.guild.id
    )

    joined_date = (
        target.joined_at.strftime(
            "%Y-%m-%d"
        )
        if target.joined_at
        else "Unknown"
    )

    if lang == "en":

        embed = discord.Embed(
            title=(
                f"User Info: "
                f"{target.display_name}"
            ),
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="Name:",
            value=target.name,
            inline=True,
        )

        embed.add_field(
            name="ID:",
            value=str(target.id),
            inline=True,
        )

        embed.add_field(
            name="Account Created:",
            value=target.created_at.strftime(
                "%Y-%m-%d"
            ),
            inline=False,
        )

        embed.add_field(
            name="Server Joined:",
            value=joined_date,
            inline=False,
        )

        embed.add_field(
            name="Top Role:",
            value=target.top_role.mention,
            inline=True,
        )

    else:

        embed = discord.Embed(
            title=(
                f"معلومات العضو: "
                f"{target.display_name}"
            ),
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="الاسم:",
            value=target.name,
            inline=True,
        )

        embed.add_field(
            name="المعرف (ID):",
            value=str(target.id),
            inline=True,
        )

        embed.add_field(
            name="تاريخ إنشاء الحساب:",
            value=target.created_at.strftime(
                "%Y-%m-%d"
            ),
            inline=False,
        )

        embed.add_field(
            name="تاريخ الانضمام للسيرفر:",
            value=joined_date,
            inline=False,
        )

        embed.add_field(
            name="أعلى رول:",
            value=target.top_role.mention,
            inline=True,
        )

    embed.set_thumbnail(
        url=target.display_avatar.url
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# 29. SERVER INFO
# ============================================================

@bot.tree.command(
    name="serverinfo",
    description="عرض معلومات وإحصائيات السيرفر",
)
@app_commands.checks.has_permissions(
    manage_guild=True
)
@app_commands.checks.cooldown(
    1,
    10.0,
    key=lambda i: (
        i.guild_id,
        i.user.id,
    ),
)
async def serverinfo(
    interaction: discord.Interaction,
):

    guild = interaction.guild

    lang = get_guild_lang(
        guild.id
    )

    if lang == "en":

        embed = discord.Embed(
            title=f"Statistics for {guild.name}",
            color=discord.Color.purple(),
        )

        if guild.icon:
            embed.set_thumbnail(
                url=guild.icon.url
            )

        embed.add_field(
            name="Server ID:",
            value=str(guild.id),
            inline=True,
        )

        embed.add_field(
            name="Server Owner:",
            value=f"<@{guild.owner_id}>",
            inline=True,
        )

        embed.add_field(
            name="Total Members:",
            value=str(
                guild.member_count or 0
            ),
            inline=True,
        )

        embed.add_field(
            name="Channels Count:",
            value=str(
                len(guild.channels)
            ),
            inline=True,
        )

        embed.add_field(
            name="Roles Count:",
            value=str(
                len(guild.roles)
            ),
            inline=True,
        )

        embed.add_field(
            name="Creation Date:",
            value=guild.created_at.strftime(
                "%Y-%m-%d"
            ),
            inline=False,
        )

        button_label = "Support"

    else:

        embed = discord.Embed(
            title=f"إحصائيات {guild.name}",
            color=discord.Color.purple(),
        )

        if guild.icon:
            embed.set_thumbnail(
                url=guild.icon.url
            )

        embed.add_field(
            name="معرف السيرفر (ID):",
            value=str(guild.id),
            inline=True,
        )

        embed.add_field(
            name="مالك السيرفر:",
            value=f"<@{guild.owner_id}>",
            inline=True,
        )

        embed.add_field(
            name="عدد الأعضاء الإجمالي:",
            value=str(
                guild.member_count or 0
            ),
            inline=True,
        )

        embed.add_field(
            name="عدد القنوات:",
            value=str(
                len(guild.channels)
            ),
            inline=True,
        )

        embed.add_field(
            name="عدد الرولات:",
            value=str(
                len(guild.roles)
            ),
            inline=True,
        )

        embed.add_field(
            name="تاريخ الإنشاء:",
            value=guild.created_at.strftime(
                "%Y-%m-%d"
            ),
            inline=False,
        )

        button_label = "دعم"

    view = discord.ui.View()

    view.add_item(
        discord.ui.Button(
            label=button_label,
            url=(
                "https://top.gg/discord/"
                "servers/876867145879965696"
            ),
            style=discord.ButtonStyle.link,
            emoji="🛠️",
        )
    )

    await interaction.response.send_message(
        embed=embed,
        view=view,
    )


# ============================================================
# 30. CLEAR
# ============================================================

@bot.tree.command(
    name="clear",
    description="حذف عدد معين من الرسائل",
)
@app_commands.describe(
    amount="عدد الرسائل 1 - 100",
    member="عضو معين لتنظيف رسائله",
)
@app_commands.checks.has_permissions(
    manage_guild=True
)
@app_commands.checks.cooldown(
    1,
    5.0,
    key=lambda i: (
        i.guild_id,
        i.user.id,
    ),
)
async def clear(
    interaction: discord.Interaction,
    amount: int,
    member: discord.Member | None = None,
):

    lang = get_guild_lang(
        interaction.guild.id
    )

    if amount < 1 or amount > 100:

        msg = (
            "Please enter a number between 1 and 100."
            if lang == "en"
            else
            "يرجى إدخال رقم بين 1 و100."
        )

        await interaction.response.send_message(
            msg,
            ephemeral=True,
        )

        return

    await interaction.response.defer(
        ephemeral=True
    )

    def check(msg):

        if member:
            return msg.author.id == member.id

        return True

    try:

        deleted = await interaction.channel.purge(
            limit=amount,
            check=check,
        )

        success_msg = (
            f"Successfully cleared "
            f"{len(deleted)} messages."
            if lang == "en"
            else
            f"تم مسح {len(deleted)} رسالة بنجاح."
        )

        await interaction.followup.send(
            success_msg,
            ephemeral=True,
        )

    except discord.Forbidden:

        await interaction.followup.send(
            (
                "I don't have permission to delete messages."
                if lang == "en"
                else
                "ليس لدي صلاحية حذف الرسائل."
            ),
            ephemeral=True,
        )

    except discord.HTTPException:

        logger.exception(
            "Clear command failed"
        )

        await interaction.followup.send(
            (
                "Failed to clear messages."
                if lang == "en"
                else
                "فشل حذف الرسائل."
            ),
            ephemeral=True,
        )


# ============================================================
# 31. PING
# ============================================================

@bot.tree.command(
    name="ping",
    description="عرض سرعة اتصال البوت",
)
@app_commands.checks.has_permissions(
    manage_guild=True
)
@app_commands.checks.cooldown(
    1,
    3.0,
    key=lambda i: (
        i.guild_id,
        i.user.id,
    ),
)
async def ping(
    interaction: discord.Interaction,
):

    latency = round(
        bot.latency * 1000
    )

    lang = get_guild_lang(
        interaction.guild.id
    )

    if lang == "en":

        embed = discord.Embed(
            title="🏓 Pong!",
            description=(
                f"Bot Latency: "
                f"**{latency} ms**"
            ),
            color=(
                discord.Color.green()
                if latency < 150
                else discord.Color.red()
            ),
        )

    else:

        embed = discord.Embed(
            title="🏓 Pong!",
            description=(
                f"سرعة استجابة البوت: "
                f"**{latency} ms**"
            ),
            color=(
                discord.Color.green()
                if latency < 150
                else discord.Color.red()
            ),
        )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# 32. BOT INFO
# ============================================================

@bot.tree.command(
    name="botinfo",
    description="عرض معلومات البوت",
)
@app_commands.checks.has_permissions(
    manage_guild=True
)
@app_commands.checks.cooldown(
    1,
    5.0,
    key=lambda i: (
        i.guild_id,
        i.user.id,
    ),
)
async def botinfo(
    interaction: discord.Interaction,
):

    total_guilds = len(
        bot.guilds
    )

    total_users = sum(
        guild.member_count or 0
        for guild in bot.guilds
    )

    lang = get_guild_lang(
        interaction.guild.id
    )

    if lang == "en":

        embed = discord.Embed(
            title="Bot Information & Support",
            description=(
                "Thanks for using the bot!"
            ),
            color=discord.Color.gold(),
        )

        embed.add_field(
            name="Serving Servers:",
            value=f"{total_guilds} servers",
            inline=True,
        )

        embed.add_field(
            name="Total Users:",
            value=f"{total_users} members",
            inline=True,
        )

        btn_label = (
            "Support Bot on Top.gg"
        )

    else:

        embed = discord.Embed(
            title="معلومات البوت والدعم",
            description=(
                "شكراً لاستخدامك البوت!"
            ),
            color=discord.Color.gold(),
        )

        embed.add_field(
            name="السيرفرات الخادمة:",
            value=f"{total_guilds} سيرفر",
            inline=True,
        )

        embed.add_field(
            name="إجمالي المستخدمين:",
            value=f"{total_users} عضو",
            inline=True,
        )

        btn_label = (
            "دعم البوت على Top.gg"
        )

    view = discord.ui.View()

    view.add_item(
        discord.ui.Button(
            label=btn_label,
            url=(
                "https://top.gg/discord/"
                "servers/876867145879965696"
            ),
            style=discord.ButtonStyle.link,
        )
    )

    await interaction.response.send_message(
        embed=embed,
        view=view,
    )


# ============================================================
# 33. HELP
# ============================================================

@bot.tree.command(
    name="help",
    description="عرض دليل استخدام البوت",
)
@app_commands.checks.cooldown(
    1,
    5.0,
    key=lambda i: (
        i.guild_id,
        i.user.id,
    ),
)
async def help_command(
    interaction: discord.Interaction,
):

    lang = get_guild_lang(
        interaction.guild.id
    )

    view = discord.ui.View()

    if lang == "en":

        embed = discord.Embed(
            title="📖 Bot Setup & Usage Guide",
            description=(
                "Welcome to the bot manual! "
                "Here is an overview of the "
                "available commands."
            ),
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="🛠️ Dashboard & Main Commands",
            value=(
                "`/setup` — Open the web control panel.\n"
                "`/language` — Change bot language.\n"
                "`/ticket-setup` — Send ticket panel.\n"
                "`/clear [amount]` — Delete 1-100 messages.\n"
                "`/userinfo` & `/serverinfo` — Show information.\n"
                "`/ping` & `/botinfo` — Connection and bot information."
            ),
            inline=False,
        )

        embed.add_field(
            name="🛡️ Staff Shifts & Management",
            value=(
                "`/shift-panel` — Shift control panel.\n"
                "`/shift-log-channel` — Set shift logs channel.\n"
                "`/shift-stats [member]` — View shift statistics.\n"
                "`/shift-leaderboard` — Staff leaderboard."
            ),
            inline=False,
        )

        embed.add_field(
            name="📊 Leveling & Leaderboard",
            value=(
                "`/level [member]` — View XP and level.\n"
                "`/leaderboard` — Top active members."
            ),
            inline=False,
        )

        embed.add_field(
            name="🌐 Cross-Server Network",
            value=(
                "`!network create <name>` — Create network.\n"
                "`!network join <id>` — Join network.\n"
                "`!network leave <id>` — Leave network.\n"
                "`!network del <id>` — Delete network."
            ),
            inline=False,
        )

        embed.add_field(
            name="💡 Quick Tips",
            value=(
                "• Slash management commands require Manage Server.\n"
                "• Network commands should be restricted to trusted staff.\n"
                "• Global ban/network functionality depends on your Network Cog."
            ),
            inline=False,
        )

        button_label = "For more information"

    else:

        embed = discord.Embed(
            title="📖 دليل الاستخدام والتعليمات",
            description=(
                "مرحباً بك في دليل البوت! "
                "إليك أهم الأوامر والأنظمة المتاحة."
            ),
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="🛠️ لوحة التحكم والأوامر العامة",
            value=(
                "`/setup` — فتح لوحة التحكم.\n"
                "`/language` — تغيير لغة البوت.\n"
                "`/ticket-setup` — إرسال لوحة التذاكر.\n"
                "`/clear [العدد]` — مسح 1-100 رسالة.\n"
                "`/userinfo` و `/serverinfo` — معلومات العضو والسيرفر.\n"
                "`/ping` و `/botinfo` — معلومات الاتصال والبوت."
            ),
            inline=False,
        )

        embed.add_field(
            name="🛡️ المناوبات والإدارة",
            value=(
                "`/shift-panel` — لوحة المناوبات.\n"
                "`/shift-log-channel` — قناة سجلات المناوبات.\n"
                "`/shift-stats [العضو]` — إحصائيات المناوبات.\n"
                "`/shift-leaderboard` — قائمة المتصدرين."
            ),
            inline=False,
        )

        embed.add_field(
            name="📊 نظام المستويات XP",
            value=(
                "`/level [العضو]` — عرض المستوى وXP.\n"
                "`/leaderboard` — أفضل الأعضاء."
            ),
            inline=False,
        )

        embed.add_field(
            name="🌐 شبكة التواصل بين السيرفرات",
            value=(
                "`!network create <اسم>` — إنشاء شبكة.\n"
                "`!network join <id>` — الانضمام.\n"
                "`!network leave <id>` — المغادرة.\n"
                "`!network del <id>` — حذف الشبكة."
            ),
            inline=False,
        )

        embed.add_field(
            name="💡 ملاحظات مهمة",
            value=(
                "• أوامر الإدارة تتطلب صلاحية إدارة السيرفر.\n"
                "• أوامر الشبكة يجب أن تكون للمشرفين الموثوقين.\n"
                "• نظام الشبكات يعتمد على Network Cog."
            ),
            inline=False,
        )

        button_label = "للمزيد من المعلومات"

    view.add_item(
        discord.ui.Button(
            label=button_label,
            url="https://discord.gg/PZcZYu8AEa",
            style=discord.ButtonStyle.link,
        )
    )

    if (
        interaction.guild
        and interaction.guild.icon
    ):
        embed.set_thumbnail(
            url=interaction.guild.icon.url
        )

    await interaction.response.send_message(
        embed=embed,
        view=view,
        ephemeral=True,
    )


# ============================================================
# 34. LEVEL
# ============================================================

@bot.tree.command(
    name="level",
    description="عرض المستوى الحالي وXP",
)
@app_commands.describe(
    member="العضو المراد عرض مستواه"
)
async def level_command(
    interaction: discord.Interaction,
    member: discord.Member | None = None,
):

    target = (
        member
        or interaction.user
    )

    lang = get_guild_lang(
        interaction.guild.id
    )

    if hasattr(
        database,
        "get_user_level",
    ):

        try:

            xp, lvl = database.get_user_level(
                interaction.guild.id,
                target.id,
            )

        except Exception:

            logger.exception(
                "get_user_level failed"
            )

            xp, lvl = 0, 1

    else:

        xp, lvl = 0, 1

    xp = safe_int(
        xp,
        0,
        minimum=0,
    )

    lvl = safe_int(
        lvl,
        1,
        minimum=1,
    )

    next_xp = (
        lvl * 100
        + 100
    )

    if lang == "en":

        embed = discord.Embed(
            title=(
                f"📊 User Rank: "
                f"{target.name}"
            ),
            color=discord.Color.pink(),
        )

        embed.add_field(
            name="Level",
            value=str(lvl),
            inline=True,
        )

        embed.add_field(
            name="XP Points",
            value=(
                f"{xp} / {next_xp}"
            ),
            inline=True,
        )

    else:

        embed = discord.Embed(
            title=(
                f"📊 رتبة العضو "
                f"{target.name}"
            ),
            color=discord.Color.pink(),
        )

        embed.add_field(
            name="المستوى",
            value=str(lvl),
            inline=True,
        )

        embed.add_field(
            name="نقاط الخبرة XP",
            value=(
                f"{xp} / {next_xp}"
            ),
            inline=True,
        )

    embed.set_thumbnail(
        url=target.display_avatar.url
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# 35. LEADERBOARD
# ============================================================

@bot.tree.command(
    name="leaderboard",
    description="عرض قائمة المتصدرين",
)
@app_commands.checks.cooldown(
    1,
    10.0,
    key=lambda i: (
        i.guild_id,
        i.user.id,
    ),
)
async def leaderboard(
    interaction: discord.Interaction,
):

    guild_id = interaction.guild.id

    lang = get_guild_lang(
        guild_id
    )

    if hasattr(
        database,
        "get_top_users",
    ):

        try:

            top_users = database.get_top_users(
                guild_id,
                limit=10,
            )

        except Exception:

            logger.exception(
                "get_top_users failed"
            )

            top_users = []

    else:

        top_users = []

    if lang == "en":

        embed = discord.Embed(
            title=(
                f"🏆 Leaderboard for "
                f"{interaction.guild.name}"
            ),
            description=(
                "Most active members with "
                "the highest XP points:"
            ),
            color=discord.Color.gold(),
        )

    else:

        embed = discord.Embed(
            title=(
                f"🏆 قائمة المتصدرين في "
                f"{interaction.guild.name}"
            ),
            description=(
                "أكثر الأعضاء تفاعلاً "
                "وحصولاً على XP:"
            ),
            color=discord.Color.gold(),
        )

    if not top_users:

        if lang == "en":

            embed.add_field(
                name="No data yet",
                value=(
                    "Start sending messages "
                    "to appear here!"
                ),
                inline=False,
            )

        else:

            embed.add_field(
                name="لا توجد بيانات بعد",
                value=(
                    "ابدأ بإرسال الرسائل "
                    "لتظهر في القائمة!"
                ),
                inline=False,
            )

    else:

        desc_list = []

        for index, row in enumerate(
            top_users,
            start=1,
        ):

            try:

                uid, xp, lvl = row

                uid_int = int(uid)

            except (
                ValueError,
                TypeError,
            ):

                continue

            member = interaction.guild.get_member(
                uid_int
            )

            if member:

                name = member.mention

            else:

                name = (
                    f"Left user ({uid_int})"
                    if lang == "en"
                    else
                    f"مستخدم مغادر ({uid_int})"
                )

            if index == 1:
                medal = "🥇"

            elif index == 2:
                medal = "🥈"

            elif index == 3:
                medal = "🥉"

            else:
                medal = f"**#{index}**"

            lvl_text = (
                "Level"
                if lang == "en"
                else "المستوى"
            )

            desc_list.append(
                f"{medal} {name} — "
                f"{lvl_text}: **{lvl}** "
                f"(`{xp} XP`)"
            )

        if desc_list:
            embed.description = (
                "\n".join(desc_list)
            )

    if interaction.guild.icon:

        embed.set_thumbnail(
            url=interaction.guild.icon.url
        )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# 36. FLASK SERVER
# ============================================================

def run_web_server():

    logger.info(
        "Starting Flask dashboard on port %s",
        PORT,
    )

    # مهم:
    # debug=False لمنع reloader من تشغيل البوت مرتين.
    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        use_reloader=False,
    )


# ============================================================
# 37. SHUTDOWN
# ============================================================

async def close_http_session():

    global http_session

    if (
        http_session
        and not http_session.closed
    ):

        await http_session.close()

        http_session = None


# ============================================================
# 38. BOT STARTUP
# ============================================================

if __name__ == "__main__":

    # تشغيل Flask في Thread منفصل
    web_thread = threading.Thread(
        target=run_web_server,
        name="FlaskDashboard",
        daemon=True,
    )

    web_thread.start()

    if not TOKEN:

        raise RuntimeError(
            "TOKEN غير موجود. "
            "أضفه إلى Environment Variables."
        )

    try:

        bot.run(TOKEN)

    except KeyboardInterrupt:

        logger.info(
            "تم إيقاف البوت."
        )

    finally:

        logger.info(
            "تم إغلاق البوت."
        )
