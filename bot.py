import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

from database.db import init_db

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True


class MokokoMateBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await init_db()
        await self.load_extension("cogs.recruit")
        await self.load_extension("cogs.verification")
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()


bot = MokokoMateBot()

@bot.event
async def on_ready():
    print(f"[모코코 메이트] 로그인 완료: {bot.user} ({bot.user.id})")

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN이 설정되지 않았습니다.")
    bot.run(TOKEN)
