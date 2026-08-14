import os
import json
import threading
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for
import discord
from discord.ext import commands
import database

# ==========================================
# 1. إعداد خادم الويب (Flask Dashboard)
# ==========================================
app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/save', methods=['POST'])
def save():
    guild_id = request.form.get('guild_id', '').strip()
    if not guild_id:
        return "خطأ: يرجى إدخال معرّف السيرفر (Server ID) الصحيح!", 400

    # معالجة القنوات والكلمات
    media_channels = [c.strip() for c in request.form.get('media_channels', '').split(',') if c.strip()]
    banned_words = [w.strip().lower() for w in request.form.get('banned_words', '').split(',') if w.strip()]
    
    # معالجة الردود التلقائية
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
        "farewell_channel": request.form.get('farewell_channel', '').strip(),
        "farewell_title": request.form.get('farewell_title', ''),
        "farewell_desc": request.form.get('farewell_desc', ''),
        "farewell_img": request.form.get('farewell_img', '').strip(),
        "farewell_action": request.form.get('farewell_action', 'none'),
        "auto_responses": auto_responses,
        "auto_role": request.form.get('auto_role', '').strip(),
        "auto_nickname": request.form.get('auto_nickname', '').strip()
    }

    database.save_settings(guild_id, settings)
    return "<h1>تم حفظ الإعدادات بنجاح للسيرفر! يمكنك العودة للوحة والتحكم بسيرفر آخر.</h1><br><a href='/'>العودة للوحة التحكم</a>"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_web_server, daemon=True).start()

# ==========================================
# 2. إعداد وتشغيل بوت ديسكورد
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# تتبع مخالفي السيرفرات {guild_id: {user_id: count}}
violations = {}

@bot.event
async def on_ready():
    print(f'تم تشغيل البوت بنجاح باسم: {bot.user}')

# --- الخيار الخامس والسادس: الأعضاء الجدد (الرول + اللقب التلقائي) ---
@bot.event
async def on_member_join(member):
    settings = database.get_settings(member.guild.id)
    if not settings:
        return

    # إعطاء الرول التلقائي
    if settings.get("auto_role"):
        role = discord.utils.get(member.guild.roles, name=settings["auto_role"])
        if role:
            try:
                await member.add_roles(role)
            except Exception as e:
                print(f"تعذر إعطاء الرول: {e}")

    # تعيين اللقب التلقائي
    if settings.get("auto_nickname"):
        try:
            await member.edit(nick=settings["auto_nickname"])
        except Exception as e:
            print(f"تعذر تغيير اللقب: {e}")

# --- الخيار الثالث: رسائل الوداع ---
@bot.event
async def on_member_remove(member):
    settings = database.get_settings(member.guild.id)
    if not settings or not settings.get("farewell_channel"):
        return

    channel = discord.utils.get(member.guild.text_channels, name=settings["farewell_channel"])
    if not channel:
        try:
            channel = member.guild.get_channel(int(settings["farewell_channel"]))
        except:
            pass

    if channel:
        embed = discord.Embed(
            title=settings.get("farewell_title", "وداعاً"),
            description=settings.get("farewell_desc", "").replace("{user}", member.mention),
            color=discord.Color.red()
        )
        if settings.get("farewell_img"):
            embed.set_image(url=settings["farewell_img"])

        # إنشاء الزر إذا كان مفاعلاً
        view = None
        action = settings.get("farewell_action")
        if action in ["ban", "timeout"]:
            class FarewellView(discord.ui.View):
                @discord.ui.button(label=f"تطبيق {action.upper()}", style=discord.ButtonStyle.danger)
                async def btn_callback(self, interaction, button):
                    if action == "ban":
                        await member.ban(reason="عن طريق زر الوداع")
                        await interaction.response.send_message("تم حظر العضو بنجاح.", ephemeral=True)
                    elif action == "timeout":
                        await member.timeout(timedelta(minutes=10), reason="عن طريق زر الوداع")
                        await interaction.response.send_message("تم إعطاء تايم أوت للعضو.", ephemeral=True)
            view = FarewellView()

        await channel.send(embed=embed, view=view)

# --- الخيار الأول والثاني والرابع: الرسائل، الميديا، الكلمات، الردود ---
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    settings = database.get_settings(message.guild.id)
    if not settings:
        await bot.process_commands(message)
        return

    # 1. خيار قنوات الميديا فقط
    media_channels = settings.get("media_channels", [])
    if message.channel.name in media_channels or str(message.channel.id) in media_channels:
        has_media = len(message.attachments) > 0 or any(ext in message.content.lower() for ext in ['.jpg', '.png', '.gif', '.mp4', 'http://', 'https://'])
        if not has_media:
            await message.delete()
            warn_msg = settings.get("media_warning", "عذراً هذه القناة للميديا فقط!").replace("{user}", message.author.mention)
            await message.channel.send(warn_msg, delete_after=5)
            return

    # 2. خيار الكلمات المحظورة والعقوبات
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
            # تطبيق العقوبة عند التجاوز
            p_type = settings.get("punishment_type", "timeout")
            t_min = settings.get("timeout_minutes", 10)
            
            try:
                if p_type == "timeout":
                    await message.author.timeout(timedelta(minutes=t_min), reason="تجاوز عدد الكلمات المحظورة")
                elif p_type == "kick":
                    await message.author.kick(reason="تجاوز عدد الكلمات المحظورة")
                elif p_type == "mute":
                    await message.author.timeout(timedelta(days=7), reason="كتم كامل لتجاوز المخالفات")
                
                await message.channel.send(f"تم تطبيق عقوبة ({p_type}) على {message.author.mention} لتكرار المخالفة.")
            except Exception as e:
                await message.channel.send(f"تعذر تطبيق العقوبة: تحقق من صلاحيات البوت.")
            
            violations[g_id][u_id] = 0
        return

    # 3. خيار الردود التلقائية
    auto_resp = settings.get("auto_responses", {})
    if msg_content in auto_resp:
        await message.channel.send(auto_resp[msg_content])
        return

    await bot.process_commands(message)

# تشغيل البوت بواسطة التوكن من البيئة
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
