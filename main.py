import os
import json
import threading
import io
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import discord
from discord import app_commands
from discord.ext import commands
import requests
import database

# ==========================================
# 0. إعدادات الأمان و OAuth2 (Discord)
# ==========================================
CLIENT_ID = os.getenv("CLIENT_ID", "YOUR_CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "YOUR_CLIENT_SECRET")
# رابط الـ Redirect يجب أن يتطابق مع المنصة (Render مثلاً)
REDIRECT_URI = os.getenv("REDIRECT_URI", "https://my-bot-05wx.onrender.com/callback")
DISCORD_API_ENDPOINT = "https://discord.com/api/v10"

# ==========================================
# 1. قاموس الترجمة للغات (العربية والإنجليزية)
# ==========================================
TRANSLATIONS = {
    'ar': {
        'title': 'لوحة التحكم',
        'dashboard_subtitle': 'لوحة التحكم الاحترافية',
        'change_guild': 'تغيير السيرفر',
        'total_members': 'إجمالي الأعضاء',
        'channels': 'القنوات',
        'roles': 'الرولات',
        'tab_general': 'الإعدادات العامة',
        'tab_analytics': 'التحليلات والإحصائيات',
        'tab_welcome': 'رسائل الترحيب',
        'tab_media': 'حماية الميديا',
        'tab_banned': 'الكلمات المحظورة',
        'tab_farewell': 'رسالة الوداع',
        'tab_responses': 'الردود التلقائية',
        'tab_logs': 'سجلات الرقابة',
        'tab_tickets': 'نظام التذاكر',
        'save_btn': 'حفظ جميع التغييرات',
        'auto_role': 'الرول التلقائي عند الدخول:',
        'no_role': 'بدون رول',
        'auto_nickname': 'اللقب التلقائي (Auto-Nickname):',
        'auto_nick_placeholder': 'مثال: [VIP] {user}',
        'auto_nick_help': 'استخدم {user} لتمثيل اسم العضو، أو اترك البادئة ليتم وضعها قبل اسمه.',
        'analytics_title': 'تحليلات نشاط البوت والحماية',
        'stat_banned': 'الكلمات المحظورة المحذوفة',
        'stat_media': 'مخالفات قنوات الميديا',
        'stat_responses': 'الردود التلقائية المرسلة',
        'stat_timeout': 'عقوبات التايم أوت',
        'stat_ban': 'عقوبات الحظر النهائيات',
        'welcome_channel': 'قناة الترحيب:',
        'welcome_title': 'عنوان رسالة الترحيب:',
        'default_welcome_title': 'مرحباً بك!',
        'welcome_desc': 'نص الرسالة ({user} لذكر العضو):',
        'default_welcome_desc': 'أهلاً بك يا {user} في السيرفر!',
        'welcome_img': 'رابط صورة/بانر الترحيب (Embed Image):',
        'media_title': 'حماية قنوات الميديا',
        'select_media_channels': 'حدد قنوات الميديا فقط:',
        'media_warn_msg': 'رسالة التنبيه عند كتابة نص فقط:',
        'default_media_warn': 'عذراً هذه القناة للميديا فقط!',
        'banned_title': 'الكلمات المحظورة والعقوبات',
        'banned_words_label': 'الكلمات المحظورة (افصل بينها بفاصلة ,):',
        'max_violations_label': 'حد المخالفات قبل العقوبة:',
        'punishment_type_label': 'نوع العقوبة:',
        'timeout_opt': 'تايم أوت',
        'kick_opt': 'طرد',
        'mute_opt': 'كتم 7 أيام',
        'timeout_mins_label': 'مدة التايم أوت (بالدقائق):',
        'warn_title_label': 'عنوان رسالة التحذير:',
        'default_warn_title': 'تحذير مخالفة',
        'warn_msg_1_label': 'رسالة التحذير الأول:',
        'default_warn_1': 'انتبه يا {user}، الكلمة محظورة! (الإنذار الأول)',
        'warn_msg_2_label': 'رسالة التحذير الثاني:',
        'default_warn_2': 'هذا هو الإنذار الأخير يا {user}!',
        'farewell_title': 'إعدادات الوداع',
        'farewell_channel_label': 'قناة الوداع:',
        'disable_opt': 'تعطيل',
        'farewell_title_label': 'عنوان الوداع:',
        'default_farewell_title': 'وداعاً!',
        'farewell_desc_label': 'وصف الرسالة ({user} لذكر العضو):',
        'default_farewell_desc': 'لقد غادر {user} السيرفر.',
        'farewell_img_label': 'رابط صورة Embed (اختياري):',
        'farewell_action_label': 'إجراء الأزرار التفاعلية:',
        'action_none': 'بدون زر',
        'action_ban': 'زر Ban حظر تلقائي',
        'action_timeout': 'زر Timeout تايم أوت',
        'discord_preview_title': 'معاينة حية لرسالة الوداع (Discord Live Preview)',
        'keyword_placeholder': 'الكلمة المفتاحية',
        'response_placeholder': 'الرد التلقائي للبوت',
        'log_channel': 'قناة الإدارة لإرسال السجلات والتنبيهات:',
        'ticket_channel': 'قناة لوحة التذاكر (التي يظهر فيها زر فتح تكت):',
        'ticket_archive_channel': 'قناة أرشيف التذاكر (التي تُنقل إليها التذاكر المغلقة):',
        'save_success': 'تم حفظ الإعدادات بنجاح!'
    },
    'en': {
        'title': 'Dashboard',
        'dashboard_subtitle': 'Professional Control Panel',
        'change_guild': 'Switch Server',
        'total_members': 'Total Members',
        'channels': 'Channels',
        'roles': 'Roles',
        'tab_general': 'General Settings',
        'tab_analytics': 'Analytics & Stats',
        'tab_welcome': 'Welcome Messages',
        'tab_media': 'Media Protection',
        'tab_banned': 'Banned Words',
        'tab_farewell': 'Farewell Message',
        'tab_responses': 'Auto Responses',
        'tab_logs': 'Audit Logs',
        'tab_tickets': 'Ticket System',
        'save_btn': 'Save All Changes',
        'auto_role': 'Auto Role on Join:',
        'no_role': 'No Role',
        'auto_nickname': 'Auto-Nickname:',
        'auto_nick_placeholder': 'Ex: [VIP] {user}',
        'auto_nick_help': 'Use {user} to represent the member\'s name, or leave a prefix to place before their name.',
        'analytics_title': 'Bot Activity & Protection Analytics',
        'stat_banned': 'Deleted Banned Words',
        'stat_media': 'Media Channel Violations',
        'stat_responses': 'Sent Auto Responses',
        'stat_timeout': 'Applied Timeouts',
        'stat_ban': 'Applied Bans',
        'welcome_channel': 'Welcome Channel:',
        'welcome_title': 'Welcome Message Title:',
        'default_welcome_title': 'Welcome!',
        'welcome_desc': 'Message Text ({user} to mention member):',
        'default_welcome_desc': 'Welcome {user} to the server!',
        'welcome_img': 'Welcome Image/Banner URL (Embed Image):',
        'media_title': 'Media Channels Protection',
        'select_media_channels': 'Select Media Channels Only:',
        'media_warn_msg': 'Warning message when text-only is sent:',
        'default_media_warn': 'Sorry, this channel is for media only!',
        'banned_title': 'Banned Words & Punishments',
        'banned_words_label': 'Banned Words (separate with commas ,):',
        'max_violations_label': 'Violation Limit Before Punishment:',
        'punishment_type_label': 'Punishment Type:',
        'timeout_opt': 'Timeout',
        'kick_opt': 'Kick',
        'mute_opt': 'Mute 7 Days',
        'timeout_mins_label': 'Timeout Duration (minutes):',
        'warn_title_label': 'Warning Message Title:',
        'default_warn_title': 'Violation Warning',
        'warn_msg_1_label': 'First Warning Message:',
        'default_warn_1': 'Be careful {user}, that word is banned! (First Warning)',
        'warn_msg_2_label': 'Second Warning Message:',
        'default_warn_2': 'This is your final warning {user}!',
        'farewell_title': 'Farewell Settings',
        'farewell_channel_label': 'Farewell Channel:',
        'disable_opt': 'Disable',
        'farewell_title_label': 'Farewell Title:',
        'default_farewell_title': 'Goodbye!',
        'farewell_desc_label': 'Message Description ({user} to mention member):',
        'default_farewell_desc': '{user} has left the server.',
        'farewell_img_label': 'Embed Image URL (Optional):',
        'farewell_action_label': 'Interactive Button Action:',
        'action_none': 'No Button',
        'action_ban': 'Auto Ban Button',
        'action_timeout': 'Timeout Button',
        'discord_preview_title': 'Discord Live Preview',
        'keyword_placeholder': 'Keyword',
        'response_placeholder': 'Auto Bot Response',
        'log_channel': 'Admin Log Channel:',
        'ticket_channel': 'Ticket Panel Channel:',
        'ticket_archive_channel': 'Ticket Archive Channel:',
        'save_success': 'Settings saved successfully!'
    }
}

# ==========================================
# 2. إعداد وتشغيل بوت ديسكورد
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
violations = {}

async def send_audit_log(guild, title, description, color=discord.Color.orange()):
    settings = database.get_settings(guild.id)
    if not settings or not settings.get("log_channel"):
        return
    
    log_ch_id = settings.get("log_channel")
    channel = guild.get_channel(int(log_ch_id)) if str(log_ch_id).isdigit() else discord.utils.get(guild.text_channels, name=log_ch_id)
    if channel:
        embed = discord.Embed(title=f"📜 {title}", description=description, color=color)
        embed.set_footer(text="نظام سجلات الرقابة والتنبيهات")
        try:
            await channel.send(embed=embed)
        except Exception as e:
            print(f"تعذر إرسال السجل: {e}")

# ==========================================
# 3. إعداد خادم الويب (Flask Dashboard & OAuth2)
# ==========================================
app = Flask(__name__)
app.secret_key = os.urandom(24) # مطلوب لإدارة الـ Session بأمان

@app.route('/')
def home():
    return redirect(url_for('guild_list'))

@app.route('/ping')
def ping():
    return "OK", 200

# --- مسارات المصادقة عبر Discord OAuth2 ---
@app.route('/login')
def login():
    discord_login_url = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={requests.utils.quote(REDIRECT_URI)}&response_type=code&scope=identify%20guilds"
    return redirect(discord_login_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "❌ فشل تسجيل الدخول عبر ديسكورد.", 400

    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    res = requests.post(f"{DISCORD_API_ENDPOINT}/oauth2/token", data=data, headers=headers)
    if res.status_code != 200:
        return "❌ تعذر جلب الـ Token من ديسكورد.", 400

    token_json = res.json()
    session['oauth2_token'] = token_json
    return redirect(url_for('guild_list'))

def has_permission(permissions):
    # فحص صلاحية Administrator (0x8) أو Manage Server (0x20)
    try:
        perms = int(permissions)
        return (perms & 0x8) == 0x8 or (perms & 0x20) == 0x20
    except:
        return False

@app.route('/guilds')
def guild_list():
    # التأكد من تسجيل الدخول
    token = session.get('oauth2_token')
    if not token:
        return redirect(url_for('login'))

    headers = {'Authorization': f"Bearer {token['access_token']}"}
    user_guilds_res = requests.get(f"{DISCORD_API_ENDPOINT}/users/@me/guilds", headers=headers)
    
    if user_guilds_res.status_code != 200:
        return redirect(url_for('login'))

    user_guilds = user_guilds_res.json()
    bot_guild_ids = [str(guild.id) for guild in bot.guilds]

    # تصفية السيرفرات: البوت متواجد فيها + المستخدم يمتلك صلاحية إدارة
    allowed_guilds = []
    for g in user_guilds:
        if str(g['id']) in bot_guild_ids:
            if g.get('owner') or has_permission(g.get('permissions', 0)):
                allowed_guilds.append(g)

    # عرض صفحة اختيار السيرفر الخاص بالمستخدم فقط
    return render_template('guild_select.html', guilds=allowed_guilds)

@app.route('/dashboard/<guild_id>')
def dashboard(guild_id):
    # التحقق من أن المستخدم يملك صلاحية على هذا السيرفر المحدد
    token = session.get('oauth2_token')
    if not token:
        return redirect(url_for('login'))

    headers = {'Authorization': f"Bearer {token['access_token']}"}
    user_guilds_res = requests.get(f"{DISCORD_API_ENDPOINT}/users/@me/guilds", headers=headers)
    if user_guilds_res.status_code != 200:
        return redirect(url_for('login'))

    user_guilds = user_guilds_res.json()
    authorized = False
    for g in user_guilds:
        if str(g['id']) == str(guild_id):
            if str(g['id']) in [str(bg.id) for bg in bot.guilds] and (g.get('owner') or has_permission(g.get('permissions', 0))):
                authorized = True
                break

    if not authorized:
        return "❌ غير مسموح لك بالوصول لإعدادات هذا السيرفر أو أن البوت غير متواجد فيه.", 403

    guild = bot.get_guild(int(guild_id))
    if not guild:
        return "البوت غير متواجد في هذا السيرفر!", 404

    channels = [{"id": str(c.id), "name": c.name} for c in guild.text_channels]
    roles = [{"id": str(r.id), "name": r.name} for r in guild.roles if not r.is_default()]
    
    stats = {
        "member_count": guild.member_count,
        "channel_count": len(guild.channels),
        "role_count": len(guild.roles)
    }

    settings = database.get_settings(guild_id)
    analytics = database.get_analytics(guild_id)

    lang = request.args.get('lang', 'ar')
    t = TRANSLATIONS.get(lang, TRANSLATIONS['ar'])

    return render_template('index.html', guild=guild, channels=channels, roles=roles, settings=settings, stats=stats, analytics=analytics, t=t, lang=lang)

@app.route('/save/<guild_id>', methods=['POST'])
def save(guild_id):
    guild = bot.get_guild(int(guild_id))
    if not guild:
        return jsonify({"status": "error", "message": "السيرفر غير موجود!"}), 400

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
        "welcome_channel": request.form.get('welcome_channel', ''),
        "welcome_title": request.form.get('welcome_title', ''),
        "welcome_desc": request.form.get('welcome_desc', ''),
        "welcome_img": request.form.get('welcome_img', ''),
        "farewell_channel": request.form.get('farewell_channel', ''),
        "farewell_title": request.form.get('farewell_title', ''),
        "farewell_desc": request.form.get('farewell_desc', ''),
        "farewell_img": request.form.get('farewell_img', ''),
        "farewell_action": request.form.get('farewell_action', 'none'),
        "auto_responses": auto_responses,
        "auto_role": request.form.get('auto_role', ''),
        "auto_nickname": request.form.get('auto_nickname', ''),
        "log_channel": request.form.get('log_channel', ''),
        "ticket_channel": request.form.get('ticket_channel', ''),
        "ticket_archive_channel": request.form.get('ticket_archive_channel', '')
    }

    database.save_settings(guild_id, settings)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({"status": "success", "message": "تم حفظ الإعدادات بنجاح!"})
        
    return f"<h1>تم حفظ إعدادات السيرفر ({guild.name}) بنجاح!</h1><br><a href='/dashboard/{guild_id}'>العودة للوحة التحكم</a>"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_web_server, daemon=True).start()

