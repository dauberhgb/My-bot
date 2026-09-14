import asyncio
import io
import logging
import os
import re
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageOps
import arabic_reshaper
from bidi.algorithm import get_display

import database as db


logger = logging.getLogger("discord_bot.welcome")


# ============================================================
# المسارات
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
FRAMES_DIR = BASE_DIR / "frames"
FONT_PATH = BASE_DIR / "tajawal.ttf"


# ============================================================
# الإطارات المتاحة
# ============================================================

AVAILABLE_FRAMES = {
    "admin_gold": {
        "en_file": FRAMES_DIR / "admin_gold.png",
        "ar_file": FRAMES_DIR / "admin_gold_ar.png",
    },
    "cyberpunk": {
        "en_file": FRAMES_DIR / "cyberpunk.png",
        "ar_file": FRAMES_DIR / "cyberpunk_ar.png",
    },
    "galaxy_space": {
        "en_file": FRAMES_DIR / "galaxy_space.png",
        "ar_file": FRAMES_DIR / "galaxy_space_ar.png",
    },
    "mafia_gangs": {
        "en_file": FRAMES_DIR / "mafia_gangs.png",
        "ar_file": FRAMES_DIR / "mafia_gangs_ar.png",
    },
    "royal_blue": {
        "en_file": FRAMES_DIR / "royal_blue.png",
        "ar_file": FRAMES_DIR / "royal_blue_ar.png",
    },
}


# ============================================================
# إعدادات البطاقة
# ============================================================

CARD_WIDTH = 1536
CARD_HEIGHT = 1024

AVATAR_SIZE = 380

MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_TIMEOUT = aiohttp.ClientTimeout(total=15)

MAX_TEXT_1 = 120
MAX_TEXT_2 = 80
MAX_TEXT_3 = 100

HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


# ============================================================
# أدوات عامة
# ============================================================

def clean_text(value, default="", max_length=500):
    if value is None:
        return default

    value = str(value).strip()

    if not value:
        return default

    return value[:max_length]


def valid_color(value, default):
    value = str(value or "").strip()

    if HEX_COLOR_RE.fullmatch(value):
        return value

    return default


def hex_to_rgb(value, default):
    value = valid_color(value, default)

    try:
        return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
    except Exception:
        fallback = default.lstrip("#")
        return tuple(int(fallback[i:i + 2], 16) for i in (0, 2, 4))


def rtl_text(text):
    """
    تجهيز النص العربي للرسم بواسطة Pillow.
    """
    text = str(text or "")

    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


def replace_placeholders(text, member):
    """
    استبدال المتغيرات الموجودة في إعدادات الترحيب.
    """

    server_name = member.guild.name
    username = member.display_name
    count = member.guild.member_count or 0

    replacements = {
        "{server}": server_name,
        "{user_name}": username,
        "{user}": username,
        "{count}": str(count),
        "{member_count}": str(count),
    }

    result = str(text or "")

    for key, value in replacements.items():
        result = result.replace(key, value)

    return result


# ============================================================
# تحميل الخط
# ============================================================

def get_font(size):
    """
    تحميل الخط بدون إعادة تحميله بشكل متكرر.
    """

    try:
        if FONT_PATH.exists():
            return ImageFont.truetype(str(FONT_PATH), size)
    except Exception as exc:
        logger.warning("تعذر تحميل tajawal.ttf: %s", exc)

    return ImageFont.load_default()


# ============================================================
# Cog الترحيب
# ============================================================

