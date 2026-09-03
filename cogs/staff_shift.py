import discord
from discord import app_commands
from discord.ext import commands
import datetime
import io

# تخزين مؤقت لبيانات المناوبات النشطة حالياً (يمكن ربطه بقاعدة البيانات لاحقاً)
# format: {user_id: {"start_time": timestamp, "tickets_closed": 0, "actions_count": 0}}
active_shifts = {}

class ShiftControlView(discord.ui.View):
    def __init__(self, lang="ar"):
        super().__init__(timeout=None)
        self.lang = lang

    @discord.ui.button(label="بدء المناوبة 🟢", style=discord.ButtonStyle.success, custom_id="start_shift_btn")
    async def start_shift(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id

      
        import time
        if not hasattr(self, "cooldowns"):
            self.cooldowns = {}
        if user_id in self.cooldowns and time.time() - self.cooldowns[user_id] < 5:
            await interaction.response.send_message("⚠️ يرجى الانتظار قليلاً قبل الضغط مرة أخرى.", ephemeral=True)
            return
        self.cooldowns[user_id] = time.time()
        # ---------------------------------------------
      
        if user_id in active_shifts:
            msg = "You are already on duty!" if self.lang == "en" else "أنت مسجل في مناوبة فعالة بالفعل ولا تحتاج لبدئها مرة أخرى."
            await interaction.response.send_message(msg, ephemeral=True)
            return

        active_shifts[user_id] = {
            "start_time": datetime.datetime.now(),
            "tickets_closed": 0,
            "actions_count": 0
        }
        
        msg = f"تم بدء مناوبتك بنجاح في {datetime.datetime.now().strftime('%H:%M')} 🟢. بالتوفيق في عملك!"
        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(label="تسليم المناوبة 🔴", style=discord.ButtonStyle.danger, custom_id="end_shift_btn")
    async def end_shift(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id not in active_shifts:
            msg = "You are not currently on duty!" if self.lang == "en" else "ليس لديك مناوبة نشطة حالياً لتسليمها."
            await interaction.response.send_message(msg, ephemeral=True)
            return

        shift_data = active_shifts.pop(user_id)
        start_time = shift_data["start_time"]
        end_time = datetime.datetime.now()
        duration = end_time - start_time
        
        hours, remainder = divmod(int(duration.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)

        embed = discord.Embed(
            title="📊 تقرير تسليم مناوبة إدارية",
            color=discord.Color.blue(),
            timestamp=end_time
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.add_field(name="👤 المشرف", value=interaction.user.mention, inline=True)
        embed.add_field(name="⏱️ مدة المناوبة", value=f"`{hours} ساعة و {minutes} دقيقة`", inline=True)
        embed.add_field(name="🕒 وقت البدء", value=start_time.strftime('%Y-%m-%d %H:%M'), inline=False)
        embed.add_field(name="🏁 وقت الانتهاء", value=end_time.strftime('%Y-%m-%d %H:%M'), inline=False)
        
        embed.set_footer(text="نظام إدارة الدوام الإداري للسيرفر")

        # إرسال التقرير للشات العام أو قناة مخصصة للإدارة إن أردت، أو الرد على المشرف مباشرة
        await interaction.response.send_message("✅ تم إنهاء مناوبتك وتسليم التقرير بنجاح إليك:", embed=embed, ephemeral=True)
        
        # يمكنك إرسال نسخة من التقرير لقناة لوغات الإدارة إذا كانت موجودة في سيرفرك
        # log_channel = interaction.guild.get_channel(CHANNEL_ID)
        # if log_channel: await log_channel.send(embed=embed)

class StaffShiftCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="shift-panel", description="إرسال لوحة تسجيل وتسليم المناوبات الإدارية")
    @commands.has_permissions(manage_guild=True)
    async def shift_panel(self, ctx: commands.Context):
        embed = discord.Embed(
            title="📋 لوحة دوام وتسليم المناوبات الإدارية",
            description="اضغط على الأزرار في الأسفل لتسجيل بداية مناوبتك أو إنهاء وتسليم تقرير عملك للطاقم بكل سهولة.",
            color=0x2b2d31
        )
        embed.set_footer(text="نظام مراقبة الدوام الإداري")
        
        if ctx.interaction:
            await ctx.interaction.response.send_message("✅ Done", ephemeral=True)
            await ctx.channel.send(embed=embed, view=ShiftControlView())
        else:
            await ctx.send(embed=embed, view=ShiftControlView())

async def setup(bot):
    # تسجيل الـ View بشكل مستمر لكي تعمل الأزرار حتى بعد إعادة تشغيل البوت
    bot.add_view(ShiftControlView())
    await bot.add_cog(StaffShiftCog(bot))
