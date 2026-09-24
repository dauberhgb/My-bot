import time
import asyncio
import re
from collections import defaultdict

import discord
from discord.ext import commands

import database as db


# ============================================================
# CONFIGURATION
# ============================================================

NETWORK_ID_PATTERN = re.compile(r"^net_\d+$")

MAX_NETWORK_NAME_LENGTH = 80
MAX_BROADCAST_LENGTH = 3900
MAX_MESSAGE_LENGTH = 2000

MAX_ATTACHMENTS = 10
MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024  # 25 MB

MESSAGE_LINK_TTL = 60 * 60 * 6          # 6 hours
REACTION_LOG_TTL = 60 * 60 * 6          # 6 hours

MAX_REACTION_LOGS = 5000
MAX_REACTORS_PER_MESSAGE = 500

WEBHOOK_NAME = "Fabric Sync"

BAN_SYNC_REASON_PREFIX = "NetworkSyncBan:"
BAN_SYNC_PENDING_TTL = 60


# ============================================================
# HELPERS
# ============================================================

def get_guild_lang(guild_id):
    if not guild_id:
        return "ar"

    try:
        settings = db.get_settings(guild_id)
        return settings.get("language", "ar")
    except Exception:
        return "ar"


def is_valid_network_id(network_id):
    if not network_id:
        return False

    return bool(
        NETWORK_ID_PATTERN.fullmatch(str(network_id))
    )


def sanitize_network_id(network_id):
    if network_id is None:
        return None

    network_id = str(network_id).strip()

    if not is_valid_network_id(network_id):
        return None

    return network_id


def sanitize_network_name(name):
    if not name:
        return None

    name = str(name).strip()

    if not name:
        return None

    if len(name) > MAX_NETWORK_NAME_LENGTH:
        return None

    return name


def sanitize_broadcast_content(content):
    if content is None:
        return ""

    content = str(content).strip()

    if len(content) > MAX_BROADCAST_LENGTH:
        return None

    return content


def safe_guild_name(guild):
    if not guild:
        return "Unknown Server"

    return str(guild.name)[:100]


# ============================================================
# REACTORS VIEW
# ============================================================

