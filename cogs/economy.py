import discord
from discord.ext import commands
from discord import app_commands
import datetime

class EconomySystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 1. أمر عرض الرصيد النقدي (Balance)
    @app_commands.command(name="balance", description="عرض الرصيد الحالي من النقاط | View your current balance")
    async def balance(self, interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        
        # هنا يتم جلب الرصيد من دالة قاعدة البيانات لديك (MongoDB)
        # user_coins = await self.bot.db.get_coins(target.id)
        user_coins = 2500  # قيمة افتراضية للتجربة

        embed = discord.Embed(
            title=f"🪙 رصيد الحساب | Balance",
            description=f"الرصيد الحالي لـ {target.mention}:\n**{user_coins:,}** نقطة / Coins",
            color=discord.Color.gold(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    # 2. أمر عرض المتجر الافتراضي (Shop)
    @app_commands.command(name="shop", description="عرض متجر السيرفر لشراء الرتب والمكافآت | View the server shop")
    async def shop(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛒 متجر السيرفر | Server Shop",
            description="استخدم النقاط التي حصلت عليها من التفاعل لشراء رتب وألقاب مجهزة!",
            color=discord.Color.purple()
        )

        # قائمة عناصر المتجر (يمكن ربطها بقاعدة البيانات لاحقاً)
        embed.add_field(
            name="1️⃣ رتبة مميز | VIP Role", 
            value="السعر: `1,000` نقطة\nالرمز التشغيلي: `vip`", 
            inline=False
        )
        embed.add_field(
            name="2️⃣ رتبة أسطورة | Legend Role", 
            value="السعر: `5,000` نقطة\nالرمز التشغيلي: `legend`", 
            inline=False
        )
        embed.add_field(
            name="3️⃣ لقب ملك التفاعل | Activity King", 
            value="السعر: `10,000` نقطة\nالرمز التشغيلي: `king`", 
            inline=False
        )

        embed.set_footer(text="للشراء استخدم الأمر: /buy <item_code>")
        await interaction.response.send_message(embed=embed)

    # 3. أمر شراء الرتب والألقاب من المتجر (Buy)
    @app_commands.command(name="buy", description="شراء عنصر من المتجر | Purchase an item from the shop")
    @app_commands.describe(item_code="رمز العنصر مثل: vip, legend, king")
    async def buy(self, interaction: discord.Interaction, item_code: str):
        await interaction.response.defer(ephemeral=True)

        # أسعار وتفاصيل العناصر
        items_db = {
            "vip": {"price": 1000, "role_name": "VIP"},
            "legend": {"price": 5000, "role_name": "Legend"},
            "king": {"price": 10000, "role_name": "Activity King"}
        }

        item_code = item_code.lower()
        if item_code not in items_db:
            await interaction.followup.send("❌ هذا العنصر غير موجود بالمتجر! تحقق من الكود باستخدام `/shop`.", ephemeral=True)
            return

        item = items_db[item_code]
        user_coins = 2500  # جلب رصيد المستخدم الحقيقي من DB

        # التحقق من كفاية الرصيد
        if user_coins < item["price"]:
            await interaction.followup.send(
                f"⚠️ رصيدك غير كافٍ! سعر العنصر **{item['price']:,}** بينما رصيدك **{user_coins:,}** نقطة.",
                ephemeral=True
            )
            return

        # البحث عن الرتبة وإسنادها للمستخدم
        role = discord.utils.get(interaction.guild.roles, name=item["role_name"])
        if not role:
            await interaction.followup.send(f"❌ لم يتم العثور على الرتبة المخصصة (`{item['role_name']}`) في السيرفر! يرجى التواصل مع الإدارة.", ephemeral=True)
            return

        if role in interaction.user.roles:
            await interaction.followup.send("⚠️ أنت تمتلك هذه الرتبة بالفعل!", ephemeral=True)
            return

        # الخصم وإسناد الرتبة
        # await self.bot.db.remove_coins(interaction.user.id, item["price"])
        await interaction.user.add_roles(role)

        embed = discord.Embed(
            title="🎉 عملية شراء ناجحة | Purchase Successful!",
            description=f"تم شراء الرتبة {role.mention} بنجاح مقابل **{item['price']:,}** نقطة!",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed)

    # 4. مكافأة يومية كتحفيز تفاعلي (Daily Reward)
    @app_commands.command(name="daily", description="استلام المكافأة اليومية | Claim your daily reward")
    async def daily(self, interaction: discord.Interaction):
        reward = 200
        # إضافة النقاط لحساب المستخدم في قاعدة البيانات
        # await self.bot.db.add_coins(interaction.user.id, reward)

        embed = discord.Embed(
            title="🎁 المكافأة اليومية | Daily Reward",
            description=f"لقد حصلت على **{reward}** نقطة مجانية اليوم! عد غداً للمزيد.",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(EconomySystem(bot))
