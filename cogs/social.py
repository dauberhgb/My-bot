import random
import discord
from discord import app_commands
from discord.ext import commands


class Social(commands.Cog):

  def __init__(self, bot):
    self.bot = bot

  # 1. أمر نظام الحيوان الأليف الافتراضي (Tamagotchi)
  @app_commands.command(
      name="pet", description="تفاعل مع حيوانك الأليف الافتراضي (إطعام، اللعب)"
  )
  @app_commands.choices(
      action=[
          app_commands.Choice(name="إطعام (Feed)", value="feed"),
          app_commands.Choice(name="اللعب (Play)", value="play"),
          app_commands.Choice(name="فحص الحالة (Status)", value="status"),
      ]
  )
  async def pet(self, interaction: discord.Interaction, action: str):
    user_name = interaction.user.display_name

    if action == "feed":
      msg = f"🍽️ قام {user_name} بإطعام حيوانه الأليف! يبدو سعيداً وممتناً."
    elif action == "play":
      msg = f"🎾 لعب {user_name} مع حيوانه الأليف وقضيا وقتاً ممتعاً معاً!"
    else:
      msg = (
          f"📊 حالة حيوان {user_name} الأليف:\n- الصحة: 100%\n- الجوع: طبيعي\n-"
          " المزاج: مرح!"
      )

    embed = discord.Embed(
        title="🐾 رفيق السيرفر الافتراضي",
        description=msg,
        color=discord.Color.green(),
    )
    await interaction.response.send_message(embed=embed)

  # 2. أمر مبارزات المخاطرة والسحب
  @app_commands.command(
      name="duel", description="تحدَّ عضواً آخر في مباراة حظ سريعة"
  )
  @app_commands.describe(member="العضو المراد تحديه")
  async def duel(self, interaction: discord.Interaction, member: discord.Member):
    if member.bot or member == interaction.user:
      await interaction.response.send_message(
          "❌ لا يمكنك تحدي نفسك أو بوت!", ephemeral=True
      )
      return

    winner = random.choice([interaction.user, member])
    loser = member if winner == interaction.user else interaction.user

    embed = discord.Embed(
        title="⚔️ حلبة المبارزة",
        description=(
            f"تقاتل كل من {interaction.user.mention} و {member.mention} بشجاعة!\n\n🏆"
            f" الفائز في هذه الجولة هو: **{winner.mention}**!"
        ),
        color=discord.Color.gold(),
    )
    await interaction.response.send_message(embed=embed)


async def setup(bot):
  await bot.add_cog(Social(bot))