class ReactorsView(discord.ui.View):

    def __init__(self, bot, original_message_id, lang="ar"):
        super().__init__(timeout=None)

        self.bot = bot
        self.original_message_id = int(original_message_id)
        self.lang = lang if lang in ("ar", "en") else "ar"

        if self.lang == "en":
            self.reactors_button.label = "👥 View Reactors"
        else:
            self.reactors_button.label = "👥 عرض المتفاعلين"

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        custom_id="view_reactors_btn"
    )
    async def reactors_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        cog = self.bot.get_cog("NetworkCog")

        if not cog:
            msg = (
                "No reactors recorded yet."
                if self.lang == "en"
                else "لا توجد تفاعلات مسجلة حتى الآن."
            )

            await interaction.response.send_message(
                msg,
                ephemeral=True
            )
            return

        logs = cog.reaction_logs.get(
            self.original_message_id
        )

        if not logs:
            msg = (
                "No reactors recorded yet."
                if self.lang == "en"
                else "لا توجد تفاعلات مسجلة حتى الآن."
            )

            await interaction.response.send_message(
                msg,
                ephemeral=True
            )
            return

        description_parts = []

        for idx, entry in enumerate(logs, 1):
            emoji = str(entry.get("emoji", "❔"))
            name = str(entry.get("name", "User"))[:100]
            server = str(entry.get("server", "Server"))[:100]

            line = (
                f"{idx}. {emoji} **{name}** (`{server}`)"
            )

            if sum(len(x) + 1 for x in description_parts) + len(line) > 3800:
                more = (
                    "\n...and more."
                    if self.lang == "en"
                    else "\n...والمزيد."
                )

                description_parts.append(more)
                break

            description_parts.append(line)

        description = "\n".join(description_parts)

        if self.lang == "en":
            embed = discord.Embed(
                title="📊 Network Reactors List",
                description=description,
                color=discord.Color.blue()
            )
        else:
            embed = discord.Embed(
                title="📊 قائمة المتفاعلين في الشبكة",
                description=description,
                color=discord.Color.blue()
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


# ============================================================
# NETWORK COG
# ============================================================

class NetworkCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

        # ----------------------------------------------------
        # Message synchronization
        # ----------------------------------------------------

        # source_message_id -> {
        #     target_guild_id: target_message_id
        # }
        self.synced_messages = {}

        # target_message_id -> source_message_id
        self.reverse_synced_messages = {}

        # ----------------------------------------------------
        # Reaction logs
        # ----------------------------------------------------

        # source_message_id -> list[dict]
        self.reaction_logs = {}

        # source_message_id -> timestamp
        self.reaction_log_times = {}

        # ----------------------------------------------------
        # Pending network bans
        # Used to prevent bot-generated ban loops.
        # ----------------------------------------------------

        # (guild_id, user_id) -> timestamp
        self.pending_network_bans = {}

        # ----------------------------------------------------
        # Webhook cache
        # target_channel_id -> webhook_id
        # ----------------------------------------------------

        self.webhook_cache = {}

        # ----------------------------------------------------
        # Message processing rate control
        # ----------------------------------------------------

        self.processed_messages = {}

        # ----------------------------------------------------
        # Background cleanup task
        # ----------------------------------------------------

        self.cleanup_task = asyncio.create_task(
            self._cleanup_loop()
        )

    def cog_unload(self):
        if self.cleanup_task:
            self.cleanup_task.cancel()

    # ========================================================
    # DATABASE HELPERS
    # ========================================================

    async def _db_get_network(self, network_id):
        return await asyncio.to_thread(
            db.get_network,
            network_id
        )

    async def _db_get_guild_networks(self, guild_id):
        return await asyncio.to_thread(
            db.get_guild_networks,
            guild_id
        )

    async def _db_get_network_guilds(self, network_id):
        return await asyncio.to_thread(
            db.get_network_guilds,
            network_id
        )

    async def _db_create_network(
        self,
        network_id,
        network_name,
        owner_id
    ):
        return await asyncio.to_thread(
            db.create_network,
            network_id,
            network_name,
            owner_id
        )

    async def _db_join_network(
        self,
        guild_id,
        network_id,
        channel_id
    ):
        return await asyncio.to_thread(
            db.join_network,
            guild_id,
            network_id,
            channel_id
        )

    async def _db_leave_network(
        self,
        guild_id,
        network_id
    ):
        return await asyncio.to_thread(
            db.leave_network,
            guild_id,
            network_id
        )

    async def _db_delete_network(self, network_id):
        return await asyncio.to_thread(
            db.delete_network,
            network_id
        )

    # ========================================================
    # CLEANUP
    # ========================================================

    async def _cleanup_loop(self):

        try:
            while True:

                await asyncio.sleep(300)

                now = time.time()

                # ------------------------------------------------
                # Processed message cleanup
                # ------------------------------------------------

                self.processed_messages = {
                    key: timestamp
                    for key, timestamp
                    in self.processed_messages.items()
                    if now - timestamp < 10
                }

                # ------------------------------------------------
                # Synced message cleanup
                # ------------------------------------------------

                expired_source_ids = []

                for source_id, targets in self.synced_messages.items():

                    if isinstance(targets, dict):
                        # No timestamp information here.
                        # Keep active mappings.
                        continue

                    expired_source_ids.append(source_id)

                for source_id in expired_source_ids:
                    self.synced_messages.pop(
                        source_id,
                        None
                    )

                # ------------------------------------------------
                # Reaction logs cleanup
                # ------------------------------------------------

                expired_reaction_ids = [
                    message_id
                    for message_id, timestamp
                    in self.reaction_log_times.items()
                    if now - timestamp > REACTION_LOG_TTL
                ]

                for message_id in expired_reaction_ids:
                    self.reaction_logs.pop(
                        message_id,
                        None
                    )

                    self.reaction_log_times.pop(
                        message_id,
                        None
                    )

                # ------------------------------------------------
                # Pending bans cleanup
                # ------------------------------------------------

                expired_bans = [
                    key
                    for key, timestamp
                    in self.pending_network_bans.items()
                    if now - timestamp > BAN_SYNC_PENDING_TTL
                ]

                for key in expired_bans:
                    self.pending_network_bans.pop(
                        key,
                        None
                    )

        except asyncio.CancelledError:
            pass

    # ========================================================
    # MESSAGE LINK MANAGEMENT
    # ========================================================

    def _add_message_link(
        self,
        source_message_id,
        target_guild_id,
        target_message_id
    ):

        source_message_id = int(source_message_id)
        target_guild_id = str(target_guild_id)
        target_message_id = int(target_message_id)

        if source_message_id not in self.synced_messages:
            self.synced_messages[source_message_id] = {}

        self.synced_messages[
            source_message_id
        ][target_guild_id] = target_message_id

        self.reverse_synced_messages[
            target_message_id
        ] = source_message_id

    def _get_source_message_id(self, message_id):

        message_id = int(message_id)

        if message_id in self.synced_messages:
            return message_id

        return self.reverse_synced_messages.get(
            message_id
        )

    # ========================================================
    # WEBHOOK
    # ========================================================

    async def _get_or_create_webhook(self, channel):

        cached_id = self.webhook_cache.get(
            channel.id
        )

        if cached_id:
            try:
                webhook = await channel.fetch_webhook(
                    cached_id
                )

                if webhook:
                    return webhook

            except (
                discord.NotFound,
                discord.Forbidden,
                discord.HTTPException
            ):
                self.webhook_cache.pop(
                    channel.id,
                    None
                )

        try:
            webhooks = await channel.webhooks()

            webhook = discord.utils.get(
                webhooks,
                name=WEBHOOK_NAME
            )

            if webhook:
                self.webhook_cache[
                    channel.id
                ] = webhook.id

                return webhook

            webhook = await channel.create_webhook(
                name=WEBHOOK_NAME,
                reason="Network synchronization webhook"
            )

            self.webhook_cache[
                channel.id
            ] = webhook.id

            return webhook

        except discord.Forbidden:
            return None

        except discord.HTTPException:
            return None

    # ========================================================
    # CHANNEL VALIDATION
    # ========================================================

    def _can_send_to_channel(self, channel):

        if not channel:
            return False

        guild = getattr(channel, "guild", None)

        if not guild:
            return False

        me = guild.me

        if not me:
            return False

        permissions = channel.permissions_for(me)

        return (
            permissions.view_channel
            and permissions.send_messages
            and permissions.manage_webhooks
        )

    # ========================================================
    # NETWORK COMMAND GROUP
    # ========================================================

    @commands.group(
        name="network",
        invoke_without_command=True
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def network(self, ctx):

        guild_id = ctx.guild.id
        lang = get_guild_lang(guild_id)

        if lang == "en":

            help_text = (
                "Available Network Commands:\n"
                "`!network create <network_name>`\n"
                "`!network join <network_id>`\n"
                "`!network leave <network_id>`\n"
                "`!network del [network_id]`\n"
                "`!network broadcast <message>`\n"
                "`!network stats [network_id]`"
            )

        else:

            help_text = (
                "تنسيق الأوامر المتاحة:\n"
                "`!network create <اسم_الشبكة>`\n"
                "`!network join <معرف_الشبكة>`\n"
                "`!network leave <معرف_الشبكة>`\n"
                "`!network del [معرف_الشبكة]`\n"
                "`!network broadcast <الرسالة>`\n"
                "`!network stats [معرف_الشبكة]`"
            )

        await ctx.send(
            help_text,
            allowed_mentions=discord.AllowedMentions.none()
        )

    # ========================================================
    # CREATE
    # ========================================================

    @network.command(name="create")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def network_create(
        self,
        ctx,
        *,
        network_name: str
    ):

        guild_id = ctx.guild.id
        lang = get_guild_lang(guild_id)

        network_name = sanitize_network_name(
            network_name
        )

        if not network_name:

            msg = (
                "❌ Network name must be between 1 and 80 characters."
                if lang == "en"
                else "❌ اسم الشبكة يجب أن يكون بين 1 و80 حرفًا."
            )

            await ctx.send(msg)
            return

        network_id = f"net_{ctx.guild.id}"

        existing = await self._db_get_network(
            network_id
        )

        if existing:

            msg = (
                f"⚠️ This server has already created a network with this ID: `{network_id}`."
                if lang == "en"
                else
                f"⚠️ هذا السيرفر قام بإنشاء شبكة مسبقاً بهذا المعرف: `{network_id}`."
            )

            await ctx.send(msg)
            return

        try:

            await self._db_create_network(
                network_id,
                network_name,
                str(ctx.author.id)
            )

            await self._db_join_network(
                str(ctx.guild.id),
                network_id,
                str(ctx.channel.id)
            )

        except Exception as e:

            print(
                f"[Network] Failed to create network: {e}"
            )

            msg = (
                "❌ Failed to create the network."
                if lang == "en"
                else "❌ فشل إنشاء الشبكة."
            )

            await ctx.send(msg)
            return

        if lang == "en":

            msg = (
                f"✅ Network **{network_name}** created successfully!\n"
                f"Your network ID is:\n"
                f"`{network_id}`\n"
                f"This channel (`#{ctx.channel.name}`) has been automatically linked to the network."
            )

        else:

            msg = (
                f"✅ تم إنشاء الشبكة **{network_name}** بنجاح!\n"
                f"معرف الشبكة الخاص بك هو:\n"
                f"`{network_id}`\n"
                f"تم ربط هذا الروم (`#{ctx.channel.name}`) تلقائياً للشبكة."
            )

        await ctx.send(msg)

    # ========================================================
    # JOIN
    # ========================================================

    @network.command(name="join")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def network_join(
        self,
        ctx,
        network_id: str
    ):

        guild_id = ctx.guild.id
        lang = get_guild_lang(guild_id)

        network_id = sanitize_network_id(
            network_id
        )

        if not network_id:

            msg = (
                "❌ Invalid network ID."
                if lang == "en"
                else "❌ معرف الشبكة غير صالح."
            )

            await ctx.send(msg)
            return

        network = await self._db_get_network(
            network_id
        )

        if not network:

            msg = (
                "❌ Sorry, no network found with this ID!"
                if lang == "en"
                else
                "❌ عذراً، لم يتم العثور على شبكة بهذا المعرف!"
            )

            await ctx.send(msg)
            return

        try:

            await self._db_join_network(
                str(ctx.guild.id),
                network_id,
                str(ctx.channel.id)
            )

        except Exception as e:

            print(
                f"[Network] Failed to join network: {e}"
            )

            msg = (
                "❌ Failed to join the network."
                if lang == "en"
                else "❌ فشل الانضمام إلى الشبكة."
            )

            await ctx.send(msg)
            return

        network_name = str(
            network.get("network_name", "Network")
        )[:100]

        if lang == "en":

            msg = (
                f"✅ This server has successfully joined the network: "
                f"**{network_name}**!\n"
                f"This channel (`#{ctx.channel.name}`) has been linked "
                f"to relay messages for this network."
            )

        else:

            msg = (
                f"✅ تم انضمام هذا السيرفر بنجاح إلى شبكة: "
                f"**{network_name}**!\n"
                f"تم ربط هذا الروم (`#{ctx.channel.name}`) "
                f"لنقل الرسائل الخاصة بهذه الشبكة."
            )

        await ctx.send(msg)

    # ========================================================
    # LEAVE
    # ========================================================

    @network.command(name="leave")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def network_leave(
        self,
        ctx,
        network_id: str
    ):

        guild_id = ctx.guild.id
        lang = get_guild_lang(guild_id)

        network_id = sanitize_network_id(
            network_id
        )

        if not network_id:

            msg = (
                "❌ Invalid network ID."
                if lang == "en"
                else "❌ معرف الشبكة غير صالح."
            )

            await ctx.send(msg)
            return

        network = await self._db_get_network(
            network_id
        )

        if not network:

            msg = (
                "❌ No network found with this ID."
                if lang == "en"
                else
                "❌ لم يتم العثور على شبكة بهذا المعرف."
            )

            await ctx.send(msg)
            return

        try:

            await self._db_leave_network(
                str(ctx.guild.id),
                network_id
            )

        except Exception as e:

            print(
                f"[Network] Failed to leave network: {e}"
            )

            msg = (
                "❌ Failed to leave the network."
                if lang == "en"
                else "❌ فشل مغادرة الشبكة."
            )

            await ctx.send(msg)
            return

        msg = (
            f"✅ Successfully disconnected the server from network `{network_id}`."
            if lang == "en"
            else
            f"✅ تم قطع اتصال السيرفر بالشبكة `{network_id}` بنجاح."
        )

        await ctx.send(msg)

    # ========================================================
    # DELETE
    # ========================================================

    @network.command(
        name="del",
        aliases=["delete"]
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def network_delete(
        self,
        ctx,
        network_id: str = None
    ):

        guild_id = ctx.guild.id
        lang = get_guild_lang(guild_id)

        if not network_id:

            network_id = f"net_{ctx.guild.id}"

        else:

            network_id = sanitize_network_id(
                network_id
            )

            if not network_id:

                msg = (
                    "❌ Invalid network ID."
                    if lang == "en"
                    else "❌ معرف الشبكة غير صالح."
                )

                await ctx.send(msg)
                return

        network = await self._db_get_network(
            network_id
        )

        if not network:

            msg = (
                "❌ No network found with this ID!"
                if lang == "en"
                else
                "❌ لم يتم العثور على شبكة بهذا المعرف!"
            )

            await ctx.send(msg)
            return

        # ----------------------------------------------------
        # CRITICAL SECURITY CHECK
        # Only the network owner can delete the network.
        # ----------------------------------------------------

        owner_id = str(
            network.get("owner_id", "")
        )

        if str(ctx.author.id) != owner_id:

            msg = (
                "🚫 Only the network owner can delete this network."
                if lang == "en"
                else
                "🚫 مالك الشبكة فقط يستطيع حذف هذه الشبكة."
            )

            await ctx.send(msg)
            return

        try:

            await self._db_delete_network(
                network_id
            )

        except Exception as e:

            print(
                f"[Network] Failed to delete network: {e}"
            )

            msg = (
                "❌ Failed to delete the network."
                if lang == "en"
                else
                "❌ فشل حذف الشبكة."
            )

            await ctx.send(msg)
            return

        msg = (
            f"🗑️ Network `{network_id}` has been deleted and all its connections closed successfully."
            if lang == "en"
            else
            f"🗑️ تم حذف الشبكة `{network_id}` وإغلاق جميع اتصالاتها بنجاح."
        )

        await ctx.send(msg)

    # ========================================================
    # BROADCAST
    # ========================================================

    @network.command(name="broadcast")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def network_broadcast(
        self,
        ctx,
        *,
        message_content: str
    ):

        guild_id = ctx.guild.id
        lang = get_guild_lang(guild_id)

        message_content = sanitize_broadcast_content(
            message_content
        )

        if message_content is None:

            msg = (
                "❌ Broadcast message is too long."
                if lang == "en"
                else
                "❌ رسالة التعميم طويلة جدًا."
            )

            await ctx.send(msg)
            return

        current_guild_id = str(
            ctx.guild.id
        )

        current_channel_id = str(
            ctx.channel.id
        )

        guild_networks = await self._db_get_guild_networks(
            current_guild_id
        )

        if not guild_networks:

            msg = (
                "❌ This server is not connected to any network to send a broadcast!"
                if lang == "en"
                else
                "❌ هذا السيرفر غير متصل بأي شبكة لإرسال تعميم!"
            )

            await ctx.send(msg)
            return

        active_network_id = None

        for g_data in guild_networks:

            if str(
                g_data.get("bound_channel_id")
            ) == current_channel_id:

                active_network_id = str(
                    g_data.get("network_id")
                )

                break

        if not active_network_id:

            msg = (
                "❌ Please run this command inside the channel bound to the network!"
                if lang == "en"
                else
                "❌ يرجى تنفيذ هذا الأمر داخل الروم المربوط بالشبكة!"
            )

            await ctx.send(msg)
            return

        network = await self._db_get_network(
            active_network_id
        )

        if not network:

            msg = (
                "❌ Network data not found!"
                if lang == "en"
                else
                "❌ لم يتم العثور على بيانات الشبكة!"
            )

            await ctx.send(msg)
            return

        owner_id = str(
            network.get("owner_id", "")
        )

        if str(ctx.author.id) != owner_id:

            msg = (
                "🚫 This command is restricted to the network owner only!"
                if lang == "en"
                else
                "🚫 هذا الأمر مخصص لمالك الشبكة فقط!"
            )

            await ctx.send(msg)
            return

        all_network_guilds = await self._db_get_network_guilds(
            active_network_id
        )

        if lang == "en":

            embed = discord.Embed(
                title=(
                    f"📢 Official Broadcast from Network: "
                    f"{str(network.get('network_name', 'Network'))[:200]}"
                ),
                description=message_content or " ",
                color=discord.Color.gold()
            )

            embed.set_footer(
                text=(
                    f"Sent from server: "
                    f"{safe_guild_name(ctx.guild)}"
                )[:2048]
            )

        else:

            embed = discord.Embed(
                title=(
                    f"📢 تعميم رسمي من شبكة: "
                    f"{str(network.get('network_name', 'الشبكة'))[:200]}"
                ),
                description=message_content or " ",
                color=discord.Color.gold()
            )

            embed.set_footer(
                text=(
                    f"تم الإرسال من سيرفر: "
                    f"{safe_guild_name(ctx.guild)}"
                )[:2048]
            )

        embed.set_author(
            name=str(
                ctx.author.display_name
            )[:256],
            icon_url=ctx.author.display_avatar.url
        )

        # ----------------------------------------------------
        # Attachment validation
        # ----------------------------------------------------

        if ctx.message.attachments:

            first_attachment = ctx.message.attachments[0]

            if (
                first_attachment.size <= MAX_ATTACHMENT_SIZE
                and any(
                    first_attachment.filename.lower().endswith(ext)
                    for ext in (
                        ".png",
                        ".jpg",
                        ".jpeg",
                        ".gif",
                        ".webp"
                    )
                )
            ):

                embed.set_image(
                    url=first_attachment.url
                )

        sent_count = 0

        for g_data in all_network_guilds:

            target_guild_id = str(
                g_data.get("guild_id")
            )

            target_channel_id = str(
                g_data.get("bound_channel_id")
            )

            if target_guild_id == current_guild_id:
                continue

            try:

                target_guild = self.bot.get_guild(
                    int(target_guild_id)
                )

                if not target_guild:
                    continue

                target_channel = target_guild.get_channel(
                    int(target_channel_id)
                )

                if not target_channel:
                    continue

                if not self._can_send_to_channel(
                    target_channel
                ):
                    continue

                target_lang = get_guild_lang(
                    int(target_guild_id)
                )

                view = ReactorsView(
                    self.bot,
                    ctx.message.id,
                    lang=target_lang
                )

                sent_msg = await target_channel.send(
                    embed=embed,
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none()
                )

                self._add_message_link(
                    ctx.message.id,
                    target_guild_id,
                    sent_msg.id
                )

                sent_count += 1

                await asyncio.sleep(0.25)

            except discord.Forbidden:

                print(
                    f"[Network] Missing permissions in guild "
                    f"{target_guild_id}"
                )

            except discord.HTTPException as e:

                print(
                    f"[Network] HTTP error during broadcast: {e}"
                )

            except Exception as e:

                print(
                    f"[Network] Broadcast error: {e}"
                )

        msg = (
            f"✅ Broadcast sent successfully to "
            f"**{sent_count}** connected servers/channels."
            if lang == "en"
            else
            f"✅ تم إرسال التعميم بنجاح إلى "
            f"**{sent_count}** سيرفر/قناة متصلة بالشبكة."
        )

        await ctx.send(msg)

    # ========================================================
    # STATS
    # ========================================================

    @network.command(
        name="stats",
        aliases=["list"]
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def network_stats(
        self,
        ctx,
        network_id: str = None
    ):

        guild_id = ctx.guild.id
        lang = get_guild_lang(guild_id)

        current_guild_id = str(
            ctx.guild.id
        )

        current_channel_id = str(
            ctx.channel.id
        )

        if network_id:

            network_id = sanitize_network_id(
                network_id
            )

            if not network_id:

                msg = (
                    "❌ Invalid network ID."
                    if lang == "en"
                    else "❌ معرف الشبكة غير صالح."
                )

                await ctx.send(msg)
                return

        else:

            guild_networks = await self._db_get_guild_networks(
                current_guild_id
            )

            if guild_networks:

                for g_data in guild_networks:

                    if str(
                        g_data.get("bound_channel_id")
                    ) == current_channel_id:

                        network_id = str(
                            g_data.get("network_id")
                        )

                        break

                if not network_id:

                    network_id = str(
                        guild_networks[0].get(
                            "network_id"
                        )
                    )

            else:

                network_id = (
                    f"net_{current_guild_id}"
                )

        network = await self._db_get_network(
            str(network_id)
        )

        if not network:

            msg = (
                "❌ No network found with this ID!"
                if lang == "en"
                else
                "❌ لم يتم العثور على شبكة بهذا المعرف!"
            )

            await ctx.send(msg)
            return

        network_guilds = await self._db_get_network_guilds(
            str(network_id)
        )

        is_server_in_network = any(
            str(g.get("guild_id"))
            == current_guild_id
            for g in network_guilds
        )

        owner_id = str(
            network.get("owner_id", "")
        )

        if (
            str(ctx.author.id) != owner_id
            and not is_server_in_network
        ):

            msg = (
                "🚫 You do not have permission to view stats for this network because your server is not linked to it!"
                if lang == "en"
                else
                "🚫 ليس لديك صلاحية لعرض إحصائيات هذه الشبكة لأن سيرفرك غير مرتبط بها!"
            )

            await ctx.send(msg)
            return

        owner_user = (
            "Unknown"
            if lang == "en"
            else "غير معروف"
        )

        if owner_id.isdigit():

            try:

                owner_user = await self.bot.fetch_user(
                    int(owner_id)
                )

            except (
                discord.NotFound,
                discord.HTTPException
            ):

                pass

        description_parts = []
        total_members = 0

        for idx, g_data in enumerate(
            network_guilds,
            1
        ):

            raw_guild_id = g_data.get(
                "guild_id"
            )

            try:

                target_guild = self.bot.get_guild(
                    int(raw_guild_id)
                )

            except (
                TypeError,
                ValueError
            ):

                target_guild = None

            if target_guild:

                member_count = (
                    target_guild.member_count or 0
                )

                total_members += member_count

                if lang == "en":

                    description_parts.append(
                        f"**{idx}. "
                        f"{target_guild.name[:80]}** — "
                        f"👥 `{member_count}` members"
                    )

                else:

                    description_parts.append(
                        f"**{idx}. "
                        f"{target_guild.name[:80]}** — "
                        f"👥 `{member_count}` عضو"
                    )

            else:

                if lang == "en":

                    description_parts.append(
                        f"**{idx}. Server ID "
                        f"(`{raw_guild_id}`)** — "
                        f"*(Disconnected)*"
                    )

                else:

                    description_parts.append(
                        f"**{idx}. سيرفر معرف "
                        f"(`{raw_guild_id}`)** — "
                        f"*(غير متصل)*"
                    )

        description = "\n".join(
            description_parts
        )

        if len(description) > 3800:

            description = (
                description[:3700]
                + "\n..."
            )

        if not description:

            description = (
                "⚠️ No servers linked to this network currently."
                if lang == "en"
                else
                "⚠️ لا يوجد سيرفرات مرتبطة بهذه الشبكة حالياً."
            )

        network_name = str(
            network.get(
                "network_name",
                "Network"
            )
        )[:200]

        if lang == "en":

            embed = discord.Embed(
                title=(
                    f"📊 Statistics & List for Network: "
                    f"{network_name}"
                ),
                description=description,
                color=discord.Color.green()
            )

            embed.add_field(
                name="🆔 Network ID",
                value=f"`{network_id}`",
                inline=True
            )

            embed.add_field(
                name="👑 Owner",
                value=str(owner_user)[:1024],
                inline=True
            )

            embed.add_field(
                name="🏰 Linked Servers",
                value=f"`{len(network_guilds)}`",
                inline=True
            )

            embed.set_footer(
                text=(
                    f"Total members in network: "
                    f"{total_members} members"
                )
            )

        else:

            embed = discord.Embed(
                title=(
                    f"📊 إحصائيات وقائمة شبكة: "
                    f"{network_name}"
                ),
                description=description,
                color=discord.Color.green()
            )

            embed.add_field(
                name="🆔 معرف الشبكة",
                value=f"`{network_id}`",
                inline=True
            )

            embed.add_field(
                name="👑 المالك",
                value=str(owner_user)[:1024],
                inline=True
            )

            embed.add_field(
                name="🏰 عدد السيرفرات المربوطة",
                value=f"`{len(network_guilds)}`",
                inline=True
            )

            embed.set_footer(
                text=(
                    f"إجمالي الأعضاء في الشبكة: "
                    f"{total_members} عضو"
                )
            )

        await ctx.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none()
        )

    # ========================================================
    # MESSAGE SYNCHRONIZATION
    # ========================================================

    @commands.Cog.listener()
    async def on_message(self, message):

        if (
            message.author.bot
            or message.webhook_id is not None
            or not message.guild
        ):
            return

        prefix = self.bot.command_prefix

        if (
            isinstance(prefix, str)
            and message.content.startswith(prefix)
        ):
            return

        # ----------------------------------------------------
        # Message length protection
        # ----------------------------------------------------

        if len(message.content) > MAX_MESSAGE_LENGTH:

            return

        # ----------------------------------------------------
        # Rate/deduplication
        # ----------------------------------------------------

        current_time = time.time()

        expired_keys = [
            key
            for key, timestamp
            in self.processed_messages.items()
            if current_time - timestamp >= 5
        ]

        for key in expired_keys:

            self.processed_messages.pop(
                key,
                None
            )

        # Message ID is unique.
        # We intentionally do not use content as the key.
        msg_key = message.id

        if msg_key in self.processed_messages:
            return

        self.processed_messages[
            msg_key
        ] = current_time

        # ----------------------------------------------------
        # Find active network
        # ----------------------------------------------------

        current_guild_id = str(
            message.guild.id
        )

        current_channel_id = str(
            message.channel.id
        )

        guild_networks = await self._db_get_guild_networks(
            current_guild_id
        )

        if not guild_networks:
            return

        active_network_id = None

        for g_data in guild_networks:

            if str(
                g_data.get("bound_channel_id")
            ) == current_channel_id:

                active_network_id = str(
                    g_data.get("network_id")
                )

                break

        if not active_network_id:
            return

        all_network_guilds = await self._db_get_network_guilds(
            active_network_id
        )

        # ----------------------------------------------------
        # Attachment protection
        # ----------------------------------------------------

        if len(message.attachments) > MAX_ATTACHMENTS:

            return

        for attachment in message.attachments:

            if attachment.size > MAX_ATTACHMENT_SIZE:

                return

        # ----------------------------------------------------
        # Mention protection
        # ----------------------------------------------------

        safe_content = message.content or ""

        safe_content = safe_content.replace(
            "@everyone",
            "@\u200beveryone"
        )

        safe_content = safe_content.replace(
            "@here",
            "@\u200bhere"
        )

        sent_channels = set()

        for g_data in all_network_guilds:

            target_guild_id = str(
                g_data.get("guild_id")
            )

            target_channel_id = str(
                g_data.get("bound_channel_id")
            )

            if (
                target_guild_id == current_guild_id
                or target_channel_id in sent_channels
            ):
                continue

            try:

                target_guild = self.bot.get_guild(
                    int(target_guild_id)
                )

                if not target_guild:
                    continue

                target_channel = target_guild.get_channel(
                    int(target_channel_id)
                )

                if not target_channel:
                    continue

                if not self._can_send_to_channel(
                    target_channel
                ):
                    continue

                webhook = await self._get_or_create_webhook(
                    target_channel
                )

                if not webhook:
                    continue

                sent_channels.add(
                    target_channel_id
                )

                files = []

                try:

                    for attachment in message.attachments:

                        files.append(
                            await attachment.to_file()
                        )

                    avatar_url = (
                        message.author.display_avatar.url
                    )

                    target_lang = get_guild_lang(
                        int(target_guild_id)
                    )

                    view = ReactorsView(
                        self.bot,
                        message.id,
                        lang=target_lang
                    )

                    sent_msg = await webhook.send(
                        content=safe_content,
                        username=(
                            f"{message.author.display_name} "
                            f"({message.guild.name})"
                        )[:80],
                        avatar_url=avatar_url,
                        files=files,
                        wait=True,
                        view=view,
                        allowed_mentions=discord.AllowedMentions.none()
                    )

                    self._add_message_link(
                        message.id,
                        target_guild_id,
                        sent_msg.id
                    )

                finally:

                    for file in files:

                        try:
                            file.close()
                        except Exception:
                            pass

            except discord.Forbidden:

                print(
                    f"[Network] Missing webhook/send permission "
                    f"in {target_guild.name}"
                )

            except discord.HTTPException as e:

                print(
                    f"[Network] HTTP error while syncing message: {e}"
                )

            except Exception as e:

                print(
                    f"[Network] Message synchronization error: {e}"
                )

    # ========================================================
    # REACTION SYNCHRONIZATION
    # ========================================================

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):

        if payload.user_id == self.bot.user.id:
            return

        if not payload.guild_id:
            return

        source_message_id = self._get_source_message_id(
            payload.message_id
        )

        if not source_message_id:
            return

        current_guild_id = str(
            payload.guild_id
        )

        guild_networks = await self._db_get_guild_networks(
            current_guild_id
        )

        if not guild_networks:
            return

        current_channel_id = str(
            payload.channel_id
        )

        active_network_id = None

        for g_data in guild_networks:

            if str(
                g_data.get("bound_channel_id")
            ) == current_channel_id:

                active_network_id = str(
                    g_data.get("network_id")
                )

                break

        if not active_network_id:
            return

        # ----------------------------------------------------
        # Record reaction
        # ----------------------------------------------------

        logs = self.reaction_logs.setdefault(
            source_message_id,
            []
        )

        self.reaction_log_times[
            source_message_id
        ] = time.time()

        reactor_name = "User"
        server_name = "Server"

        if payload.member:

            reactor_name = str(
                payload.member.display_name
            )[:100]

            if payload.member.guild:

                server_name = str(
                    payload.member.guild.name
                )[:100]

        emoji_str = str(
            payload.emoji
        )

        entry_key = (
            payload.user_id,
            emoji_str,
            payload.guild_id
        )

        # ----------------------------------------------------
        # Prevent duplicate entries
        # ----------------------------------------------------

        already_exists = any(
            (
                entry.get("user_id"),
                entry.get("emoji"),
                entry.get("guild_id")
            ) == entry_key
            for entry in logs
        )

        if not already_exists:

            if len(logs) < MAX_REACTORS_PER_MESSAGE:

                logs.append(
                    {
                        "user_id": payload.user_id,
                        "guild_id": payload.guild_id,
                        "emoji": emoji_str,
                        "name": reactor_name,
                        "server": server_name
                    }
                )

            # ------------------------------------------------
            # Global memory safety
            # ------------------------------------------------

            if len(self.reaction_logs) > MAX_REACTION_LOGS:

                oldest_id = min(
                    self.reaction_log_times,
                    key=self.reaction_log_times.get
                )

                self.reaction_logs.pop(
                    oldest_id,
                    None
                )

                self.reaction_log_times.pop(
                    oldest_id,
                    None
                )

        # ----------------------------------------------------
        # Synchronize to all linked guilds
        # ----------------------------------------------------

        all_network_guilds = await self._db_get_network_guilds(
            active_network_id
        )

        source_links = self.synced_messages.get(
            source_message_id,
            {}
        )

        if not isinstance(source_links, dict):
            return

        for g_data in all_network_guilds:

            target_guild_id = str(
                g_data.get("guild_id")
            )

            if target_guild_id == current_guild_id:
                continue

            target_message_id = source_links.get(
                target_guild_id
            )

            if not target_message_id:
                continue

            target_guild = self.bot.get_guild(
                int(target_guild_id)
            )

            if not target_guild:
                continue

            target_channel = target_guild.get_channel(
                int(
                    g_data.get(
                        "bound_channel_id"
                    )
                )
            )

            if not target_channel:
                continue

            try:

                target_message = await target_channel.fetch_message(
                    int(target_message_id)
                )

                await target_message.add_reaction(
                    payload.emoji
                )

            except discord.NotFound:

                continue

            except discord.Forbidden:

                print(
                    f"[Network] Cannot add reaction in "
                    f"{target_guild.name}"
                )

            except discord.HTTPException:

                continue

            except Exception as e:

                print(
                    f"[Network] Reaction sync error: {e}"
                )

    # ========================================================
    # AUDIT LOG BAN EXECUTOR
    # ========================================================

    async def _get_ban_executor(
        self,
        guild,
        user_id
    ):

        try:

            async for entry in guild.audit_logs(
                limit=10,
                action=discord.AuditLogAction.ban
            ):

                target = entry.target

                if not target:
                    continue

                if int(target.id) != int(user_id):
                    continue

                # Audit log entries can be delayed.
                if (
                    discord.utils.utcnow()
                    - entry.created_at
                ).total_seconds() > 15:

                    continue

                return entry.user

        except discord.Forbidden:

            print(
                f"[Network] Missing View Audit Log permission "
                f"in {guild.name}"
            )

        except discord.HTTPException:

            pass

        except Exception as e:

            print(
                f"[Network] Audit log error: {e}"
            )

        return None

    # ========================================================
    # NETWORK BAN SYNCHRONIZATION
    # ========================================================

    @commands.Cog.listener()
    async def on_member_ban(
        self,
        guild,
        user
    ):

        current_guild_id = str(
            guild.id
        )

        user_id = int(
            user.id
        )

        pending_key = (
            guild.id,
            user_id
        )

        # ----------------------------------------------------
        # Ignore a ban that this NetworkCog itself generated.
        # This is the primary anti-loop mechanism.
        # ----------------------------------------------------

        pending_time = self.pending_network_bans.get(
            pending_key
        )

        if pending_time:

            if (
                time.time() - pending_time
                <= BAN_SYNC_PENDING_TTL
            ):

                self.pending_network_bans.pop(
                    pending_key,
                    None
                )

                return

            self.pending_network_bans.pop(
                pending_key,
                None
            )

        guild_networks = await self._db_get_guild_networks(
            current_guild_id
        )

        if not guild_networks:
            return

        # ----------------------------------------------------
        # Determine who performed the ban.
        # ----------------------------------------------------

        executor = await self._get_ban_executor(
            guild,
            user_id
        )

        if not executor:
            print(
                f"[Network] Ban sync skipped for {user_id}: "
                f"executor could not be verified."
            )
            return

        # ----------------------------------------------------
        # Process every network this guild belongs to.
        # ----------------------------------------------------

        processed_networks = set()

        for net in guild_networks:

            network_id = str(
                net.get("network_id", "")
            )

            if not network_id:
                continue

            if network_id in processed_networks:
                continue

            processed_networks.add(
                network_id
            )

            network = await self._db_get_network(
                network_id
            )

            if not network:
                continue

            network_owner_id = str(
                network.get("owner_id", "")
            )

            # ------------------------------------------------
            # IMPORTANT AUTHORIZATION CHECK
            #
            # Only the network owner can cause a global
            # network ban.
            # ------------------------------------------------

            if str(executor.id) != network_owner_id:

                print(
                    f"[Network] Global ban sync rejected. "
                    f"Executor {executor.id} is not network owner."
                )

                continue

            network_guilds = await self._db_get_network_guilds(
                network_id
            )

            for g_data in network_guilds:

                target_guild_id = str(
                    g_data.get("guild_id")
                )

                if target_guild_id == current_guild_id:
                    continue

                try:

                    target_guild = self.bot.get_guild(
                        int(target_guild_id)
                    )

                    if not target_guild:
                        continue

                    # ------------------------------------------------
                    # Check bot hierarchy.
                    # ------------------------------------------------

                    me = target_guild.me

                    if not me:

                        continue

                    if not me.guild_permissions.ban_members:

                        print(
                            f"[Network] Missing Ban Members "
                            f"permission in {target_guild.name}"
                        )

                        continue

                    # ------------------------------------------------
                    # Avoid trying to ban the server owner.
                    # ------------------------------------------------

                    if (
                        target_guild.owner_id
                        == user_id
                    ):

                        continue

                    # ------------------------------------------------
                    # Fetch member if present and verify hierarchy.
                    # ------------------------------------------------

                    target_member = target_guild.get_member(
                        user_id
                    )

                    if target_member:

                        if (
                            target_member.id
                            == target_guild.owner_id
                        ):
                            continue

                        if (
                            me.top_role
                            <= target_member.top_role
                        ):
                            print(
                                f"[Network] Cannot ban "
                                f"{user_id} in {target_guild.name}: "
                                f"target role is above/equal bot."
                            )
                            continue

                    # ------------------------------------------------
                    # Mark BEFORE banning.
                    # This prevents the resulting event from
                    # starting another propagation chain.
                    # ------------------------------------------------

                    self.pending_network_bans[
                        (
                            target_guild.id,
                            user_id
                        )
                    ] = time.time()

                    try:

                        await target_guild.ban(
                            user,
                            reason=(
                                f"{BAN_SYNC_REASON_PREFIX}"
                                f"{guild.id}"
                            )
                        )

                        print(
                            f"[Network] User {user_id} "
                            f"banned in {target_guild.name}"
                        )

                    except discord.Forbidden:

                        self.pending_network_bans.pop(
                            (
                                target_guild.id,
                                user_id
                            ),
                            None
                        )

                        print(
                            f"[Network] Forbidden while banning "
                            f"{user_id} in {target_guild.name}"
                        )

                    except discord.HTTPException:

                        self.pending_network_bans.pop(
                            (
                                target_guild.id,
                                user_id
                            ),
                            None
                        )

                    except Exception as e:

                        self.pending_network_bans.pop(
                            (
                                target_guild.id,
                                user_id
                            ),
                            None
                        )

                        print(
                            f"[Network] Ban synchronization error: {e}"
                        )

            # ----------------------------------------------------
            # Only process one matching network for this event.
            # Prevent duplicate propagation if multiple DB records
            # unexpectedly reference the same network.
            # ----------------------------------------------------

            break


# ============================================================
# SETUP
# ============================================================

async def setup(bot):
    await bot.add_cog(
        NetworkCog(bot)
    )
