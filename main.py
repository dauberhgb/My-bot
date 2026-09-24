import static_ffmpeg
static_ffmpeg.add_paths()

import time
from datetime import timedelta
from functools import wraps
import json
import os
import threading
import database
from discord import app_commands
from discord.ext import commands
import discord
import requests
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import aiohttp
from aiohttp_socks import ProxyConnector
import shutil

# استيراد مكتبات تشكيل النصوص العربية للرسم على الصور
import arabic_reshaper
from bidi.algorithm import get_display

# استيراد نظام الترجمات ودالة الترجمة
from translations import _

# ==========================================
# 1. إعداد وتشغيل بوت ديسكورد
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
violations = {}

# معرف حسابك في ديسكورد (User ID)
OWNER_ID = 1462429084377157832

# ==========================================
# 2. إعداد خادم الويب (Flask Dashboard مع Discord OAuth2)
# ==========================================
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "A_VERY_SECRET_KEY_FOR_SESSIONS_12345")

# إعدادات ديسكورد OAuth2 (تأكد من إضافتها في متغيرات البيئة Environment Variables)
CLIENT_ID = os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
# ضع رابط الـ Callback الخاص بموقعك هنا أو اجعله يعتمده تلقائياً
REDIRECT_URI = os.getenv("REDIRECT_URI", "")


def get_base_url():
  base_url = os.getenv("DASHBOARD_URL", "").rstrip("/")
  if not base_url:
    return f"https://{os.getenv('RENDER_SERVICE_NAME', 'app')}.onrender.com"
  return base_url


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

    # 1. التحقق عبر الـ Session (لوحة الويب)
    admin_guilds = session.get("admin_guilds", [])
    user_id = session.get("user_id")

    # 2. التحقق عبر الـ Request parameters (إن وجدت)
    req_user_id = (
        request.args.get("user_id")
        or request.headers.get("X-User-ID")
        or request.form.get("user_id")
    )
    if req_user_id and req_user_id.isdigit():
      user_id = req_user_id

    is_authorized = False
    if user_id:
      u_id = int(user_id)
      member = guild.get_member(u_id)
      
      if u_id == OWNER_ID or u_id == guild.owner_id:
        is_authorized = True
      elif str(guild_id) in admin_guilds:
        is_authorized = True
      elif member and (member.guild_permissions.administrator or member.guild_permissions.manage_guild):
        is_authorized = True

    if not is_authorized:
      if request.path.startswith("/save/"):
        return (
            jsonify({
                "status": "error",
                "message": (
                    "عذراً، لا تملك صلاحية (إدارة السيرفر) للقيام بهذا الإجراء!"
                ),
            }),
            403,
        )
      return (
          "عذراً، يجب تسجيل الدخول وامتلاك صلاحية إدارة السيرفر للدخول إلى هذه اللوحة!",
          403,
      )

    return f(guild_id, *args, **kwargs)

  return decorated_function


@app.route("/login")
def login():
  base_url = get_base_url()
  redirect_uri = REDIRECT_URI or f"{base_url}/auth/callback"
  discord_login_url = (
      f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}"
      f"&redirect_uri={requests.utils.quote(redirect_uri, safe='')}"
      "&response_type=code&scope=identify+guilds"
  )
  return redirect(discord_login_url)


@app.route("/auth/callback")
def auth_callback():
  code = request.args.get("code")
  if not code:
    return "فشل تسجيل الدخول: لم يتم استلام رمز المصادقة.", 400

  base_url = get_base_url()
  redirect_uri = REDIRECT_URI or f"{base_url}/auth/callback"

  token_data = {
      "client_id": CLIENT_ID,
      "client_secret": CLIENT_SECRET,
      "grant_type": "authorization_code",
      "code": code,
      "redirect_uri": redirect_uri,
  }
  headers = {"Content-Type": "application/x-www-form-urlencoded"}

  try:
    r = requests.post(
        "https://discord.com/api/oauth2/token", data=token_data, headers=headers
    )
    res_json = r.json()
    access_token = res_json.get("access_token")
    if not access_token:
      return "فشل جلب رمز الوصول من ديسكورد.", 400

    user_headers = {"Authorization": f"Bearer {access_token}"}
    
    # جلب معلومات المستخدم
    user_res = requests.get(
        "https://discord.com/api/users/@me", headers=user_headers
    )
    user_data = user_res.json()
    session["user_id"] = str(user_data.get("id"))

    # جلب سيرفرات المستخدم
    guilds_res = requests.get(
        "https://discord.com/api/users/@me/guilds", headers=user_headers
    )
    guilds = guilds_res.json()

    admin_guilds = []
    for guild in guilds:
      permissions = int(guild.get("permissions", 0))
      # التحقق من صلاحية الإدارة (Administrator = 0x8) أو مالك السيرفر
      if guild.get("owner") or (permissions & 0x8) == 0x8:
        admin_guilds.append(str(guild.get("id")))

    session["admin_guilds"] = admin_guilds
    return redirect(url_for("guild_list"))
  except Exception as e:
    return f"حدث خطأ أثناء المصادقة: {e}", 500

