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
  current_lang = "ar"  # اللغة الافتراضية

  for guild in bot.guilds:
    if user_id and user_id.isdigit():
      member = guild.get_member(int(user_id))
      if member and member.guild_permissions.manage_guild:
        # أخذ لغة أول سيرفر يملكه المستخدم لتعيين لغة الواجهة الحالية
        if not bot_guilds:
          settings = database.get_settings(guild.id)
          current_lang = settings.get("language", "ar")

        bot_guilds.append({
            "id": str(guild.id),
            "name": guild.name,
            "icon": guild.icon.url if guild.icon else None,
        })
    else:
      pass

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

  # تحديد اللغة الحالية (افتراضياً العربية إذا لم يتم تحديدها)
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

  # استقبال قنوات الميديا وحالات التفعيل بشكل صحيح
  media_channels = request.form.getlist("media_channels")
  media_enabled = True if request.form.get("media_enabled") == "on" else False
  banned_enabled = True if request.form.get("banned_enabled") == "on" else False
  farewell_enabled = True if request.form.get("farewell_enabled") == "on" else False

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
# 3. أحداث وأوامر البوت (Discord Events & Commands)
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
    name="setup",
    description="الانتقال إلى صفحة سيرفراتك في لوحة التحكم",
)
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.checks.cooldown(1, 5.0)
async def setup(interaction: discord.Interaction):
  user_id = str(interaction.user.id)

  base_url = os.getenv("DASHBOARD_URL", "").rstrip("/")
  if not base_url:
    guilds_link = f"https://{os.getenv('RENDER_SERVICE_NAME', 'app')}.onrender.com/guilds?user_id={user_id}"
  else:
    guilds_link = f"{base_url}/guilds?user_id={user_id}"

  view = discord.ui.View()
  button = discord.ui.Button(
      label="عرض سيرفراتي ⚙️",
      url=guilds_link,
      style=discord.ButtonStyle.link,
  )
  view.add_item(button)

  embed = discord.Embed(
      title="🛠️ لوحة تحكم البوت",
      description=(
          "مرحباً بك! يمكنك إدارة جميع سيرفراتك التي تمتلك صلاحية إدارتها عبر الضغط على الزر أدناه:"
      ),
      color=discord.Color.blue(),
  )

  await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.event
async def on_member_join(member):
  settings = database.get_settings(member.guild.id)
  if not settings:
    return

  if settings.get("auto_role"):
    role = discord.utils.get(member.guild.roles, name=settings["auto_role"])
    if role:
      try:
        await member.add_roles(role)
      except Exception as e:
        print(f"تعذر إعطاء الرول: {e}")

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
    embed = discord.Embed(
        title=settings.get("farewell_title", "وداعاً"),
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
            label=f"تطبيق {action.upper()}", style=discord.ButtonStyle.danger
        )
        async def btn_callback(self, interaction, button):
          if action == "ban":
            await member.ban(reason="عن طريق زر الوداع")
            await interaction.response.send_message(
                "تم حظر العضو.", ephemeral=True
            )
          elif action == "timeout":
            await member.timeout(
                timedelta(minutes=10), reason="عن طريق زر الوداع"
            )
            await interaction.response.send_message(
                "تم إعطاء تايم أوت.", ephemeral=True
            )

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

  if settings.get("xp_enabled", 1) == 1:
    xp_gain = settings.get("xp_per_message", 15)
    if hasattr(database, "add_user_xp"):
      new_level, leveled_up = database.add_user_xp(
          message.guild.id, message.author.id, xp_gain
      )
      if leveled_up:
        try:
          await message.channel.send(
              f"🎉 مبروك {message.author.mention}! لقد ترقيت إلى المستوى **{new_level}** 🚀"
          )

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
              await message.channel.send(
                  f"🎁 لقد حصلت على رول التميز: **{target_role.name}**!"
              )
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
        warn_msg = settings.get(
            "media_warning", "عذراً هذه القناة للميديا فقط!"
        ).replace("{user}", message.author.mention)
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
        title = settings.get("warning_title", "تحذير")
        msg_text = (
            settings.get("warning_msg_1")
            if count == 1
            else settings.get("warning_msg_2")
        )
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
                timedelta(minutes=t_min), reason="مخالفة القوانين"
            )
          elif p_type == "kick":
            await message.author.kick(reason="مخالفة القوانين")
          elif p_type == "mute":
            await message.author.timeout(timedelta(days=7), reason="كتم كامل")
          await message.channel.send(
              f"تم تطبيق ({p_type}) على {message.author.mention}."
          )
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

  embed = discord.Embed(
      title=f"معلومات العضو: {target.display_name}", color=discord.Color.blue()
  )
  embed.set_thumbnail(url=target.display_avatar.url)
  embed.add_field(name="الاسم:", value=target.name, inline=True)
  embed.add_field(name="المعرف (ID):", value=target.id, inline=True)
  embed.add_field(
      name="تاريخ إنشاء الحساب:",
      value=target.created_at.strftime("%Y-%m-%d"),
      inline=False,
  )
  embed.add_field(
      name="تاريخ الانضمام للسيرفر:",
      value=target.joined_at.strftime("%Y-%m-%d"),
      inline=False,
  )
  embed.add_field(name="أعلى رول:", value=target.top_role.mention, inline=True)

  await interaction.response.send_message(embed=embed)


