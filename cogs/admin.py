import discord
from discord.ext import commands

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='leaveguild', hidden=True)
    @commands.is_owner()
    async def leave_guild(self, ctx: commands.Context, guild_id: int):
        # محاولة حذف رسالة الأمر للسرية
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            await ctx.send("❌ السيرفر غير موجود أو لست عضواً فيه.", delete_after=5)
            return

        try:
            guild_name = guild.name
            await guild.leave()
            await ctx.send(f"✅ تم مغادرة السيرفر: **{guild_name}** (`{guild_id}`)", delete_after=5)
        except discord.HTTPException as e:
            await ctx.send(f"❌ خطأ أثناء المغادرة: {e}", delete_after=5)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
