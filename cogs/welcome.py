import os
import io
import asyncio
import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
import database as db

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _draw_card_sync(self, avatar_bytes, bg_bytes, t1_text, t2_text, t3_text, c1, c2, c3):
        """رسم الصورة داخل Thread منفصل لعدم تجميد البوت"""
        width, height = 1536, 1024
        base = Image.new("RGBA", (width, height), (0, 0, 0, 0))

        if bg_bytes:
            try:
                custom_bg = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")
                custom_bg = custom_bg.resize((width, height))
                base.paste(custom_bg, (0, 0))
            except Exception as e:
                print(f"❌ خطأ تحميل الخلفية: {e}")

        font_path = "tajawal.ttf"
        try:
            font_title = ImageFont.truetype(font_path, 38)
            font_name = ImageFont.truetype(font_path, 48)
            font_sub = ImageFont.truetype(font_path, 28)
        except Exception:
            font_title = font_name = font_sub = ImageFont.load_default()

        draw = ImageDraw.Draw(base)

        t1_reshaped = get_display(arabic_reshaper.reshape(t1_text))
        t2_reshaped = get_display(arabic_reshaper.reshape(t2_text[:18]))
        t3_reshaped = get_display(arabic_reshaper.reshape(t3_text))

        if avatar_bytes:
            try:
                avatar_size = 440
                avatar_y = ((height - avatar_size) // 2) - 20
                avatar_x = width - avatar_size - 50

                avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
                avatar = avatar.resize((avatar_size, avatar_size))
                
                mask = Image.new("L", (avatar_size, avatar_size), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)

                base.paste(avatar, (avatar_x, avatar_y), mask)
            except Exception as ae:
                print(f"❌ خطأ رسم البروفايل: {ae}")

        draw.text((width - 120, 529), t1_reshaped, fill=c1, font=font_title, anchor="ra")
        draw.text((width - 160, 315), t2_reshaped, fill=c2, font=font_name, anchor="ra")
        draw.text((width - 90, 731), t3_reshaped, fill=c3, font=font_sub, anchor="ra")

        final_buffer = io.BytesIO()
        base.save(final_buffer, format="PNG")
        final_buffer.seek(0)
        return final_buffer

    async def generate_welcome_card(self, member):
        """جلب البيانات وتمرير المعالجة للـ Thread"""
        settings = db.get_settings(member.guild.id) or {}
        
        raw_t1 = settings.get("text_1", "WELCOME TO THE SERVER")
        raw_t2 = settings.get("text_2", "{user_name}")
        raw_t3 = settings.get("text_3", "MEMBER #{count}")

        c1 = settings.get("color_1", "#FFFFFF")
        c2 = settings.get("color_2", "#93C5FD")
        c3 = settings.get("color_3", "#D1D5DB")

        t1_text = raw_t1.replace("{server}", member.guild.name)
        t2_text = raw_t2.replace("{user_name}", member.display_name).replace("{user}", member.display_name)
        t3_text = raw_t3.replace("{count}", str(member.guild.member_count))

        bg_bytes = None
        avatar_bytes = None
        bg_url = settings.get("welcome_img", "")

        async with aiohttp.ClientSession() as session:
            if bg_url and bg_url.startswith("http"):
                try:
                    async with session.get(bg_url) as resp:
                        if resp.status == 200:
                            bg_bytes = await resp.read()
                except Exception as e:
                    print(f"❌ خطأ جلب الخلفية: {e}")

            try:
                avatar_target = member.display_avatar.url
                async with session.get(avatar_target) as resp:
                    if resp.status == 200:
                        avatar_bytes = await resp.read()
            except Exception as e:
                print(f"❌ خطأ جلب الصورة الشخصية: {e}")

        buffer = await asyncio.to_thread(
            self._draw_card_sync,
            avatar_bytes, bg_bytes, t1_text, t2_text, t3_text, c1, c2, c3
        )
        return discord.File(buffer, filename="welcome_card.png")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """إرسال البطاقة عند انضمام عضو جديد"""
        settings = db.get_settings(member.guild.id) or {}
        if not settings.get("welcome_enabled", 1):
            return

        channel_id = settings.get("welcome_channel")
        if not channel_id:
            return

        channel = member.guild.get_channel(int(channel_id))
        if not channel:
            return

        welcome_file = await self.generate_welcome_card(member)
        msg_text = settings.get("welcome_msg", "أهلاً بك يا {user} في السيرفر! 🎉").replace("{user}", member.mention)

        await channel.send(content=msg_text, file=welcome_file)

    @commands.command(name="set_texts")
    @commands.has_permissions(administrator=True)
    async def set_texts(self, ctx, t1: str, t2: str, t3: str):
        """تعديل النصوص الثلاثة المطبوعة على الإطار"""
        settings = db.get_settings(ctx.guild.id) or {}
        settings.update({
            "text_1": t1,
            "text_2": t2,
            "text_3": t3
        })
        db.save_settings(ctx.guild.id, settings)
        await ctx.send("✅ تم تحديث النصوص المطبوعة على الإطار بنجاح!")

    @commands.command(name="set_colors")
    @commands.has_permissions(administrator=True)
    async def set_colors(self, ctx, c1: str, c2: str, c3: str):
        """تعديل ألوان النصوص الثلاثة المطبوعة بصيغة Hex"""
        for color in [c1, c2, c3]:
            if not color.startswith("#") or len(color) != 7:
                await ctx.send("❌ يرجى إدخال ألوان بصيغة Hex صحيحة مثل: `#FFFFFF`")
                return

        settings = db.get_settings(ctx.guild.id) or {}
        settings.update({
            "color_1": c1,
            "color_2": c2,
            "color_3": c3
        })
        db.save_settings(ctx.guild.id, settings)
        await ctx.send("🎨 تم تحديث ألوان النصوص الثلاثة بنجاح!")

async def setup(bot):
    await bot.add_cog(Welcome(bot))
