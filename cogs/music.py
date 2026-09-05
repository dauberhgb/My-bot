import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import time
import database as db
import shutil

# إعدادات yt-dlp للاستخراج السريع بدون تحميل الملف كاملاً
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'cookiefile': 'cookies.txt',
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web']
        }
    }
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


def get_guild_lang(guild_id):
    if not guild_id:
        return "ar"
    try:
        settings = db.get_settings(guild_id)
        return settings.get("language", "ar")
    except Exception:
        return "ar"


class MusicControlView(discord.ui.View):
    """لوحة تحكم تفاعلية بأزرار للتحكم في التشغيل"""
    def __init__(self, music_cog, guild_id: int, lang="ar"):
        super().__init__(timeout=None)
        self.cog = music_cog
        self.guild_id = guild_id
        self.button_cooldowns = {}  # {user_id: timestamp}
        
        if lang == "en":
            self.pause_resume_btn.label = "Pause/Resume ⏯️"
            self.skip_btn.label = "Skip ⏭️"
            self.stop_btn.label = "Stop ⏹️"
        else:
            self.pause_resume_btn.label = "إيقاف/استئناف ⏯️"
            self.skip_btn.label = "تخطي ⏭️"
            self.stop_btn.label = "إيقاف شامل ⏹️"

    def is_on_cooldown(self, user_id: int, cooldown_seconds: float = 3.0) -> float:
        """تحقق مما إذا كان المستخدم في فترة الانتظار للأزرار"""
        now = time.time()
        last_time = self.button_cooldowns.get(user_id, 0)
        remaining = cooldown_seconds - (now - last_time)
        if remaining > 0:
            return remaining
        self.button_cooldowns[user_id] = now
        return 0.0

    @discord.ui.button(style=discord.ButtonStyle.primary, custom_id="music_pause_resume", row=0)
    async def pause_resume_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = get_guild_lang(self.guild_id)
        
        # فحص Cooldown للأزرار (3 ثوانٍ)
        remaining = self.is_on_cooldown(interaction.user.id, 3.0)
        if remaining > 0:
            msg = f"⏳ Please wait {remaining:.1f}s before clicking again." if lang == "en" else f"⏳ يرجى الانتظار {remaining:.1f} ثوانٍ قبل الضغط مجدداً."
            await interaction.response.send_message(msg, ephemeral=True)
            return

        vc = interaction.guild.voice_client

        if not vc or not vc.is_connected():
            msg = "❌ The bot is not in a voice channel!" if lang == "en" else "❌ البوت غير متواجد في روم صوتي!"
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if vc.is_playing():
            vc.pause()
            msg = "⏸️ Music paused." if lang == "en" else "⏸️ تم إيقاف التشغيل مؤقتاً."
        elif vc.is_paused():
            vc.resume()
            msg = "▶️ Music resumed." if lang == "en" else "▶️ تم استئناف التشغيل."
        else:
            msg = "❌ Nothing is playing right now." if lang == "en" else "❌ لا يوجد شيء يعمل حالياً."

        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.secondary, custom_id="music_skip", row=0)
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = get_guild_lang(self.guild_id)

        # فحص Cooldown للأزرار (3 ثوانٍ)
        remaining = self.is_on_cooldown(interaction.user.id, 3.0)
        if remaining > 0:
            msg = f"⏳ Please wait {remaining:.1f}s before clicking again." if lang == "en" else f"⏳ يرجى الانتظار {remaining:.1f} ثوانٍ قبل الضغط مجدداً."
            await interaction.response.send_message(msg, ephemeral=True)
            return

        vc = interaction.guild.voice_client

        if not vc or not vc.is_playing():
            msg = "❌ Nothing is playing to skip!" if lang == "en" else "❌ لا يوجد شيء يعمل حالياً لتخطيه!"
            await interaction.response.send_message(msg, ephemeral=True)
            return

        vc.stop()  # يتسبب إيقاف التشغيل في الانتقال التلقائي للأغنية التالية عبر دالة بعد التشغيل
        msg = "⏭️ Skipped to the next track." if lang == "en" else "⏭️ تم تخطي المقطع الحالي."
        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.danger, custom_id="music_stop", row=0)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        lang = get_guild_lang(self.guild_id)

        # فحص Cooldown للأزرار (3 ثوانٍ)
        remaining = self.is_on_cooldown(interaction.user.id, 3.0)
        if remaining > 0:
            msg = f"⏳ Please wait {remaining:.1f}s before clicking again." if lang == "en" else f"⏳ يرجى الانتظار {remaining:.1f} ثوانٍ قبل الضغط مجدداً."
            await interaction.response.send_message(msg, ephemeral=True)
            return

        vc = interaction.guild.voice_client

        if self.guild_id in self.cog.queues:
            self.cog.queues[self.guild_id].clear()

        if vc and vc.is_connected():
            await vc.disconnect()

        msg = "⏹️ Stopped music and cleared queue." if lang == "en" else "⏹️ تم إيقاف الموسيقى ومسح قائمة الانتظار والمغادرة."
        await interaction.response.send_message(msg, ephemeral=True)


