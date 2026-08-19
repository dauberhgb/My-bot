import discord
from discord import app_commands
from discord.ext import commands
import database


class UtilityTools(commands.Cog):

  def __init__(self, bot):
    self.bot = bot

  # دالة مساعدة لجلب لغة السيرفر
  def get_lang(self, guild_id):
    if not guild_id:
      return "ar"
    settings = database.get_settings(str(guild_id))
    return settings.get("language", "ar")

  # نظام التذاكر السريع (Ticket Creation)
  @app_commands.command(
      name="ticket", description="إنشاء رسالة تذاكر الدعم الفني في القناة"
  )
  @app_commands.checks.has_permissions(manage_channels=True)
  async def ticket(self, interaction: discord.Interaction):
    lang = self.get_lang(interaction.guild_id)

    class TicketView(discord.ui.View):

      def __init__(self, lang_code):
        super().__init__(timeout=None)
        self.lang_code = lang_code
        
        # تحديث نص الزر حسب اللغة
        btn_label = "Open New Ticket 🎫" if self.lang_code == "en" else "فتح تذكرة جديدة 🎫"
        self.create_ticket.label = btn_label

      @discord.ui.button(
          style=discord.ButtonStyle.success,
          custom_id="create_ticket",
      )
      async def create_ticket(
          self, interaction: discord.Interaction, button: discord.ui.Button
      ):
        guild = interaction.guild
        current_lang = database.get_settings(str(guild.id)).get("language", "ar") if guild else "ar"
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            ),
            guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            ),
        }
        
        cat_name = "Tickets" if current_lang == "en" else "التذاكر"
        category = discord.utils.get(guild.categories, name=cat_name)
        if not category:
          category = await guild.create_category(cat_name)

        channel_prefix = "ticket-" if current_lang == "en" else "تذكرة-"
        channel = await guild.create_text_channel(
            f"{channel_prefix}{interaction.user.name}",
            category=category,
            overwrites=overwrites,
        )
        
        success_msg = f"✅ Your ticket has been opened successfully: {channel.mention}" if current_lang == "en" else f"✅ تم فتح تذكرتك بنجاح: {channel.mention}"
        await interaction.response.send_message(
            success_msg, ephemeral=True
        )

    if lang == "en":
      embed = discord.Embed(
          title="🎫 Support & Tickets System",
          description=(
              "Need help or have an inquiry? Click the button below to open a private ticket."
          ),
          color=discord.Color.blue(),
      )
      response_msg = "Ticket panel sent successfully!"
    else:
      embed = discord.Embed(
          title="🎫 نظام الدعم الفني والتذاكر",
          description=(
              "هل تحتاج إلى مساعدة أو لديك استفسار؟ اضغط على الزر أدناه لفتح تذكرة خاصة."
          ),
          color=discord.Color.blue(),
      )
      response_msg = "تم إرسال لوحة التذاكر بنجاح!"

    await interaction.channel.send(embed=embed, view=TicketView(lang))
    await interaction.response.send_message(
        response_msg, ephemeral=True
    )


async def setup(bot):
  await bot.add_cog(UtilityTools(bot))
