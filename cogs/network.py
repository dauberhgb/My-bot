import discord
from discord.ext import commands
import database as db

class NetworkCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="network", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def network(self, ctx):
        await ctx.send("تنسيق الأوامر المتاحة:\n`!network create <اسم_الشبكة>`\n`!network join <معرف_الشبكة>`\n`!network leave <معرف_الشبكة>`\n`!network del`")

    @network.command(name="create")
    @commands.has_permissions(administrator=True)
    async def network_create(self, ctx, *, network_name: str):
        network_id = f"net_{str(ctx.guild.id)}"
        existing = db.get_network(network_id)
        
        if existing:
            await ctx.send(f"⚠️ هذا السيرفر قام بإنشاء شبكة مسبقاً بهذا المعرف: `{network_id}`. لا يمكنك إنشاء أكثر من شبكة واحدة.")
            return

        db.create_network(network_id, network_name, str(ctx.author.id))
        
        # ربط السيرفر المنشئ والروم الحالي بالشبكة تلقائياً (تحويل المعرفات لـ str)
        db.join_network(str(ctx.guild.id), network_id, str(ctx.channel.id))

        await ctx.send(f"✅ تم إنشاء الشبكة **{network_name}** بنجاح!\nمعرف الشبكة الخاص بك هو: `{network_id}`\nتم ربط هذا الروم (`#{ctx.channel.name}`) تلقائياً للشبكة.")

    @network.command(name="join")
    @commands.has_permissions(administrator=True)
    async def network_join(self, ctx, network_id: str):
        network = db.get_network(str(network_id))
        if not network:
            await ctx.send("❌ عذراً، لم يتم العثور على شبكة بهذا المعرف!")
            return

        db.join_network(str(ctx.guild.id), str(network_id), str(ctx.channel.id))
        await ctx.send(f"✅ تم انضمام هذا السيرفر بنجاح إلى شبكة: **{network['network_name']}**!\nتم ربط هذا الروم (`#{ctx.channel.name}`) لنقل الرسائل الخاصة بهذه الشبكة.")

    @network.command(name="leave")
    @commands.has_permissions(administrator=True)
    async def network_leave(self, ctx, network_id: str):
        guild_id_str = str(ctx.guild.id)
        guild_data_list = db.get_guild_networks(guild_id_str) if hasattr(db, 'get_guild_networks') else [db.get_guild_network(guild_id_str)]
        
        if not guild_data_list or not any(guild_data_list):
            await ctx.send("❌ هذا السيرفر غير مربوط بأي شبكة حالياً!")
            return

        db.leave_network(guild_id_str, str(network_id))
        await ctx.send(f"✅ تم قطع اتصال السيرفر بالشبكة `{network_id}` بنجاح.")

    @network.command(name="del", aliases=["delete"])
    @commands.has_permissions(administrator=True)
    async def network_delete(self, ctx, network_id: str = None):
        if not network_id:
            network_id = f"net_{str(ctx.guild.id)}"
        else:
            network_id = str(network_id)

        network = db.get_network(network_id)
        if not network:
            await ctx.send("❌ لم يتم العثور على شبكة بهذا المعرف!")
            return

        db.delete_network(network_id)
        await ctx.send(f"🗑️ تم حذف الشبكة `{network_id}` وإغلاق جميع اتصالاتها بنجاح.")

    # --- حدث مزامنة الرسائل بين السيرفرات ---
    @commands.Cog.listener()
    async def on_message(self, message):
        # منع التكرار: تجاهل رسائل البوتات والـ Webhooks والرسائل الخاصة
        if message.author.bot or message.webhook_id or not message.guild:
            return

        current_guild_id = str(message.guild.id)
        current_channel_id = str(message.channel.id)

        guild_networks = db.get_guild_networks(current_guild_id) if hasattr(db, 'get_guild_networks') else [db.get_guild_network(current_guild_id)]
        if not guild_networks:
            return

        # تحديد الشبكة المنتمية للروم الحالي
        active_network = None
        for g_data in guild_networks:
            if g_data and str(g_data.get("bound_channel_id")) == current_channel_id:
                active_network = g_data
                break

        if not active_network:
            return

        network_id = str(active_network["network_id"])
        all_guilds = db.get_network_guilds(network_id)

        # تجميع السيرفرات والرومات التي تم الإرسال لها لمنع التكرار
        sent_guilds = set()

        for g_data in all_guilds:
            if not g_data:
                continue

            target_guild_id = str(g_data["guild_id"])
            target_channel_id = str(g_data["bound_channel_id"])

            # عدم إرسال الرسالة إلى السيرفر المرسل نفسه أو سيرفر تم الإرسال له مسبقاً
            if target_guild_id == current_guild_id or target_guild_id in sent_guilds:
                continue

            target_guild = self.bot.get_guild(int(target_guild_id))
            if not target_guild:
                continue

            target_channel = target_guild.get_channel(int(target_channel_id))
            if not target_channel:
                continue

            try:
                webhooks = await target_channel.webhooks()
                webhook = webhooks[0] if webhooks else await target_channel.create_webhook(name="Fabric Sync")

                files = [await attachment.to_file() for attachment in message.attachments]

                await webhook.send(
                    content=message.content or "",
                    username=f"{message.author.name} ({message.guild.name})",
                    avatar_url=message.author.avatar.url if message.author.avatar else None,
                    files=files
                )
                sent_guilds.add(target_guild_id)
            except Exception as e:
                print(f"خطأ في مزامنة الرسالة للسيرفر {target_guild.name}: {e}")

    # --- حدث تعميم الحظر (Global Ban-Sync) ---
    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        guild_id_str = str(guild.id)
        guild_networks = db.get_guild_networks(guild_id_str) if hasattr(db, 'get_guild_networks') else [db.get_guild_network(guild_id_str)]
        if not guild_networks:
            return

        for guild_data in guild_networks:
            if not guild_data or not guild_data.get("is_banned_sync_enabled"):
                continue

            network_id = str(guild_data["network_id"])
            all_guilds = db.get_network_guilds(network_id)

            for g_data in all_guilds:
                if not g_data:
                    continue
                target_guild_id = str(g_data["guild_id"])
                if target_guild_id == guild_id_str:
                    continue

                target_guild = self.bot.get_guild(int(target_guild_id))
                if target_guild:
                    try:
                        await target_guild.ban(user, reason=f"حظر تعميمي أمني من شبكة السيرفرات (عبر سيرفر {guild.name})")
                    except Exception as e:
                        print(f"فشل حظر المستخدم في السيرفر {target_guild.name}: {e}")

async def setup(bot):
    await bot.add_cog(NetworkCog(bot))
