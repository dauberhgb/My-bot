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
            await ctx.send(f"⚠️ هذا السيرفر قام بإنشاء شبكة مسبقاً بهذا المعرف: `{network_id}`.")
            return

        db.create_network(network_id, network_name, str(ctx.author.id))
        db.join_network(str(ctx.guild.id), network_id, str(ctx.channel.id))

        await ctx.send(f"✅ تم إنشاء الشبكة **{network_name}** بنجاح!\nمعرف الشبكة الخاص بك هو:\n`{network_id}`\nتم ربط هذا الروم (`#{ctx.channel.name}`) تلقائياً للشبكة.")

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
        db.leave_network(str(ctx.guild.id), str(network_id))
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
        # 1. منع التكرار القاطع: تجاهل البوت، الـ Webhooks، أو أي أجهزة إرسال تلقائية
        if message.author.bot or message.webhook_id is not None or not message.guild:
            return

        # 2. تجاهل الأوامر لتجنب نقل أزرار أو أوامر !network بين السيرفرين
        prefix = self.bot.command_prefix
        if isinstance(prefix, str) and message.content.startswith(prefix):
            return

        current_guild_id = str(message.guild.id)
        current_channel_id = str(message.channel.id)

        # جلب الشبكات المربوطة بالسيرفر الحالي
        guild_networks = db.get_guild_networks(current_guild_id)
        if not guild_networks:
            return

        # البحث عن الشبكة المطابقة لروم إرسال الرسالة
        active_network_id = None
        for g_data in guild_networks:
            if str(g_data.get("bound_channel_id")) == current_channel_id:
                active_network_id = str(g_data.get("network_id"))
                break

        if not active_network_id:
            return

        # جلب جميع السيرفرات المنضمة لهذه الشبكة
        all_network_guilds = db.get_network_guilds(active_network_id)

        # قائمة لتتبع القنوات التي تم الإرسال لها لمنع التكرار نهائياً
        sent_channels = set()

        for g_data in all_network_guilds:
            target_guild_id = str(g_data.get("guild_id"))
            target_channel_id = str(g_data.get("bound_channel_id"))

            # تجاهل السيرفر الذي خرجت منه الرسالة
            if target_guild_id == current_guild_id:
                continue

            # تجاهل القناة إذا تم الإرسال لها مسبقاً في نفس الدورة
            if target_channel_id in sent_channels:
                continue

            target_guild = self.bot.get_guild(int(target_guild_id))
            if not target_guild:
                continue

            target_channel = target_guild.get_channel(int(target_channel_id))
            if not target_channel:
                continue

            try:
                # تسجيل القناة كقناة تم الإرسال إليها
                sent_channels.add(target_channel_id)

                # إنشاء أو جلب الـ Webhook الخاص بالبوت
                webhooks = await target_channel.webhooks()
                webhook = discord.utils.get(webhooks, name="Fabric Sync")
                if not webhook:
                    webhook = await target_channel.create_webhook(name="Fabric Sync")

                files = [await attachment.to_file() for attachment in message.attachments]

                avatar_url = message.author.avatar.url if message.author.avatar else message.author.default_avatar.url

                await webhook.send(
                    content=message.content or "",
                    username=f"{message.author.display_name} ({message.guild.name})",
                    avatar_url=avatar_url,
                    files=files
                )
            except Exception as e:
                print(f"خطأ في نقل الرسالة إلى {target_guild.name}: {e}")

async def setup(bot):
    await bot.add_cog(NetworkCog(bot))
