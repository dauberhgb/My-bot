from datetime import timedelta
import discord
from discord import app_commands
from discord.ext import commands
import database


class ModerationSystem(commands.Cog):

  def __init__(self, bot):
    self.bot = bot

  # دالة مساعدة لجلب لغة السيرفر
  def get_lang(self, guild_id):
    if not guild_id:
      return "ar"
    settings = database.get_settings(str(guild_id))
    return settings.get("language", "ar")

  # أمر حظر مؤقت متقدم (Timeout)
  @app_commands.command(
      name="mute", description="إسكات (Timeout) عضو مزعج لفترة محددة"
  )
  @app_commands.describe(
      member="العضو المراد إسكاته",
      minutes="عدد الدقائق (مثلاً: 10)",
      reason="السبب",
  )
  @app_commands.checks.has_permissions(moderate_members=True)
  async def mute(
      self,
      interaction: discord.Interaction,
      member: discord.Member,
      minutes: int,
      reason: str = None,
  ):
    lang = self.get_lang(interaction.guild_id)
    default_reason = "No reason provided" if lang == "en" else "لم يُذكر سبب"
    used_reason = reason if reason else default_reason

    try:
      await member.timeout(timedelta(minutes=minutes), reason=used_reason)
      if lang == "en":
        embed = discord.Embed(
            title="🔇 Member Muted Successfully",
            description=(
                f"Member: {member.mention}\nDuration: {minutes}"
                f" minutes\nReason: {used_reason}"
            ),
            color=discord.Color.red(),
        )
      else:
        embed = discord.Embed(
            title="🔇 تم إسكات العضو بنجاح",
            description=(
                f"العضو: {member.mention}\nالمدة: {minutes}"
                f" دقائق\nالسبب: {used_reason}"
            ),
            color=discord.Color.red(),
        )
      await interaction.response.send_message(embed=embed)
    except Exception as e:
      err_msg = f"❌ Failed to apply penalty: {e}" if lang == "en" else f"❌ تعذر تطبيق العقوبة: {e}"
      await interaction.response.send_message(
          err_msg, ephemeral=True
      )

  # أمر مسح التحذيرات أو إدارتها
  @app_commands.command(name="lock", description="قفل القناة الحالية مؤقتاً")
  @app_commands.checks.has_permissions(manage_channels=True)
  async def lock(self, interaction: discord.Interaction):
    lang = self.get_lang(interaction.guild_id)
    channel = interaction.channel
    overwrite = channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    
    if lang == "en":
      embed = discord.Embed(
          title="🔒 Channel Locked",
          description="This channel has been locked and messaging is temporarily disabled.",
          color=discord.Color.dark_red(),
      )
    else:
      embed = discord.Embed(
          title="🔒 قفل القناة",
          description="تم قفل هذه القناة وإيقاف الإرسال مؤقتاً.",
          color=discord.Color.dark_red(),
      )
    await interaction.response.send_message(embed=embed)


async def setup(bot):
  await bot.add_cog(ModerationSystem(bot))
