from datetime import timedelta
from functools import wraps
import json
import os
import threading
import database
from discord import app_commands
from discord.ext import commands
import discord
from flask import Flask, jsonify, redirect, render_template, request, url_for
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import aiohttp

# استيراد نظام الترجمات ودالة الترجمة
from translations import _

# ==========================================
# 1. إعداد وتشغيل بوت ديسكورد
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
violations = {}

# معرف حسابك في ديسكورد (User ID)
OWNER_ID = 1462429084377157832

# ==========================================
# 2. إعداد خادم الويب (Flask Dashboard)
# ==========================================
app = Flask(__name__)


# دالة مساعدة لجلب لغة السيرفر
def get_guild_lang(guild_id):
  if not guild_id:
    return "ar"
  settings = database.get_settings(guild_id)
  return settings.get("language", "ar")


# دالة ديكوراتور للتحقق من هوية وصلاحية المشرف
def admin_required(f):
  @wraps(f)
  def decorated_function(guild_id, *args, **kwargs):
    guild = bot.get_guild(int(guild_id))
    if not guild:
      if request.path.startswith("/save/"):
        return (
            jsonify({
                "status": "error",
                "message": "السيرفر غير موجود أو البوت ليس عضواً فيه!",
            }),
            404,
        )
      return "السيرفر غير موجود أو البوت ليس عضواً فيه!", 404

    user_id = (
        request.args.get("user_id")
        or request.headers.get("X-User-ID")
        or request.form.get("user_id")
    )

    if user_id and user_id.isdigit():
      member = guild.get_member(int(user_id))
      if not member or not member.guild_permissions.manage_guild:
        if request.path.startswith("/save/"):
          return (
              jsonify({
                  "status": "error",
                  "message": (
                      "عذراً، لا تملك صلاحية (إدارة السيرفر) للقيام بهذا"
                      " الإجراء!"
                  ),
              }),
              403,
          )
        return (
            "عذراً، لا تملك صلاحية (إدارة السيرفر) للدخول إلى هذه اللوحة!",
            403,
        )

    return f(guild_id, *args, **kwargs)

  return decorated_function


@app.route("/")
def home():
  user_id = request.args.get("user_id")
  if user_id:
    return redirect(url_for("guild_list", user_id=user_id))
  return redirect(url_for("guild_list"))


@app.route("/guilds")
def guild_list():
  user_id = request.args.get("user_id")
  bot_guilds = []
  current_lang = "ar"

  for guild in bot.guilds:
    if user_id and user_id.isdigit():
      member = guild.get_member(int(user_id))
      if member and member.guild_permissions.manage_guild:
        if not bot_guilds:
          settings = database.get_settings(guild.id)
          current_lang = settings.get("language", "ar")

        bot_guilds.append({
            "id": str(guild.id),
            "name": guild.name,
            "icon": guild.icon.url if guild.icon else None,
        })

  return render_template(
      "guilds.html",
      guilds=bot_guilds,
      user_id=user_id,
      current_lang=current_lang,
  )


@app.route("/dashboard/<guild_id>")
@admin_required
def dashboard(guild_id):
  guild = bot.get_guild(int(guild_id))

  channels = [{"id": str(c.id), "name": c.name} for c in guild.text_channels]
  roles = [
      {"id": str(r.id), "name": r.name}
      for r in guild.roles
      if not r.is_default()
  ]
  categories = [{"id": str(cat.id), "name": cat.name} for cat in guild.categories]

  settings = database.get_settings(guild_id)
  icon_url = guild.icon.url if guild.icon else None
  current_lang = settings.get("language", "ar")

  return render_template(
      "index.html",
      guild=guild,
      channels=channels,
      roles=roles,
      categories=categories,
      settings=settings,
      icon_url=icon_url,
      current_lang=current_lang,
      **{'_': lambda text: text}
  )


@app.route("/update_language", methods=["POST"])
def update_language():
  user_id = request.form.get("user_id")
  new_lang = request.form.get("language")

  if not user_id or not user_id.isdigit() or not new_lang:
    return jsonify({"status": "error", "message": "بيانات غير صالحة!"}), 400

  for guild in bot.guilds:
    try:
      member = guild.get_member(int(user_id))
      if member and member.guild_permissions.manage_guild:
        settings = database.get_settings(guild.id)
        settings["language"] = new_lang
        database.save_settings(guild.id, settings)
    except Exception as e:
      print(f"Error saving language for guild {guild.id}: {e}")

  return jsonify({"status": "success", "message": "تم تحديث اللغة بنجاح"})


