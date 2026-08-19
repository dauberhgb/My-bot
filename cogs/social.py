import random
import discord
from discord import app_commands
from discord.ext import commands
import database


class Social(commands.Cog):

  def __init__(self, bot):
    self.bot = bot

  # دالة مساعدة لجلب لغة السيرفر
  def get_lang(self, guild_id):
    if not guild_id:
      return "ar"
    settings = database.get_settings(str(guild_id))
    return settings.get("language", "ar")

  # 1. أمر نظام الحيوان الأليف الافتراضي
  @app_commands.command(
      name="pet", description="تفاعل مع حيوانك الأليف الافتراضي (إطعام، اللعب)"
  )
  @app_commands.choices(
      action=[
          app_commands.Choice(name="إطعام / Feed", value="feed"),
          app_commands.Choice(name="اللعب / Play", value="play"),
          app_commands.Choice(name="فحص الحالة / Status", value="status"),
      ]
  )
  async def pet(self, interaction: discord.Interaction, action: str):
    lang = self.get_lang(interaction.guild_id)
    user_name = interaction.user.display_name

    if lang == "en":
      if action == "feed":
        msg = f"🍽️ {user_name} fed their pet! It looks happy and grateful."
      elif action == "play":
        msg = f"🎾 {user_name} played with their pet and they had a great time!"
      else:
        msg = f"📊 {user_name}'s pet status:\n- Health: 100%\n- Hunger: Normal\n- Mood: Playful!"
      title = "🐾 Virtual Server Companion"
    else:
      if action == "feed":
        msg = f"🍽️ قام {user_name} بإطعام حيوانه الأليف! يبدو سعيداً وممتناً."
      elif action == "play":
        msg = f"🎾 لعب {user_name} مع حيوانه الأليف وقضيا وقتاً ممتعاً معاً!"
      else:
        msg = f"📊 حالة حيوان {user_name} الأليف:\n- الصحة: 100%\n- الجوع: طبيعي\n- المزاج: مرح!"
      title = "🐾 رفيق السيرفر الافتراضي"

    embed = discord.Embed(title=title, description=msg, color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

  # 2. أمر مبارزات المخاطرة والسحب
  @app_commands.command(
      name="duel", description="تحدَّ عضواً آخر في مباراة حظ سريعة"
  )
  @app_commands.describe(member="العضو المراد تحديه")
  async def duel(self, interaction: discord.Interaction, member: discord.Member):
    lang = self.get_lang(interaction.guild_id)
    
    if member.bot or member == interaction.user:
      err_msg = "❌ You cannot duel yourself or a bot!" if lang == "en" else "❌ لا يمكنك تحدي نفسك أو بوت!"
      await interaction.response.send_message(err_msg, ephemeral=True)
      return

    winner = random.choice([interaction.user, member])
    
    if lang == "en":
      embed = discord.Embed(
          title="⚔️ Duel Arena",
          description=f"{interaction.user.mention} and {member.mention} fought bravely!\n\n🏆 The winner of this round is: **{winner.mention}**!",
          color=discord.Color.gold(),
      )
    else:
      embed = discord.Embed(
          title="⚔️ حلبة المبارزة",
          description=f"تقاتل كل من {interaction.user.mention} و {member.mention} بشجاعة!\n\n🏆 الفائز في هذه الجولة هو: **{winner.mention}**!",
          color=discord.Color.gold(),
      )
      
    await interaction.response.send_message(embed=embed)


async def setup(bot):
  await bot.add_cog(Social(bot))
