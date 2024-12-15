import os
from aiohttp import web

async def handle(request):
    data = await request.json()
    print("收到来自 Telegram 的数据：", data)
    return web.Response(text="OK")

async def main():
    app = web.Application()
    app.router.add_post("/", handle)
    port = int(os.getenv("PORT", 8443))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    print(f"服务器启动，监听端口：{port}")
    await site.start()

if __name__ == "__main__":
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.run_forever()