# دالة مساعدة لجلب لغة السيرفر
def get_guild_lang(guild_id):
  if not guild_id:
    return "ar"
  settings = database.get_settings(guild_id)
  return settings.get("language", "ar")


@app.route("/")
def home():
  if "user_id" in session:
    return redirect(url_for("guild_list"))
  return redirect(url_for("login"))


@app.route("/guilds")
def guild_list():
  user_id = session.get("user_id")
  if not user_id:
    return redirect(url_for("login"))

  admin_guilds = session.get("admin_guilds", [])
  bot_guilds = []
  current_lang = "ar"

  for guild in bot.guilds:
    # 🛠️ التعديل هنا: يتم عرض السيرفر فقط إذا كان البوت موجوداً فيه
    # وكانت آية الـ ID موجودة ضمن قائمة الـ admin_guilds (التي يملك فيها صلاحية الإدارة أو مالكها)
    if str(guild.id) in admin_guilds:
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

  user_id = session.get("user_id")
  is_admin = False
  if user_id:
    u_id = int(user_id)
    member = guild.get_member(u_id)
    if u_id == OWNER_ID or u_id == guild.owner_id:
      is_admin = True
    elif member and (member.guild_permissions.administrator or member.guild_permissions.manage_guild):
      is_admin = True
    elif str(guild_id) in session.get("admin_guilds", []):
      is_admin = True

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
  raw_welcome = str(request.form.get("welcome_enabled", "")).strip().lower()
  welcome_enabled = False if raw_welcome in ["0", "false", "off", "disabled", "معطل"] else True


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
      "language": request.form.get("language", "ar"),
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
      "welcome_frame": request.form.get("welcome_frame", ""),
      "farewell_enabled": farewell_enabled,
      "farewell_channel": request.form.get("farewell_channel", ""),
      "farewell_title": request.form.get("farewell_title", ""),
      "farewell_desc": request.form.get("farewell_desc", ""),
      "farewell_img": request.form.get("farewell_img", ""),
      "farewell_action": request.form.get("farewell_action", "none"),
      "auto_responses": auto_responses,
      "auto_role": request.form.get("auto_role", ""),
      "auto_nickname": request.form.get("auto_nickname", ""),
      "ticket_status": "enabled" if request.form.get("ticket_status") == "1" else "disabled",
      "ticket_category": request.form.get("ticket_category", ""),
      "ticket_support_role": request.form.get("ticket_support_role", ""),
      "ticket_archive_channel": request.form.get("ticket_archive_channel", ""),
      "xp_enabled": int(request.form.get("xp_enabled", 1)),
      "xp_per_message": int(request.form.get("xp_per_message", 15)),
      "xp_role_5": request.form.get("xp_role_5", ""),
      "xp_role_10": request.form.get("xp_role_10", ""),
      "xp_role_20": request.form.get("xp_role_20", ""),
      "text_1": request.form.get("text_1", ""),
      "text_2": request.form.get("text_2", ""),
      "text_3": request.form.get("text_3", ""),
      "color_1": request.form.get("color_1", "#FFFFFF"),
      "color_2": request.form.get("color_2", "#FFD700"),
      "color_3": request.form.get("color_3", "#FFFFFF"),
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
  elif isinstance(error, app_commands.CommandOnCooldown):
    remaining = round(error.retry_after, 1)
    if lang == "en":
      msg = f"⏳ Please wait! You can use this command again in {remaining} seconds."
    else:
      msg = f"⏳ انتظر قليلاً! يمكنك استخدام الأمر مجدداً بعد {remaining} ثانية."
  else:
    print(f"⚠️ خطأ غير متوقع في أمر السلاش: {error}")
    if lang == "en":
      msg = "An unexpected error occurred while executing the command."
    else:
      msg = "حدث خطأ غير متوقع أثناء تنفيذ الأمر."

  if not interaction.response.is_done():
    await interaction.response.send_message(msg, ephemeral=True)
  else:
    await interaction.followup.send(msg, ephemeral=True)


