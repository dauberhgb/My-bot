import discord
from discord.ext import commands
import io
import database

# 1. قائمة اختيار أقسام التذاكر
class TicketSelect(discord.ui.Select):
    def __init__(self, lang="ar"):
        self.lang = lang
        if lang == "en":
            options = [
                discord.SelectOption(label="General Support", description="Ask general questions or get help", emoji="🛠️", value="support"),
                discord.SelectOption(label="Report a Member", description="Report rule breakers or abuse", emoji="🚨", value="report"),
                discord.SelectOption(label="Store & Purchases", description="Inquiries about store items or roles", emoji="🛒", value="store"),
                discord.SelectOption(label="Staff Application", description="Apply to join the server staff team", emoji="📝", value="staff")
            ]
            placeholder = "Select ticket department..."
        else:
            options = [
                discord.SelectOption(label="الدعم الفني العام", description="طرح أسئلة عامة أو طلب المساعدة", emoji="🛠️", value="support"),
                discord.SelectOption(label="الإبلاغ عن عضو", description="الإبلاغ عن مخالفين أو إساءة استخدام", emoji="🚨", value="report"),
                discord.SelectOption(label="المتجر والاشتراكات", description="استفسارات بخصوص الشراء أو الرولات الخاصة", emoji="🛒", value="store"),
                discord.SelectOption(label="تقديم إداري", description="التقدم للانضمام لطاقم الإشراف والسيرفر", emoji="📝", value="staff")
            ]
            placeholder = "اختر قسم التذكرة المناسب..."

        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options, custom_id="advanced_ticket_select")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        settings = database.get_settings(guild.id)

        if settings.get("ticket_status", "enabled") == "disabled":
            msg = "Ticket system is currently disabled." if settings.get("language") == "en" else "نظام التذاكر معطل حالياً في هذا السيرفر."
            await interaction.followup.send(msg, ephemeral=True)
            return
            
        lang = settings.get("language", "ar")
        
        dept_value = self.values[0]
        dept_names = {
            "support": ("الدعم الفني", "Support"),
            "report": ("بلاغ", "Report"),
            "store": ("المتجر", "Store"),
            "staff": ("تقديم-إداري", "Staff-App")
        }
        dept_name_ar, dept_name_en = dept_names.get(dept_value, ("تذكرة", "Ticket"))
        dept_display = dept_name_en if lang == "en" else dept_name_ar

        cat_id = settings.get("ticket_category")
        support_role_id = settings.get("ticket_support_role")
        
        category = guild.get_channel(int(cat_id)) if cat_id and str(cat_id).isdigit() else None
        support_role = guild.get_role(int(support_role_id)) if support_role_id and str(support_role_id).isdigit() else None

        # التحقق من وجود تذكرة مفتوحة سابقة للمستخدم
        existing_channel = discord.utils.get(guild.text_channels, name=f"ticket-{dept_value}-{interaction.user.name.lower()}")
        if existing_channel:
            msg = f"You already have an open ticket here: {existing_channel.mention}" if lang == "en" else f"لديك تذكرة مفتوحة بالفعل في هذا القسم: {existing_channel.mention}"
            await interaction.followup.send(msg, ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        channel_name = f"ticket-{dept_value}-{interaction.user.name}"
        try:
            ticket_chan = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)

            if lang == "en":
                embed = discord.Embed(
                    title=f"🎫 Support Ticket — {dept_display}",
                    description=f"Welcome {interaction.user.mention},\nDepartment: **{dept_display}**\nPlease describe your issue clearly, and staff will assist you shortly.",
                    color=0x6366f1
                )
            else:
                embed = discord.Embed(
                    title=f"🎫 تذكرة دعم فني — {dept_display}",
                    description=f"مرحباً {interaction.user.mention}،\nالقسم المحدد: **{dept_display}**\nيرجى شرح مشكلتك بالتفصيل وسيتم الرد عليك قريباً من قبل الفريق المختص.",
                    color=0x6366f1
                )

            await ticket_chan.send(content=f"{interaction.user.mention} {support_role.mention if support_role else ''}", embed=embed, view=TicketControlView(lang=lang))
            success_msg = f"Ticket created successfully: {ticket_chan.mention}" if lang == "en" else f"تم إنشاء تذكرتك بنجاح: {ticket_chan.mention}"
            await interaction.followup.send(success_msg, ephemeral=True)
        except Exception as e:
            err_msg = "An error occurred while creating the ticket." if lang == "en" else "حدث خطأ أثناء إنشاء التذكرة، تأكد من صلاحيات البوت (Manage Channels)."
            await interaction.followup.send(err_msg, ephemeral=True)

# 2. واجهة إرسال لوحة التذاكر الرئيسية
class TicketSetupView(discord.ui.View):
    def __init__(self, lang="ar"):
        super().__init__(timeout=None)
        self.add_item(TicketSelect(lang=lang))