# ==========================================
# 4. أحداث وأوامر البوت (Discord Events & Commands)
# ==========================================
@bot.event
async def on_ready():
    bot.add_view(TicketLaunchView())
    bot.add_view(TicketCloseView())
    print(f'تم تشغيل البوت بنجاح باسم: {bot.user}')

@bot.command(name="sync")
@commands.is_owner()
async def sync(ctx):
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"✅ تم تسجيل {len(synced)} أمر بشكل عالمي (Global) بنجاح!")
    except Exception as e:
        await ctx.send(f"❌ حدث خطأ أثناء المزامنة: {e}")

@bot.tree.command(name="setup", description="الانتقال المباشر إلى لوحة تحكم البوت (لمالك السيرفر ورتبة Manager فقط)")
@app_commands.checks.cooldown(1, 5.0)
async def setup(interaction: discord.Interaction):
    is_owner = (interaction.user.id == interaction.guild.owner_id)
    user_roles = [role.name.lower() for role in interaction.user.roles]
    has_manager_role = "manager" in user_roles

    if not (is_owner or has_manager_role):
        await interaction.response.send_message(
            "❌ عذراً! هذا الأمر مخصص فقط لمالك السيرفر أو الأشخاص الذين يملكون رتبة (Manager).", 
            ephemeral=True
        )
        return

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

