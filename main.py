import os
import json
import threading
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for
import discord
from discord import app_commands
from discord.ext import commands
import database

# ==========================================
# 1. إعداد وتشغيل بوت ديسكورد
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
violations = {}

# ضع معرف حسابك في ديسكورد (User ID) هنا مكان هذا الرقم
OWNER_ID = 1462429084377157832

# ==========================================
# 2. إعداد خادم الويب (Flask Dashboard)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return redirect(url_for('guild_list'))

# صفحة عرض كافة السيرفرات المتواجد فيها البوت تلقائياً
@app.route('/guilds')
def guild_list():
    bot_guilds = []
    for guild in bot.guilds:
        bot_guilds.append({
            "id": str(guild.id),
            "name": guild.name,
            "icon": guild.icon.url if guild.icon else None
        })
    return render_template('guilds.html', guilds=bot_guilds)

# صفحة لوحة التحكم الخاصة بسيرفر معين مع جلب قنواته ورولاته تلقائياً
@app.route('/dashboard/<guild_id>')
def dashboard(guild_id):
    guild = bot.get_guild(int(guild_id))
    if not guild:
        return "البوت غير متواجد في هذا السيرفر!", 404

    # جلب جميع القنوات النصية والرولات تلقائياً
    channels = [{"id": str(c.id), "name": c.name} for c in guild.text_channels]
    roles = [{"id": str(r.id), "name": r.name} for r in guild.roles if not r.is_default()]
    
    settings = database.get_settings(guild_id)

    # جلب رابط صورة السيرفر المباشر
    icon_url = guild.icon.url if guild.icon else None

    return render_template('index.html', guild=guild, channels=channels, roles=roles, settings=settings, icon_url=icon_url)

# حفظ الإعدادات للسيرفر المختار
@app.route('/save/<guild_id>', methods=['POST'])
def save(guild_id):
    guild = bot.get_guild(int(guild_id))
    if not guild:
        return "السيرفر غير موجود!", 400

    media_channels = request.form.getlist('media_channels')
    banned_words = [w.strip().lower() for w in request.form.get('banned_words', '').split(',') if w.strip()]
    
    auto_responses = {}
    for i in range(1, 4):
        w = request.form.get(f'word{i}', '').strip().lower()
        r = request.form.get(f'resp{i}', '').strip()
        if w and r:
            auto_responses[w] = r

    settings = {
        "guild_id": guild_id,
        "media_channels": media_channels,
        "media_warning": request.form.get('media_warning', ''),
        "banned_words": banned_words,
        "max_violations": int(request.form.get('max_violations', 3)),
        "punishment_type": request.form.get('punishment_type', 'timeout'),
        "timeout_minutes": int(request.form.get('timeout_minutes', 10)),
        "warning_title": request.form.get('warning_title', ''),
        "warning_msg_1": request.form.get('warning_msg_1', ''),
        "warning_msg_2": request.form.get('warning_msg_2', ''),
        "farewell_channel": request.form.get('farewell_channel', ''),
        "farewell_title": request.form.get('farewell_title', ''),
        "farewell_desc": request.form.get('farewell_desc', ''),
        "farewell_img": request.form.get('farewell_img', ''),
        "farewell_action": request.form.get('farewell_action', 'none'),
        "auto_responses": auto_responses,
        "auto_role": request.form.get('auto_role', ''),
        "auto_nickname": request.form.get('auto_nickname', '')
    }

    database.save_settings(guild_id, settings)
    return f"<h1>تم حفظ إعدادات السيرفر ({guild.name}) بنجاح!</h1><br><a href='/guilds'>العودة لقائمة السيرفرات</a>"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_web_server, daemon=True).start()

# ==========================================
# 3. أحداث وأوامر البوت (Discord Events & Commands)
# ==========================================
@bot.event
async def on_ready():
    print(f'تم تشغيل البوت بنجاح باسم: {bot.user}')

# أمر السلاش /setup مع حماية Cooldown
@bot.tree.command(name="setup", description="الانتقال المباشر إلى لوحة تحكم البوت لهذا السيرفر")
@app_commands.checks.cooldown(1, 5.0)  # مهلة 5 ثوانٍ بين الاستخدامات لمنع الحظر
async def setup(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    
    base_url = os.getenv("DASHBOARD_URL", "").rstrip('/')
    if not base_url:
        dashboard_link = f"https://{os.getenv('RENDER_SERVICE_NAME', 'app')}.onrender.com/dashboard/{guild_id}"
    else:
        dashboard_link = f"{base_url}/dashboard/{guild_id}"

    view = discord.ui.View()
    button = discord.ui.Button(label="فتح لوحة التحكم ⚙️", url=dashboard_link, style=discord.ButtonStyle.link)
    view.add_item(button)

    embed = discord.Embed(
        title="🛠️ لوحة تحكم السيرفر",
        description=f"مرحباً بك! يمكنك ضبط جميع إعدادات البوت لسيرفر **{interaction.guild.name}** عبر الضغط على الزر أدناه:",
        color=discord.Color.blue()
    )
    
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# معالجة خطأ الـ Cooldown
@setup.error
async def setup_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"⏳ يرجى الانتظار {round(error.retry_after, 1)} ثانية قبل استخدام الأمر مرة أخرى!", 
            ephemeral=True
        )