# 3. نافذة تقييم الخدمة قبل الإغلاق وحفظ الأرشيف
class RatingModal(discord.ui.Modal):
    def __init__(self, lang="ar"):
        self.lang = lang
        title = "Rate Support Service" if lang == "en" else "تقييم خدمة الدعم الفني"
        super().__init__(title=title)
        
        self.stars = discord.ui.TextInput(
            label="Rating (1 to 5 Stars)" if lang == "en" else "التقييم من 1 إلى 5 نجوم",
            placeholder="5",
            max_length=1,
            required=True
        )
        self.feedback = discord.ui.TextInput(
            label="Additional Feedback (Optional)" if lang == "en" else "ملاحظات إضافية (اختياري)",
            style=discord.TextStyle.paragraph,
            required=False
        )
        self.add_item(self.stars)
        self.add_item(self.feedback)

    async def on_submit(self, interaction: discord.Interaction):
        lang = self.lang
        guild = interaction.guild
        await interaction.response.defer(ephemeral=True)
        
        settings = database.get_settings(guild.id)
        archive_channel_id = settings.get("ticket_archive_channel")
        
        # إنشاء ملف نصي للأرشيف (Transcript)
        messages = [f"--- TICKET TRANSCRIPT: {interaction.channel.name} ---"]
        async for msg in interaction.channel.history(limit=150, oldest_first=True):
            messages.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M')}] {msg.author}: {msg.content}")
        
        transcript_content = "\n".join(messages)
        transcript_file = discord.File(
            fp=io.BytesIO(transcript_content.encode('utf-8')),
            filename=f"transcript-{interaction.channel.name}.txt"
        )

        # إرسال الأرشيف لقناة اللوغات المحددة في لوحة التحكم إن وجدت
        if archive_channel_id and str(archive_channel_id).isdigit():
            archive_chan = guild.get_channel(int(archive_channel_id))
            if archive_chan:
                rating_val = self.stars.value
                feedback_val = self.feedback.value or ("No feedback provided" if lang == "en" else "لا توجد ملاحظات")
                
                log_embed = discord.Embed(
                    title="📁 Closed Ticket Transcript & Rating",
                    description=f"**Channel:** `{interaction.channel.name}`\n**Rating:** `⭐ {rating_val}/5`\n**Feedback:** `{feedback_val}`",
                    color=discord.Color.orange()
                )
                try:
                    await archive_chan.send(embed=log_embed, file=transcript_file)
                except Exception as e:
                    print(f"❌ تعذر إرسال الأرشيف لقناة اللوغات: {e}")

        thank_msg = "Thank you for your rating! Closing channel..." if lang == "en" else "شكراً لك على تقييمك! جاري إغلاق القناة..."
        await interaction.followup.send(thank_msg, ephemeral=True)
        
        try:
            await interaction.channel.delete()
        except:
            pass

# 4. أزرار التحكم داخل التذكرة (استلام، إغلاق)
class TicketControlView(discord.ui.View):
    def __init__(self, lang="ar"):
        super().__init__(timeout=None)
        self.lang = lang

    @discord.ui.button(label="Claim 🙋‍♂️", style=discord.ButtonStyle.primary, custom_id="claim_ticket_btn")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = self.lang
        button.disabled = True
        button.label = f"Claimed by {interaction.user.display_name}"[:80]
        button.style = discord.ButtonStyle.secondary
        
        await interaction.message.edit(view=self)
        msg = f"Ticket claimed by {interaction.user.mention}." if lang == "en" else f"تم استلام التذكرة بواسطة المشرف {interaction.user.mention}."
        await interaction.response.send_message(msg)

    @discord.ui.button(label="Close Ticket 🔒", style=discord.ButtonStyle.danger, custom_id="close_ticket_advanced")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RatingModal(lang=self.lang))

class AdvancedTicketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="ticket-setup", description="إرسال لوحة التذاكر والأقسام المتطورة")
    @commands.has_permissions(manage_guild=True)
    async def ticket_setup(self, ctx):
        settings = database.get_settings(ctx.guild.id)
        lang = settings.get("language", "ar")

        if lang == "en":
            embed = discord.Embed(
                title="🎫 Advanced Support & Ticket System",
                description="Need help or have an inquiry? Choose the appropriate department from the menu below to open a private support ticket.",
                color=0xa855f7
            )
            embed.set_footer(text="Server Support Management System")
        else:
            embed = discord.Embed(
                title="🎫 نظام التذاكر والدعم الفني المتقدم",
                description="هل تحتاج إلى مساعدة أو لديك استفسار؟ اختر القسم المناسب من القائمة أدناه لفتح تذكرة خاصة مع طاقم الإدارة.",
                color=0xa855f7
            )
            embed.set_footer(text="نظام إدارة الدعم الفني للسيرفر")

        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)

        await ctx.send(embed=embed, view=TicketSetupView(lang=lang))

async def setup(bot):
    await bot.add_cog(AdvancedTicketCog(bot))
