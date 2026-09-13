import discord
from discord import app_commands
from discord.ext import commands
import database

audit_channels_map = {}

TRANSLATIONS = {
    "ar": {
        "set_success": "✅ تم تحديد قناة السجل بنجاح إلى {channel}",
        "ch_create_title": "📁 إنشاء قناة جديدة",
        "ch_delete_title": "🗑️ حذف قناة",
        "role_create_title": "🛡️ إنشاء رتبة جديدة",
        "role_delete_title": "🛡️ حذف رتبة",
        "member_remove_title": "👋 مغادرة عضو",
        "name": "الاسم",
        "type": "النوع",
        "id": "الآيدي",
        "member": "العضو"
    },
    "en": {
        "set_success": "✅ Audit log channel set to {channel}",
        "ch_create_title": "📁 Channel Created",
        "ch_delete_title": "🗑️ Channel Deleted",
        "role_create_title": "🛡️ Role Created",
        "role_delete_title": "🛡️ Role Deleted",
        "member_remove_title": "👋 Member Left",
        "name": "Name",
        "type": "Type",
        "id": "ID",
        "member": "Member"
    }
}

def get_lang(guild_id):
    try:
        settings = database.get_settings(guild_id)
        if isinstance(settings, dict):
            return settings.get("language", "ar")
    except Exception:
        pass
    return "ar"

class AuditLogsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="set_audit_channel", description="تحديد قناة سجل التدقيق الموسع")
    @app_commands.describe(channel="القناة المخصصة لسجل التدقيق")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_audit_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        audit_channels_map[interaction.guild.id] = channel.id
        lang = get_lang(interaction.guild.id)
        msg = TRANSLATIONS[lang]["set_success"].format(channel=channel.mention)
        await interaction.response.send_message(msg, ephemeral=True)

    async def _log(self, guild, embed):
        ch_id = audit_channels_map.get(guild.id)
        if not ch_id:
            ch = discord.utils.get(guild.text_channels, name="audit-logs")
            if ch:
                ch_id = ch.id
            else:
                return
        channel = guild.get_channel(ch_id)
        if channel:
            try:
                await channel.send(embed=embed)
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        lang = get_lang(channel.guild.id)
        t = TRANSLATIONS[lang]
        embed = discord.Embed(title=t["ch_create_title"], color=discord.Color.green(), timestamp=discord.utils.utcnow())
        embed.add_field(name=t["name"], value=channel.name, inline=True)
        embed.add_field(name=t["type"], value=str(channel.type), inline=True)
        embed.add_field(name=t["id"], value=f"`{channel.id}`", inline=False)
        await self._log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        lang = get_lang(channel.guild.id)
        t = TRANSLATIONS[lang]
        embed = discord.Embed(title=t["ch_delete_title"], color=discord.Color.red(), timestamp=discord.utils.utcnow())
        embed.add_field(name=t["name"], value=channel.name, inline=True)
        embed.add_field(name=t["type"], value=str(channel.type), inline=True)
        embed.add_field(name=t["id"], value=f"`{channel.id}`", inline=False)
        await self._log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        lang = get_lang(role.guild.id)
        t = TRANSLATIONS[lang]
        embed = discord.Embed(title=t["role_create_title"], color=discord.Color.blue(), timestamp=discord.utils.utcnow())
        embed.add_field(name=t["name"], value=role.name, inline=True)
        embed.add_field(name=t["id"], value=f"`{role.id}`", inline=True)
        await self._log(role.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        lang = get_lang(role.guild.id)
        t = TRANSLATIONS[lang]
        embed = discord.Embed(title=t["role_delete_title"], color=discord.Color.orange(), timestamp=discord.utils.utcnow())
        embed.add_field(name=t["name"], value=role.name, inline=True)
        embed.add_field(name=t["id"], value=f"`{role.id}`", inline=True)
        await self._log(role.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        lang = get_lang(member.guild.id)
        t = TRANSLATIONS[lang]
        embed = discord.Embed(title=t["member_remove_title"], color=discord.Color.dark_grey(), timestamp=discord.utils.utcnow())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name=t["member"], value=f"{member} (`{member.id}`)", inline=False)
        await self._log(member.guild, embed)

async def setup(bot):
    await bot.add_cog(AuditLogsCog(bot))
