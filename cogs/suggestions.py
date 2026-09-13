import discord
from discord import app_commands
from discord.ext import commands
import database as db

suggestion_votes = {}  # {message_id: {'up': set(), 'down': set()}}

TRANSLATIONS = {
    "ar": {
        "title": "💡 اقتراح جديد",
        "status": "الحالة",
        "accepted": "✅ مقبول بواسطة {user}",
        "rejected": "❌ مرفوض بواسطة {user}",
        "no_perm": "❌ ليس لديك صلاحية لإدارة السيرفر.",
        "accepted_resp": "تم قبول الاقتراح وتحديثه.",
        "rejected_resp": "تم رفض الاقتراح وتحديثه."
    },
    "en": {
        "title": "💡 New Suggestion",
        "status": "Status",
        "accepted": "✅ Accepted by {user}",
        "rejected": "❌ Rejected by {user}",
        "no_perm": "❌ You don't have permission to manage the server.",
        "accepted_resp": "Suggestion accepted and updated.",
        "rejected_resp": "Suggestion rejected and updated."
    }
}

def get_guild_lang(guild_id):
    if not guild_id:
        return "ar"
    try:
        settings = db.get_settings(guild_id)
        if isinstance(settings, dict):
            return settings.get("language", "ar")
    except Exception:
        pass
    return "ar"

class SuggestionButtonView(discord.ui.View):
    def __init__(self, guild_id=None):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="👍 0", style=discord.ButtonStyle.secondary, custom_id="sugg_up")
    async def up(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg_id = interaction.message.id
        if msg_id not in suggestion_votes:
            suggestion_votes[msg_id] = {'up': set(), 'down': set()}
        
        uid = interaction.user.id
        s = suggestion_votes[msg_id]
        if uid in s['up']:
            s['up'].remove(uid)
        else:
            s['up'].add(uid)
            s['down'].discard(uid)
        
        up_count = len(s['up'])
        down_count = len(s['down'])
        
        for child in self.children:
            if child.custom_id == 'sugg_up':
                child.label = f"👍 {up_count}"
            elif child.custom_id == 'sugg_down':
                child.label = f"👎 {down_count}"
        
        await interaction.response.defer()
        await interaction.message.edit(view=self)

    @discord.ui.button(label="👎 0", style=discord.ButtonStyle.secondary, custom_id="sugg_down")
    async def down(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg_id = interaction.message.id
        if msg_id not in suggestion_votes:
            suggestion_votes[msg_id] = {'up': set(), 'down': set()}
        
        uid = interaction.user.id
        s = suggestion_votes[msg_id]
        if uid in s['down']:
            s['down'].remove(uid)
        else:
            s['down'].add(uid)
            s['up'].discard(uid)
        
        up_count = len(s['up'])
        down_count = len(s['down'])
        
        for child in self.children:
            if child.custom_id == 'sugg_up':
                child.label = f"👍 {up_count}"
            elif child.custom_id == 'sugg_down':
                child.label = f"👎 {down_count}"
        
        await interaction.response.defer()
        await interaction.message.edit(view=self)

    @discord.ui.button(label="✅", style=discord.ButtonStyle.green, custom_id="sugg_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = get_guild_lang(interaction.guild.id if interaction.guild else None)
        t = TRANSLATIONS[lang]
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(t["no_perm"], ephemeral=True)
        
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.add_field(name=t["status"], value=t["accepted"].format(user=interaction.user.mention), inline=False)
        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message(t["accepted_resp"], ephemeral=True)

    @discord.ui.button(label="❌", style=discord.ButtonStyle.red, custom_id="sugg_reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = get_guild_lang(interaction.guild.id if interaction.guild else None)
        t = TRANSLATIONS[lang]
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(t["no_perm"], ephemeral=True)
        
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.add_field(name=t["status"], value=t["rejected"].format(user=interaction.user.mention), inline=False)
        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message(t["rejected_resp"], ephemeral=True)

class SuggestionsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="suggestion", description="إرسال اقتراح جديد للسيرفر")
    @app_commands.describe(text="نص الاقتراح")
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: (i.guild_id, i.user.id))  # حماية من السبام (استخدام كل 10 ثوانٍ)
    async def suggestion(self, interaction: discord.Interaction, text: str):
        guild_id = interaction.guild.id if interaction.guild else None
        lang = get_guild_lang(guild_id)
        t = TRANSLATIONS[lang]
        
        embed = discord.Embed(
            title=t["title"],
            description=text,
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f"ID: {interaction.user.id}")
        
        view = SuggestionButtonView(guild_id=guild_id)
        await interaction.response.send_message(embed=embed, view=view)

    @suggestion.error
    async def suggestion_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            lang = get_guild_lang(interaction.guild.id if interaction.guild else None)
            msg = f"⏳ Please wait {error.retry_after:.1f}s before sending another suggestion." if lang == "en" else f"⏳ يرجى الانتظار {error.retry_after:.1f} ثانية قبل إرسال اقتراح آخر."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        else:
            raise error

async def setup(bot):
    await bot.add_cog(SuggestionsCog(bot))
