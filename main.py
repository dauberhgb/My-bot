import os
import json
import threading
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, jsonify
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
            "icon": guild.icon.key if guild.icon else None
        })
    return render_template('guilds.html', guilds=bot_guilds)

# صفحة لوحة التحكم الخاصة بسيرفر معين مع جلب الإحصائيات والقنوات والرولات
@app.route('/dashboard/<guild_id>')
def dashboard(guild_id):
    guild = bot.get_guild(int(guild_id))
    if not guild:
        return "البوت غير متواجد في هذا السيرفر!", 404

    channels = [{"id": str(c.id), "name": c.name} for c in guild.text_channels]
    roles = [{"id": str(r.id), "name": r.name} for r in guild.roles if not r.is_default()]
    
    # جلب إحصائيات السيرفر
    stats = {
        "member_count": guild.member_count,
        "channel_count": len(guild.channels),
        "role_count": len(guild.roles)
    }

    settings = database.get_settings(guild_id)

    return render_template('index.html', guild=guild, channels=channels, roles=roles, settings=settings, stats=stats)

# حفظ الإعدادات مع دعم AJAX لتجنب إعادة تحميل الصفحة
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
        "media_enabled": request.form.get('media_enabled') == 'on',
        "media_channels": media_channels,
        "media_warning": request.form.get('media_warning', ''),
        "banned_enabled": request.form.get('banned_enabled') == 'on',
        "banned_words": banned_words,
        "max_violations": int(request.form.get('max_violations', 3)),
        "punishment_type": request.form.get('punishment_type', 'timeout'),
        "timeout_minutes": int(request.form.get('timeout_minutes', 10)),
        "warning_title": request.form.get('warning_title', ''),
        "warning_msg_1": request.form.get('warning_msg_1', ''),
        "warning_msg_2": request.form.get('warning_msg_2', ''),
        "farewell_enabled": request.form.get('farewell_enabled') == 'on',
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
    
    # إذا كان الطلب AJAX يرجع JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({"status": "success", "message": "تم حفظ الإعدادات بنجاح!"})
        
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

# أمر يديوي خاص بمالك البوت لمزامنة الأوامر عالمياً (Global Sync) لإظهار الشارة الخضراء
@bot.command(name="sync")
@commands.is_owner()
async def sync(ctx):
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"✅ تم تسجيل {len(synced)} أمر بشكل عالمي (Global) بنجاح! ستظهر الشارة الخضراء خلال وقت قصير.")
    except Exception as e:
        await ctx.send(f"❌ حدث خطأ أثناء المزامنة: {e}")

# أمر السلاش /setup مخصص فقط لمن يمتلك صلاحيات الأدمن administrator
@bot.tree.command(name="setup", description="الانتقال المباشر إلى لوحة تحكم البوت (للإدارة فقط)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.checks.cooldown(1, 5.0)
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

# معالجة أخطاء الصلاحيات والـ Cooldown لأمر Setup
@setup.error
async def setup_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ عذراً! هذا الأمر مخصص فقط للمسؤولين (Administrator) ولا يمكنك استخدامه.", 
            ephemeral=True
        )
    elif isinstance(error, app_commands.CommandOnCooldown):
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

# رسالة الوداع والزر
@bot.event
async def on_member_remove(member):
    settings = database.get_settings(member.guild.id)
    if not settings or not settings.get("farewell_enabled", True) or not settings.get("farewell_channel"):
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

    # 1. قنوات الميديا (إذا كانت مفعلة)
    if settings.get("media_enabled", True):
        media_channels = settings.get("media_channels", [])
        if str(message.channel.id) in media_channels or message.channel.name in media_channels:
            has_media = len(message.attachments) > 0 or any(ext in message.content.lower() for ext in ['.jpg', '.png', '.gif', '.mp4', 'http://', 'https://'])
            if not has_media:
                await message.delete()
                warn_msg = settings.get("media_warning", "عذراً هذه القناة للميديا فقط!").replace("{user}", message.author.mention)
                await message.channel.send(warn_msg, delete_after=5)
                return

    # 2. الكلمات المحظورة والعقوبات الذكية (إذا كانت مفعلة)
    if settings.get("banned_enabled", True):
        banned_words = settings.get("banned_words", [])
        msg_content = message.content.lower()
        if any(word in msg_content for word in banned_words):
            try:
                await message.delete()
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
            
            # تحديد نص التحذير: المرة الأولى -> التحذير 1 / المرات التالية -> التحذير 2
            if count == 1:
                msg_text = settings.get("warning_msg_1", "انتبه يا {user}، الكلمة محظورة!")
            else:
                msg_text = settings.get("warning_msg_2", "هذا هو الإنذار المتقدم يا {user}!")
            
            msg_text = msg_text.replace("{user}", message.author.mention)
            embed = discord.Embed(title=title, description=msg_text, color=discord.Color.gold())
            
            # 1. إرسال رسالة التحذير دائمًا أولاً وتختفي بعد 5 ثوانٍ
            await message.channel.send(embed=embed, delete_after=5)

            # 2. إذا وصل العضو للحد الأقصى أو تجاوز -> تطبيق العقوبة فوراً
            if count >= max_v:
                p_type = settings.get("punishment_type", "timeout")
                try:
                    t_min = int(settings.get("timeout_minutes", 10))
                except (ValueError, TypeError):
                    t_min = 10

                applied = False
                try:
                    if p_type == "timeout":
                        await message.author.timeout(timedelta(minutes=t_min), reason="تجاوز حد الكلمات المحظورة")
                        applied = True
                    elif p_type == "kick":
                        await message.author.kick(reason="تجاوز حد الكلمات المحظورة")
                        applied = True
                    elif p_type == "mute":
                        await message.author.timeout(timedelta(days=7), reason="تجاوز حد الكلمات المحظورة")
                        applied = True

                    if applied:
                        embed_punish = discord.Embed(
                            title="⛔ تم تطبيق العقوبة",
                            description=f"تم تطبيق عقوبة ({p_type.upper()}) على {message.author.mention} لتجاوزه الحد الأقصى للمخالفات ({max_v}).",
                            color=discord.Color.red()
                        )
                        await message.channel.send(embed=embed_punish, delete_after=5)
                        
                        # تصفير عدد مخالفات العضو بعد العقوبة
                        violations[g_id][u_id] = 0

                except Exception as e:
                    print(f"خطأ في تطبيق العقوبة: {e}")
                    await message.channel.send(
                        f"⚠️ تعذر تطبيق العقوبة على {message.author.mention}. يرجى التأكد من منح البوت صلاحية إدارة الأعضاء وأن رتبته أعلى من العضو!", 
                        delete_after=7
                    )
            return

    # 3. الردود التلقائية
    auto_resp = settings.get("auto_responses", {})
    if message.content.lower() in auto_resp:
        await message.channel.send(auto_resp[message.content.lower()])
        return

    await bot.process_commands(message)

TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