@app.route("/save/<guild_id>", methods=["POST"])
@admin_required
def save(guild_id):
  guild = bot.get_guild(int(guild_id))

  media_channels = request.form.getlist("media_channels")
  media_enabled = True if request.form.get("media_enabled") == "on" else False
  banned_enabled = True if request.form.get("banned_enabled") == "on" else False
  farewell_enabled = True if request.form.get("farewell_enabled") == "on" else False
  welcome_enabled = True if request.form.get("welcome_enabled") == "on" else False

  banned_words = [
      w.strip().lower()
      for w in request.form.get("banned_words", "").split(",")
      if w.strip()
  ]

  auto_responses = {}
  for i in range(1, 4):
    w = request.form.get(f"word{i}", "").strip().lower()
    r = request.form.get(f"resp{i}", "").strip()
    if w and r:
      auto_responses[w] = r

  settings = {
      "guild_id": guild_id,
      "media_enabled": media_enabled,
      "media_channels": media_channels,
      "media_warning": request.form.get("media_warning", ""),
      "banned_enabled": banned_enabled,
      "banned_words": banned_words,
      "max_violations": int(request.form.get("max_violations", 3)),
      "punishment_type": request.form.get("punishment_type", "timeout"),
      "timeout_minutes": int(request.form.get("timeout_minutes", 10)),
      "warning_title": request.form.get("warning_title", ""),
      "warning_msg_1": request.form.get("warning_msg_1", ""),
      "warning_msg_2": request.form.get("warning_msg_2", ""),
      "welcome_enabled": welcome_enabled,
      "welcome_channel": request.form.get("welcome_channel", ""),
      "welcome_msg": request.form.get("welcome_msg", ""),
      "welcome_img": request.form.get("welcome_img", ""),
      "farewell_enabled": farewell_enabled,
      "farewell_channel": request.form.get("farewell_channel", ""),
      "farewell_title": request.form.get("farewell_title", ""),
      "farewell_desc": request.form.get("farewell_desc", ""),
      "farewell_img": request.form.get("farewell_img", ""),
      "farewell_action": request.form.get("farewell_action", "none"),
      "auto_responses": auto_responses,
      "auto_role": request.form.get("auto_role", ""),
      "auto_nickname": request.form.get("auto_nickname", ""),
      "ticket_category": request.form.get("ticket_category", ""),
      "ticket_support_role": request.form.get("ticket_support_role", ""),
      "xp_enabled": int(request.form.get("xp_enabled", 1)),
      "xp_per_message": int(request.form.get("xp_per_message", 15)),
      "xp_role_5": request.form.get("xp_role_5", ""),
      "xp_role_10": request.form.get("xp_role_10", ""),
      "xp_role_20": request.form.get("xp_role_20", ""),
      "language": request.form.get("language", "ar"),
  }

  database.save_settings(guild_id, settings)
  return (
      jsonify({
          "status": "success",
          "message": f"تم حفظ إعدادات السيرفر ({guild.name}) بنجاح!",
      }),
      200,
  )


def run_web_server():
  port = int(os.environ.get("PORT", 8080))
  app.run(host="0.0.0.0", port=port)


threading.Thread(target=run_web_server, daemon=True).start()


# ==========================================
# 3. دالة توليد بطاقة الترحيب المتعددة اللغات والكبيرة (Welcome Card Generator)
# ==========================================
async def generate_welcome_card(member, bg_url=None, lang="ar"):
  try:
    width, height = 900, 400
    base = Image.new("RGBA", (width, height), (30, 30, 35, 255))
    draw = ImageDraw.Draw(base)

    # تحميل الخلفية أو رسم خلفية متدرجة
    bg = None
    if bg_url:
      try:
        async with aiohttp.ClientSession() as session:
          async with session.get(bg_url) as resp:
            if resp.status == 200:
              bg_data = await resp.read()
              bg = Image.open(BytesIO(bg_data)).convert("RGBA")
              bg = bg.resize((width, height))
      except Exception:
        bg = None

    if bg:
      base.paste(bg, (0, 0))
    else:
      for x in range(width):
        color = (int(30 + (x / width) * 40), int(30 + (x / width) * 20), int(60 + (x / width) * 100))
        draw.line([(x, 0), (x, height)], fill=color)

    # طبقة شفافة داكنة لزيادة التباين ووضوح النصوص
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 150))
    base = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(base)

    # معالجة صورة البروفايل بحجم 200x200 مع إطار مضيء
    avatar_size = 200
    avatar_x, avatar_y = 50, 100
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

          # إطار دائري حول البروفايل
          draw.ellipse(
              (avatar_x - 5, avatar_y - 5, avatar_x + avatar_size + 5, avatar_y + avatar_size + 5),
              outline=(99, 102, 241, 255),
              width=6
          )

          base.paste(avatar, (avatar_x, avatar_y), mask)

    # اختيار النصوص حسب اللغة
    if lang == "en":
      welcome_title = "WELCOME TO THE SERVER"
      member_count_text = f"Member #{member.guild.member_count}"
    else:
      welcome_title = "أهلاً بك في السيرفر"
      member_count_text = f"العضو رقم #{member.guild.member_count}"

    # تحميل الخطوط بأحجام كبيرة وواضحة
    try:
      font_title = ImageFont.truetype("arial.ttf", 36)
      font_name = ImageFont.truetype("arial.ttf", 52)
      font_sub = ImageFont.truetype("arial.ttf", 32)
    except IOError:
      font_title = ImageFont.load_default()
      font_name = ImageFont.load_default()
      font_sub = ImageFont.load_default()

    text_x = 280

    # 1. العنوان الرئيسي مع ظلال داكنة
    draw.text((text_x + 2, 102), welcome_title, fill=(0, 0, 0), font=font_title)
    draw.text((text_x, 100), welcome_title, fill=(147, 197, 253), font=font_title)

    # 2. اسم العضو
    draw.text((text_x + 2, 162), member.name, fill=(0, 0, 0), font=font_name)
    draw.text((text_x, 160), member.name, fill=(255, 255, 255), font=font_name)

    # 3. رقم العضو
    draw.text((text_x + 2, 242), member_count_text, fill=(0, 0, 0), font=font_sub)
    draw.text((text_x, 240), member_count_text, fill=(209, 213, 219), font=font_sub)

    final_buffer = BytesIO()
    base.convert("RGB").save(final_buffer, format="PNG")
    final_buffer.seek(0)
    return discord.File(final_buffer, filename="welcome_card.png")
  except Exception as e:
    print(f"خطأ في توليد بطاقة الترحيب: {e}")
    return None