@setup.error
async def setup_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"⏳ يرجى الانتظار {round(error.retry_after, 1)} ثانية قبل استخدام الأمر مرة أخرى!", 
            ephemeral=True
        )

# ==========================================
# 5. أوامر السلاش الإضافية (Slash Commands)
# ==========================================

@bot.tree.command(name="stats", description="عرض إحصائيات الحماية والنشاط للسيرفر")
async def stats_command(interaction: discord.Interaction):
    analytics = database.get_analytics(interaction.guild_id)
    
    embed = discord.Embed(
        title=f"📊 إحصائيات حماية {interaction.guild.name}",
        color=discord.Color.blue()
    )
    embed.add_field(name="🚫 كلمات محظورة محذوفة", value=str(analytics.get("banned_blocked", 0)), inline=True)
    embed.add_field(name="🖼️ مخالفات الميديا", value=str(analytics.get("media_deleted", 0)), inline=True)
    embed.add_field(name="🤖 ردود تلقائية أُرسلت", value=str(analytics.get("auto_replies", 0)), inline=True)
    embed.add_field(name="⏰ عقوبات تايم أوت", value=str(analytics.get("timeout_count", 0)), inline=True)
    embed.add_field(name="🔨 عقوبات حظر", value=str(analytics.get("ban_count", 0)), inline=True)
    embed.set_footer(text="يتم التحديث تلقائياً عبر نظام التحليلات")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="settings", description="عرض الإعدادات الحالية المطبقة من لوحة التحكم")
