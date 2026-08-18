import discord
from discord import app_commands
from discord.ext import commands


class UtilityTools(commands.Cog):

  def __init__(self, bot):
    self.bot = bot

  # نظام التذاكر السريع (Ticket Creation)
  @app_commands.command(
      name="ticket", description="إنشاء رسالة تذاكر الدعم الفني في القناة"
  )
  @app_commands.checks.has_permissions(manage_channels=True)
  async def ticket(self, interaction: discord.Interaction):
    class TicketView(discord.ui.View):

      def __init__(self):
        super().__init__(timeout=None)

      @discord.ui.button(
          label="فتح تذكرة جديدة 🎫",
          style=discord.ButtonStyle.success,
          custom_id="create_ticket",
      )
      async def create_ticket(
          self, interaction: discord.Interaction, button: discord.ui.Button
      ):
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            ),
            guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            ),
        }
        category = discord.utils.get(guild.categories, name="التذاكر")
        if not category:
          category = await guild.create_category("التذاكر")

        channel = await guild.create_text_channel(
            f"تذكرة-{interaction.user.name}",
            category=category,
            overwrites=overwrites,
        )
        await interaction.response.send_message(
            f"✅ تم فتح تذكرتك بنجاح: {channel.mention}", ephemeral=True
        )

    embed = discord.Embed(
        title="🎫 نظام الدعم الفني والتذاكر",
        description=(
            "هل تحتاج إلى مساعدة أو لديك استفسار؟ اضغط على الزر أدناه لفتح"
            " تذكرة خاصة."
        ),
        color=discord.Color.blue(),
    )
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message(
        "تم إرسال لوحة التذاكر بنجاح!", ephemeral=True
    )


async def setup(bot):
  await bot.add_cog(UtilityTools(bot))