# ==========================================
# 4. أحداث وأوامر البوت (Discord Events & Commands)
# ==========================================
@bot.event
async def on_ready():
  print(f"تم تشغيل البوت بنجاح باسم: {bot.user}")

  if os.path.exists("./cogs"):
    for filename in os.listdir("./cogs"):
      if filename.endswith(".py"):
        try:
          await bot.load_extension(f"cogs.{filename[:-3]}")
          print(f"📦 تم تحميل النظام المضاف: {filename[:-3]}")
        except Exception as e:
          print(f"❌ فشل تحميل النظام {filename[:-3]}: {e}")
  else:
    print("⚠️ مجلد cogs غير موجود، سيتم إنشاؤه لإضافة الأنظمة الجديدة لاحقاً.")


@bot.tree.command(
    name="language", description="تغيير لغة ردود وبوتات السيرفر"
)
@app_commands.describe(lang="اختر اللغة المفضلة / Select your preferred language")
@app_commands.choices(lang=[
    app_commands.Choice(name="العربية (Arabic)", value="ar"),
    app_commands.Choice(name="English (الإنجليزية)", value="en")
])
@app_commands.checks.has_permissions(manage_guild=True)
async def language_command(interaction: discord.Interaction, lang: app_commands.Choice[str]):
  guild_id = interaction.guild.id
  settings = database.get_settings(guild_id)
  settings["language"] = lang.value
  database.save_settings(guild_id, settings)

  if lang.value == "en":
    await interaction.response.send_message("✅ Successfully changed the bot response language to **English**!", ephemeral=True)
  else:
    await interaction.response.send_message("✅ تم تغيير لغة ردود البوت إلى **العربية** بنجاح!", ephemeral=True)


@bot.tree.command(
    name="setup",
    description="الانتقال إلى صفحة سيرفراتك في لوحة التحكم",
)
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.checks.cooldown(1, 5.0)
async def setup(interaction: discord.Interaction):
  user_id = str(interaction.user.id)
  lang = get_guild_lang(interaction.guild.id)

  base_url = os.getenv("DASHBOARD_URL", "").rstrip("/")
  if not base_url:
    guilds_link = f"https://{os.getenv('RENDER_SERVICE_NAME', 'app')}.onrender.com/guilds?user_id={user_id}"
  else:
    guilds_link = f"{base_url}/guilds?user_id={user_id}"

  view = discord.ui.View()
  button = discord.ui.Button(
      label="View My Servers ⚙️" if lang == "en" else "عرض سيرفراتي ⚙️",
      url=guilds_link,
      style=discord.ButtonStyle.link,
  )
  view.add_item(button)

  if lang == "en":
    embed = discord.Embed(
        title="🛠️ Bot Control Panel",
        description="Welcome! You can manage all your servers where you have management permissions by clicking the button below:",
        color=discord.Color.blue(),
    )
  else:
    embed = discord.Embed(
        title="🛠️ لوحة تحكم البوت",
        description="مرحباً بك! يمكنك إدارة جميع سيرفراتك التي تمتلك صلاحية إدارتها عبر الضغط على الزر أدناه:",
        color=discord.Color.blue(),
    )

  await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.event