class Welcome(commands.Cog):
    """
    نظام الترحيب الكامل:

    - استقبال عضو جديد
    - قراءة إعدادات السيرفر
    - النصوص
    - الألوان
    - الإطارات
    - الخلفية
    - صورة العضو
    - العربية والإنجليزية
    - عدد الأعضاء
    - إنشاء البطاقة
    - إرسال البطاقة
    """

    def __init__(self, bot):
        self.bot = bot
        self._session = None
        self._session_lock = asyncio.Lock()

    # ========================================================
    # Session مشتركة
    # ========================================================

    async def _get_session(self):
        """
        إنشاء aiohttp session واحدة وإعادة استخدامها.
        """

        if self._session is not None and not self._session.closed:
            return self._session

        async with self._session_lock:

            if self._session is None or self._session.closed:

                self._session = aiohttp.ClientSession(
                    timeout=IMAGE_TIMEOUT,
                    headers={
                        "User-Agent": "DiscordWelcomeBot/1.0"
                    },
                )

        return self._session

    async def cog_unload_async(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def cog_unload(self):
        """
        إغلاق Session عند إزالة الـ Cog.
        """

        if self._session and not self._session.closed:

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._session.close())
            except RuntimeError:
                pass

    # ========================================================
    # تحميل صورة آمنة
    # ========================================================

    async def _download_image(self, url):
        """
        تحميل صورة مع حد للحجم ووقت انتظار.
        """

        if not url:
            return None

        url = str(url).strip()

        if not (
            url.startswith("http://")
            or url.startswith("https://")
        ):
            return None

        try:
            session = await self._get_session()

            async with session.get(
                url,
                allow_redirects=True,
            ) as response:

                if response.status != 200:
                    logger.warning(
                        "فشل تحميل الصورة: HTTP %s",
                        response.status,
                    )
                    return None

                content_type = (
                    response.headers.get("Content-Type", "")
                    .lower()
                )

                if content_type and not content_type.startswith("image/"):
                    logger.warning(
                        "الرابط ليس صورة: %s",
                        content_type,
                    )
                    return None

                content_length = response.headers.get(
                    "Content-Length"
                )

                if content_length:

                    try:
                        if int(content_length) > MAX_IMAGE_BYTES:
                            logger.warning(
                                "الصورة أكبر من الحد المسموح."
                            )
                            return None
                    except ValueError:
                        pass

                data = bytearray()

                async for chunk in response.content.iter_chunked(64 * 1024):

                    data.extend(chunk)

                    if len(data) > MAX_IMAGE_BYTES:
                        logger.warning(
                            "تم رفض الصورة لأنها أكبر من الحد."
                        )
                        return None

                if not data:
                    return None

                return bytes(data)

        except asyncio.TimeoutError:
            logger.warning("انتهت مهلة تحميل الصورة.")

        except aiohttp.ClientError as exc:
            logger.warning(
                "خطأ HTTP أثناء تحميل الصورة: %s",
                exc,
            )

        except Exception as exc:
            logger.exception(
                "خطأ غير متوقع أثناء تحميل الصورة: %s",
                exc,
            )

        return None

    # ========================================================
    # تجهيز صورة العضو
    # ========================================================

    async def _download_avatar(self, member):

        try:
            avatar_url = str(member.display_avatar.url)

            return await self._download_image(avatar_url)

        except Exception as exc:
            logger.warning(
                "تعذر الحصول على صورة العضو %s: %s",
                member.id,
                exc,
            )

            return None

    # ========================================================
    # رسم البطاقة
    # ========================================================

    def _draw_card_sync(
        self,
        avatar_bytes,
        bg_bytes,
        text_1,
        text_2,
        text_3,
        color_1,
        color_2,
        color_3,
        lang,
        frame_key,
    ):
        """
        هذه الدالة تعمل داخل Thread حتى لا يتم تجميد Discord.
        """

        base = Image.new(
            "RGBA",
            (CARD_WIDTH, CARD_HEIGHT),
            (0, 0, 0, 0),
        )

        # ----------------------------------------------------
        # الخلفية
        # ----------------------------------------------------

        if bg_bytes:

            try:

                background = Image.open(
                    io.BytesIO(bg_bytes)
                ).convert("RGBA")

                background = ImageOps.fit(
                    background,
                    (CARD_WIDTH, CARD_HEIGHT),
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.5),
                )

                base.alpha_composite(background)

            except Exception as exc:

                logger.warning(
                    "تعذر تركيب خلفية الترحيب: %s",
                    exc,
                )

        is_ar = str(lang).lower().strip() == "ar"

        # ----------------------------------------------------
        # الألوان
        # ----------------------------------------------------

        color_1 = hex_to_rgb(color_1, "#FFFFFF")
        color_2 = hex_to_rgb(color_2, "#93C5FD")
        color_3 = hex_to_rgb(color_3, "#D1D5DB")

        # ----------------------------------------------------
        # الخطوط
        # ----------------------------------------------------

        font_title = get_font(38)
        font_name = get_font(48)
        font_sub = get_font(28)

        # ----------------------------------------------------
        # النصوص
        # ----------------------------------------------------

        text_1 = clean_text(
            text_1,
            "",
            MAX_TEXT_1,
        )

        text_2 = clean_text(
            text_2,
            "",
            MAX_TEXT_2,
        )

        text_3 = clean_text(
            text_3,
            "",
            MAX_TEXT_3,
        )

        if is_ar:

            text_1 = rtl_text(text_1)
            text_2 = rtl_text(text_2[:18])
            text_3 = rtl_text(text_3)

            avatar_x = 960
            avatar_y = 320

            name_x = 600
            title_x = 500
            sub_x = 360

        else:

            text_2 = text_2[:18]

            avatar_x = 145
            avatar_y = 320

            name_x = 650
            title_x = 650
            sub_x = 650

        # ----------------------------------------------------
        # صورة العضو
        # ----------------------------------------------------

        if avatar_bytes:

            try:

                avatar = Image.open(
                    io.BytesIO(avatar_bytes)
                ).convert("RGBA")

                avatar = ImageOps.fit(
                    avatar,
                    (AVATAR_SIZE, AVATAR_SIZE),
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.5),
                )

                mask = Image.new(
                    "L",
                    (AVATAR_SIZE, AVATAR_SIZE),
                    0,
                )

                mask_draw = ImageDraw.Draw(mask)

                mask_draw.ellipse(
                    (
                        0,
                        0,
                        AVATAR_SIZE,
                        AVATAR_SIZE,
                    ),
                    fill=255,
                )

                base.paste(
                    avatar,
                    (avatar_x, avatar_y),
                    mask,
                )

            except Exception as exc:

                logger.warning(
                    "تعذر رسم صورة العضو: %s",
                    exc,
                )

        # ----------------------------------------------------
        # الإطار
        # ----------------------------------------------------

        if frame_key in AVAILABLE_FRAMES:

            frame_info = AVAILABLE_FRAMES[frame_key]

            frame_path = (
                frame_info["ar_file"]
                if is_ar
                else frame_info["en_file"]
            )

            try:

                if frame_path.exists():

                    frame = Image.open(
                        frame_path
                    ).convert("RGBA")

                    if frame.size != (
                        CARD_WIDTH,
                        CARD_HEIGHT,
                    ):
                        frame = frame.resize(
                            (
                                CARD_WIDTH,
                                CARD_HEIGHT,
                            ),
                            Image.Resampling.LANCZOS,
                        )

                    base.alpha_composite(frame)

                else:

                    logger.warning(
                        "الإطار غير موجود: %s",
                        frame_path,
                    )

            except Exception as exc:

                logger.warning(
                    "خطأ دمج الإطار: %s",
                    exc,
                )

        # ----------------------------------------------------
        # النصوص النهائية
        # ----------------------------------------------------

        draw = ImageDraw.Draw(base)

        draw.text(
            (name_x, 390),
            text_2,
            fill=color_2,
            font=font_name,
            anchor="mm",
        )

        draw.text(
            (title_x, 500),
            text_1,
            fill=color_1,
            font=font_title,
            anchor="mm",
        )

        draw.text(
            (sub_x, 610),
            text_3,
            fill=color_3,
            font=font_sub,
            anchor="mm",
        )

        # ----------------------------------------------------
        # حفظ PNG
        # ----------------------------------------------------

        output = io.BytesIO()

        base.save(
            output,
            format="PNG",
            optimize=True,
        )

        output.seek(0)

        return output

    # ========================================================
    # إنشاء بطاقة الترحيب
    # ========================================================

    async def generate_welcome_card(self, member):
        """
        قراءة الإعدادات + تحميل الصور + إنشاء البطاقة.
        """

        settings = db.get_settings(
            member.guild.id
        ) or {}

        # ----------------------------------------------------
        # النصوص
        # ----------------------------------------------------

        raw_text_1 = settings.get(
            "text_1",
            "WELCOME TO THE SERVER",
        )

        raw_text_2 = settings.get(
            "text_2",
            "{user_name}",
        )

        raw_text_3 = settings.get(
            "text_3",
            "MEMBER #{count}",
        )

        # ----------------------------------------------------
        # الألوان
        # ----------------------------------------------------

        color_1 = valid_color(
            settings.get("color_1"),
            "#FFFFFF",
        )

        color_2 = valid_color(
            settings.get("color_2"),
            "#93C5FD",
        )

        color_3 = valid_color(
            settings.get("color_3"),
            "#D1D5DB",
        )

        # ----------------------------------------------------
        # اللغة والإطار
        # ----------------------------------------------------

        lang = str(
            settings.get(
                "language",
                "ar",
            )
        ).lower()

        if lang not in ("ar", "en"):
            lang = "ar"

        frame_key = settings.get(
            "welcome_frame"
        )

        if frame_key not in AVAILABLE_FRAMES:
            frame_key = None

        # ----------------------------------------------------
        # استبدال المتغيرات
        # ----------------------------------------------------

        text_1 = replace_placeholders(
            raw_text_1,
            member,
        )

        text_2 = replace_placeholders(
            raw_text_2,
            member,
        )

        text_3 = replace_placeholders(
            raw_text_3,
            member,
        )

        # ----------------------------------------------------
        # الروابط
        # ----------------------------------------------------

        background_url = str(
            settings.get(
                "welcome_img",
                "",
            ) or ""
        ).strip()

        # ----------------------------------------------------
        # تحميل الخلفية + الأفاتار بالتوازي
        # ----------------------------------------------------

        background_task = (
            self._download_image(background_url)
            if background_url
            else asyncio.sleep(0, result=None)
        )

        avatar_task = self._download_avatar(
            member
        )

        bg_bytes, avatar_bytes = await asyncio.gather(
            background_task,
            avatar_task,
            return_exceptions=False,
        )

        # ----------------------------------------------------
        # الرسم في Thread
        # ----------------------------------------------------

        buffer = await asyncio.to_thread(
            self._draw_card_sync,
            avatar_bytes,
            bg_bytes,
            text_1,
            text_2,
            text_3,
            color_1,
            color_2,
            color_3,
            lang,
            frame_key,
        )

        return discord.File(
            buffer,
            filename="welcome_card.png",
        )

    # ========================================================
    # حدث دخول عضو جديد
    # ========================================================

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """
        المسؤول الوحيد عن إرسال بطاقة الترحيب.
        """

        if member.bot:
            return

        try:

            settings = db.get_settings(
                member.guild.id
            ) or {}

            # ------------------------------------------------
            # هل الترحيب مفعل؟
            # ------------------------------------------------

            if not settings.get(
                "welcome_enabled",
                True,
            ):
                return

            # ------------------------------------------------
            # قناة الترحيب
            # ------------------------------------------------

            channel_id = settings.get(
                "welcome_channel"
            )

            if not channel_id:
                return

            try:
                channel_id = int(channel_id)
            except (TypeError, ValueError):
                logger.warning(
                    "welcome_channel غير صالح في السيرفر %s",
                    member.guild.id,
                )
                return

            channel = member.guild.get_channel(
                channel_id
            )

            if channel is None:
                logger.warning(
                    "قناة الترحيب غير موجودة في السيرفر %s",
                    member.guild.id,
                )
                return

            if not hasattr(channel, "send"):
                return

            # ------------------------------------------------
            # إنشاء البطاقة
            # ------------------------------------------------

            welcome_file = await self.generate_welcome_card(
                member
            )

            # ------------------------------------------------
            # رسالة الترحيب
            # ------------------------------------------------

            lang = str(
                settings.get(
                    "language",
                    "ar",
                )
            ).lower()

            custom_message = clean_text(
                settings.get(
                    "welcome_msg",
                    "",
                ),
                "",
                1800,
            )

            if custom_message:

                message_text = (
                    custom_message
                    .replace(
                        "{user}",
                        member.mention,
                    )
                    .replace(
                        "{user_name}",
                        member.display_name,
                    )
                    .replace(
                        "{server}",
                        member.guild.name,
                    )
                    .replace(
                        "{count}",
                        str(
                            member.guild.member_count
                            or 0
                        ),
                    )

                )

            elif lang == "en":

                message_text = (
                    f"Welcome {member.mention} "
                    f"to {member.guild.name}! 🎉"
                )

            else:

                message_text = (
                    f"أهلاً بك يا {member.mention} "
                    f"في سيرفر {member.guild.name}! 🎉"
                )

            # ------------------------------------------------
            # الإرسال
            # ------------------------------------------------

            allowed_mentions = discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=False,
                replied_user=False,
            )

            await channel.send(
                content=message_text,
                file=welcome_file,
                allowed_mentions=allowed_mentions,
            )

            logger.info(
                "تم إرسال بطاقة ترحيب للعضو %s في %s",
                member,
                member.guild.name,
            )

        except discord.Forbidden:

            logger.error(
                "لا توجد صلاحية لإرسال الترحيب في %s",
                member.guild.name,
            )

        except discord.HTTPException as exc:

            logger.error(
                "Discord HTTP error أثناء الترحيب: %s",
                exc,
            )

        except Exception as exc:

            logger.exception(
                "خطأ في نظام الترحيب للسيرفر %s: %s",
                member.guild.id,
                exc,
            )

    # ========================================================
    # أمر تعديل النصوص
    # ========================================================

    @commands.command(name="set_texts")
    @commands.has_permissions(administrator=True)
    async def set_texts(
        self,
        ctx,
        t1: str,
        t2: str,
        t3: str,
    ):
        """
        تعديل النصوص الثلاثة الموجودة داخل البطاقة.
        """

        settings = db.get_settings(
            ctx.guild.id
        ) or {}

        settings.update({
            "text_1": clean_text(
                t1,
                "",
                MAX_TEXT_1,
            ),
            "text_2": clean_text(
                t2,
                "",
                MAX_TEXT_2,
            ),
            "text_3": clean_text(
                t3,
                "",
                MAX_TEXT_3,
            ),
        })

        db.save_settings(
            ctx.guild.id,
            settings,
        )

        await ctx.send(
            "✅ تم تحديث نصوص بطاقة الترحيب بنجاح!"
        )

    # ========================================================
    # أمر تعديل الألوان
    # ========================================================

    @commands.command(name="set_colors")
    @commands.has_permissions(administrator=True)
    async def set_colors(
        self,
        ctx,
        c1: str,
        c2: str,
        c3: str,
    ):
        """
        تعديل ألوان النصوص الثلاثة.
        """

        colors = [c1, c2, c3]

        for color in colors:

            if not HEX_COLOR_RE.fullmatch(
                str(color)
            ):
                await ctx.send(
                    "❌ يجب أن يكون اللون بصيغة Hex مثل `#FFFFFF`"
                )
                return

        settings = db.get_settings(
            ctx.guild.id
        ) or {}

        settings.update({
            "color_1": c1.upper(),
            "color_2": c2.upper(),
            "color_3": c3.upper(),
        })

        db.save_settings(
            ctx.guild.id,
            settings,
        )

        await ctx.send(
            "🎨 تم تحديث ألوان بطاقة الترحيب بنجاح!"
        )


# ============================================================
# تحميل الـ Cog
# ============================================================

async def setup(bot):
    await bot.add_cog(
        Welcome(bot)
    )