@app_commands.checks.has_permissions(administrator=True)
async def settings_command(interaction: discord.Interaction):
    settings = database.get_settings(interaction.guild_id)
    
    embed = discord.Embed(
        title=f"⚙️ إعدادات البوت الحالية - {interaction.guild.name}",
        color=discord.Color.green()
    )
    
    banned_words_count = len(settings.get("banned_words", []))
    media_channels_count = len(settings.get("media_channels", []))
    auto_role = settings.get("auto_role") or "غير مفعل"
    auto_nick = settings.get("auto_nickname") or "غير مفعل"
    
    embed.add_field(name="🛡️ الكلمات المحظورة", value=f"{banned_words_count} كلمة", inline=True)
    embed.add_field(name="📁 قنوات الميديا", value=f"{media_channels_count} قناة", inline=True)
    embed.add_field(name="👤 الرول التلقائي", value=auto_role, inline=True)
    embed.add_field(name="🏷️ اللقب التلقائي", value=auto_nick, inline=True)
    embed.add_field(name="⚖️ نوع العقوبة", value=settings.get("punishment_type", "timeout").upper(), inline=True)
    embed.add_field(name="⚠️ حد المخالفات", value=str(settings.get("max_violations", 3)), inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="warn", description="إعطاء تحذير يدوي لعضو")