async def on_member_join(member):
  settings = database.get_settings(member.guild.id)
  if not settings:
    return

  # 1. إعطاء الرول التلقائي إن وجد
  if settings.get("auto_role"):
    role = discord.utils.get(member.guild.roles, name=settings["auto_role"])
    if role:
      try:
        await member.add_roles(role)
      except Exception as e:
        print(f"تعذر إعطاء الرول: {e}")

  # 2. تغيير اللقب التلقائي إن وجد
  auto_nick = settings.get("auto_nickname", "").strip()
  if auto_nick:
    try:
      if "{user}" in auto_nick:
        new_nick = auto_nick.replace("{user}", member.display_name)
      else:
        new_nick = f"{auto_nick} {member.display_name}"

      await member.edit(nick=new_nick[:32])
    except Exception as e:
      print(f"تعذر تغيير اللقب: {e}")

  # 3. إرسال بطاقة الترحيب التفاعلية المتطورة في القناة المخصصة (إن وجدت)
  welcome_channel_id = settings.get("welcome_channel") or settings.get("farewell_channel")
  if welcome_channel_id and str(welcome_channel_id).isdigit():
    channel = member.guild.get_channel(int(welcome_channel_id))
    if channel:
      bg_url = settings.get("welcome_img") or settings.get("farewell_img")
      lang = settings.get("language", "ar")
      
      # تمرير اللغة لدالة إنشاء البطاقة
      card_file = await generate_welcome_card(member, bg_url, lang=lang)
      if card_file:
        custom_msg = settings.get("welcome_msg", "")
        if custom_msg:
          welcome_text = custom_msg.replace("{user}", member.mention).replace("{server}", member.guild.name)
        else:
          welcome_text = f"Welcome {member.mention} to **{member.guild.name}**! 🎉" if lang == "en" else f"أهلاً بك يا {member.mention} في سيرفر **{member.guild.name}**! 🎉"
        await channel.send(content=welcome_text, file=card_file)


@bot.event
async def on_member_remove(member):
  settings = database.get_settings(member.guild.id)
  if not settings or not settings.get("farewell_enabled", True) or not settings.get("farewell_channel"):
    return

  channel = (
      member.guild.get_channel(int(settings["farewell_channel"]))
      if settings["farewell_channel"].isdigit()
      else discord.utils.get(
          member.guild.text_channels, name=settings["farewell_channel"]
      )
  )

  if channel:
    lang = settings.get("language", "ar")
    default_title = "Goodbye" if lang == "en" else "وداعاً"
    embed = discord.Embed(
        title=settings.get("farewell_title", default_title),
        description=settings.get("farewell_desc", "").replace(
            "{user}", member.mention
        ),
        color=discord.Color.red(),
    )
    if settings.get("farewell_img"):
      embed.set_image(url=settings["farewell_img"])

    view = None
    action = settings.get("farewell_action")
    if action in ["ban", "timeout"]:

      class FarewellView(discord.ui.View):

        @discord.ui.button(
            label=f"Apply {action.upper()}" if lang == "en" else f"تطبيق {action.upper()}", style=discord.ButtonStyle.danger
        )
        async def btn_callback(self, interaction, button):
          if action == "ban":
            await member.ban(reason="Farewell button action" if lang == "en" else "عن طريق زر الوداع")
            msg = "Member banned." if lang == "en" else "تم حظر العضو."
            await interaction.response.send_message(msg, ephemeral=True)
          elif action == "timeout":
            await member.timeout(
                timedelta(minutes=10), reason="Farewell button action" if lang == "en" else "عن طريق زر الوداع"
            )
            msg = "Member timed out." if lang == "en" else "تم إعطاء تايم أوت."
            await interaction.response.send_message(msg, ephemeral=True)

      view = FarewellView()

    await channel.send(embed=embed, view=view)


