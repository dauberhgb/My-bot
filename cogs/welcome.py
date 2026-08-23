import discord
from discord.ext import commands
import database as db

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="set_texts")
    @commands.has_permissions(administrator=True)
    async def set_texts(self, ctx, t1: str, t2: str, t3: str):
        """تعديل النصوص الثلاثة المطبوعة على الإطار"""
        settings = db.get_settings(ctx.guild.id) or {}
        settings.update({
            "text_1": t1,
            "text_2": t2,
            "text_3": t3
        })
        db.save_settings(ctx.guild.id, settings)
        await ctx.send("✅ تم تحديث النصوص المطبوعة على الإطار بنجاح!")

    @commands.command(name="set_colors")
    @commands.has_permissions(administrator=True)
    async def set_colors(self, ctx, c1: str, c2: str, c3: str):
        """تعديل ألوان النصوص الثلاثة المطبوعة بصيغة Hex"""
        for color in [c1, c2, c3]:
            if not color.startswith("#") or len(color) != 7:
                await ctx.send("❌ يرجى إدخال ألوان بصيغة Hex صحيحة مثل: `#FFFFFF`")
                return

        settings = db.get_settings(ctx.guild.id) or {}
        settings.update({
            "color_1": c1,
            "color_2": c2,
            "color_3": c3
        })
        db.save_settings(ctx.guild.id, settings)
        await ctx.send("🎨 تم تحديث ألوان النصوص الثلاثة بنجاح!")

async def setup(bot):
    await bot.add_cog(Welcome(bot))
