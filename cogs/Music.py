import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import database
import time

# حماية محلية ضد التكرار السريع بالأزرار
music_cooldowns = {}

# إعدادات الاستخراج الصوتي
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
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title', 'Unknown Title')
        self.url = data.get('webpage_url', data.get('url'))
        self.duration = data.get('duration', 0)
        self.thumbnail = data.get('thumbnail', None)

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)


# أزرار التحكم التفاعلية بالصوت (Pause/Resume, Skip, Loop, Stop)
class MusicControlView(discord.ui.View):
    def __init__(self, cog, guild_id: int, lang="ar"):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.lang = lang

        # تحديث نصوص الأزرار بحسب اللغة
        if lang == "en":
            self.pause_btn.label = "Pause/Resume ⏯️"
            self.skip_btn.label = "Skip ⏭️"
            self.loop_btn.label = "Loop 🔁"
            self.stop_btn.label = "Stop 🛑"
        else:
            self.pause_btn.label = "إيقاف/استئناف ⏯️"
            self.skip_btn.label = "تخطي ⏭️"
            self.loop_btn.label = "تكرار 🔁"
            self.stop_btn.label = "إيقاف 🛑"

    async def check_rate_limit(self, user_id: int) -> bool:
        now = time.time()
        if user_id in music_cooldowns and now - music_cooldowns[user_id] < 2.5:
            return False
        music_cooldowns[user_id] = now
        return True

    @discord.ui.button(style=discord.ButtonStyle.primary, custom_id="music_pause_resume")
    async def pause_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_rate_limit(interaction.user.id):
            msg = "Please wait a moment..." if self.lang == "en" else "يرجى الانتظار بضع ثوانٍ لتفادي الضغط."
            return await interaction.response.send_message(msg, ephemeral=True)

        voice_client = interaction.guild.voice_client
        if not voice_client:
            msg = "Bot is not connected to a voice channel." if self.lang == "en" else "البوت غير متصل بأي روم صوتي."
            return await interaction.response.send_message(msg, ephemeral=True)

        if voice_client.is_playing():
            voice_client.pause()
            msg = "⏸️ Paused music." if self.lang == "en" else "⏸️ تم إيقاف التشغيل مؤقتاً."
        elif voice_client.is_paused():
            voice_client.resume()
            msg = "▶️ Resumed music." if self.lang == "en" else "▶️ تم استئناف التشغيل."
        else:
            msg = "Nothing is playing." if self.lang == "en" else "لا يوجد شيء يعمل حالياً."

        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.secondary, custom_id="music_skip")
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_rate_limit(interaction.user.id):
            msg = "Please wait..." if self.lang == "en" else "يرجى الانتظار قليلاً."
            return await interaction.response.send_message(msg, ephemeral=True)

        voice_client = interaction.guild.voice_client
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            msg = "⏭️ Skipped to the next track." if self.lang == "en" else "⏭️ تم تخطي المقطع الحالي."
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            msg = "Nothing to skip." if self.lang == "en" else "لا يوجد شيء لتخطيه."
            await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.secondary, custom_id="music_loop")
    async def loop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_state = self.cog.loops.get(self.guild_id, False)
        new_state = not current_state
        self.cog.loops[self.guild_id] = new_state

        if new_state:
            button.style = discord.ButtonStyle.success
            msg = "🔁 Loop enabled." if self.lang == "en" else "🔁 تم تفعيل وضع التكرار للمقطع الحالي."
        else:
            button.style = discord.ButtonStyle.secondary
            msg = "🔁 Loop disabled." if self.lang == "en" else "🔁 تم إلغاء وضع التكرار."

        await interaction.message.edit(view=self)
        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.danger, custom_id="music_stop")
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = interaction.guild.voice_client
        if voice_client:
            self.cog.queues[self.guild_id] = []
            self.cog.loops[self.guild_id] = False
            self.cog.current_track[self.guild_id] = None
            await voice_client.disconnect()
            msg = "🛑 Stopped music and left the channel." if self.lang == "en" else "🛑 تم إيقاف الموسيقى ومغادرة الروم الصوتي."
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            msg = "Bot is not in a voice channel." if self.lang == "en" else "البوت غير متصل بأي روم صوتي."
            return await interaction.response.send_message(msg, ephemeral=True)


class AdvancedMusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}
        self.loops = {}
        self.current_track = {}

    def get_queue(self, guild_id: int):
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    def play_next(self, guild: discord.Guild, channel: discord.TextChannel):
        guild_id = guild.id
        voice_client = guild.voice_client

        if not voice_client or not voice_client.is_connected():
            return

        settings = database.get_settings(guild_id)
        lang = settings.get("language", "ar")

        # حالة التكرار Loop
        if self.loops.get(guild_id, False) and guild_id in self.current_track and self.current_track[guild_id]:
            track_data = self.current_track[guild_id]
            asyncio.run_coroutine_threadsafe(self._replay_track(guild, channel, track_data, lang), self.bot.loop)
            return

        queue = self.get_queue(guild_id)
        if len(queue) > 0:
            next_track = queue.pop(0)
            self.current_track[guild_id] = next_track

            asyncio.run_coroutine_threadsafe(self._play_track_stream(guild, channel, next_track, lang), self.bot.loop)
        else:
            self.current_track[guild_id] = None

    async def _replay_track(self, guild, channel, track_data, lang):
        try:
            player = await YTDLSource.from_url(track_data['query'], loop=self.bot.loop, stream=True)
            guild.voice_client.play(player, after=lambda e: self.play_next(guild, channel))
            embed = self.build_music_embed(player, lang, is_playing=True)
            view = MusicControlView(self, guild.id, lang=lang)
            await channel.send(embed=embed, view=view)
        except Exception as e:
            print(f"❌ Error playing loop track: {e}")

    async def _play_track_stream(self, guild, channel, track_data, lang):
        try:
            player = await YTDLSource.from_url(track_data['query'], loop=self.bot.loop, stream=True)
            guild.voice_client.play(player, after=lambda e: self.play_next(guild, channel))
            embed = self.build_music_embed(player, lang, is_playing=True)
            view = MusicControlView(self, guild.id, lang=lang)
            await channel.send(embed=embed, view=view)
        except Exception as e:
            print(f"❌ Error streaming track: {e}")

    def build_music_embed(self, player, lang="ar", is_playing=True):
        if lang == "en":
            title = "🎶 Now Playing" if is_playing else "➕ Added to Queue"
            embed = discord.Embed(title=title, description=f"[{player.title}]({player.url})", color=0x6366f1)
            embed.add_field(name="Duration", value=f"`{player.duration} seconds`" if player.duration else "`Live Stream`", inline=True)
        else:
            title = "🎶 جاري التشغيل الآن" if is_playing else "➕ تم الإضافة لقائمة الانتظار"
            embed = discord.Embed(title=title, description=f"[{player.title}]({player.url})", color=0x6366f1)
            embed.add_field(name="المدة", value=f"`{player.duration} ثانية`" if player.duration else "`بث مباشر`", inline=True)

        if player.thumbnail:
            embed.set_thumbnail(url=player.thumbnail)
        return embed

    @commands.hybrid_command(name="play", description="تشغيل مقطع صوتي أو إضافة أغنية لقائمة الانتظار / Play a song or add to queue")
    @commands.cooldown(1, 4.0, commands.BucketType.user)
    @app_commands.describe(query="اسم الأغنية أو الرابط / Song name or URL")
    async def play(self, ctx: commands.Context, *, query: str):
        settings = database.get_settings(ctx.guild.id)
        lang = settings.get("language", "ar")

        if not ctx.author.voice or not ctx.author.voice.channel:
            msg = "❌ You must be in a voice channel first!" if lang == "en" else "❌ يجب أن تكون في روم صوتي أولاً!"
            return await ctx.reply(msg, ephemeral=True)

        await ctx.defer()

        voice_channel = ctx.author.voice.channel
        voice_client = ctx.guild.voice_client

        if not voice_client:
            voice_client = await voice_channel.connect()
        elif voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)

        try:
            player = await YTDLSource.from_url(query, loop=self.bot.loop, stream=True)
        except Exception as e:
            print(f"❌ Error fetching music: {e}")
            err_msg = "❌ Error occurred while fetching audio." if lang == "en" else "❌ حدث خطأ أثناء جلب المقطع الصوتي."
            return await ctx.followup.send(err_msg, ephemeral=True)

        queue = self.get_queue(ctx.guild.id)

        if voice_client.is_playing() or voice_client.is_paused():
            queue.append({'query': query, 'title': player.title})
            embed = self.build_music_embed(player, lang, is_playing=False)
            await ctx.followup.send(embed=embed)
        else:
            self.current_track[ctx.guild.id] = {'query': query, 'title': player.title}
            voice_client.play(player, after=lambda e: self.play_next(ctx.guild, ctx.channel))
            embed = self.build_music_embed(player, lang, is_playing=True)
            view = MusicControlView(self, ctx.guild.id, lang=lang)
            await ctx.followup.send(embed=embed, view=view)

    @commands.hybrid_command(name="stop", description="إيقاف الموسيقى وإخلاء الروم الصوتي / Stop music and disconnect")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def stop(self, ctx: commands.Context):
        settings = database.get_settings(ctx.guild.id)
        lang = settings.get("language", "ar")

        voice_client = ctx.guild.voice_client
        if voice_client:
            self.get_queue(ctx.guild.id).clear()
            self.loops[ctx.guild.id] = False
            self.current_track[ctx.guild.id] = None
            await voice_client.disconnect()
            msg = "🛑 Stopped playing and left the voice channel." if lang == "en" else "🛑 تم إيقاف التشغيل ومغادرة الروم الصوتي."
            await ctx.reply(msg)
        else:
            msg = "❌ Bot is not connected to any voice channel." if lang == "en" else "❌ البوت غير متصل بأي روم صوتي."
            await ctx.reply(msg, ephemeral=True)

    @commands.hybrid_command(name="skip", description="تخطي المقطع الحالي / Skip current track")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def skip(self, ctx: commands.Context):
        settings = database.get_settings(ctx.guild.id)
        lang = settings.get("language", "ar")

        voice_client = ctx.guild.voice_client
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            msg = "⏭️ Track skipped." if lang == "en" else "⏭️ تم تخطي المقطع الحالي."
            await ctx.reply(msg)
        else:
            msg = "❌ Nothing is playing to skip." if lang == "en" else "❌ لا يوجد شيء يعمل حالياً لتخطيه."
            await ctx.reply(msg, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AdvancedMusicCog(bot))