@app_commands.checks.has_permissions(moderate_members=True)
async def warn_command(interaction: discord.Interaction, member: discord.Member, reason: str = "مخالفة القوانين"):
    g_id = str(interaction.guild_id)
    u_id = str(member.id)
    
    violations.setdefault(g_id, {}).setdefault(u_id, 0)
    violations[g_id][u_id] += 1
    
    count = violations[g_id][u_id]
    settings = database.get_settings(g_id)
    max_v = int(settings.get("max_violations", 3))
    
    embed = discord.Embed(
        title="⚠️ تحذير يدوي من الإدارة",
        description=f"تم تحذير {member.mention}.\n**السبب:** {reason}\n**عدد المخالفات الحالي:** ({count}/{max_v})",
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed)
    
    await send_audit_log(interaction.guild, "تحذير يدوي", f"قام {interaction.user.mention} بتحذير {member.mention}.\nالسبب: {reason}")

    if count >= max_v:
        p_type = settings.get("punishment_type", "timeout")
        t_min = int(settings.get("timeout_minutes", 10))
        
        try:
            if p_type == "timeout":
                await member.timeout(timedelta(minutes=t_min), reason=reason)
                database.increment_stat(g_id, "timeout_count")
            elif p_type == "kick":
                await member.kick(reason=reason)
            elif p_type == "mute":
                await member.timeout(timedelta(days=7), reason=reason)
                database.increment_stat(g_id, "timeout_count")

            await interaction.followup.send(f"⛔ تم تطبيق عقوبة ({p_type.upper()}) على {member.mention} لتجاوزه حد التحذيرات.")
            violations[g_id][u_id] = 0
            await send_audit_log(interaction.guild, "تطبيق عقوبة تلقائية", f"تم تطبيق عقوبة ({p_type}) على {member.mention} لتجاوز حد التحذيرات.", discord.Color.red())
        except Exception as e:
            await interaction.followup.send(f"❌ تعذر تطبيق العقوبة: {e}")