@bot.event
async def on_message(message):
  if message.author.bot or not message.guild:
    return

  settings = database.get_settings(message.guild.id)
  if not settings:
    await bot.process_commands(message)
    return

  lang = settings.get("language", "ar")

  if settings.get("xp_enabled", 1) == 1:
    xp_gain = settings.get("xp_per_message", 15)
    if hasattr(database, "add_user_xp"):
      new_level, leveled_up = database.add_user_xp(
          message.guild.id, message.author.id, xp_gain
      )
      if leveled_up:
        try:
          if lang == "en":
            await message.channel.send(f"🎉 Congratulations {message.author.mention}! You leveled up to **{new_level}** 🚀")
          else:
            await message.channel.send(f"🎉 مبروك {message.author.mention}! لقد ترقيت إلى المستوى **{new_level}** 🚀")

          role_id_to_give = None
          if new_level == 5:
            role_id_to_give = settings.get("xp_role_5")
          elif new_level == 10:
            role_id_to_give = settings.get("xp_role_10")
          elif new_level == 20:
            role_id_to_give = settings.get("xp_role_20")

          if role_id_to_give and role_id_to_give.isdigit():
            target_role = message.guild.get_role(int(role_id_to_give))
            if target_role:
              await message.author.add_roles(target_role)
              if lang == "en":
                await message.channel.send(f"🎁 You received the role: **{target_role.name}**!")
              else:
                await message.channel.send(f"🎁 لقد حصلت على رول التميز: **{target_role.name}**!")
        except Exception as e:
          print(f"خطأ في منح رول المستوى: {e}")

  if settings.get("media_enabled", True):
    media_channels = settings.get("media_channels", [])
    if (
        str(message.channel.id) in media_channels
        or message.channel.name in media_channels
    ):
      has_media = len(message.attachments) > 0 or any(
          ext in message.content.lower()
          for ext in [".jpg", ".png", ".gif", ".mp4", "http://", "https://"]
      )
      if not has_media:
        await message.delete()
        default_warn = "Sorry, this channel is for media only!" if lang == "en" else "عذراً هذه القناة للميديا فقط!"
        warn_msg = settings.get("media_warning", default_warn).replace("{user}", message.author.mention)
        await message.channel.send(warn_msg, delete_after=5)
        return

  if settings.get("banned_enabled", True):
    banned_words = settings.get("banned_words", [])
    msg_content = message.content.lower()
    if any(word in msg_content for word in banned_words):
      await message.delete()

      g_id = str(message.guild.id)
      u_id = str(message.author.id)
      violations.setdefault(g_id, {}).setdefault(u_id, 0)
      violations[g_id][u_id] += 1

      count = violations[g_id][u_id]
      max_v = settings.get("max_violations", 3)

      if count < max_v:
        default_title = "Warning" if lang == "en" else "تحذير"
        title = settings.get("warning_title", default_title)
        msg_text = (
            settings.get("warning_msg_1")
            if count == 1
            else settings.get("warning_msg_2")
        )
        if not msg_text:
          msg_text = "Please follow the rules!" if lang == "en" else "يرجى الالتزام بالقوانين!"
        msg_text = msg_text.replace("{user}", message.author.mention)
        embed = discord.Embed(
            title=title, description=msg_text, color=discord.Color.gold()
        )
        await message.channel.send(embed=embed)
      else:
        p_type = settings.get("punishment_type", "timeout")
        t_min = settings.get("timeout_minutes", 10)
        try:
          if p_type == "timeout":
            await message.author.timeout(
                timedelta(minutes=t_min), reason="Rule violation" if lang == "en" else "مخالفة القوانين"
            )
          elif p_type == "kick":
            await message.author.kick(reason="Rule violation" if lang == "en" else "مخالفة القوانين")
          elif p_type == "mute":
            await message.author.timeout(timedelta(days=7), reason="Full mute" if lang == "en" else "كتم كامل")
          
          punishment_msg = f"Applied ({p_type}) to {message.author.mention}." if lang == "en" else f"تم تطبيق ({p_type}) على {message.author.mention}."
          await message.channel.send(punishment_msg)
        except Exception as e:
          print(f"خطأ في العقوبة: {e}")
        violations[g_id][u_id] = 0
      return

  auto_resp = settings.get("auto_responses", {})
  msg_content = message.content.lower()
  if msg_content in auto_resp:
    await message.channel.send(auto_resp[msg_content])
    return

  await bot.process_commands(message)


@bot.command(name="sync")
async def sync_commands(ctx):
  if ctx.author.id != OWNER_ID:
    await ctx.send("عذراً! هذا الأمر مخصص لصاحب البوت فقط.")
    return

  msg = await ctx.send("جاري مزامنة أوامر السلاش عالمياً...")

  try:
    synced = await bot.tree.sync()
    await msg.edit(
        content=f"تمت مزامنة {len(synced)} أمر سلاش بنجاح على مستوى العالم!"
    )
  except Exception as e:
    await msg.edit(content=f"حدث خطأ أثناء المزامنة: {e}")


@bot.tree.command(
    name="userinfo", description="عرض معلومات تفصيلية عن عضويتك أو عضو آخر"
)
@app_commands.describe(member="العضو المراد عرض معلوماته (اختياري)")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
async def userinfo(
    interaction: discord.Interaction, member: discord.Member = None
):
  target = member or interaction.user
  lang = get_guild_lang(interaction.guild.id)

  if lang == "en":
    embed = discord.Embed(title=f"User Info: {target.display_name}", color=discord.Color.blue())
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Name:", value=target.name, inline=True)
    embed.add_field(name="ID:", value=target.id, inline=True)
    embed.add_field(name="Account Created:", value=target.created_at.strftime("%Y-%m-%d"), inline=False)
    embed.add_field(name="Server Joined:", value=target.joined_at.strftime("%Y-%m-%d"), inline=False)
    embed.add_field(name="Top Role:", value=target.top_role.mention, inline=True)
  else:
    embed = discord.Embed(title=f"معلومات العضو: {target.display_name}", color=discord.Color.blue())
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="الاسم:", value=target.name, inline=True)
    embed.add_field(name="المعرف (ID):", value=target.id, inline=True)
    embed.add_field(name="تاريخ إنشاء الحساب:", value=target.created_at.strftime("%Y-%m-%d"), inline=False)
    embed.add_field(name="تاريخ الانضمام للسيرفر:", value=target.joined_at.strftime("%Y-%m-%d"), inline=False)
    embed.add_field(name="أعلى رول:", value=target.top_role.mention, inline=True)

  await interaction.response.send_message(embed=embed)