@bot.tree.command(
    name="language", description="تغيير لغة ردود وبوتات السيرفر"
)
@app_commands.describe(lang="اختر اللغة المفضلة / Select your preferred language")
@app_commands.choices(lang=[
    app_commands.Choice(name="العربية (Arabic)", value="ar"),
    app_commands.Choice(name="English (الإنجليزية)", value="en")
])
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
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
    description="الانتقال إلى لوحة التحكم الآمنة",
)
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
async def setup(interaction: discord.Interaction):
  lang = get_guild_lang(interaction.guild.id)
  base_url = get_base_url()
  login_link = f"{base_url}/login"

  view = discord.ui.View()
  button = discord.ui.Button(
      label="Open Control Panel ⚙️" if lang == "en" else "فتح لوحة التحكم ⚙️",
      url=login_link,
      style=discord.ButtonStyle.link,
  )
  view.add_item(button)

  if lang == "en":
    embed = discord.Embed(
        title="🛠️ Bot Control Panel",
        description="Click the button below to log in securely with Discord and manage your servers:",
        color=discord.Color.blue(),
    )
  else:
    embed = discord.Embed(
        title="🛠️ لوحة تحكم البوت",
        description="اضغط على الزر أدناه لتسجيل الدخول بأمان عبر ديسكورد وإدارة سيرفراتك:",
        color=discord.Color.blue(),
    )

  await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.event
async def on_guild_join(guild):
    owner = bot.get_user(OWNER_ID)
    if not owner:
        try:
            owner = await bot.fetch_user(OWNER_ID)
        except Exception as e:
            print(f"❌ تعذر جلب صاحب البوت: {e}")
            return

    if owner:
        embed = discord.Embed(
            title="📥 تم إضافة البوت إلى سيرفر جديد!",
            description=f"**اسم السيرفر:** {guild.name}\n**أيدي السيرفر:** `{guild.id}`\n**عدد الأعضاء:** `{guild.member_count}`",
            color=discord.Color.green()
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        try:
            await owner.send(embed=embed)
        except Exception as e:
            print(f"❌ تعذر إرسال إشعار الانضمام في الخاص: {e}")
            

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
  if message.author.bot:
    return
  if message.guild is None:
    await bot.process_commands(message)
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

    # إرسال الرسالة لنظام الشبكات في cogs وتفعيل الأوامر
    network_cog = bot.get_cog("NetworkCog")
    if network_cog:
        await network_cog.on_message(message)

    await bot.process_commands(message)


@bot.command(name="sync")
async def sync_commands(ctx):
    if ctx.author.id != OWNER_ID:
        await ctx.send("⚠️ عذراً! هذا الأمر مخصص لصاحب البوت فقط.")
        return

    msg = await ctx.send("⏳ جاري مسح الأوامر القديمة وإعادة مزامنة أوامر الكود...")
    try:
        # 1. مسح أوامر السيرفر المحلية السابقة إن وجدت
        bot.tree.clear_commands(guild=ctx.guild)
        await bot.tree.sync(guild=ctx.guild)

        # 2. مزامنة الأوامر العامة الحالية مباشرة بدون تفريغ الشجرة كودياً
        synced = await bot.tree.sync()

        await msg.edit(content=f"✅ تم تنظيف ديسكورد ومزامنة **{len(synced)}** أمر سلاش بنجاح!")
    except Exception as e:
        await msg.edit(content=f"❌ حدث خطأ أثناء المزامنة: {e}")
        

@bot.command(name="servers")
async def list_servers(ctx):
    # التأكد أن المستخدم هو صاحب البوت فقط
    if ctx.author.id != OWNER_ID:
        return  # يتجاهل الأمر كلياً كأن البوت لا يستجيب للآخرين

    servers_list = []
    for guild in bot.guilds:
        servers_list.append(f"• **{guild.name}** (`{guild.id}`) - الأعضاء: `{guild.member_count}`")
    
    desc = "\n".join(servers_list) if servers_list else "لا توجد سيرفرات مرتبطة."
    
    embed = discord.Embed(
        title=f"📊 السيرفرات المرتبطة بالبوت ({len(bot.guilds)})",
        description=desc,
        color=discord.Color.blue()
    )
    
    try:
        # إرسال القائمة في رسالتك الخاصة (DM) للحفاظ على السرية التامة
        await ctx.author.send(embed=embed)
        # حذف رسالتك الأصلية من الشات حتى لا يلاحظ أحد أنك كتبت شيئاً
        if ctx.guild:
            await ctx.message.delete()
    except Exception as e:
        await ctx.send(embed=embed, delete_after=10)
        

@bot.tree.command(name="userinfo", description="عرض معلومات تفصيلية عن عضويتك أو عضو آخر")
@app_commands.describe(member="العضو المراد عرض معلوماته (اختياري)")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
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
    
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Support", url="https://top.gg/discord/servers/876867145879965696?s=03defad4113ee", emoji="🛠️"))
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
    
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="دعم", url="https://top.gg/discord/servers/876867145879965696?s=03defad4113ee", emoji="🛠️"))

  await interaction.response.send_message(embed=embed, view=view)


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
          url="https://top.gg/discord/servers/876867145879965696?s=0cb418225bcb1",
          style=discord.ButtonStyle.link,
      )
  )

  await interaction.response.send_message(embed=embed, view=view)