@bot.tree.command(name="serverinfo", description="عرض معلومات وإحصائيات هذا السيرفر")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.checks.cooldown(1, 10.0, key=lambda i: (i.guild_id, i.user.id))
async def serverinfo(interaction: discord.Interaction):
  guild = interaction.guild

  embed = discord.Embed(
      title=f"إحصائيات {guild.name}", color=discord.Color.purple()
  )
  if guild.icon:
    embed.set_thumbnail(url=guild.icon.url)

  embed.add_field(name="معرف السيرفر (ID):", value=guild.id, inline=True)
  embed.add_field(name="مالك السيرفر:", value=f"<@{guild.owner_id}>", inline=True)
  embed.add_field(name="عدد الأعضاء الإجمالي:", value=guild.member_count, inline=True)
  embed.add_field(name="عدد القنوات:", value=len(guild.channels), inline=True)
  embed.add_field(name="عدد الرولات:", value=len(guild.roles), inline=True)
  embed.add_field(
      name="تاريخ الإنشاء:",
      value=guild.created_at.strftime("%Y-%m-%d"),
      inline=False,
  )

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
  if amount < 1 or amount > 100:
    await interaction.response.send_message(
        "يرجى إدخال رقم بين 1 و 100.", ephemeral=True
    )
    return

  await interaction.response.defer(ephemeral=True)

  def check(msg):
    return msg.author == member if member else True

  deleted = await interaction.channel.purge(limit=amount, check=check)
  await interaction.followup.send(
      f"تم مسح {len(deleted)} رسالة بنجاح.", ephemeral=True
  )


@bot.tree.command(name="ping", description="عرض سرعة اتصال البوت واستجابته")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
async def ping(interaction: discord.Interaction):
  latency = round(bot.latency * 1000)
  embed = discord.Embed(
      title="🏓 Pong!",
      description=f"سرعة استجابة البوت (Latency): **{latency} ms**",
      color=discord.Color.green()
      if latency < 150
      else discord.Color.red(),
  )
  await interaction.response.send_message(embed=embed)


@bot.tree.command(name="botinfo", description="عرض معلومات البوت ورابط التصويت")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
async def botinfo(interaction: discord.Interaction):
  total_guilds = len(bot.guilds)
  total_users = sum(g.member_count for g in bot.guilds)

  embed = discord.Embed(
      title="معلومات البوت ورابط الدعم",
      description=(
          "شكراً لاستخدامك البوت! يمكنك دعمنا وتقييمنا على منصة Top.gg."
      ),
      color=discord.Color.gold(),
  )
  embed.add_field(
      name="السيرفرات الخادمة:", value=f"{total_guilds} سيرفر", inline=True
  )
  embed.add_field(
      name="إجمالي المستخدمين:", value=f"{total_users} عضو", inline=True
  )

  view = discord.ui.View()
  view.add_item(
      discord.ui.Button(
          label="دعم البوت على Top.gg",
          url="https://top.gg",
          style=discord.ButtonStyle.link,
      )
  )

  await interaction.response.send_message(embed=embed, view=view)


