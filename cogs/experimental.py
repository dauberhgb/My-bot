import random
import discord
from discord import app_commands
from discord.ext import commands


class ExperimentalTools(commands.Cog):

  def __init__(self, bot):
    self.bot = bot

  # أمر حظ السيرفر اليومي (نسبة الحظ الإبداعية)
  @app_commands.command(
      name="luck", description="احسب نسبة حظك اليوم في السيرفر بشكل عشوائي ومرح"
  )
  async def luck(self, interaction: discord.Interaction):
    score = random.randint(0, 100)
    
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