# ==========================================
# ضع دالة /help الجديدة هنا مباشرةً
# ==========================================
@bot.tree.command(name="help", description="عرض دليل الإرشادات والتعليمات لاستخدام البوت والأوامر والشبكات")
@app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
async def help_command(interaction: discord.Interaction):
  lang = get_guild_lang(interaction.guild.id)
  
  view = discord.ui.View()

  if lang == "en":
    embed = discord.Embed(
        title="📖 Bot Setup & Usage Guide",
        description=(
            "Welcome to the bot manual! Here is everything you need to know"
            " about slash commands and server networking."
        ),
        color=discord.Color.blue(),
    )

    embed.add_field(
        name="🛠️ Dashboard & Main Commands",
        value=(
            "`/setup` — Get link to the Web Control Panel (Manage Server"
            " required).\n`/language` — Change bot response language (Arabic /"
            " English).\n`/ticket-setup` — Send support ticket creation"
            " panel.\n`/clear [amount]` — Purge 1-100 messages from current"
            " channel.\n`/userinfo` & `/serverinfo` — Show details about member"
            " or server.\n`/ping` & `/botinfo` — Bot connection speed and"
            " support info."
        ),
        inline=False,
    )

    embed.add_field(
        name="🛡️ Staff Shifts & Management",
        value=(
            "`/shift-panel` — Send shift control panel to start, pause, or end shifts.\n"
            "`/shift-log-channel` — Set the official shift logs report channel.\n"
            "`/shift-stats [member]` — View shift stats and hours for yourself or another staff member.\n"
            "`/shift-leaderboard` — Display the top staff members leaderboard based on shifts and points."
        ),
        inline=False,
    )

    embed.add_field(
        name="📊 Leveling & Leaderboard",
        value=(
            "`/level [member]` — View your current XP and level"
            " rank.\n`/leaderboard` — Display top 10 most active members."
        ),
        inline=False,
    )

    embed.add_field(
        name="🌐 Cross-Server Network Commands (Prefix: `!network`)",
        value=(
            "*(Admin Only)* Connect channels and sync messages/bans across"
            " servers:\n`!network create <name>` — Create a new network & bind"
            " current channel.\n`!network join <net_id>` — Join an existing"
            " network using its ID.\n`!network leave <net_id>` — Disconnect"
            " your server from a network.\n`!network del [net_id]` — Permanently"
            " delete a network you created."
        ),
        inline=False,
    )

    embed.add_field(
        name="💡 Quick Tips",
        value=(
            "• All Slash commands require **Manage Server** permission.\n•"
            " Network commands require **Server owner** permission.\n• When"
            " a user is banned in a network server, **Auto Global Ban** will"
            " sync the ban to all connected servers."
        ),
        inline=False,
    )
  
    # زر المساعدة باللغة الإنجليزية
    view.add_item(
        discord.ui.Button(
            label="For more information",
            url="https://discord.gg/PZcZYu8AEa",
            style=discord.ButtonStyle.link,
        )
    )
  
  else:
    embed = discord.Embed(
        title="📖 دليل الاستخدام والتعليمات الشامل",
        description=(
            "مرحباً بك في دليل البوت! تجد أدناه شرحاً مفصلاً لكيفية استخدام أوامر"
            " السلاش ونظام الشبكات بين السيرفرات."
        ),
        color=discord.Color.blue(),
    )

    embed.add_field(
        name="🛠️ لوحة التحكم والأوامر العامة (Slash Commands)",
        value=(
            "`/setup` — الحصول على رابط لوحة التحكم الخاصة بسيرفراتك.\n`/language`"
            " — تغيير لغة ردود وبوت السيرفر (عربي / إنجليزي).\n`/ticket-setup` —"
            " إرسال لوحة إنشاء التذاكر والدعم الفني.\n`/clear [العدد]` — مسح من"
            " 1 إلى 100 رسالة من القناة الحالية.\n`/userinfo` & `/serverinfo` —"
            " عرض معلومات تفصيلية عن العضو أو السيرفر.\n`/ping` & `/botinfo` —"
            " عرض سرعة الاستجابة ومعلومات الدعم."
        ),
        inline=False,
    )

    embed.add_field(
        name="🛡️ مناوبات وطاقم الإدارة",
        value=(
            "`/shift-panel` — إرسال لوحة التحكم لبدء، إيقاف مؤقت، أو إنهاء المناوبات.\n"
            "`/shift-log-channel` — تحديد قناة تقارير سجلات المناوبات الرسمية.\n"
            "`/shift-stats [member]` — عرض إحصائيات المناوبات والساعات الخاصة بك أو بمشرف آخر.\n"
            "`/shift-leaderboard` — عرض قائمة المتصدرين لأفضل المشرفين بناءً على المناوبات والنقاط."
        ),
        inline=False,
    )

    embed.add_field(
        name="📊 نظام المستويات والخبرة (XP)",
        value=(
            "`/level [العضو]` — عرض مستواك الحالي ونقاط الخبرة"
            " XP.\n`/leaderboard` — عرض قائمة أفضل 10 أعضاء تفاعلاً في السيرفر."
        ),
        inline=False,
    )

    embed.add_field(
        name="🌐 أوامر شبكة التواصل بين السيرفرات (البريفكس: `!network`)",
        value=(
            "*(للمشرفين فقط)* لربط القنوات ومزامنة الرسائل والحظر"
            " التلقائي:\n`!network create <اسم_الشبكة>` — إنشاء شبكة جديدة"
            " وربط القناة الحالية بها.\n`!network join <معرف_الشبكة>` — الانضمام"
            " لشبكة موجودة عبر الـ ID الخاص بها.\n`!network leave"
            " <معرف_الشبكة>` — مغادرة السيرفر للشبكة وإلغاء الربط.\n`!network del"
            " [معرف_الشبكة]` — حذف الشبكة بالكامل وإغلاق جميع اتصالاتها."
        ),
        inline=False,
    )

    embed.add_field(
        name="💡 ملاحظات وإرشادات مهمة",
        value=(
            "• جميع أوامر السلاش تتطلب صلاحية **إدارة السيرفر (Manage"
            " Server)**.\n• أوامر الشبكة تتطلب صلاحية **مسؤول"
            " (مالك السارفر)**.\n• نظام الحظر الشامل: عند حظر عضو في سيرفر"
            " مرتبط بشبكة، سيتم حظره تلقائياً من بقية السيرفرات المرتبطة."
        ),
        inline=False,
    )
    
    # زر المساعدة باللغة العربية
    view.add_item(
        discord.ui.Button(
            label="للمزيد من المعلومات",
            url="https://discord.gg/PZcZYu8AEa",
            style=discord.ButtonStyle.link,
        )
    )

  if interaction.guild and interaction.guild.icon:
    embed.set_thumbnail(url=interaction.guild.icon.url)

  await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

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


@bot.event
async def on_ready():
  print(f"تم تسجيل الدخول بنجاح باسم {bot.user}")
  print("🔄 بدء فحص وتحميل الأنظمة من مجلد cogs...")
  
  if os.path.exists("./cogs"):
      for filename in os.listdir("./cogs"):
          if filename.endswith(".py"):
              extension_name = f"cogs.{filename[:-3]}"
              if extension_name not in bot.extensions:
                  try:
                      await bot.load_extension(extension_name)
                      print(f"✅ تم تحميل النظام بنجاح: {filename[:-3]}")
                  except Exception as e:
                      print(f"❌ خطأ تفصيلي في تحميل {filename[:-3]}: {e}")
  else:
      print("⚠️ مجلد cogs غير موجود أصلاً!")

TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
