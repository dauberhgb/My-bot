import discord
from discord import app_commands
from discord.ext import commands
import database


class DeveloperTools(commands.Cog):

  def __init__(self, bot):
    self.bot = bot
    self.owner_id = 1462429084377157832  # معرفك الخاص

  # أمر فحص حالة قاعدة البيانات وصيانتها
  @app_commands.command(
      name="db_status", description="عرض حالة اتصال قاعدة البيانات (خاص بالمطور)"
  )
  async def db_status(self, interaction: discord.Interaction):
    if interaction.user.id != self.owner_id:
      await interaction.response.send_message(
          "❌ هذا الأمر مخصص لمطور البوت فقط!", ephemeral=True
      )
      return

    try:
      # فحص جلب الإعدادات كاختبار لاتصال قاعدة البيانات
      settings = database.get_settings(str(interaction.guild_id))
      status = "متصلة وتعمل بكفاءة ✅" if settings is not None else "متصلة ولكن لا توجد بيانات مسجلة لهذا السيرفر ⚠️"
      
      embed = discord.Embed(
          title="🛠️ فحص نظام قواعد البيانات",
          description=f"حالة الـ Database: **{status}**",
          color=discord.Color.blue(),
      )
      await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
      await interaction.response.send_message(
          f"❌ حدث خطأ في الاتصال بقاعدة البيانات: {e}", ephemeral=True
      )


async def setup(bot):
  await bot.add_cog(DeveloperTools(bot))
