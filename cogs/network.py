import discord
from discord.ext import commands
import database as db

class NetworkCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="network", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def network(self, ctx):
        await ctx.send("تنسيق الأوامر المتاحة:\n`!network create <اسم_الشبكة>`\n`!network join <معرف_الشبكة>`\n`!network leave`\n`!network delete <معرف_الشبكة>`")

    @network.command(name="create")
    @commands.has_permissions(administrator=True)
    async def network_create(self, ctx, *, network_name: str):
        # توليد معرف فريد للشبكة بناءً على معرف السيرفر
        network_id = f"net_{ctx.guild.id}"
        existing = db.get_network(network_id)
        
        if existing:
            await ctx.send(f"⚠️ لديك شبكة مسبقاً بهذا المعرف: `{network_id}`")
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

        # ربط السيرفر الحالي بالشبكة وتحديد الروم الحالي رومَ ربط
        db.join_network(ctx.guild.id, network_id, ctx.channel.id)
        await ctx.send(f"✅ تم انضمام هذا السيرفر بنجاح إلى شبكة: **{network['network_name']}**!\nتم ربط هذا الروم (`#{ctx.channel.name}`) لنقل الرسائل.")
    @network.command(name="leave")
    @commands.has_permissions(administrator=True)
    async def network_leave(self, ctx):
        guild_data = db.get_guild_network(ctx.guild.id)
        if not guild_data:
            await ctx.send("❌ هذا السيرفر غير مربوط بأي شبكة حالياً!")
            return

        db.leave_network(ctx.guild.id)
        await ctx.send("✅ تم قطع اتصال السيرفر والغرفة بالشبكة بنجاح.")

    @network.command(name="delete")
    @commands.has_permissions(administrator=True)
    async def network_delete(self, ctx, network_id: str):
        network = db.get_network(network_id)
        if not network:
            await ctx.send("❌ لم يتم العثور على شبكة بهذا المعرف!")
            return

        if network.get("owner_id") != ctx.author.id:
            await ctx.send("⚠️ هذا الأمر مخصص لمالك الشبكة فقط!")
            return

        db.delete_network(network_id)
        await ctx.send(f"🗑️ تم حذف الشبكة `{network_id}` وإغلاق جميع اتصالاتها بنجاح.")

    # --- حدث مزامنة الرسائل بين السيرفرات ---
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        # التحقق مما إذا كان السيرفر منضم لشبكة والروم هو روم الربط
        guild_data = db.get_guild_network(message.guild.id)
        if not guild_data:
            return

        if str(message.channel.id) != guild_data.get("bound_channel_id"):
            return

        network_id = guild_data["network_id"]
        all_guilds = db.get_network_guilds(network_id)

        # إرسال الرسالة إلى باقي السيرفرات في نفس الشبكة
        for g_data in all_guilds:
            target_guild_id = int(g_data["guild_id"])
            target_channel_id = int(g_data["bound_channel_id"])

            if target_guild_id == message.guild.id:
                continue  # لا ترسل الرسالة لنفس السيرفر المرسل

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
            except Exception as e:
                print(f"خطأ في مزامنة الرسالة للسيرفر {target_guild.name}: {e}")

    # --- حدث تعميم الحظر (Global Ban-Sync) ---
    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        guild_data = db.get_guild_network(guild.id)
        if not guild_data or not guild_data.get("is_banned_sync_enabled"):
            return

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
