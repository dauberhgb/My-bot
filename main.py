import os
import json
import threading
import io
import asyncio
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import discord
from discord import app_commands
from discord.ext import commands, tasks
import requests
import database

# ==========================================
# 0. إعدادات الأمان و OAuth2 (Discord)
# ==========================================
CLIENT_ID = os.getenv("CLIENT_ID", "YOUR_CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "YOUR_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "https://my-bot-05wx.onrender.com/callback")
DISCORD_API_ENDPOINT = "https://discord.com/api/v10"

# ==========================================
# 1. قاموس الترجمة
# ==========================================
TRANSLATIONS = {
    'ar': {
        'title': 'لوحة التحكم',
        # ... (باقي الترجمات محفوظة كما هي)
    },
    'en': {
        # ... (باقي الترجمات محفوظة كما هي)
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

def is_manager(interaction: discord.Interaction) -> bool:
    if not interaction.guild: return False
    if interaction.user.id == interaction.guild.owner_id: return True
    perms = interaction.user.guild_permissions
    return perms.manage_guild or perms.administrator or perms.manage_roles

async def send_audit_log(guild, title, description, color=discord.Color.orange()):
    settings = database.get_settings(guild.id)
    if not settings or not settings.get("log_channel"): return
    log_ch_id = settings.get("log_channel")
    channel = guild.get_channel(int(log_ch_id)) if str(log_ch_id).isdigit() else discord.utils.get(guild.text_channels, name=log_ch_id)
    if channel:
        embed = discord.Embed(title=f"📜 {title}", description=description, color=color)
        try: await channel.send(embed=embed)
        except Exception as e: print(f"تعذر إرسال السجل: {e}")

# ==========================================
# 3. إعداد خادم الويب (Flask)
# ==========================================
app = Flask(__name__)
app.secret_key = os.urandom(24)

# (نحتفظ بنفس دوال Flask السابقة كما هي)
@app.route('/')
def home(): return redirect(url_for('guild_list'))
@app.route('/login')
def login(): return redirect(f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={requests.utils.quote(REDIRECT_URI)}&response_type=code&scope=identify%20guilds")

# ==========================================
# 6. نظام التذاكر المطور (تم دمجه بالكامل)
# ==========================================
class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="إغلاق التكت والأرشفة 🔒", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⏳ جاري الأرشفة...", ephemeral=True)
        thread = interaction.channel
        settings = database.get_settings(interaction.guild_id)
        archive_ch_id = settings.get("ticket_archive_channel")
        
        messages = []
        async for msg in thread.history(limit=500, oldest_first=True):
            messages.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author}: {msg.clean_content}")

        transcript_file = discord.File(io.BytesIO("\n".join(messages).encode('utf-8')), filename=f"transcript-{thread.name}.txt")
        archive_channel = interaction.guild.get_channel(int(archive_ch_id)) if str(archive_ch_id).isdigit() else None
        if archive_channel:
            await archive_channel.send(f"📁 أرشيف تكت: {thread.name}", file=transcript_file)
        
        await send_audit_log(interaction.guild, "إغلاق تكت", f"أغلق {interaction.user.mention} التكت: {thread.name}")
        await thread.edit(archived=True, locked=True)

    @discord.ui.button(label="استلام التذكرة 🙋‍♂️", style=discord.ButtonStyle.success, custom_id="claim_ticket_btn")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_manager(interaction): return await interaction.response.send_message("للمشرفين فقط!", ephemeral=True)
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.channel.send(f"✅ تم استلام التذكرة بواسطة: {interaction.user.mention}")

class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="الدعم الفني", emoji="🛠️", value="general"),
            discord.SelectOption(label="الشكاوى", emoji="⚠️", value="reports"),
            discord.SelectOption(label="طلب رتب", emoji="🎖️", value="roles")
        ]
        super().__init__(placeholder="اختر قسم التذكرة...", options=options)

    async def callback(self, interaction: discord.Interaction):
        thread = await interaction.channel.create_thread(name=f"ticket-{self.values[0]}-{interaction.user.name}", type=discord.ChannelType.private_thread)
        await thread.add_user(interaction.user)
        await thread.send(f"مرحباً {interaction.user.mention}، سيقوم الإداريون بالرد عليك قريباً.", view=TicketCloseView())
        await interaction.response.send_message(f"✅ تم إنشاء التذكرة: {thread.mention}", ephemeral=True)

class TicketLaunchView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

# ==========================================
# 4 & 5 & 7. أوامر وأحداث البوت الأساسية
# ==========================================
@bot.event
async def on_ready():
    bot.add_view(TicketLaunchView())
    bot.add_view(TicketCloseView())
    print(f'تم تشغيل البوت: {bot.user}')

@bot.tree.command(name="setup-tickets", description="إرسال لوحة التذاكر المحدثة")
@app_commands.checks.has_permissions(administrator=True)
async def setup_tickets_command(interaction: discord.Interaction):
    settings = database.get_settings(interaction.guild_id)
    ch = interaction.guild.get_channel(int(settings.get("ticket_channel", 0)))
    if ch:
        await ch.send("🎫 **مركز الدعم:** اختر قسماً لفتح تذكرة:", view=TicketLaunchView())
        await interaction.response.send_message("تم!", ephemeral=True)

# ... (باقي كود البوت كما هو)

if __name__ == "__main__":
    bot.run(os.getenv("TOKEN"))
