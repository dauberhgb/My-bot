import time
import asyncio
import discord
from discord.ext import commands
import database as db

def get_guild_lang(guild_id):
    if not guild_id:
        return "ar"
    try:
        settings = db.get_settings(guild_id)
        return settings.get("language", "ar")
    except Exception:
        return "ar"

class NetworkCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.processed_messages = {} 
        
    @commands.group(name="network", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def network(self, ctx):
        guild_id = ctx.guild.id if ctx.guild else None
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
        await ctx.send(help_text)

    @network.command(name="create")
    @commands.has_permissions(administrator=True)
    async def network_create(self, ctx, *, network_name: str):
        guild_id = ctx.guild.id if ctx.guild else None
        lang = get_guild_lang(guild_id)
        
        network_id = f"net_{str(ctx.guild.id)}"
        existing = db.get_network(network_id)
        
        if existing:
            msg = f"⚠️ This server has already created a network with this ID: `{network_id}`." if lang == "en" else f"⚠️ هذا السيرفر قام بإنشاء شبكة مسبقاً بهذا المعرف: `{network_id}`."
            await ctx.send(msg)
            return

        db.create_network(network_id, network_name, str(ctx.author.id))
        db.join_network(str(ctx.guild.id), network_id, str(ctx.channel.id))

        if lang == "en":
            msg = f"✅ Network **{network_name}** created successfully!\nYour network ID is:\n`{network_id}`\nThis channel (`#{ctx.channel.name}`) has been automatically linked to the network."
        else:
            msg = f"✅ تم إنشاء الشبكة **{network_name}** بنجاح!\nمعرف الشبكة الخاص بك هو:\n`{network_id}`\nتم ربط هذا الروم (`#{ctx.channel.name}`) تلقائياً للشبكة."
        await ctx.send(msg)

    @network.command(name="join")
    @commands.has_permissions(administrator=True)
    async def network_join(self, ctx, network_id: str):
        guild_id = ctx.guild.id if ctx.guild else None
        lang = get_guild_lang(guild_id)

        network = db.get_network(str(network_id))
        if not network:
            msg = "❌ Sorry, no network found with this ID!" if lang == "en" else "❌ عذراً، لم يتم العثور على شبكة بهذا المعرف!"
            await ctx.send(msg)
            return

        db.join_network(str(ctx.guild.id), str(network_id), str(ctx.channel.id))
        if lang == "en":
            msg = f"✅ This server has successfully joined the network: **{network['network_name']}**!\nThis channel (`#{ctx.channel.name}`) has been linked to relay messages for this network."
        else:
            msg = f"✅ تم انضمام هذا السيرفر بنجاح إلى شبكة: **{network['network_name']}**!\nتم ربط هذا الروم (`#{ctx.channel.name}`) لنقل الرسائل الخاصة بهذه الشبكة."
        await ctx.send(msg)

    @network.command(name="leave")
    @commands.has_permissions(administrator=True)
    async def network_leave(self, ctx, network_id: str):
        guild_id = ctx.guild.id if ctx.guild else None
        lang = get_guild_lang(guild_id)

        db.leave_network(str(ctx.guild.id), str(network_id))
        msg = f"✅ Successfully disconnected the server from network `{network_id}`." if lang == "en" else f"✅ تم قطع اتصال السيرفر بالشبكة `{network_id}` بنجاح."
        await ctx.send(msg)

    @network.command(name="del", aliases=["delete"])
    @commands.has_permissions(administrator=True)
    async def network_delete(self, ctx, network_id: str = None):
        guild_id = ctx.guild.id if ctx.guild else None
        lang = get_guild_lang(guild_id)

        if not network_id:
            network_id = f"net_{str(ctx.guild.id)}"
        else:
            network_id = str(network_id)

        network = db.get_network(network_id)
        if not network:
            msg = "❌ No network found with this ID!" if lang == "en" else "❌ لم يتم العثور على شبكة بهذا المعرف!"
            await ctx.send(msg)
            return

        db.delete_network(network_id)
        msg = f"🗑️ Network `{network_id}` has been deleted and all its connections closed successfully." if lang == "en" else f"🗑️ تم حذف الشبكة `{network_id}` وإغلاق جميع اتصالاتها بنجاح."
        await ctx.send(msg)

    @network.command(name="broadcast")
    @commands.has_permissions(administrator=True)
    async def network_broadcast(self, ctx, *, message_content: str):
        guild_id = ctx.guild.id if ctx.guild else None
        lang = get_guild_lang(guild_id)

        current_guild_id = str(ctx.guild.id)
        current_channel_id = str(ctx.channel.id)

        guild_networks = db.get_guild_networks(current_guild_id)
        if not guild_networks:
            msg = "❌ This server is not connected to any network to send a broadcast!" if lang == "en" else "❌ هذا السيرفر غير متصل بأي شبكة لإرسال تعميم!"
            await ctx.send(msg)
            return

        active_network_id = None
        for g_data in guild_networks:
            if str(g_data.get("bound_channel_id")) == current_channel_id:
                active_network_id = str(g_data.get("network_id"))
                break

        if not active_network_id:
            msg = "❌ Please run this command inside the channel bound to the network!" if lang == "en" else "❌ يرجى تنفيذ هذا الأمر داخل الروم المربوط بالشبكة!"
            await ctx.send(msg)
            return

        network = db.get_network(active_network_id)
        if not network:
            msg = "❌ Network data not found!" if lang == "en" else "❌ لم يتم العثور على بيانات الشبكة!"
            await ctx.send(msg)
            return

        owner_id = str(network.get("owner_id", ""))
        if str(ctx.author.id) != owner_id:
            msg = "🚫 This command is restricted to the network owner only!" if lang == "en" else "🚫 هذا الأمر مخصص لمالك الشبكة فقط!"
            await ctx.send(msg)
            return

        all_network_guilds = db.get_network_guilds(active_network_id)
        
        if lang == "en":
            embed = discord.Embed(
                title=f"📢 Official Broadcast from Network: {network.get('network_name', 'Network')}",
                description=message_content,
                color=discord.Color.gold()
            )
            embed.set_footer(text=f"Sent from server: {ctx.guild.name}")
        else:
            embed = discord.Embed(
                title=f"📢 تعميم رسمي من شبكة: {network.get('network_name', 'الشبكة')}",
                description=message_content,
                color=discord.Color.gold()
            )
            embed.set_footer(text=f"تم الإرسال من سيرفر: {ctx.guild.name}")

        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)

        # التحقق من وجود مرفق (صورة) لدمجه مباشرة داخل الـ Embed
        if ctx.message.attachments:
            first_attachment = ctx.message.attachments[0]
            # التأكد أن المرفق عبارة عن صورة
            if any(first_attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                embed.set_image(url=first_attachment.url)

        sent_count = 0
        for g_data in all_network_guilds:
            target_guild_id = str(g_data.get("guild_id"))
            target_channel_id = str(g_data.get("bound_channel_id"))

            target_guild = self.bot.get_guild(int(target_guild_id))
            if not target_guild:
                continue

            target_channel = target_guild.get_channel(int(target_channel_id))
            if not target_channel:
                continue

            try:
                # إرسال الـ Embed فقط بعد تضمين الصورة داخله
                await target_channel.send(embed=embed)
                sent_count += 1
                await asyncio.sleep(0.2)
            except Exception as e:
                print(f"فشل إرسال التعميم إلى {target_guild.name}: {e}")

        msg = f"✅ Broadcast sent successfully to **{sent_count}** connected servers/channels." if lang == "en" else f"✅ تم إرسال التعميم بنجاح إلى **{sent_count}** سيرفر/قناة متصلة بالشبكة."
        await ctx.send(msg)

    @network.command(name="stats", aliases=["list"])
    @commands.has_permissions(administrator=True)
    async def network_stats(self, ctx, network_id: str = None):
        guild_id = ctx.guild.id if ctx.guild else None
        lang = get_guild_lang(guild_id)

        current_guild_id = str(ctx.guild.id)
        current_channel_id = str(ctx.channel.id)

        if not network_id:
            guild_networks = db.get_guild_networks(current_guild_id)
            if guild_networks:
                for g_data in guild_networks:
                    if str(g_data.get("bound_channel_id")) == current_channel_id:
                        network_id = str(g_data.get("network_id"))
                        break
                if not network_id:
                    network_id = guild_networks[0].get("network_id")
            else:
                network_id = f"net_{current_guild_id}"

        network = db.get_network(str(network_id))
        if not network:
            msg = "❌ No network found with this ID!" if lang == "en" else "❌ لم يتم العثور على شبكة بهذا المعرف!"
            await ctx.send(msg)
            return

        network_guilds = db.get_network_guilds(str(network_id))
        is_server_in_network = any(str(g.get("guild_id")) == current_guild_id for g in network_guilds)
        
        if str(ctx.author.id) != str(network.get("owner_id")) and not is_server_in_network:
            msg = "🚫 You do not have permission to view stats for this network because your server is not linked to it!" if lang == "en" else "🚫 ليس لديك صلاحية لعرض إحصائيات هذه الشبكة لأن سيرفرك غير مرتبط بها!"
            await ctx.send(msg)
            return

        owner_user = await self.bot.fetch_user(int(network.get("owner_id", 0))) if network.get("owner_id") else ("Unknown" if lang == "en" else "غير معروف")

        description = ""
        total_members = 0

        for idx, g_data in enumerate(network_guilds, 1):
            target_guild = self.bot.get_guild(int(g_data.get("guild_id")))
            if target_guild:
                member_count = target_guild.member_count
                total_members += member_count
                if lang == "en":
                    description += f"**{idx}. {target_guild.name}** — 👥 `{member_count}` members\n"
                else:
                    description += f"**{idx}. {target_guild.name}** — 👥 `{member_count}` عضو\n"
            else:
                if lang == "en":
                    description += f"**{idx}. Server ID (`{g_data.get('guild_id')}`)** — *(Disconnected)*\n"
                else:
                    description += f"**{idx}. سيرفر معرف (`{g_data.get('guild_id')}`)** — *(غير متصل)*\n"

        if not description:
            description = "⚠️ No servers linked to this network currently." if lang == "en" else "⚠️ لا يوجد سيرفرات مرتبطة بهذه الشبكة حالياً."

        if lang == "en":
            embed = discord.Embed(
                title=f"📊 Statistics & List for Network: {network.get('network_name')}",
                description=description,
                color=discord.Color.green()
            )
            embed.add_field(name="🆔 Network ID", value=f"`{network_id}`", inline=True)
            embed.add_field(name="👑 Owner", value=f"{owner_user}", inline=True)
            embed.add_field(name="🏰 Linked Servers", value=f"`{len(network_guilds)}`", inline=True)
            embed.set_footer(text=f"Total members in network: {total_members} members")
        else:
            embed = discord.Embed(
                title=f"📊 إحصائيات وقائمة شبكة: {network.get('network_name')}",
                description=description,
                color=discord.Color.green()
            )
            embed.add_field(name="🆔 معرف الشبكة", value=f"`{network_id}`", inline=True)
            embed.add_field(name="👑 المالك", value=f"{owner_user}", inline=True)
            embed.add_field(name="🏰 عدد السيرفرات المربوطة", value=f"`{len(network_guilds)}`", inline=True)
            embed.set_footer(text=f"إجمالي الأعضاء في الشبكة: {total_members} عضو")

        await ctx.send(embed=embed)

    # --- حدث مزامنة الرسائل بين السيرفرات ---
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.webhook_id is not None or not message.guild:
            return

        prefix = self.bot.command_prefix
        if isinstance(prefix, str) and message.content.startswith(prefix):
            return

        current_time = time.time()
        self.processed_messages = {
            k: v
            for k, v in self.processed_messages.items()
            if current_time - v < 5
        }

        msg_signature = (
            f"{message.author.id}_{message.content}_{message.channel.id}"
        )

        if msg_signature in self.processed_messages:
            return

        self.processed_messages[msg_signature] = current_time

        current_guild_id = str(message.guild.id)
        current_channel_id = str(message.channel.id)

        guild_networks = db.get_guild_networks(current_guild_id)
        if not guild_networks:
            return

        active_network_id = None
        for g_data in guild_networks:
            if str(g_data.get("bound_channel_id")) == current_channel_id:
                active_network_id = str(g_data.get("network_id"))
                break

        if not active_network_id:
            return

        all_network_guilds = db.get_network_guilds(active_network_id)
        sent_channels = set()

        for g_data in all_network_guilds:
            target_guild_id = str(g_data.get("guild_id"))
            target_channel_id = str(g_data.get("bound_channel_id"))

            if target_guild_id == current_guild_id or target_channel_id in sent_channels:
                continue

            target_guild = self.bot.get_guild(int(target_guild_id))
            if not target_guild:
                continue

            target_channel = target_guild.get_channel(int(target_channel_id))
            if not target_channel:
                continue

            try:
                sent_channels.add(target_channel_id)

                webhooks = await target_channel.webhooks()
                webhook = discord.utils.get(webhooks, name="Fabric Sync")
                if not webhook:
                    webhook = await target_channel.create_webhook(name="Fabric Sync")

                files = [await attachment.to_file() for attachment in message.attachments]
                avatar_url = message.author.avatar.url if message.author.avatar else message.author.default_avatar.url

                sent_msg = await webhook.send(
                    content=message.content or "",
                    username=f"{message.author.display_name} ({message.guild.name})",
                    avatar_url=avatar_url,
                    files=files,
                    wait=True
                )
                
                if not hasattr(self, "synced_messages"):
                    self.synced_messages = {}
                self.synced_messages[message.id] = sent_msg.id
                self.synced_messages[sent_msg.id] = message.id
            except Exception as e:
                print(f"خطأ في نقل الرسالة إلى {target_guild.name}: {e}")
                
    # --- حدث مزامنة التفاعلات (Reactions) مع تتبع أسماء المتفاعلين ---
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.member and payload.member.bot:
            return

        if not hasattr(self, "synced_messages") or payload.message_id not in self.synced_messages:
            return

        current_guild_id = str(payload.guild_id)
        guild_networks = db.get_guild_networks(current_guild_id)
        if not guild_networks:
            return

        current_channel_id = str(payload.channel_id)
        active_network_id = None
        for g_data in guild_networks:
            if str(g_data.get("bound_channel_id")) == current_channel_id:
                active_network_id = str(g_data.get("network_id"))
                break

        if not active_network_id:
            return

        all_network_guilds = db.get_network_guilds(active_network_id)
        
        for g_data in all_network_guilds:
            target_guild_id = str(g_data.get("guild_id"))
            target_channel_id = str(g_data.get("bound_channel_id"))

            if target_guild_id == current_guild_id:
                continue

            target_guild = self.bot.get_guild(int(target_guild_id))
            if not target_guild:
                continue

            target_channel = target_guild.get_channel(int(target_channel_id))
            if not target_channel:
                continue

            try:
                target_msg_id = self.synced_messages.get(payload.message_id)
                if not target_msg_id:
                    continue
                
                target_message = await target_channel.fetch_message(target_msg_id)
                if target_message:
                    # 1. وضع التفاعل شكلياً عبر البوت للتزامن البصري
                    await target_message.add_reaction(payload.emoji)
                    
                    # 2. تحديث تذييل الرسالة (Footer) أو محتواها لتضمين اسم المستخدم الحقيقي وسيرفره لتجاوز مشكلة علامة الـ APP
                    reactor_name = payload.member.display_name if payload.member else "User"
                    server_name = payload.member.guild.name if payload.member and payload.member.guild else target_guild.name
                    emoji_str = str(payload.emoji)
                    
                    if target_message.embeds:
                        embed = target_message.embeds[0]
                        current_footer = embed.footer.text or ""
                        new_footer_text = f"{current_footer} | {emoji_str} بواسطة: {reactor_name} ({server_name})" if current_footer else f"{emoji_str} بواسطة: {reactor_name} ({server_name})"
                        if len(new_footer_text) <= 2048:
                            embed.set_footer(text=new_footer_text)
                            await target_message.edit(embed=embed)
                    else:
                        current_content = target_message.content or ""
                        append_text = f"\n{emoji_str} بواسطة: {reactor_name} ({server_name})"
                        if len(current_content) + len(append_text) <= 2000:
                            await target_message.edit(content=current_content + append_text)
            except Exception as e:
                print(f"خطأ في مزامنة وتحديث تفاعلات الأسماء: {e}")

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        current_guild_id = str(guild.id)
        
        guild_networks = db.get_guild_networks(current_guild_id)
        if not guild_networks:
            return

        banned_guilds = set()

        for net in guild_networks:
            network_id = net.get("network_id")
            if not network_id:
                continue

            network_guilds = db.get_network_guilds(network_id)
            for g_data in network_guilds:
                target_guild_id = str(g_data.get("guild_id"))
                
                if target_guild_id == current_guild_id or target_guild_id in banned_guilds:
                    continue

                target_guild = self.bot.get_guild(int(target_guild_id))
                if not target_guild:
                    continue

                try:
                    await target_guild.ban(
                        user, 
                        reason=f"مزامنة حظر تلقائية: تم حظره من سيرفر {guild.name}"
                    )
                    banned_guilds.add(target_guild_id)
                    print(f"تم حظر {user.name} تلقائياً من سيرفر {target_guild.name}")
                except discord.Forbidden:
                    print(f"فشل حظر {user.name} في {target_guild.name}: البوت لا يملك صلاحية Ban Members")
                except Exception as e:
                    print(f"خطأ أثناء حظر {user.name} في {target_guild.name}: {e}")

async def setup(bot):
    await bot.add_cog(NetworkCog(bot))