@bot.tree.command(name="serverinfo", description="عرض معلومات وإحصائيات هذا السيرفر")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.checks.cooldown(1, 10.0, key=lambda i: (i.guild_id, i.user.id))
async def serverinfo(interaction: discord.Interaction):
  guild = interaction.guild
  lang = get_guild_lang(guild.id)

  if lang == "en":
    embed = discord.Embed(title=f"Statistics for {guild.name}", color=discord.Color.purple())
    if guild.icon:
      embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="Server ID:", value=guild.id, inline=True)
    embed.add_field(name="Server Owner:", value=f"<@{guild.owner_id}>", inline=True)
    embed.add_field(name="Total Members:", value=guild.member_count, inline=True)
    embed.add_field(name="Channels Count:", value=len(guild.channels), inline=True)
    embed.add_field(name="Roles Count:", value=len(guild.roles), inline=True)
    embed.add_field(name="Creation Date:", value=guild.created_at.strftime("%Y-%m-%d"), inline=False)
  else:
    embed = discord.Embed(title=f"إحصائيات {guild.name}", color=discord.Color.purple())
    if guild.icon:
      embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="معرف السيرفر (ID):", value=guild.id, inline=True)
    embed.add_field(name="مالك السيرفر:", value=f"<@{guild.owner_id}>", inline=True)
    embed.add_field(name="عدد الأعضاء الإجمالي:", value=guild.member_count, inline=True)
    embed.add_field(name="عدد القنوات:", value=len(guild.channels), inline=True)
    embed.add_field(name="عدد الرولات:", value=len(guild.roles), inline=True)
    embed.add_field(name="تاريخ الإنشاء:", value=guild.created_at.strftime("%Y-%m-%d"), inline=False)

  await interaction.response.send_message(embed=embed)


@bot.tree.command(
    name="clear", description="حذف عدد معين من الرسائل من القناة الحالية"
)
@app_commands.describe(
    amount="عدد الرسائل المراد مسحها (1 - 100)",
    member="تحديد عضو معين لتنظيف رسائله فقط (اختياري)",
)
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
async def clear(
    interaction: discord.Interaction, amount: int, member: discord.Member = None
):
  lang = get_guild_lang(interaction.guild.id)

  if amount < 1 or amount > 100:
    msg = "Please enter a number between 1 and 100." if lang == "en" else "يرجى إدخال رقم بين 1 و 100."
    await interaction.response.send_message(msg, ephemeral=True)
    return

  await interaction.response.defer(ephemeral=True)

  def check(msg):
    return msg.author == member if member else True

  deleted = await interaction.channel.purge(limit=amount, check=check)
  success_msg = f"Successfully cleared {len(deleted)} messages." if lang == "en" else f"تم مسح {len(deleted)} رسالة بنجاح."
  await interaction.followup.send(success_msg, ephemeral=True)


@bot.tree.command(name="ping", description="عرض سرعة اتصال البوت واستجابته")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
async def ping(interaction: discord.Interaction):
  latency = round(bot.latency * 1000)
  lang = get_guild_lang(interaction.guild.id)

  if lang == "en":
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Bot Latency: **{latency} ms**",
        color=discord.Color.green() if latency < 150 else discord.Color.red(),
    )
  else:
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"سرعة استجابة البوت (Latency): **{latency} ms**",
        color=discord.Color.green() if latency < 150 else discord.Color.red(),
    )
  await interaction.response.send_message(embed=embed)


@bot.tree.command(name="botinfo", description="عرض معلومات البوت ورابط التصويت")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
async def botinfo(interaction: discord.Interaction):
  total_guilds = len(bot.guilds)
  total_users = sum(g.member_count for g in bot.guilds)
  lang = get_guild_lang(interaction.guild.id)

  if lang == "en":
    embed = discord.Embed(
        title="Bot Information & Support",
        description="Thanks for using the bot! You can support and rate us on Top.gg.",
        color=discord.Color.gold(),
    )
    embed.add_field(name="Serving Servers:", value=f"{total_guilds} servers", inline=True)
    embed.add_field(name="Total Users:", value=f"{total_users} members", inline=True)
    btn_label = "Support Bot on Top.gg"
  else:
    embed = discord.Embed(
        title="معلومات البوت ورابط الدعم",
        description="شكراً لاستخدامك البوت! يمكنك دعمنا وتقييمنا على منصة Top.gg.",
        color=discord.Color.gold(),
    )
    embed.add_field(name="السيرفرات الخادمة:", value=f"{total_guilds} سيرفر", inline=True)
    embed.add_field(name="إجمالي المستخدمين:", value=f"{total_users} عضو", inline=True)
    btn_label = "دعم البوت على Top.gg"

  view = discord.ui.View()
  view.add_item(
      discord.ui.Button(
          label=btn_label,
          url="https://top.gg",
          style=discord.ButtonStyle.link,
      )
  )

  await interaction.response.send_message(embed=embed, view=view)


