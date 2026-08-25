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
        # توليد معرف فريد للشبكة بناءً على معرف السيرفر
        network_id = f"net_{ctx.guild.id}"
        existing = db.get_network(network_id)
        
        # حصر الإنشاء: السيرفر لا يمكنه إنشاء أكثر من شبكة واحدة
        if existing:
            await ctx.send(f"⚠️ هذا السيرفر قام بإنشاء شبكة مسبقاً بهذا المعرف: `{network_id}`. لا يمكنك إنشاء أكثر من شبكة واحدة.")
            return

        db.create_network(network_id, network_name, ctx.author.id)
        await ctx.send(f"✅ تم إنشاء الشبكة **{network_name}** بنجاح!\nمعرف الشبكة الخاص بك هو: `{network_id}`\nشارك هذا المعرف مع السيرفرات الأخرى للانضمام.")

    @network.command(name="join")
    @commands.has_permissions(administrator=True)
    async def network_join(self, ctx, network_id: str):
        network = db.get_network(network_id)
        if not network:
            await ctx.send("❌ عذراً، لم يتم العثور على شبكة بهذا المعرف!")
            return

        # الانضمام متاح لأكثر من شبكة (يربط السيرفر والقناة الحالية بالشبكة المحددة)
        db.join_network(ctx.guild.id, network_id, ctx.channel.id)
        await ctx.send(f"✅ تم انضمام هذا السيرفر بنجاح إلى شبكة: **{network['network_name']}**!\nتم ربط هذا الروم (`#{ctx.channel.name}`) لنقل الرسائل الخاصة بهذه الشبكة.")

    @network.command(name="leave")
    @commands.has_permissions(administrator=True)
    async def network_leave(self, ctx, network_id: str):
        # تحديد المعرف مغادرة الشبكة بما أن السيرفر قد يكون منضماً لأكثر من شبكة
        guild_data_list = db.get_guild_networks(ctx.guild.id) if hasattr(db, 'get_guild_networks') else [db.get_guild_network(ctx.guild.id)]
        
        if not guild_data_list or not any(guild_data_list):
            await ctx.send("❌ هذا السيرفر غير مربوط بأي شبكة حالياً!")
            return

        db.leave_network(ctx.guild.id, network_id)
        await ctx.send(f"✅ تم قطع اتصال السيرفر بالشبكة `{network_id}` بنجاح.")

    @network.command(name="del", aliases=["delete"])
    @commands.has_permissions(administrator=True)
    async def network_delete(self, ctx, network_id: str = None):
        # إذا لم يتم تحديد network_id يُجلب المعرف الخاص بنفس السيرفر تلقائياً
        if not network_id:
            network_id = f"net_{ctx.guild.id}"

        network = db.get_network(network_id)
        if not network:
            await ctx.send("❌ لم يتم العثور على شبكة بهذا المعرف!")
            return

        db.delete_network(network_id)
        await ctx.send(f"🗑️ تم حذف الشبكة `{network_id}` وإغلاق جميع اتصالاتها بنجاح.")

    # --- حدث مزامنة الرسائل بين السيرفرات ---
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        # جلب جميع ارتباطات السيرفر الحالي بالشبكات (لدعم تعدد الانضمام)
        guild_networks = db.get_guild_networks(message.guild.id) if hasattr(db, 'get_guild_networks') else [db.get_guild_network(message.guild.id)]
        if not guild_networks:
            return

        # البحث عن القناة المرتبطة بالشبكة
        active_network = None
        for g_data in guild_networks:
            if g_data and str(message.channel.id) == str(g_data.get("bound_channel_id")):
                active_network = g_data
                break

        if not active_network:
            return

        network_id = active_network["network_id"]
        all_guilds = db.get_network_guilds(network_id)

        # تجميع السيرفرات لمنع تكرار الإرسال لنفس السيرفر
        sent_guilds = set()

        # إرسال الرسالة إلى باقي السيرفرات في نفس الشبكة
        for g_data in all_guilds:
            target_guild_id = int(g_data["guild_id"])
            target_channel_id = int(g_data["bound_channel_id"])

            # تجاهل السيرفر المرسل أو السيرفرات التي تم الإرسال لها مسبقاً
            if target_guild_id == message.guild.id or target_guild_id in sent_guilds:
                continue

            target_guild = self.bot.get_guild(target_guild_id)
            if not target_guild:
                continue

            target_channel = target_guild.get_channel(target_channel_id)
            if not target_channel:
                continue

            # البحث عن Webhook في الروم أو إنشاؤه لإرسال الرسالة باسم المستخدم الحقيقي
            try:
                webhooks = await target_channel.webhooks()
                webhook = webhooks[0] if webhooks else await target_channel.create_webhook(name="Fabric Sync")

                # تجهيز المرفقات إن وجدت
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
        guild_networks = db.get_guild_networks(guild.id) if hasattr(db, 'get_guild_networks') else [db.get_guild_network(guild.id)]
        if not guild_networks:
            return

        for guild_data in guild_networks:
            if not guild_data or not guild_data.get("is_banned_sync_enabled"):
                continue

            network_id = guild_data["network_id"]
            all_guilds = db.get_network_guilds(network_id)

            for g_data in all_guilds:
                target_guild_id = int(g_data["guild_id"])
                if target_guild_id == guild.id:
                    continue

                target_guild = self.bot.get_guild(target_guild_id)
                if target_guild:
                    try:
                        await target_guild.ban(user, reason=f"حظر تعميمي أمني من شبكة السيرفرات (عبر سيرفر {guild.name})")
                    except Exception as e:
                        print(f"فشل حظر المستخدم في السيرفر {target_guild.name}: {e}")

async def setup(bot):
    await bot.add_cog(NetworkCog(bot))
