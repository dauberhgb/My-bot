import discord
from discord import app_commands
from discord.ext import commands
import database


class DeveloperTools(commands.Cog):

  def __init__(self, bot):
    self.bot = bot
    self.owner_id = 1462429084377157832  # معرفك الخاص

  # دالة مساعدة لجلب لغة السيرفر
  def get_lang(self, guild_id):
    if not guild_id:
      return "ar"
    settings = database.get_settings(str(guild_id))
    return settings.get("language", "ar")

  # أمر فحص حالة قاعدة البيانات وصيانتها
  @app_commands.command(
      name="db_status", description="عرض حالة اتصال قاعدة البيانات (خاص بالمطور)"
  )
  async def db_status(self, interaction: discord.Interaction):
    lang = self.get_lang(interaction.guild_id)

    if interaction.user.id != self.owner_id:
      msg = "❌ This command is restricted to the bot developer only!" if lang == "en" else "❌ هذا الأمر مخصص لمطور البوت فقط!"
      await interaction.response.send_message(msg, ephemeral=True)
      return

    try:
      # فحص جلب الإعدادات كاختبار لاتصال قاعدة البيانات
      settings = database.get_settings(str(interaction.guild_id))
      
      if lang == "en":
        status = "Connected and working efficiently ✅" if settings is not None else "Connected, but no data recorded for this server ⚠️"
        embed = discord.Embed(
            title="🛠️ Database System Check",
            description=f"Database Status: **{status}**",
            color=discord.Color.blue(),
        )
      else:
        status = "متصلة وتعمل بكفاءة ✅" if settings is not None else "متصلة ولكن لا توجد بيانات مسجلة لهذا السيرفر ⚠️"
        embed = discord.Embed(
            title="🛠️ فحص نظام قواعد البيانات",
            description=f"حالة الـ Database: **{status}**",
            color=discord.Color.blue(),
        )

      await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
      err_msg = f"❌ An error occurred while connecting to the database: {e}" if lang == "en" else f"❌ حدث خطأ في الاتصال بقاعدة البيانات: {e}"
      await interaction.response.send_message(err_msg, ephemeral=True)


async def setup(bot):
  await bot.add_cog(DeveloperTools(bot))
