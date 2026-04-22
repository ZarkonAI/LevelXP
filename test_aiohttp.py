import asyncio
import aiohttp

TOKEN = "8341593591:AAGXwuB1SYy9Gi18CSwKFwWtavpUk4TXv3s"

async def main():
    url = f"https://api.telegram.org/bot{TOKEN}/getMe"
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            print(resp.status)
            print(await resp.text())

asyncio.run(main())