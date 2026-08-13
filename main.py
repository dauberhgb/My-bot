import os
import threading
from flask import Flask
import discord
from discord.ext import commands

# 1. إعداد خادم ويب بسيط لإرضاء Render
app = Flask('')

@app.route('/')
def home():
    return "البوت يعمل بنجاح!"

def run_web_server():
    # Render يمرر رقم المنفذ تلقائياً في PORT
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# تشغيل خادم الويب في الخلفية
threading.Thread(target=run_web_server).start()

# 2. إعداد وتشغيل بوت ديسكورد
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'البوت متصل الآن باسم: {bot.user}')

TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