class CloseTicketView(discord.ui.View):

  def __init__(self, lang="ar"):
    super().__init__(timeout=None)
    self.lang = lang
    self.children[0].label = "Close Ticket 🔒" if lang == "en" else "إغلاق التذكرة 🔒"

  @discord.ui.button(
      label="إغلاق التذكرة 🔒",
      style=discord.ButtonStyle.red,
      custom_id="close_ticket_btn",
  )
  async def close_ticket(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    lang = get_guild_lang(interaction.guild.id)
    closing_msg = "Closing channel..." if lang == "en" else "جاري إغلاق القناة..."
    await interaction.response.send_message(closing_msg, ephemeral=True)
    try:
      await interaction.channel.delete()
    except:
      pass


class TicketButtonView(discord.ui.View):

  def __init__(self, lang="ar"):
    super().__init__(timeout=None)
    self.lang = lang
    self.children[0].label = "Open Ticket 🎫" if lang == "en" else "فتح تذكرة 🎫"

  @discord.ui.button(
      label="فتح تذكرة 🎫",
      style=discord.ButtonStyle.green,
      custom_id="create_ticket_btn",
  )
  async def create_ticket(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    settings = database.get_settings(guild.id)
    lang = settings.get("language", "ar")
    cat_id = settings.get("ticket_category")
    support_role_id = settings.get("ticket_support_role")

    category = (
        guild.get_channel(int(cat_id)) if cat_id and cat_id.isdigit() else None
    )
    support_role = (
        guild.get_role(int(support_role_id))
        if support_role_id and support_role_id.isdigit()
        else None
    )

    existing_channel = discord.utils.get(
        guild.text_channels, name=f"ticket-{interaction.user.name.lower()}"
    )
    if existing_channel:
      msg = f"You already have an open ticket here: {existing_channel.mention}" if lang == "en" else f"لديك تذكرة مفتوحة بالفعل هنا: {existing_channel.mention}"
      await interaction.followup.send(msg, ephemeral=True)
      return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True
        ),
    }
    if support_role:
      overwrites[support_role] = discord.PermissionOverwrite(
          view_channel=True, send_messages=True, read_message_history=True
      )

    channel_name = f"ticket-{interaction.user.name}"
    try:
      ticket_chan = await guild.create_text_channel(
          channel_name, category=category, overwrites=overwrites
      )

      if lang == "en":
        embed = discord.Embed(
            title="🎫 New Support Ticket",
            description=f"Welcome {interaction.user.mention}, please describe your issue and support staff will reply soon.",
            color=0x6366f1,
        )
      else:
        embed = discord.Embed(
            title="🎫 تذكرة دعم فني جديدة",
            description=f"مرحباً {interaction.user.mention}، يرجى كتابة مشكلتك وسيتم الرد عليك قريباً من قبل فريق الدعم.",
            color=0x6366f1,
        )

      await ticket_chan.send(
          content=interaction.user.mention,
          embed=embed,
          view=CloseTicketView(lang=lang),
      )
      success_msg = f"Ticket created successfully: {ticket_chan.mention}" if lang == "en" else f"تم إنشاء تذكرتك بنجاح: {ticket_chan.mention}"
      await interaction.followup.send(success_msg, ephemeral=True)
    except Exception as e:
      err_msg = "An error occurred while creating the ticket, please check bot permissions." if lang == "en" else "حدث خطأ أثناء إنشاء التذكرة، يرجى التحقق من صلاحيات البوت."
      await interaction.followup.send(err_msg, ephemeral=True)


