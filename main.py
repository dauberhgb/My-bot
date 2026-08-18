import os
import json
import threading
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, jsonify
import discord
from discord import app_commands
from discord.ext import commands
import database

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

app = Flask(__name__)

@app.route('/')
def home():
    return redirect(url_for('guild_list'))

@app.route('/guilds')
def guild_list():
    bot_guilds = [{"id": str(g.id), "name": g.name, "icon": g.icon.key if g.icon else None} for g in bot.guilds]
    return render_template('guilds.html', guilds=bot_guilds)

@app.route('/dashboard/<guild_id>')
def dashboard(guild_id):
    guild = bot.get_guild(int(guild_id))
    if not guild:
        return "البوت غير متواجد في هذا السيرفر!", 404

    channels = [{"id": str(c.id), "name": c.name} for c in guild.text_channels]
    roles = [{"id": str(r.id), "name": r.name} for r in guild.roles if not r.is_default()]
    stats = {"member_count": guild.member_count, "channel_count": len(guild.channels), "role_count": len(guild.roles)}
    settings = database.get_settings(guild_id)

    return render_template('index.html', guild=guild, channels=channels, roles=roles, settings=settings, stats=stats)

@app.route('/save/<guild_id>', methods=['POST'])
def save(guild_id):
    guild = bot.get_guild(int(guild_id))
    if not guild:
        return jsonify({"status": "error", "message": "السيرفر غير موجود!"}), 400

    media_channels = request.form.getlist('media_channels')
    banned_words = [w.strip().lower() for w in request.form.get('banned_words', '').split(',') if w.strip()]
    
    auto_responses = {}
    keys = request.form.getlist('resp_keys[]')
    values = request.form.getlist('resp_values[]')
    for k, v in zip(keys, values):
        if k.strip() and v.strip():
            auto_responses[k.strip().lower()] = v.strip()

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
    return jsonify({"status": "success", "message": "تم حفظ الإعدادات بنجاح!"})

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_web_server, daemon=True).start()

@bot.event
async def on_ready():
    try:
        for guild in bot.guilds:
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
        print("تمت مزامنة أوامر السلاش بنجاح!")
    except Exception as e:
        print(f"خطأ المزامنة: {e}")
    print(f'البوت يعمل الآن باسم: {bot.user}')

# ==========================================
# 🎫 نظام تذاكر الدعم الفني الخارق (Ticket System)
# ==========================================
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="فتح تذكرة دعم 🎫", style=discord.ButtonStyle.success, custom_id="create_ticket_btn")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="🎫 التذاكر")
        if not category:
            category = await guild.create_category("🎫 التذاكر")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }

        channel_name = f"ticket-{interaction.user.name}"
        ticket_channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)

        close_view = TicketCloseView()
        embed = discord.Embed(
            title="🎟️ تذكرة جديدة",
            description=f"مرحباً {interaction.user.mention}!\nطرح فريق الإدارة قريباً لمساعدتك. للغلق اضغط على الزر أدناه.",
            color=discord.Color.green()
        )
        await ticket_channel.send(embed=embed, view=close_view)
        await interaction.response.send_message(f"✅ تم فتح تذكرتك بنجاح: {ticket_channel.mention}", ephemeral=True)

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="إغلاق التذكرة 🔒", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 سيتم حذف القناة خلال 5 ثوانٍ...")
        await discord.utils.sleep_until(discord.utils.utcnow() + timedelta(seconds=5))
        await interaction.channel.delete()

@bot.tree.command(name="ticket-panel", description="إرسال لوحة تفاعلية لفتح التذاكر في الشات الحالي")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛠️ مركز الدعم الفني والمساعدة",
        description="هل تواجه مشكلة أو تحتاج إلى مساعدة؟ اضغط على الزر أدناه لفتح تذكرة خاصة مع الإدارة فوراً.",
        color=discord.Color.blurple()
    )
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message("✅ تم إنشاء لوحة التذاكر بنجاح!", ephemeral=True)

# ==========================================
# 🔊 نظام الغرف الصوتية المؤقتة (Temp Voice Channels)
# ==========================================
@bot.event
async def on_voice_state_update(member, before, after):
    # افتراض أن الروم الرئيسية اسمها "➕ | انشئ غرفتك"
    if after.channel and after.channel.name == "➕ | انشئ غرفتك":
        guild = member.guild
        category = after.channel.category
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=True),
            member: discord.PermissionOverwrite(manage_channels=True, mute_members=True, deafen_members=True)
        }
        
        new_channel = await guild.create_voice_channel(f"🎙️ | روم {member.display_name}", category=category, overwrites=overwrites)
        await member.move_to(new_channel)
        
        def check(b,, a):
            return len(new_channel.members) == 0

        try:
            await bot.wait_for('voice_state_update', check=check, timeout=86400)
            if len(new_channel.members) == 0:
                await new_channel.delete()
        except:
            if len(new_channel.members) == 0:
                await new_channel.delete()

@bot.tree.command(name="setup", description="الانتقال المباشر إلى لوحة تحكم البوت")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    base_url = os.getenv("DASHBOARD_URL", "").rstrip('/')
    dashboard_link = f"{base_url}/dashboard/{guild_id}" if base_url else f"https://{os.getenv('RENDER_SERVICE_NAME', 'app')}.onrender.com/dashboard/{guild_id}"

    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="فتح لوحة التحكم الخارقة ⚙️", url=dashboard_link, style=discord.ButtonStyle.link))
    
    embed = discord.Embed(title="🛠️ لوحة التحكم المتطورة", description="اضغط بالأسفل لضبط إعدادات السيرفر:", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
