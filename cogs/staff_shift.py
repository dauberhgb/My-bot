import datetime
import io
import discord
from discord import app_commands
from discord.ext import commands

# تخزين مؤقت لبيانات المناوبات النشطة وقنوات اللوجات والإحصائيات
active_shifts = {}
shift_channels = {}  # {guild_id: channel_id}
shift_stats_db = {}  # {user_id: {"total_seconds": 0, "shifts_count": 0, "points": 100}}


def get_guild_lang(guild_id):
  if not guild_id:
    return "ar"
  try:
    from __main__ import database

    settings = database.get_settings(guild_id)
    return settings.get("language", "ar")
  except Exception:
    return "ar"


class ShiftControlView(discord.ui.View):

  def __init__(self, lang="ar"):
    super().__init__(timeout=None)
    if lang == "en":
      self.start_btn.label = "Start Shift 🟢"
      self.pause_btn.label = "Break ⏸️"
      self.end_btn.label = "End Shift 🔴"
    else:
      self.start_btn.label = "بدء المناوبة 🟢"
      self.pause_btn.label = "استراحة ⏸️"
      self.end_btn.label = "تسليم المناوبة 🔴"

  @discord.ui.button(
      style=discord.ButtonStyle.success,
      custom_id="start_shift_btn",
      row=0,
  )
  async def start_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    user_id = interaction.user.id
    guild_id = interaction.guild.id if interaction.guild else None
    lang = get_guild_lang(guild_id)

    import time

    if not hasattr(self, "cooldowns"):
      self.cooldowns = {}
    if user_id in self.cooldowns and time.time() - self.cooldowns[user_id] < 5:
      msg = (
          "⚠️ Please wait a moment before trying again."
          if lang == "en"
          else "⚠️ يرجى الانتظار قليلاً قبل الضغط مرة أخرى."
      )
      await interaction.response.send_message(msg, ephemeral=True)
      return
    self.cooldowns[user_id] = time.time()

    if user_id in active_shifts:
      msg = (
          "You are already on duty!"
          if lang == "en"
          else "أنت مسجل في مناوبة فعالة بالفعل ولا تحتاج لبدئها مرة أخرى."
      )
      await interaction.response.send_message(msg, ephemeral=True)
      return

    if not interaction.user.voice or not interaction.user.voice.channel:
      msg = (
          "❌ You must be in a voice channel to start your shift!"
          if lang == "en"
          else "❌ يجب أن تكون متواجداً في روم صوتي لبدء المناوبة!"
      )
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
        "violations_count": 0,
        "out_of_voice_seconds": 0,
        "last_left_timestamp": None,
        "is_paused": False,
        "tickets_closed": 0,
        "actions_count": 0,
    }

    if lang == "en":
      msg = f"Shift started successfully at {now.strftime('%H:%M')} 🟢 (Voice Channel: **{voice_channel_name}**). Good luck!"
    else:
      msg = f"تم بدء مناوبتك بنجاح في {now.strftime('%H:%M')} 🟢 (الروم الصوتي: **{voice_channel_name}**). بالتوفيق في عملك!"

    await interaction.response.send_message(msg, ephemeral=True)

    # ميزة الإشعار الشخصي عبر الـ DM عند البدء
    try:
      dm_msg = (
          f"🟢 Your shift has started in **{interaction.guild.name}** at"
          f" {now.strftime('%H:%M')}."
          if lang == "en"
          else f"🟢 تم بدء مناوبتك في سيرفر **{interaction.guild.name}** الساعة"
          f" {now.strftime('%H:%M')}."
      )
      await interaction.user.send(dm_msg)
    except Exception:
      pass

  @discord.ui.button(
      style=discord.ButtonStyle.secondary,
      custom_id="pause_shift_btn",
      row=0,
  )
  async def pause_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    user_id = interaction.user.id
    guild_id = interaction.guild.id if interaction.guild else None
    lang = get_guild_lang(guild_id)

    if user_id not in active_shifts:
      msg = (
          "You are not currently on duty!"
          if lang == "en"
          else "ليس لديك مناوبة نشطة حالياً لتفعيل الاستراحة."
      )
      await interaction.response.send_message(msg, ephemeral=True)
      return

    shift_data = active_shifts[user_id]
    shift_data["is_paused"] = not shift_data["is_paused"]

    if shift_data["is_paused"]:
      shift_data["last_left_timestamp"] = (
          None  # إيقاف احتساب الخروج كمخالفة أثناء الاستراحة
      )
      msg = (
          "⏸️ Shift paused. Voice warnings are temporarily suspended."
          if lang == "en"
          else "⏸️ تم تفعيل الاستراحة المؤقتة. لن يتم احتساب مغادرة الروم"
          " كمخالفة حتى عودتك."
      )
    else:
      msg = (
          "▶️ Shift resumed. Welcome back!"
          if lang == "en"
          else "▶️ تم استئناف المناوبة. عودة ميمونة!"
      )

    await interaction.response.send_message(msg, ephemeral=True)

  @discord.ui.button(
      style=discord.ButtonStyle.danger, custom_id="end_shift_btn", row=0
  )
  async def end_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    user_id = interaction.user.id
    guild_id = interaction.guild.id if interaction.guild else None
    lang = get_guild_lang(guild_id)

    if user_id not in active_shifts:
      msg = (
          "You are not currently on duty!"
          if lang == "en"
          else "ليس لديك مناوبة نشطة حالياً لتسليمها."
      )
      await interaction.response.send_message(msg, ephemeral=True)
      return

    shift_data = active_shifts.pop(user_id)
    start_time = shift_data["start_time"]
    start_voice = shift_data["voice_channel"]

    if (
        shift_data["last_left_timestamp"] is not None
        and not shift_data["is_paused"]
    ):
      extra_out = (
          datetime.datetime.now() - shift_data["last_left_timestamp"]
      ).total_seconds()
      shift_data["out_of_voice_seconds"] += extra_out

    end_voice_name = (
        "غير متواجد في روم صوتي" if lang == "ar" else "Not in a voice channel"
    )
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

    # نظام العقوبات التلقائي (خصم نقاط بناء على المخالفات)
    if user_id not in shift_stats_db:
      shift_stats_db[user_id] = {
          "total_seconds": 0,
          "shifts_count": 0,
          "points": 100,
      }

    shift_stats_db[user_id]["total_seconds"] += total_seconds
    shift_stats_db[user_id]["shifts_count"] += 1

    penalty_points = violations * 5
    if out_secs > 60:
      penalty_points += int(out_secs // 60)
    shift_stats_db[user_id]["points"] = max(
        0, shift_stats_db[user_id]["points"] - penalty_points
    )
    current_points = shift_stats_db[user_id]["points"]

    if violations == 0 and out_secs < 5:
      left_status = (
          "✅ التزم بالروم الصوتي طوال فترة المناوبة"
          if lang == "ar"
          else "✅ Stayed in the voice channel throughout the shift"
      )
    else:
      if lang == "en":
        left_status = f"⚠️ Left/changed voice channel {violations} times (Total away: {out_hours}h {out_mins}m) | Penalty: -{penalty_points} pts"
      else:
        left_status = f"⚠️ غادر/غير الروم الصوتي {violations} مرة (إجمالي الغياب: {out_hours} ساعة و {out_mins} دقيقة) | الخصم: -{penalty_points} نقطة"

    embed = discord.Embed(
        title=(
            "📊 تقرير تسليم مناوبة إدارية"
            if lang == "ar"
            else "📊 Administrative Shift Handover Report"
        ),
        color=discord.Color.blue(),
        timestamp=end_time,
    )
    embed.set_author(
        name=interaction.user.display_name,
        icon_url=interaction.user.display_avatar.url,
    )

    if lang == "en":
      embed.add_field(
          name="👤 Staff", value=interaction.user.mention, inline=True
      )
      embed.add_field(
          name="⏱️ Duration",
          value=f"`{hours} hours & {minutes} minutes`",
          inline=True,
      )
      embed.add_field(
          name="⭐ Evaluation Points",
          value=f"`{current_points} / 100`",
          inline=True,
      )
      embed.add_field(
          name="🔊 Voice Channel at Start",
          value=f"`{start_voice}`",
          inline=False,
      )
      embed.add_field(
          name="🔊 Voice Channel at End",
          value=f"`{end_voice_name}`",
          inline=False,
      )
      embed.add_field(
          name="🛡️ Voice Compliance Status",
          value=f"`{left_status}`",
          inline=False,
      )
      embed.add_field(
          name="🕒 Start Time",
          value=start_time.strftime("%Y-%m-%d %H:%M"),
          inline=False,
      )
      embed.add_field(
          name="🏁 End Time",
          value=end_time.strftime("%Y-%m-%d %H:%M"),
          inline=False,
      )
      embed.set_footer(text="Server Administrative Attendance System")
    else:
      embed.add_field(
          name="👤 المشرف", value=interaction.user.mention, inline=True
      )
      embed.add_field(
          name="⏱️ مدة المناوبة",
          value=f"`{hours} ساعة و {minutes} دقيقة`",
          inline=True,
      )
      embed.add_field(
          name="⭐ نقاط التقييم",
          value=f"`{current_points} / 100`",
          inline=True,
      )
      embed.add_field(
          name="🔊 الروم الصوتي عند البدء",
          value=f"`{start_voice}`",
          inline=False,
      )
      embed.add_field(
          name="🔊 الروم الصوتي عند التسليم",
          value=f"`{end_voice_name}`",
          inline=False,
      )
      embed.add_field(
          name="🛡️ حالة التواجد الصوتي", value=f"`{left_status}`", inline=False
      )
      embed.add_field(
          name="🕒 وقت البدء",
          value=start_time.strftime("%Y-%m-%d %H:%M"),
          inline=False,
      )
      embed.add_field(
          name="🏁 وقت الانتهاء",
          value=end_time.strftime("%Y-%m-%d %H:%M"),
          inline=False,
      )
      embed.set_footer(text="نظام إدارة الدوام الإداري للسيرفر")

    resp_msg = (
        "✅ Shift ended and report sent successfully to you:"
        if lang == "en"
        else "✅ تم إنهاء مناوبتك وتسليم التقرير بنجاح إليك:"
    )
    await interaction.response.send_message(
        resp_msg, embed=embed, ephemeral=True
    )

    # إرسال نسخة عبر الـ DM للمشرف بملخص الانتهاء
    try:
      dm_embed = embed.copy()
      await interaction.user.send(
          "🔴 **Shift Summary Report:**"
          if lang == "en"
          else "🔴 **ملخص تقرير مناوبتك المنتهية:**",
          embed=dm_embed,
      )
    except Exception:
      pass

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
  async def on_voice_state_update(
      self,
      member: discord.Member,
      before: discord.VoiceState,
      after: discord.VoiceState,
  ):
    user_id = member.id
    if user_id not in active_shifts:
      return

    shift_data = active_shifts[user_id]
    if shift_data.get("is_paused", False):
      return  # تجاهل الرقابة الصوتية أثناء الاستراحة المؤقتة

    target_channel_id = shift_data["voice_channel_id"]
    now = datetime.datetime.now()

    left_target = (
        before.channel
        and before.channel.id == target_channel_id
    ) and (not after.channel or after.channel.id != target_channel_id)

    returned_target = (
        not before.channel or before.channel.id != target_channel_id
    ) and (after.channel and after.channel.id == target_channel_id)

    if left_target:
      shift_data["violations_count"] += 1
      shift_data["last_left_timestamp"] = now

    elif returned_target and shift_data["last_left_timestamp"] is not None:
      away_duration = (
          now - shift_data["last_left_timestamp"]
      ).total_seconds()
      shift_data["out_of_voice_seconds"] += away_duration
      shift_data["last_left_timestamp"] = None

  @app_commands.command(
      name="shift-panel",
      description=(
          "إرسال لوحة تسجيل وتسليم المناوبات الإدارية / Send shift control panel"
      ),
  )
  @app_commands.checks.has_permissions(manage_guild=True)
  async def shift_panel(self, interaction: discord.Interaction):
    guild_id = interaction.guild.id if interaction.guild else None
    lang = get_guild_lang(guild_id)

    if lang == "en":
      title = "📋 Administrative Shifts Control Panel"
      description = (
          "Click the buttons below to start your shift, take a break, or end"
          " and submit your work report easily."
      )
      footer_text = "Administrative Attendance Monitoring System"
    else:
      title = "📋 لوحة دوام وتسليم المناوبات الإدارية"
      description = (
          "اضغط على الأزرار في الأسفل لتسجيل بداية مناوبتك، أخذ استراحة، أو"
          " إنهاء وتسليم تقرير عملك بكل سهولة."
      )
      footer_text = "نظام مراقبة الدوام الإداري"

    embed = discord.Embed(
        title=title, description=description, color=0x2B2D31
    )
    embed.set_footer(text=footer_text)

    await interaction.response.send_message(
        embed=embed, view=ShiftControlView(lang=lang)
    )

  @app_commands.command(
      name="shift-log-channel",
      description=(
          "تحديد القناة المخصصة لإرسال تقارير المناوبات الإدارية / Set shift"
          " logs channel"
      ),
  )
  @app_commands.checks.has_permissions(manage_guild=True)
  @app_commands.describe(
      channel="اختر القناة المخصصة للتقارير / Select the report channel"
  )
  async def shift_log_channel(
      self, interaction: discord.Interaction, channel: discord.TextChannel
  ):
    shift_channels[interaction.guild.id] = channel.id
    await interaction.response.send_message(
        f"✅ Successfully set {channel.mention} as the official shift logs"
        f" channel.\n✅ تم بنجاح تعيين {channel.mention} كقناة رسمية لتقارير"
        " وتسجيلات المناوبات الإدارية.",
        ephemeral=True,
    )

  @app_commands.command(
      name="shift-stats",
      description=(
          "عرض إحصائيات المناوبات الخاصة بك أو بمشرف آخر / View shift stats"
      ),
  )
  @app_commands.describe(member="اختر المشرف / Select staff member")
  async def shift_stats(
      self, interaction: discord.Interaction, member: discord.Member = None
  ):
    target = member or interaction.user
    guild_id = interaction.guild.id if interaction.guild else None
    lang = get_guild_lang(guild_id)

    stats = shift_stats_db.get(
        target.id, {"total_seconds": 0, "shifts_count": 0, "points": 100}
    )
    total_secs = stats["total_seconds"]
    hours, remainder = divmod(total_secs, 3600)
    minutes, _ = divmod(remainder, 60)
    shifts_count = stats["shifts_count"]
    points = stats["points"]

    if lang == "en":
      desc = f"📊 **Shift Statistics for {target.mention}**:\n\n- Completed Shifts: `{shifts_count}`\n- Total Time on Duty: `{hours}h {minutes}m`\n- Evaluation Points: `{points} / 100`"
    else:
      desc = f"📊 **إحصائيات المناوبات للمشرف {target.mention}**:\n\n- عدد المناوبات المنجزة: `{shifts_count}`\n- إجمالي ساعات العمل: `{hours} ساعة و {minutes} دقيقة`\n- نقاط التقييم: `{points} / 100`"

    embed = discord.Embed(
        description=desc, color=discord.Color.green(), timestamp=datetime.datetime.now()
    )
    embed.set_author(
        name=target.display_name, icon_url=target.display_avatar.url
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

  @app_commands.command(
      name="shift-leaderboard",
      description=(
          "عرض لوحة المتصدرين لأفضل المشرفين في المناوبات / Shift Leaderboard"
      ),
  )
  async def shift_leaderboard(self, interaction: discord.Interaction):
    guild_id = interaction.guild.id if interaction.guild else None
    lang = get_guild_lang(guild_id)

    if not shift_stats_db:
      msg = (
          "No shift data available yet."
          if lang == "en"
          else "لا توجد بيانات مناوبات مسجلة حتى الآن."
      )
      await interaction.response.send_message(msg, ephemeral=True)
      return

    sorted_staff = sorted(
        shift_stats_db.items(),
        key=lambda x: x[1]["total_seconds"],
        reverse=True,
    )[:10]

    desc = ""
    for rank, (uid, data) in enumerate(sorted_staff, 1):
      user = interaction.guild.get_member(uid)
      name = user.display_name if user else f"User ID: {uid}"
      hours = data["total_seconds"] // 3600
      desc += f"**{rank}.** {name} — `{hours} hours` (`{data['points']} pts`)\n"

    embed = discord.Embed(
        title=(
            "🏆 Staff Shift Leaderboard"
            if lang == "en"
            else "🏆 لوحة متصدرين المناوبات الإدارية"
        ),
        description=desc,
        color=discord.Color.gold(),
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
  bot.add_view(ShiftControlView())
  await bot.add_cog(StaffShiftCog(bot))
