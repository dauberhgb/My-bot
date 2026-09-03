import discord
from discord import app_commands
from discord.ext import commands
import datetime
import io

# تخزين مؤقت لبيانات المناوبات النشطة حالياً وقنوات اللوجات لكل سيرفر
active_shifts = {}
shift_channels = {}  # {guild_id: channel_id}

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
      
        if user_id in active_shifts:
            msg = "You are already on duty!" if self.lang == "en" else "أنت مسجل في مناوبة فعالة بالفعل ولا تحتاج لبدئها مرة أخرى."
            await interaction.response.send_message(msg, ephemeral=True)
            return

        # جلب الروم الصوتي للمشرف إن وجد
        voice_channel_name = "غير متواجد في روم صوتي"
        if interaction.user.voice and interaction.user.voice.channel:
            voice_channel_name = interaction.user.voice.channel.name

        active_shifts[user_id] = {
            "start_time": datetime.datetime.now(),
            "voice_channel": voice_channel_name,
            "tickets_closed": 0,
            "actions_count": 0
        }
        
        msg = f"تم بدء مناوبتك بنجاح في {datetime.datetime.now().strftime('%H:%M')} 🟢 (الروم الصوتي: **{voice_channel_name}**). بالتوفيق في عملك!"
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
        start_voice = shift_data["voice_channel"]
        
        # جلب الروم الصوتي الحالي وقت التسليم إن وجد
        end_voice_name = "غير متواجد في روم صوتي"
        if interaction.user.voice and interaction.user.voice.channel:
            end_voice_name = interaction.user.voice.channel.name

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
        embed.add_field(name="🔊 الروم الصوتي عند البدء", value=f"`{start_voice}`", inline=False)
        embed.add_field(name="🔊 الروم الصوتي عند التسليم", value=f"`{end_voice_name}`", inline=False)
        embed.add_field(name="🕒 وقت البدء", value=start_time.strftime('%Y-%m-%d %H:%M'), inline=False)
        embed.add_field(name="🏁 وقت الانتهاء", value=end_time.strftime('%Y-%m-%d %H:%M'), inline=False)
        
        embed.set_footer(text="نظام إدارة الدوام الإداري للسيرفر")

        # إرسال التقرير للمشرف مباشرة
        await interaction.response.send_message("✅ تم إنهاء مناوبتك وتسليم التقرير بنجاح إليك:", embed=embed, ephemeral=True)
        
        # إرسال نسخة من التقرير لقناة اللوجات المحددة إن وجدت
        if interaction.guild:
            channel_id = shift_channels.get(interaction.guild.id)
            if channel_id:
                log_channel = interaction.guild.get_channel(channel_id)
                if log_channel:
                    await log_channel.send(embed=embed)

class StaffShiftCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="shift-panel", description="إرسال لوحة تسجيل وتسليم المناوبات الإدارية")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def shift_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📋 لوحة دوام وتسليم المناوبات الإدارية",
            description="اضغط على الأزرار في الأسفل لتسجيل بداية مناوبتك أو إنهاء وتسليم تقرير عملك للطاقم بكل سهولة.",
            color=0x2b2d31
        )
        embed.set_footer(text="نظام مراقبة الدوام الإداري")
        
        await interaction.response.send_message(embed=embed, view=ShiftControlView())

    @app_commands.command(name="shift-log-channel", description="تحديد القناة المخصصة لإرسال تقارير المناوبات الإدارية إليها")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(channel="اختر القناة المخصصة للتقارير")
    async def shift_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        shift_channels[interaction.guild.id] = channel.id
        await interaction.response.send_message(f"✅ تم بنجاح تعيين {channel.mention} كقناة رسمية لتقارير وتسجيلات المناوبات الإدارية.", ephemeral=True)

async def setup(bot):
    bot.add_view(ShiftControlView())
    await bot.add_cog(StaffShiftCog(bot))
