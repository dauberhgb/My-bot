import os
import discord
from discord.ext import commands

# تحديد الصلاحيات وقراءة الرسائل
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# رسالة للتأكد من اشتغال البوت
@bot.event
async def on_ready():
    print(f'البوت متصل الآن باسم: {bot.user}')

# جلب التوكن بأمان من متغيرات البيئة بدون كتابته هنا
TOKEN = os.getenv("TOKEN")

bot.run(TOKEN)