@bot.tree.command(
    name="ticket-setup", description="إرسال لوحة إنشاء التذاكر في القناة الحالية"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_setup(interaction: discord.Interaction):
  lang = get_guild_lang(interaction.guild.id)
  if lang == "en":
    embed = discord.Embed(
        title="🎫 Ticket & Support System",
        description="Click the button below to open a new ticket and contact staff.",
        color=0xa855f7,
    )
    sent_msg = "Ticket panel sent successfully!"
  else:
    embed = discord.Embed(
        title="🎫 نظام التذاكر والدعم الفني",
        description="اضغط على الزر بالأسفل لفتح تذكرة جديدة والتواصل مع الإدارة.",
        color=0xa855f7,
    )
    sent_msg = "تم إرسال لوحة التذاكر بنجاح!"

  await interaction.channel.send(embed=embed, view=TicketButtonView(lang=lang))
  await interaction.response.send_message(sent_msg, ephemeral=True)


@bot.tree.command(name="level", description="عرض مستواك الحالي ونقاط الخبرة XP")
@app_commands.describe(member="العضو المراد عرض مستواه (اختياري)")
async def level_command(
    interaction: discord.Interaction, member: discord.Member = None
):
  target = member or interaction.user
  lang = get_guild_lang(interaction.guild.id)

  if hasattr(database, "get_user_level"):
    xp, lvl = database.get_user_level(interaction.guild.id, target.id)
  else:
    xp, lvl = 0, 1

  next_xp = lvl * 100 + 100

  if lang == "en":
    embed = discord.Embed(title=f"📊 User Rank: {target.name}", color=discord.Color.pink())
    embed.add_field(name="Level", value=str(lvl), inline=True)
    embed.add_field(name="XP Points", value=f"{xp} / {next_xp}", inline=True)
  else:
    embed = discord.Embed(title=f"📊 رتبة العضو {target.name}", color=discord.Color.pink())
    embed.add_field(name="المستوى", value=str(lvl), inline=True)
    embed.add_field(name="نقاط الخبرة (XP)", value=f"{xp} / {next_xp}", inline=True)

  embed.set_thumbnail(url=target.display_avatar.url)
  await interaction.response.send_message(embed=embed)


@bot.tree.command(
    name="leaderboard", description="عرض قائمة أكثر الأعضاء تفاعلاً ونقاطاً XP"
)
@app_commands.checks.cooldown(1, 10.0, key=lambda i: (i.guild_id, i.user.id))
async def leaderboard(interaction: discord.Interaction):
  guild_id = interaction.guild.id
  lang = get_guild_lang(guild_id)

  top_users = (
      database.get_top_users(guild_id, limit=10)
      if hasattr(database, "get_top_users")
      else []
  )

  if lang == "en":
    embed = discord.Embed(
        title=f"🏆 Leaderboard for {interaction.guild.name}",
        description="Most active members with the highest XP points:",
        color=discord.Color.gold(),
    )
  else:
    embed = discord.Embed(
        title=f"🏆 قائمة المتصدرين في {interaction.guild.name}",
        description="أكثر الأعضاء تفاعلاً وحصولاً على نقاط الخبرة (XP):",
        color=discord.Color.gold(),
    )

  if not top_users:
    no_data_name = "No data yet" if lang == "en" else "لا توجد بيانات بعد"
    no_data_val = "Start sending messages to be on top!" if lang == "en" else "ابدأ بإرسال الرسائل لتكون أول المتصدرين!"
    embed.add_field(name=no_data_name, value=no_data_val, inline=False)
  else:
    desc_list = []
    for index, (uid, xp, lvl) in enumerate(top_users, start=1):
      member = interaction.guild.get_member(int(uid))
      name = member.mention if member else (f"Left user ({uid})" if lang == "en" else f"مستخدم مغادر ({uid})")
      medal = (
          "🥇"
          if index == 1
          else "🥈"
          if index == 2
          else "🥉"
          if index == 3
          else f"**#{index}**"
      )
      lvl_text = "Level" if lang == "en" else "المستوى"
      desc_list.append(f"{medal} {name} — {lvl_text}: **{lvl}** (`{xp} XP`)")
    embed.description = "\n".join(desc_list)

  if interaction.guild.icon:
    embed.set_thumbnail(url=interaction.guild.icon.url)

  await interaction.response.send_message(embed=embed)


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
  lang = get_guild_lang(interaction.guild_id) if interaction.guild_id else "ar"

  if isinstance(error, app_commands.MissingPermissions):
    if lang == "en":
      msg = "❌ **Sorry! This command is only for members with (Manage Server) permission.**"
    else:
      msg = "❌ **عذراً! هذا الأمر مخصص فقط للأعضاء الذين يمتلكون صلاحية (إدارة السيرفر - Manage Server).**"

    if not interaction.response.is_done():
      await interaction.response.send_message(msg, ephemeral=True)
    else:
      await interaction.followup.send(msg, ephemeral=True)
  elif isinstance(error, app_commands.CommandOnCooldown):
    if lang == "en":
      msg = f"⏳ Please wait! You can use this command again in {round(error.retry_after, 1)} seconds."
    else:
      msg = f"⏳ انتظر قليلاً! يمكنك استخدام الأمر مجدداً بعد {round(error.retry_after, 1)} ثانية."

    if not interaction.response.is_done():
      await interaction.response.send_message(msg, ephemeral=True)
    else:
      await interaction.followup.send(msg, ephemeral=True)
  else:
    msg = "An unexpected error occurred while executing the command." if lang == "en" else "حدث خطأ غير متوقع أثناء تنفيذ الأمر."
    if not interaction.response.is_done():
      await interaction.response.send_message(msg, ephemeral=True)
    else:
      await interaction.followup.send(msg, ephemeral=True)


TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
