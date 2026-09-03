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
            msg = "⚠️ Please wait a moment before trying again." if self.lang == "en" else "⚠️ يرجى الانتظار قليلاً قبل الضغط مرة أخرى."
            await interaction.response.send_message(msg, ephemeral=True)
            return
        self.cooldowns[user_id] = time.time()
      
        if user_id in active_shifts:
            msg = "You are already on duty!" if self.lang == "en" else "أنت مسجل في مناوبة فعالة بالفعل ولا تحتاج لبدئها مرة أخرى."
            await interaction.response.send_message(msg, ephemeral=True)
            return

        # التحقق الإجباري من التواجد في روم صوتي لمنع الثغرات
        if not interaction.user.voice or not interaction.user.voice.channel:
            msg = "❌ You must be in a voice channel to start your shift!" if self.lang == "en" else "❌ يجب أن تكون متواجداً في روم صوتي لبدء المناوبة!"
            await interaction.response.send_message(msg, ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        voice_channel_name = voice_channel.name
        voice_channel_id = voice_channel.id
        now = datetime.datetime.now()

        active_shifts[user_id] = {
            "start_time": now,
            "voice_channel": voice_channel_name,
            "voice_channel_id": voice_channel_id,
            "violations_count": 0,           # عدد مرات مغادرة الروم
            "out_of_voice_seconds": 0,       # إجمالي الثواني خارج الروم أو بدون اتصال
            "last_left_timestamp": None,     # لتسجيل وقت الخروج المؤقت
            "tickets_closed": 0,
            "actions_count": 0
        }
        
        if self.lang == "en":
            msg = f"Shift started successfully at {now.strftime('%H:%M')} 🟢 (Voice Channel: **{voice_channel_name}**). Good luck!"
        else:
            msg = f"تم بدء مناوبتك بنجاح في {now.strftime('%H:%M')} 🟢 (الروم الصوتي: **{voice_channel_name}**). بالتوفيق في عملك!"
            
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
        
        # إذا كان المشرف خارج الروم لحظة الضغط، نقوم بحساب آخر فترة خروج حتى لحظة التسليم
        if shift_data["last_left_timestamp"] is not None:
            extra_out = (datetime.datetime.now() - shift_data["last_left_timestamp"]).total_seconds()
            shift_data["out_of_voice_seconds"] += extra_out

        # جلب الروم الصوتي الحالي وقت التسليم
        end_voice_name = "غير متواجد في روم صوتي" if self.lang == "ar" else "Not in a voice channel"
        if interaction.user.voice and interaction.user.voice.channel:
            end_voice_name = interaction.user.voice.channel.name

        end_time = datetime.datetime.now()
        duration = end_time - start_time
        total_seconds = int(duration.total_seconds())
        
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)

        out_secs = int(shift_data["out_of_voice_seconds"])
        out_hours, out_rem = divmod(out_secs, 3600)
        out_mins, _ = divmod(out_rem, 60)

        violations = shift_data["violations_count"]

        if violations == 0 and out_secs < 5:
            left_status = "✅ التزم بالروم الصوتي طوال فترة المناوبة" if self.lang == "ar" else "✅ Stayed in the voice channel throughout the shift"
        else:
            if self.lang == "en":
                left_status = f"⚠️ Left/changed voice channel {violations} times (Total away: {out_hours}h {out_mins}m)"
            else:
                left_status = f"⚠️ غادر/غير الروم الصوتي {violations} مرة (إجمالي الغياب: {out_hours} ساعة و {out_mins} دقيقة)"

        embed = discord.Embed(
            title="📊 تقرير تسليم مناوبة إدارية" if self.lang == "ar" else "📊 Administrative Shift Handover Report",
            color=discord.Color.blue(),
            timestamp=end_time
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        
        if self.lang == "en":
            embed.add_field(name="👤 Staff", value=interaction.user.mention, inline=True)
            embed.add_field(name="⏱️ Duration", value=f"`{hours} hours & {minutes} minutes`", inline=True)
            embed.add_field(name="🔊 Voice Channel at Start", value=f"`{start_voice}`", inline=False)
            embed.add_field(name="🔊 Voice Channel at End", value=f"`{end_voice_name}`", inline=False)
            embed.add_field(name="🛡️ Voice Compliance Status", value=f"`{left_status}`", inline=False)
            embed.add_field(name="🕒 Start Time", value=start_time.strftime('%Y-%m-%d %H:%M'), inline=False)
            embed.add_field(name="🏁 End Time", value=end_time.strftime('%Y-%m-%d %H:%M'), inline=False)
            embed.set_footer(text="Server Administrative Attendance System")
        else:
            embed.add_field(name="👤 المشرف", value=interaction.user.mention, inline=True)
            embed.add_field(name="⏱️ مدة المناوبة", value=f"`{hours} ساعة و {minutes} دقيقة`", inline=True)
            embed.add_field(name="🔊 الروم الصوتي عند البدء", value=f"`{start_voice}`", inline=False)
            embed.add_field(name="🔊 الروم الصوتي عند التسليم", value=f"`{end_voice_name}`", inline=False)
            embed.add_field(name="🛡️ حالة التواجد الصوتي", value=f"`{left_status}`", inline=False)
            embed.add_field(name="🕒 وقت البدء", value=start_time.strftime('%Y-%m-%d %H:%M'), inline=False)
            embed.add_field(name="🏁 وقت الانتهاء", value=end_time.strftime('%Y-%m-%d %H:%M'), inline=False)
            embed.set_footer(text="نظام إدارة الدوام الإداري للسيرفر")

        # إرسال التقرير للمشرف مباشرة
        resp_msg = "✅ Shift ended and report sent successfully to you:" if self.lang == "en" else "✅ تم إنهاء مناوبتك وتسليم التقرير بنجاح إليك:"
        await interaction.response.send_message(resp_msg, embed=embed, ephemeral=True)
        
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

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        user_id = member.id
        if user_id not in active_shifts:
            return

        shift_data = active_shifts[user_id]
        target_channel_id = shift_data["voice_channel_id"]
        now = datetime.datetime.now()

        # حالة خروج المشرف تماماً من الروم أو تغييره لروم آخر
        left_target = (before.channel and before.channel.id == target_channel_id) and \
                      (not after.channel or after.channel.id != target_channel_id)

        # حالة عودة المشرف للروم الأساسي المخصص للمناوبة
        returned_target = (not before.channel or before.channel.id != target_channel_id) and \
                          (after.channel and after.channel.id == target_channel_id)

        if left_target:
            shift_data["violations_count"] += 1
            shift_data["last_left_timestamp"] = now

        elif returned_target and shift_data["last_left_timestamp"] is not None:
            away_duration = (now - shift_data["last_left_timestamp"]).total_seconds()
            shift_data["out_of_voice_seconds"] += away_duration
            shift_data["last_left_timestamp"] = None

    @app_commands.command(name="shift-panel", description="إرسال لوحة تسجيل وتسليم المناوبات الإدارية / Send shift control panel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def shift_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📋 لوحة دوام وتسليم المناوبات الإدارية",
            description="اضغط على الأزرار في الأسفل لتسجيل بداية مناوبتك أو إنهاء وتسليم تقرير عملك للطاقم بكل سهولة.\n\nClick the buttons below to start your shift or end and submit your work report easily.",
            color=0x2b2d31
        )
        embed.set_footer(text="نظام مراقبة الدوام الإداري")
        
        await interaction.response.send_message(embed=embed, view=ShiftControlView())

    @app_commands.command(name="shift-log-channel", description="تحديد القناة المخصصة لإرسال تقارير المناوبات الإدارية / Set shift logs channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(channel="اختر القناة المخصصة للتقارير / Select the report channel")
    async def shift_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        shift_channels[interaction.guild.id] = channel.id
        await interaction.response.send_message(f"✅ Successfully set {channel.mention} as the official shift logs channel.\n✅ تم بنجاح تعيين {channel.mention} كقناة رسمية لتقارير وتسجيلات المناوبات الإدارية.", ephemeral=True)

async def setup(bot):
    bot.add_view(ShiftControlView())
    await bot.add_cog(StaffShiftCog(bot))
