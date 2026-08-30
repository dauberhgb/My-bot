import discord
from discord.ext import commands
from discord import app_commands
import datetime

class ServerAnalytics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 1. تتبع الرسائل لتحديد أوقات الذروة وأكثر القنوات تفاعلاً
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        current_hour = datetime.datetime.utcnow().hour
        guild_id = str(message.guild.id)
        channel_id = str(message.channel.id)

        # هنا يتم التحديث في قاعدة البيانات (تزيد عداد الساعة وعداد القناة)
        # مثال لمنطق MongoDB:
        # db.analytics.update_one(
        #     {"guild_id": guild_id},
        #     {
        #         "$inc": {
        #             f"hours.{current_hour}": 1,
        #             f"channels.{channel_id}": 1,
        #             "total_messages": 1
        #         }
        #     },
        #     upsert=True
        # )

    # 2. تتبع انضمام الأعضاء لحساب نسبة النمو الأسبوعي
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild_id = str(member.guild.id)
        # db.analytics.update_one({"guild_id": guild_id}, {"$inc": {"joins_this_week": 1}}, upsert=True)

    # 3. أمر السلاش لعرض التقرير الشامل
    @app_commands.command(name="analytics", description="عرض تقرير إحصائيات وتفاعل السيرفر")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def show_analytics(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # بيانات افتراضية توضيحية (يتم استبدالها بالقراءات الحقيقية من DB)
        peak_hour = "08:00 PM - 09:00 PM"
        top_channel = interaction.channel.mention
        weekly_growth = "+12.5%"

        embed = discord.Embed(
            title=f"📊 تقرير إحصائيات السيرفر | {interaction.guild.name}",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)

        embed.add_field(name="⏰ ساعة الذروة (الأكثر نشاطاً)", value=f"`{peak_hour}`", inline=False)
        embed.add_field(name="💬 القناة الأكثر تفاعلاً", value=top_channel, inline=True)
        embed.add_field(name="📈 نسبة النمو الأسبوعي", value=f"`{weekly_growth}`", inline=True)
        embed.add_field(name="👥 إجمالي الأعضاء", value=f"`{interaction.guild.member_count}` عضو", inline=False)

        embed.set_footer(text="تم استخراج البيانات بواسطة نظام التحليلات الذكي")

        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ServerAnalytics(bot))
