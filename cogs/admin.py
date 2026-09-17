import discord
from discord.ext import commands

class GuildSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        options = []
        for guild in bot.guilds[:25]:
            options.append(discord.SelectOption(
                label=guild.name[:100],
                description=f"ID: {guild.id} | Members: {guild.member_count}",
                value=str(guild.id)
            ))
        super().__init__(placeholder="اختر السيرفر للمغادرة...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("❌ للمالك فقط.", ephemeral=True)
            return
        
        guild_id = int(self.values[0])
        guild = self.bot.get_guild(guild_id)
        if guild:
            name = guild.name
            await guild.leave()
            await interaction.response.send_message(f"✅ تم مغادرة السيرفر **{name}** (`{guild_id}`).", ephemeral=True)
        else:
            await interaction.response.send_message("❌ لم يتم العثور على السيرفر أو غادره مسبقاً.", ephemeral=True)

class GuildSelectView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=60)
        self.add_item(GuildSelect(bot))

class PrefixLeaveCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='leaveserver', hidden=True)
    @commands.is_owner()
    async def leave_server_prefix(self, ctx: commands.Context):
        # التحقق هل الأمر في الخاص أم لا
        if ctx.guild is not None:
            try:
                await ctx.message.delete()
            except discord.Forbidden:
                pass
            await ctx.send("⚠️ يرجى استخدام هذا الأمر في الخاص (DM) معي لضمان السرية التامة.", delete_after=5)
            return

        view = GuildSelectView(self.bot)
        await ctx.send("📋 اختر السيرفر للمغادرة:", view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(PrefixLeaveCog(bot))