# الرول واللقب التلقائي الذكي
@bot.event
async def on_member_join(member):
    settings = database.get_settings(member.guild.id)
    if not settings:
        return

    # 1. إعطاء الرول التلقائي
    if settings.get("auto_role"):
        role = discord.utils.get(member.guild.roles, name=settings["auto_role"])
        if role:
            try:
                await member.add_roles(role)
            except Exception as e:
                print(f"تعذر إعطاء الرول: {e}")

    # 2. اللقب التلقائي الذكي (Auto-Nickname)
    auto_nick = settings.get("auto_nickname", "").strip()
    if auto_nick:
        try:
            # إذا كتب في اللوحة {user} سيضع اسم العضو مكانها
            if "{user}" in auto_nick:
                new_nick = auto_nick.replace("{user}", member.display_name)
            else:
                # إذا لم يكتب {user}، سيضيف الكلمة كبادئة قبل اسمه الأصلي تلقائياً
                new_nick = f"{auto_nick} {member.display_name}"

            # ديسكورد يقبل ألقاب حتى 32 حرفاً فقط
            await member.edit(nick=new_nick[:32])
        except Exception as e:
            print(f"تعذر تغيير اللقب: {e}")

# رسالة الوداع والزر
@bot.event
async def on_member_remove(member):
    settings = database.get_settings(member.guild.id)
    if not settings or not settings.get("farewell_channel"):
        return

    channel = member.guild.get_channel(int(settings["farewell_channel"])) if settings["farewell_channel"].isdigit() else discord.utils.get(member.guild.text_channels, name=settings["farewell_channel"])
    
    if channel:
        embed = discord.Embed(
            title=settings.get("farewell_title", "وداعاً"),
            description=settings.get("farewell_desc", "").replace("{user}", member.mention),
            color=discord.Color.red()
        )
        if settings.get("farewell_img"):
            embed.set_image(url=settings["farewell_img"])

        view = None
        action = settings.get("farewell_action")
        if action in ["ban", "timeout"]:
            class FarewellView(discord.ui.View):
                @discord.ui.button(label=f"تطبيق {action.upper()}", style=discord.ButtonStyle.danger)
                async def btn_callback(self, interaction, button):
                    if action == "ban":
                        await member.ban(reason="عن طريق زر الوداع")
                        await interaction.response.send_message("تم حظر العضو.", ephemeral=True)
                    elif action == "timeout":
                        await member.timeout(timedelta(minutes=10), reason="عن طريق زر الوداع")
                        await interaction.response.send_message("تم إعطاء تايم أوت.", ephemeral=True)
            view = FarewellView()

        await channel.send(embed=embed, view=view)

# الميديا والكلمات والردود
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    settings = database.get_settings(message.guild.id)
    if not settings:
        await bot.process_commands(message)
        return

    # 1. قنوات الميديا
    media_channels = settings.get("media_channels", [])
    if str(message.channel.id) in media_channels or message.channel.name in media_channels:
        has_media = len(message.attachments) > 0 or any(ext in message.content.lower() for ext in ['.jpg', '.png', '.gif', '.mp4', 'http://', 'https://'])
        if not has_media:
            await message.delete()
            warn_msg = settings.get("media_warning", "عذراً هذه القناة للميديا فقط!").replace("{user}", message.author.mention)
            await message.channel.send(warn_msg, delete_after=5)
            return

    # 2. الكلمات المحظورة
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
            msg_text = settings.get("warning_msg_1") if count == 1 else settings.get("warning_msg_2")
            msg_text = msg_text.replace("{user}", message.author.mention)
            embed = discord.Embed(title=title, description=msg_text, color=discord.Color.gold())
            await message.channel.send(embed=embed)
        else:
            p_type = settings.get("punishment_type", "timeout")
            t_min = settings.get("timeout_minutes", 10)
            try:
                if p_type == "timeout":
                    await message.author.timeout(timedelta(minutes=t_min), reason="مخالفة القوانين")
                elif p_type == "kick":
                    await message.author.kick(reason="مخالفة القوانين")
                elif p_type == "mute":
                    await message.author.timeout(timedelta(days=7), reason="كتم كامل")
                await message.channel.send(f"تم تطبيق ({p_type}) على {message.author.mention}.")
            except Exception as e:
                print(f"خطأ في العقوبة: {e}")
            violations[g_id][u_id] = 0
        return

    # 3. الردود التلقائية
    auto_resp = settings.get("auto_responses", {})
    if msg_content in auto_resp:
        await message.channel.send(auto_resp[msg_content])
        return

    await bot.process_commands(message)