class CloseTicketView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label="إغلاق التذكرة 🔒",
      style=discord.ButtonStyle.red,
      custom_id="close_ticket_btn",
  )
  async def close_ticket(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_message(
        "جاري إغلاق القناة...", ephemeral=True
    )
    try:
      await interaction.channel.delete()
    except:
      pass


class TicketButtonView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

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
      await interaction.followup.send(
          f"لديك تذكرة مفتوحة بالفعل هنا: {existing_channel.mention}",
          ephemeral=True,
      )
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

      embed = discord.Embed(
          title="🎫 تذكرة دعم فني جديدة",
          description=(
              f"مرحباً {interaction.user.mention}، يرجى كتابة مشكلتك وسيتم الرد"
              " عليك قريباً من قبل فريق الدعم."
          ),
          color=0x6366f1,
      )
      await ticket_chan.send(
          content=interaction.user.mention,
          embed=embed,
          view=CloseTicketView(),
      )
      await interaction.followup.send(
          f"تم إنشاء تذكرتك بنجاح: {ticket_chan.mention}", ephemeral=True
      )
    except Exception as e:
      await interaction.followup.send(
          "حدث خطأ أثناء إنشاء التذكرة، يرجى التحقق من صلاحيات البوت.",
          ephemeral=True,
      )


@bot.tree.command(
    name="ticket-setup", description="إرسال لوحة إنشاء التذاكر في القناة الحالية"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_setup(interaction: discord.Interaction):
  embed = discord.Embed(
      title="🎫 نظام التذاكر والدعم الفني",
      description="اضغط على الزر بالأسفل لفتح تذكرة جديدة والتواصل مع الإدارة.",
      color=0xa855f7,
  )
  await interaction.channel.send(embed=embed, view=TicketButtonView())
  await interaction.response.send_message(
      "تم إرسال لوحة التذاكر بنجاح!", ephemeral=True
  )


@bot.tree.command(name="level", description="عرض مستواك الحالي ونقاط الخبرة XP")
@app_commands.describe(member="العضو المراد عرض مستواه (اختياري)")
async def level_command(
    interaction: discord.Interaction, member: discord.Member = None
):
  target = member or interaction.user
  if hasattr(database, "get_user_level"):
    xp, lvl = database.get_user_level(interaction.guild.id, target.id)
  else:
    xp, lvl = 0, 1

  next_xp = lvl * 100 + 100

  embed = discord.Embed(
      title=f"📊 رتبة العضو {target.name}", color=discord.Color.pink()
  )
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

  top_users = (
      database.get_top_users(guild_id, limit=10)
      if hasattr(database, "get_top_users")
      else []
  )

  embed = discord.Embed(
      title=f"🏆 قائمة المتصدرين في {interaction.guild.name}",
      description="أكثر الأعضاء تفاعلاً وحصولاً على نقاط الخبرة (XP):",
      color=discord.Color.gold(),
  )

  if not top_users:
    embed.add_field(
        name="لا توجد بيانات بعد",
        value="ابدأ بإرسال الرسائل لتكون أول المتصدرين!",
        inline=False,
    )
  else:
    desc_list = []
    for index, (uid, xp, lvl) in enumerate(top_users, start=1):
      member = interaction.guild.get_member(int(uid))
      name = member.mention if member else f"مستخدم مغادر ({uid})"
      medal = (
          "🥇"
          if index == 1
          else "🥈"
          if index == 2
          else "🥉"
          if index == 3
          else f"**#{index}**"
      )
      desc_list.append(f"{medal} {name} — المستوى: **{lvl}** (`{xp} XP`)")
    embed.description = "\n".join(desc_list)

  if interaction.guild.icon:
    embed.set_thumbnail(url=interaction.guild.icon.url)

  await interaction.response.send_message(embed=embed)


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
  if isinstance(error, app_commands.MissingPermissions):
    if not interaction.response.is_done():
      await interaction.response.send_message(
          "❌ **عذراً! هذا الأمر مخصص فقط للأعضاء الذين يمتلكون صلاحية (إدارة"
          " السيرفر - Manage Server).**",
          ephemeral=True,
      )
    else:
      await interaction.followup.send(
          "❌ **عذراً! هذا الأمر مخصص فقط للأعضاء الذين يمتلكون صلاحية (إدارة"
          " السيرفر - Manage Server).**",
          ephemeral=True,
      )
  elif isinstance(error, app_commands.CommandOnCooldown):
    msg = (
        "⏳ انتظر قليلاً! يمكنك استخدام الأمر مجدداً بعد"
        f" {round(error.retry_after, 1)} ثانية."
    )
    if not interaction.response.is_done():
      await interaction.response.send_message(msg, ephemeral=True)
    else:
      await interaction.followup.send(msg, ephemeral=True)
  else:
    msg = "حدث خطأ غير متوقع أثناء تنفيذ الأمر."
    if not interaction.response.is_done():
      await interaction.response.send_message(msg, ephemeral=True)
    else:
      await interaction.followup.send(msg, ephemeral=True)


TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
