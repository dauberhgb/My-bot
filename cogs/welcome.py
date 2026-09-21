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

# قاموس الإطارات المتاحة
AVAILABLE_FRAMES = {
    "admin_gold": {
        "en_file": "frames/admin_gold.png",
        "ar_file": "frames/admin_gold_ar.png"
    },
    "cyberpunk": {
        "en_file": "frames/cyberpunk.png",
        "ar_file": "frames/cyberpunk_ar.png"
    },
    "galaxy_space": {
        "en_file": "frames/galaxy_space.png",
        "ar_file": "frames/galaxy_space_ar.png"
    },
    "mafia_gangs": {
        "en_file": "frames/mafia_gangs.png",
        "ar_file": "frames/mafia_gangs_ar.png"
    },
    "royal_blue": {
        "en_file": "frames/royal_blue.png",
        "ar_file": "frames/royal_blue_ar.png"
    }
}

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

# ==========================================
# 3. دالة توليد بطاقة الترحيب الشفافة مع النصوص والإطار
# ==========================================
async def generate_welcome_card(member, bg_url=None, lang="ar", frame_key=None, guild_id=None):
  try:
    width, height = 1536, 1024
    # إنشاء خلفية شفافة بالكامل
    base = Image.new("RGBA", (width, height), (0, 0, 0, 0))
      
    settings = database.get_settings(guild_id) if guild_id else {}
    
    raw_t1 = settings.get("text_1", "WELCOME TO THE SERVER")
    raw_t2 = settings.get("text_2", "{user_name}")
    raw_t3 = settings.get("text_3", "MEMBER #{count}")
    
    c1 = settings.get("color_1", "#FFFFFF")
    c2 = settings.get("color_2", "#93C5FD")
    c3 = settings.get("color_3", "#D1D5DB")

    t1_text = raw_t1.replace("{server}", member.guild.name)
    t2_text = raw_t2.replace("{user_name}", member.display_name).replace("{user}", member.display_name)
    t3_text = raw_t3.replace("{count}", str(member.guild.member_count))
    
    # بداية كود تحميل الخلفية المخصصة
    if bg_url and bg_url.startswith("http"):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(bg_url) as resp:
                    if resp.status == 200:
                        bg_data = await resp.read()
                        custom_bg = Image.open(BytesIO(bg_data)).convert("RGBA")
                        custom_bg = custom_bg.resize((width, height))
                        base.paste(custom_bg, (0, 0))
        except Exception as e:
            print(f"❌ خطأ في تحميل الصورة: {e}")
    # نهاية كود تحميل الخلفية المخصصة

    user_lang = str(lang).lower().strip()
    
    # 1. دمج الإطار الشفاف أولاً (ليكون في الخلفية)
    if frame_key and frame_key in AVAILABLE_FRAMES:
      frame_info = AVAILABLE_FRAMES[frame_key]
      frame_path = frame_info["ar_file"] if user_lang == "ar" else frame_info["en_file"]
      
      if os.path.exists(frame_path):
        try:
          frame_img = Image.open(frame_path).convert("RGBA")
          frame_img = frame_img.resize((width, height))
          base = Image.alpha_composite(base, frame_img)
        except Exception as fe:
          print(f"❌ خطأ أثناء دمج إطار البطاقة: {fe}")
            
    # 2. جلب وتجهيز الخط
    font_path = "tajawal.ttf"
    if not os.path.exists(font_path):
      font_url = "https://github.com/google/fonts/raw/main/ofl/cairo/Cairo-Bold.ttf"
      async with aiohttp.ClientSession() as session:
        async with session.get(font_url) as resp:
          if resp.status == 200:
            font_data = await resp.read()
            with open(font_path, "wb") as f:
              f.write(font_data)

    try:
      font_title = ImageFont.truetype(font_path, 41)
      font_name = ImageFont.truetype(font_path, 55)
      font_sub = ImageFont.truetype(font_path, 30)
    except Exception:
      font_title = font_name = font_sub = ImageFont.load_default()

    avatar_size = 440
    avatar_y = ((height - avatar_size) // 2) - 20

    # 3. معالجة النصوص وتعديل الاتجاه والـ X للأماكن الصحيحة (من اليمين لليسار)
    if user_lang == "ar":
      avatar_x = width - avatar_size - 96  # البروفايل على اليمين
      title_x = width - 780
      name_x = width - 870
      sub_x = width - 870
      title_y = 529
      name_y = 305
      sub_y = 731
      
      welcome_title = arabic_reshaper.reshape(t1_text)
      member_count_text = arabic_reshaper.reshape(t3_text)
      display_name = arabic_reshaper.reshape(t2_text[:18])

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
        

    # إنشاء أداة الرسم للعمليات العلوية (البروفايل والنصوص)
    draw = ImageDraw.Draw(base)

    # 4. رسم صورة البروفايل
    avatar_url = member.display_avatar.url
    async with aiohttp.ClientSession() as session:
      async with session.get(avatar_url) as resp:
        if resp.status == 200:
          avatar_data = await resp.read()
          avatar = Image.open(BytesIO(avatar_data)).convert("RGBA")
          avatar = avatar.resize((avatar_size, avatar_size))

          mask = Image.new("L", (avatar_size, avatar_size), 0)
          mask_draw = ImageDraw.Draw(mask)
          mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)

          draw.ellipse(
              (avatar_x - 5, avatar_y - 5, avatar_x + avatar_size + 5, avatar_y + avatar_size + 5),
              outline=(59, 130, 246, 255),
              width=5
          )
          base.paste(avatar, (avatar_x, avatar_y), mask)

    # 5. رسم النصوص في النهاية (لتظهر فوق كل شيء بما فيها الإطار)
    draw.text((title_x, title_y), welcome_title, fill=c1, font=font_title, anchor="ra" if user_lang == "ar" else "lm")
    draw.text((name_x, name_y), display_name, fill=c2, font=font_name, anchor="ra" if user_lang == "ar" else "lm")
    draw.text((sub_x, sub_y), member_count_text, fill=c3, font=font_sub, anchor="ra" if user_lang == "ar" else "lm")

    final_buffer = BytesIO()
    base.save(final_buffer, format="PNG")
    final_buffer.seek(0)
    return discord.File(final_buffer, filename="welcome_card.png")
  except Exception as e:
    print(f"❌ خطأ عام في توليد بطاقة الترحيب: {e}")
    return None

async def setup(bot):
    await bot.add_cog(Welcome(bot))
