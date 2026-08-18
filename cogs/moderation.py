import discord
from discord import app_commands
from discord.ext import commands


class ModerationSystem(commands.Cog):

  def __init__(self, bot):
    self.bot = bot

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
      reason: str = "لم يُذكر سبب",
  ):
    from datetime import timedelta

    try:
      await member.timeout(timedelta(minutes=minutes), reason=reason)
      embed = discord.Embed(
          title="🔇 تم إسكات العضو بنجاح",
          description=(
              f"العضو: {member.mention}\nالمدة: {minutes}"
              f" دقائق\nالسبب: {reason}"
          ),
          color=discord.Color.red(),
      )
      await interaction.response.send_message(embed=embed)
    except Exception as e:
      await interaction.response.send_message(
          f"❌ تعذر تطبيق العقوبة: {e}", ephemeral=True
      )

  # أمر مسح التحذيرات أو إدارتها
  @app_commands.command(name="lock", description="قفل القناة الحالية مؤقتاً")
  @app_commands.checks.has_permissions(manage_channels=True)
  async def lock(self, interaction: discord.Interaction):
    channel = interaction.channel
    overwrite = channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    
    embed = discord.Embed(
        title="🔒 قفل القناة",
        description="تم قفل هذه القناة وإيقاف الإرسال مؤقتاً.",
        color=discord.Color.dark_red(),
    )
    await interaction.response.send_message(embed=embed)


async def setup(bot):
  await bot.add_cog(ModerationSystem(bot))
