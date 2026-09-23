import discord
from discord.ext import commands
import database


class DeveloperTools(commands.Cog):

  def __init__(self, bot):
    self.bot = bot

  @commands.command(name="db_status", hidden=True)
  @commands.is_owner()
  async def db_status_prefix(self, ctx: commands.Context):
    # التحقق هل الأمر في الخاص أم لا
    if ctx.guild is not None:
      try:
        await ctx.message.delete()
      except discord.Forbidden:
        pass
      await ctx.send("⚠️ يرجى استخدام هذا الأمر في الخاص (DM) معي لضمان السرية التامة.", delete_after=5)
      return

    try:
      # فحص اتصال قاعدة البيانات (نستخدم آيدي افتراضي أو نجلب حالة عامة)
      # نظراً لأنه في الخاص، سنقوم بفحص حالة الاتصال العامة عبر اختبار أمر ping
      database.client.admin.command('ping')
      
      embed = discord.Embed(
          title="🛠️ فحص نظام قواعد البيانات",
          description="حالة الـ Database: **متصلة وتعمل بكفاءة ✅**",
          color=discord.Color.blue(),
      )
      await ctx.send(embed=embed)
      
    except Exception as e:
      err_msg = f"❌ حدث خطأ في الاتصال بقاعدة البيانات: {e}"
      await ctx.send(err_msg)


async def setup(bot):
  await bot.add_cog(DeveloperTools(bot))
