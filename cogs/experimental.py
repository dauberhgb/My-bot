import random
import discord
from discord import app_commands
from discord.ext import commands
import database


class ExperimentalTools(commands.Cog):

  def __init__(self, bot):
    self.bot = bot

  # دالة مساعدة لجلب لغة السيرفر
  def get_lang(self, guild_id):
    if not guild_id:
      return "ar"
    settings = database.get_settings(str(guild_id))
    return settings.get("language", "ar")

  # أمر حظ السيرفر اليومي (نسبة الحظ الإبداعية)
  @app_commands.command(
      name="luck", description="احسب نسبة حظك اليوم في السيرفر بشكل عشوائي ومرح"
  )
  async def luck(self, interaction: discord.Interaction):
    lang = self.get_lang(interaction.guild_id)
    score = random.randint(0, 100)
    
    if lang == "en":
      if score > 80:
        msg = "🌟 Your luck today is super! Today is your lucky day."
      elif score > 50:
        msg = "⚡ Your luck is good and balanced, keep up the great work."
      else:
        msg = "🌧️ Your luck is quite calm today, be careful with your steps!"
        
      embed = discord.Embed(
          title="🔮 Creative Luck Meter",
          description=f"Welcome {interaction.user.mention}!\nYour luck percentage today is: **{score}%**\n\n{msg}",
          color=discord.Color.purple(),
      )
    else:
      if score > 80:
        msg = "🌟 حظك اليوم خارق! اليوم هو يومك السعيد."
      elif score > 50:
        msg = "⚡ حظك جيد ومتوازن، استمر في العمل الرائع."
      else:
        msg = "🌧️ حظك اليوم هادئ جداً، كن حذراً في خطواتك!"

      embed = discord.Embed(
          title="🔮 مقياس الحظ الإبداعي",
          description=f"مرحباً {interaction.user.mention}!\nنسبة حظك اليوم هي: **{score}%**\n\n{msg}",
          color=discord.Color.purple(),
      )
      
    await interaction.response.send_message(embed=embed)


async def setup(bot):
  await bot.add_cog(ExperimentalTools(bot))