@bot.tree.command(name="clear-warns", description="تصفير تحذيرات عضو معين")
@app_commands.checks.has_permissions(moderate_members=True)
async def clear_warns_command(interaction: discord.Interaction, member: discord.Member):
    g_id = str(interaction.guild_id)
    u_id = str(member.id)
    
    if g_id in violations and u_id in violations[g_id]:
        violations[g_id][u_id] = 0
        await interaction.response.send_message(f"✅ تم تصفير مخالفات {member.mention} بنجاح.", ephemeral=True)
    else:
        await interaction.response.send_message(f"ℹ️ {member.mention} لا يملك أي مخالفات مسجلة.", ephemeral=True)

# ==========================================
# 6. نظام التذاكر المطور (Private Threads & Transcripts)
# ==========================================
class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="إغلاق التكت والأرشفة 🔒", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("جاري استخراج الترانسكريبت وأرشفة التكت...", ephemeral=True)

        thread = interaction.channel
        settings = database.get_settings(interaction.guild_id)
        archive_ch_id = settings.get("ticket_archive_channel")

        messages = []
        async for msg in thread.history(limit=500, oldest_first=True):
            time_str = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            messages.append(f"[{time_str}] {msg.author} ({msg.author.id}): {msg.clean_content}")

        transcript_text = "\n".join(messages)
        file_data = io.BytesIO(transcript_text.encode('utf-8'))
        transcript_file = discord.File(file_data, filename=f"transcript-{thread.name}.txt")

        archive_channel = interaction.guild.get_channel(int(archive_ch_id)) if str(archive_ch_id).isdigit() else None
        if archive_channel:
            embed_archive = discord.Embed(
                title="📁 أرشيف تكت مغلق",
                description=f"**اسم التكت:** {thread.name}\n**تم الإغلاق بواسطة:** {interaction.user.mention}",
                color=discord.Color.dark_grey()
            )
            try:
                await archive_channel.send(embed=embed_archive, file=transcript_file)
            except Exception as e:
                print(f"تعذر إرسال الترانسكريبت لقناة الأرشيف: {e}")

        await send_audit_log(interaction.guild, "إغلاق تكت", f"قام {interaction.user.mention} بإغلاق التكت: {thread.name}")
        
        import asyncio
        await asyncio.sleep(2)
        await thread.edit(archived=True, locked=True)

class TicketLaunchView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="فتح تكت دعم 📩", style=discord.ButtonStyle.primary, custom_id="open_ticket_btn")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        try:
            thread = await interaction.channel.create_thread(
                name=f"ticket-{interaction.user.name}",
                type=discord.ChannelType.private_thread,
                invitable=False
            )
            
            await thread.add_user(interaction.user)

            embed = discord.Embed(
                title="🎫 تكت دعم جديد",
                description=f"مرحباً بك {interaction.user.mention}، يرجى كتابة استفسارك هنا وسيقوم فريق الدعم بالرد عليك قريباً.",
                color=discord.Color.blue()
            )
            
            await thread.send(embed=embed, view=TicketCloseView())
            await interaction.followup.send(f"✅ تم إنشاء التكت بنجاح: {thread.mention}", ephemeral=True)
            await send_audit_log(interaction.guild, "فتح تكت جديد", f"قام {interaction.user.mention} بفتح تكت جديد: {thread.mention}")

        except Exception as e:
            await interaction.followup.send(f"❌ حدث خطأ أثناء إنشاء التكت (تأكد من تفعيل صلاحيات Private Threads للبوت): {e}", ephemeral=True)

