import os
import asyncio
import logging
import json
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import Application, CommandHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8443))

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN 未设置")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL 未设置")

# 用户数据存储
user_data = {}
user_data_lock = asyncio.Lock()
scheduler = AsyncIOScheduler()

# ============ 命令处理器 ============

async def start_command(update: Update, context):
    logger.info(f"收到 /start 命令来自：{update.effective_chat.id}")
    await update.message.reply_text("欢迎！使用 /help 查看所有命令。")

async def help_command(update: Update, context):
    await update.message.reply_text(
        "/start - 启动机器人\n"
        "/help - 获取帮助\n"
        "/addapi <API链接> - 添加 API\n"
        "/listapi - 列出已添加 API\n"
        "/removeapi <编号> - 删除 API\n\n"
        "机器人支持 JSON、XML、HTML、图片、视频等格式，"
        "同时支持 API 主动推送与定时轮询更新！"
    )

# ============ API 更新处理函数 ============

async def handle_api_update(request):
    try:
        data = await request.json()
        logger.info(f"收到的 API 更新数据：{data}")
        # 可以在此处解析和处理收到的 API 数据
        return web.Response(text="更新已收到")
    except Exception as e:
        logger.error(f"处理 API 更新时出错：{e}")
        return web.Response(text="处理失败", status=500)

# ============ Telegram Webhook 处理函数 ============

async def telegram_webhook_handler(request):
    """处理 Telegram Webhook 更新"""
    try:
        update_data = await request.json()
        logger.info(f"收到 Telegram 更新数据：{update_data}")
        
        # 获取 Application 对象
        application = request.app["application"]
        update = Update.de_json(update_data, application.bot)
        await application.process_update(update)
        
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"处理 Telegram 更新时出错：{e}")
        return web.Response(text="处理失败", status=500)

# ============ 主程序入口 ============

async def main():
    # 初始化 Telegram 应用
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # 注册命令
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))

    await application.bot.delete_webhook()
    await application.bot.set_webhook(WEBHOOK_URL + "/telegram_webhook")

    # 初始化 Aiohttp Web 应用
    app = web.Application()
    app["application"] = application  # 将 Telegram 应用对象存入 Aiohttp 应用的共享空间
    app.router.add_post("/telegram_webhook", telegram_webhook_handler)
    app.router.add_post("/api_update", handle_api_update)

    # 启动服务器
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    logger.info(f"服务器已启动，监听端口：{PORT}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