# ==========================================
# 4. أمر المزامنة اليدوي (!sync)
# ==========================================
@bot.command(name="sync")
async def sync_commands(ctx):
    # التحقق مما إذا كان منفذ الأمر هو صاحب البوت فقط
    if ctx.author.id != OWNER_ID:
        await ctx.send("عذراً! هذا الأمر مخصص لصاحب البوت فقط.")
        return

    msg = await ctx.send("جاري مزامنة أوامر السلاش عالمياً...")
    
    try:
        synced = await bot.tree.sync()
        await msg.edit(content=f"تمت مزامنة {len(synced)} أمر سلاش بنجاح على مستوى العالم!")
    except Exception as e:
        await msg.edit(content=f"حدث خطأ أثناء المزامنة: {e}")

# ==========================================
# 5. أوامر السلاش الجديدة (Slash Commands)
# ==========================================

# 1. أمر عرض معلومات العضو
@bot.tree.command(name="userinfo", description="عرض معلومات تفصيلية عن عضويتك أو عضو آخر")
@app_commands.describe(member="العضو المراد عرض معلوماته (اختياري)")
@app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    
    embed = discord.Embed(
        title=f"معلومات العضو: {target.display_name}",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="الاسم:", value=target.name, inline=True)
    embed.add_field(name="المعرف (ID):", value=target.id, inline=True)
    embed.add_field(name="تاريخ إنشاء الحساب:", value=target.created_at.strftime("%Y-%m-%d"), inline=False)
    embed.add_field(name="تاريخ الانضمام للسيرفر:", value=target.joined_at.strftime("%Y-%m-%d"), inline=False)
    embed.add_field(name="أعلى رول:", value=target.top_role.mention, inline=True)
    
    await interaction.response.send_message(embed=embed)

# 2. أمر عرض معلومات السيرفر
@bot.tree.command(name="serverinfo", description="عرض معلومات وإحصائيات هذا السيرفر")
@app_commands.checks.cooldown(1, 10.0, key=lambda i: (i.guild_id, i.user.id))
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    
    embed = discord.Embed(
        title=f"إحصائيات {guild.name}",
        color=discord.Color.purple()
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
        
    embed.add_field(name="معرف السيرفر (ID):", value=guild.id, inline=True)
    embed.add_field(name="مالك السيرفر:", value=f"<@{guild.owner_id}>", inline=True)
    embed.add_field(name="عدد الأعضاء الإجمالي:", value=guild.member_count, inline=True)
    embed.add_field(name="عدد القنوات:", value=len(guild.channels), inline=True)
    embed.add_field(name="عدد الرولات:", value=len(guild.roles), inline=True)
    embed.add_field(name="تاريخ الإنشاء:", value=guild.created_at.strftime("%Y-%m-%d"), inline=False)
    
    await interaction.response.send_message(embed=embed)

# 3. أمر مسح الرسائل
@bot.tree.command(name="clear", description="حذف عدد معين من الرسائل من القناة الحالية")
@app_commands.describe(amount="عدد الرسائل المراد مسحها (1 - 100)", member="تحديد عضو معين لتنظيف رسائله فقط (اختياري)")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
async def clear(interaction: discord.Interaction, amount: int, member: discord.Member = None):
    if amount < 1 or amount > 100:
        await interaction.response.send_message("يرجى إدخال رقم بين 1 و 100.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    
    def check(msg):
        return msg.author == member if member else True

    deleted = await interaction.channel.purge(limit=amount, check=check)
    await interaction.followup.send(f"تم مسح {len(deleted)} رسالة بنجاح.", ephemeral=True)

# 4. أمر فحص سرعة الاستجابة (Ping)
@bot.tree.command(name="ping", description="عرض سرعة اتصال البوت واستجابته")
@app_commands.checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"سرعة استجابة البوت (Latency): **{latency} ms**",
        color=discord.Color.green() if latency < 150 else discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)

# 5. أمر معلومات البوت ورابط Top.gg
@bot.tree.command(name="botinfo", description="عرض معلومات البوت ورابط التصويت")
@app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
async def botinfo(interaction: discord.Interaction):
    total_guilds = len(bot.guilds)
    total_users = sum(g.member_count for g in bot.guilds)
    
    embed = discord.Embed(
        title="معلومات البوت ورابط الدعم",
        description="شكراً لاستخدامك البوت! يمكنك دعمنا وتقييمنا على منصة Top.gg.",
        color=discord.Color.gold()
    )
    embed.add_field(name="السيرفرات الخادمة:", value=f"{total_guilds} سيرفر", inline=True)
    embed.add_field(name="إجمالي المستخدمين:", value=f"{total_users} عضو", inline=True)
    
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="دعم البوت على Top.gg", url="https://top.gg", style=discord.ButtonStyle.link))
    
    await interaction.response.send_message(embed=embed, view=view)

# ==========================================
# 6. معالجة الأخطاء العامة لأوامر السلاش
# ==========================================
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(f"انتظر قليلاً! يمكنك استخدام الأمر مجدداً بعد {round(error.retry_after, 1)} ثانية.", ephemeral=True)
    elif isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("عذراً، لا تمتلك الصلاحيات الكافية لاستخدام هذا الأمر.", ephemeral=True)
    else:
        await interaction.response.send_message("حدث خطأ غير متوقع أثناء تنفيذ الأمر.", ephemeral=True)

TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