@bot.tree.command(name="setup-tickets", description="إرسال لوحة التذاكر المباشرة إلى القناة المحددة")
@app_commands.checks.has_permissions(administrator=True)
async def setup_tickets_command(interaction: discord.Interaction):
    settings = database.get_settings(interaction.guild_id)
    ticket_ch_id = settings.get("ticket_channel")
    
    if not ticket_ch_id:
        await interaction.response.send_message("❌ يرجى تحديد قناة التذاكر من لوحة التحكم أولاً!", ephemeral=True)
        return

    channel = interaction.guild.get_channel(int(ticket_ch_id)) if str(ticket_ch_id).isdigit() else discord.utils.get(interaction.guild.text_channels, name=ticket_ch_id)
    if not channel:
        await interaction.response.send_message("❌ القناة المحددة غير موجودة!", ephemeral=True)
        return

    embed = discord.Embed(
        title="🎫 مركز الدعم والتعليمات",
        description="اضغط على الزر أدناه لفتح تكت جديد للتواصل المباشر مع فريق الإدارة والدعم الفني.",
        color=discord.Color.green()
    )
    await channel.send(embed=embed, view=TicketLaunchView())
    await interaction.response.send_message(f"✅ تم إرسال لوحة التذاكر بنجاح إلى القناة: {channel.mention}", ephemeral=True)