class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}  # {guild_id: [{'url': str, 'title': str, 'requester': Member}]}

    def get_queue(self, guild_id: int):
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    def play_next(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        queue = self.get_queue(guild_id)
        vc = interaction.guild.voice_client

        if queue and vc and vc.is_connected():
            next_track = queue.pop(0)
            try:
                ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
                audio_source = discord.FFmpegPCMAudio(next_track['url'], executable=ffmpeg_path, **FFMPEG_OPTIONS)
                vc.play(audio_source, after=lambda e: self.play_next(interaction))
                
                # إرسال إشعار عند بدء التشغيل القادم
                asyncio.run_coroutine_threadsafe(
                    self.send_now_playing_notice(interaction, next_track),
                    self.bot.loop
                )
            except Exception as e:
                print(f"[Music Error] play_next failed: {e}")
                self.play_next(interaction)

    async def send_now_playing_notice(self, interaction: discord.Interaction, track):
        lang = get_guild_lang(interaction.guild_id)
        embed = discord.Embed(
            title="🎶 Now Playing" if lang == "en" else "🎶 جاري التشغيل الآن",
            description=f"**[{track['title']}]**\n👤 Requested by: {track['requester'].mention}",
            color=discord.Color.green()
        )
        view = MusicControlView(self, interaction.guild_id, lang=lang)
        await interaction.channel.send(embed=embed, view=view)

    @app_commands.command(
        name="play",
        description="تشغيل مقطع صوتي أو إضافته لقائمة الانتظار / Play a song or add to queue"
    )
    @app_commands.describe(search="اسم الأغنية أو رابط يوتيوب / Song name or YouTube URL")
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
    async def play(self, interaction: discord.Interaction, search: str):
        await interaction.response.defer()
        guild_id = interaction.guild_id
        lang = get_guild_lang(guild_id)

        # التأكد من تواجد المستخدم في روم صوتي
        if not interaction.user.voice or not interaction.user.voice.channel:
            msg = "❌ You must be in a voice channel!" if lang == "en" else "❌ يجب أن تكون متواجداً في روم صوتي أولاً!"
            await interaction.followup.send(msg, ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        vc = interaction.guild.voice_client

        # الانضمام إلى الروم الصوتي بأمان
        try:
            if not interaction.guild.voice_client:
                await voice_channel.connect(timeout=20.0, reconnect=True)
            elif vc and vc.channel != voice_channel:
                await vc.move_to(voice_channel)
        except Exception as e:
            print(f"[Music Error] Connection failed: {e}")
            msg = "❌ Could not connect to the voice channel." if lang == "en" else "❌ تعذر الاتصال بالروم الصوتي."
            await interaction.followup.send(msg, ephemeral=True)
            return

        # تحديث المرجع للاتصال
        vc = interaction.guild.voice_client

        # تحديد إذا ما كان الإدخال رابطاً أم كلمة بحث
        query = search if search.startswith("http://") or search.startswith("https://") else f"ytsearch:{search}"

        # البحث واستخراج الصوت من يوتيوب
        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
        except Exception as e:
            print(f"[Music Error] yt_dlp extraction error: {e}")
            msg = "❌ Could not find or play this track." if lang == "en" else "❌ لم يتم العثور على المقطع أو تعذر استخراجه."
            await interaction.followup.send(msg, ephemeral=True)
            return

        if not data:
            msg = "❌ No results found." if lang == "en" else "❌ لم يتم العثور على نتائج."
            await interaction.followup.send(msg, ephemeral=True)
            return

        if 'entries' in data and data['entries']:
            data = data['entries'][0]

        stream_url = data.get('url')
        track_title = data.get('title', 'Audio Track')

        if not stream_url:
            msg = "❌ Failed to retrieve audio stream." if lang == "en" else "❌ تعذر الحصول على رابط البث الصوتي."
            await interaction.followup.send(msg, ephemeral=True)
            return

        track_data = {
            'url': stream_url,
            'title': track_title,
            'requester': interaction.user
        }

        queue = self.get_queue(guild_id)

        if vc and (vc.is_playing() or vc.is_paused()):
            queue.append(track_data)
            msg = f"⏳ Added to queue: **{track_title}**" if lang == "en" else f"⏳ تم إضافتها لقائمة الانتظار: **{track_title}**"
            await interaction.followup.send(msg)
        else:
            try:
                ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
                audio_source = discord.FFmpegPCMAudio(stream_url, executable=ffmpeg_path, **FFMPEG_OPTIONS)
                vc.play(audio_source, after=lambda e: self.play_next(interaction))
                
                embed = discord.Embed(
                    title="🎶 Now Playing" if lang == "en" else "🎶 جاري التشغيل الآن",
                    description=f"**{track_title}**\n👤 Requested by: {interaction.user.mention}",
                    color=discord.Color.purple()
                )
                view = MusicControlView(self, guild_id, lang=lang)
                await interaction.followup.send(embed=embed, view=view)
            except Exception as e:
                print(f"[Music Error] Playback start failed: {e}")
                msg = "❌ Failed to play audio." if lang == "en" else "❌ حدث خطأ أثناء بدء تشغيل الصوت."
                await interaction.followup.send(msg, ephemeral=True)

    @app_commands.command(
        name="stop",
        description="إيقاف التشغيل وإخراج البوت من الروم / Stop playing and disconnect"
    )
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
    async def stop(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        lang = get_guild_lang(guild_id)
        vc = interaction.guild.voice_client

        if guild_id in self.queues:
            self.queues[guild_id].clear()

        if vc and vc.is_connected():
            await vc.disconnect()
            msg = "⏹️ Disconnected and queue cleared." if lang == "en" else "⏹️ تم قطع الاتصال ومسح قائمة الانتظار."
        else:
            msg = "❌ The bot is not connected to a voice channel." if lang == "en" else "❌ البوت غير متصل بأي روم صوتي."

        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(
        name="queue",
        description="عرض قائمة الانتظار الحالية / View the current music queue"
    )
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
    async def queue_list(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        lang = get_guild_lang(guild_id)
        queue = self.get_queue(guild_id)

        if not queue:
            msg = "📜 Queue is empty." if lang == "en" else "📜 قائمة الانتظار فارغة حالياً."
            await interaction.response.send_message(msg, ephemeral=True)
            return

        desc = ""
        for index, track in enumerate(queue, 1):
            desc += f"**{index}.** {track['title']} — (Requested by {track['requester'].mention})\n"

        embed = discord.Embed(
            title="📜 Music Queue" if lang == "en" else "📜 قائمة انتظار الموسيقى",
            description=desc,
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """معالجة أخطاء الأوامر بشكل مخصص مع إخفاء أخطاء النظام للمستخدم وطباعتها في الـ Console"""
        lang = get_guild_lang(interaction.guild_id)
        
        if isinstance(error, app_commands.CommandOnCooldown):
            msg = f"⏳ Please wait {error.retry_after:.1f}s before using this command again." if lang == "en" else f"⏳ يرجى الانتظار {error.retry_after:.1f} ثوانٍ قبل استخدام هذا الأمر مجدداً."
        else:
            print(f"[Command Error]: {error}")
            msg = "❌ An unexpected error occurred while processing the request." if lang == "en" else "❌ حدث خطأ غير متوقع أثناء معالجة الطلب."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(MusicCog(bot))