# ==========================================
# 7. الأحداث التلقائية للبوت (Events)
# ==========================================

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

    if settings.get("welcome_channel"):
        welc_ch_id = settings.get("welcome_channel")
        channel = member.guild.get_channel(int(welc_ch_id)) if str(welc_ch_id).isdigit() else discord.utils.get(member.guild.text_channels, name=welc_ch_id)
        if channel:
            title = settings.get("welcome_title", "مرحباً بك!")
            desc = settings.get("welcome_desc", "أهلاً بك يا {user} في السيرفر!").replace("{user}", member.mention)
            embed = discord.Embed(title=title, description=desc, color=discord.Color.green())
            if settings.get("welcome_img"):
                embed.set_image(url=settings["welcome_img"])
            await channel.send(embed=embed)

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
                def __init__(self, user_id):
                    super().__init__(timeout=None)
                    self.user_id = user_id

                @discord.ui.button(label=f"تطبيق {action.upper()}", style=discord.ButtonStyle.danger)
                async def btn_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
                    try:
                        if action == "ban":
                            user_to_ban = await interaction.client.fetch_user(self.user_id)
                            await interaction.guild.ban(user_to_ban, reason="عن طريق زر الوداع")
                            database.increment_stat(interaction.guild.id, "ban_count")
                            await interaction.response.send_message("تم حظر العضو بنجاح.", ephemeral=True)
                            await send_audit_log(interaction.guild, "حظر من زر الوداع", f"تم حظر المستخدم ID: {self.user_id} عبر زر الوداع.")
                        elif action == "timeout":
                            target_member = interaction.guild.get_member(self.user_id)
                            if target_member:
                                await target_member.timeout(timedelta(minutes=10), reason="عن طريق زر الوداع")
                                database.increment_stat(interaction.guild.id, "timeout_count")
                                await interaction.response.send_message("تم إعطاء تايم أوت.", ephemeral=True)
                                await send_audit_log(interaction.guild, "تايم أوت من زر الوداع", f"تم تطبيق تايم أوت على {target_member.mention} عبر زر الوداع.")
                            else:
                                await interaction.response.send_message("⚠️ تعذر إعطاء تايم أوت لأن العضو غادر السيرفر بالفعل.", ephemeral=True)
                    except Exception as e:
                        await interaction.response.send_message(f"❌ حدث خطأ أثناء تطبيق الإجراء: {e}", ephemeral=True)

            view = FarewellView(user_id=member.id)

        await channel.send(embed=embed, view=view)

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    settings = database.get_settings(message.guild.id)
    if not settings:
        await bot.process_commands(message)
        return

    media_channels = settings.get("media_channels", [])
    if str(message.channel.id) in media_channels or message.channel.name in media_channels:
        has_media = len(message.attachments) > 0 or any(ext in message.content.lower() for ext in ['.jpg', '.png', '.gif', '.mp4', 'http://', 'https://'])
        if not has_media:
            await message.delete()
            database.increment_stat(message.guild.id, "media_deleted")
            warn_msg = settings.get("media_warning", "عذراً هذه القناة للميديا فقط!").replace("{user}", message.author.mention)
            await message.channel.send(warn_msg, delete_after=5)
            await send_audit_log(message.guild, "حذف رسالة مخالفة ميديا", f"قام {message.author.mention} بكتابة نص في قناة الميديا #{message.channel.name}")
            return

    banned_words = settings.get("banned_words", [])
    msg_content = message.content.lower()
    if any(word in msg_content for word in banned_words):
        try:
            await message.delete()
            database.increment_stat(message.guild.id, "banned_blocked")
            await send_audit_log(message.guild, "حذف كلمة محظورة", f"تم حذف رسالة تحتوي على كلمة محظورة من {message.author.mention} في #{message.channel.name}")
        except Exception as e:
            print(f"تعذر حذف الرسالة: {e}")
        
        g_id = str(message.guild.id)
        u_id = str(message.author.id)
        violations.setdefault(g_id, {}).setdefault(u_id, 0)
        violations[g_id][u_id] += 1
        
        count = violations[g_id][u_id]
        
        try:
            max_v = int(settings.get("max_violations", 3))
        except (ValueError, TypeError):
            max_v = 3

        title = settings.get("warning_title", "تحذير مخالفة")
        
        if count == 1:
            msg_text = settings.get("warning_msg_1", "انتبه يا {user}، الكلمة محظورة!")
        else:
            msg_text = settings.get("warning_msg_2", "هذا هو الإنذار المتقدم يا {user}!")
        
        msg_text = msg_text.replace("{user}", message.author.mention)
        embed = discord.Embed(title=title, description=msg_text, color=discord.Color.gold())
        await message.channel.send(embed=embed, delete_after=5)

        if count >= max_v:
            p_type = settings.get("punishment_type", "timeout")
            try:
                t_min = int(settings.get("timeout_minutes", 10))
            except (ValueError, TypeError):
                t_min = 10

            try:
                if p_type == "timeout":
                    await message.author.timeout(timedelta(minutes=t_min), reason="تجاوز حد الكلمات المحظورة")
                    database.increment_stat(message.guild.id, "timeout_count")
                elif p_type == "kick":
                    await message.author.kick(reason="تجاوز حد الكلمات المحظورة")
                elif p_type == "mute":
                    await message.author.timeout(timedelta(days=7), reason="تجاوز حد الكلمات المحظورة")
                    database.increment_stat(message.guild.id, "timeout_count")

                embed_punish = discord.Embed(
                    title="⛔ تم تطبيق العقوبة",
                    description=f"تم تطبيق عقوبة ({p_type.upper()}) على {message.author.mention} لتجاوزه الحد الأقصى للمخالفات ({max_v}).",
                    color=discord.Color.red()
                )
                await message.channel.send(embed_punish, delete_after=5)
                await send_audit_log(message.guild, "تطبيق عقوبة تلقائية", f"تم تطبيق عقوبة ({p_type}) على {message.author.mention} لتجاوزه حد الكلمات المحظورة.", discord.Color.red())
                violations[g_id][u_id] = 0

            except Exception as e:
                print(f"خطأ في تطبيق العقوبة: {e}")
                await message.channel.send(
                    f"⚠️ تعذر تطبيق العقوبة على {message.author.mention}. يرجى التأكد من صلاحيات البوت!", 
                    delete_after=7
                )
        return

    auto_resp = settings.get("auto_responses", {})
    if message.content.lower() in auto_resp:
        await message.channel.send(auto_resp[message.content.lower()])
        database.increment_stat(message.guild.id, "auto_replies")
        return

    await bot.process_commands(message)

if __name__ == "__main__":
    token = os.getenv("TOKEN")
    if not token:
        print("❌ خطأ: لم يتم العثور على TOKEN في متغيرات البيئة!")
    else:
        try:
            bot.run(token)
        except Exception as e:
            print(f"❌ حدث خطأ أثناء تشغيل البوت: {e}")
