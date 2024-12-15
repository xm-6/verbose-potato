import os
import asyncio
import logging
import json
import xml.etree.ElementTree as ET
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.constants import ParseMode
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

async def add_api(update: Update, context):
    chat_id = update.effective_chat.id
    if len(context.args) != 1:
        await update.message.reply_text("格式：/addapi <API链接>")
        return
    api_link = context.args[0]
    async with user_data_lock:
        user_data.setdefault(chat_id, {"apis": []})["apis"].append({"url": api_link, "last_id": None})
    await update.message.reply_text(f"已添加 API：{api_link}")

async def list_api(update: Update, context):
    chat_id = update.effective_chat.id
    async with user_data_lock:
        apis = user_data.get(chat_id, {}).get("apis", [])
    if not apis:
        await update.message.reply_text("你还没有添加任何 API。")
    else:
        lines = [f"{i+1}. {api['url']}" for i, api in enumerate(apis)]
        await update.message.reply_text("已添加的 API 列表：\n" + "\n".join(lines))

async def remove_api(update: Update, context):
    chat_id = update.effective_chat.id
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("格式：/removeapi <编号>")
        return
    idx = int(context.args[0]) - 1
    async with user_data_lock:
        apis = user_data.get(chat_id, {}).get("apis", [])
        if 0 <= idx < len(apis):
            removed = apis.pop(idx)
            await update.message.reply_text(f"已删除 API：{removed['url']}")
        else:
            await update.message.reply_text("无效编号。")

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
        application = request.app["application"]
        update = Update.de_json(update_data, application.bot)
        await application.process_update(update)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"处理 Telegram 更新时出错：{e}")
        return web.Response(text="处理失败", status=500)

# ============ 定时轮询与主动推送 ============

async def poll_apis(application):
    """定时轮询用户添加的 API"""
    async with aiohttp.ClientSession() as session:
        async with user_data_lock:
            for chat_id, data in user_data.items():
                for api in data.get("apis", []):
                    await check_and_notify(application, chat_id, api, session)

async def check_and_notify(application, chat_id, api, session):
    """检查 API 是否有更新"""
    try:
        async with session.get(api["url"]) as resp:
            if resp.status == 200:
                data = await resp.json()
                new_id = data.get("id")
                old_id = api.get("last_id")
                if new_id and new_id != old_id:
                    api["last_id"] = new_id
                    await parse_and_send_content(application, chat_id, json.dumps(data), "application/json")
            else:
                logger.error(f"请求失败：{api['url']} 状态码：{resp.status}")
    except Exception as e:
        logger.error(f"轮询出错：{api['url']} 错误：{e}")

# ============ 主程序入口 ============

async def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # 注册命令
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("addapi", add_api))
    application.add_handler(CommandHandler("listapi", list_api))
    application.add_handler(CommandHandler("removeapi", remove_api))

    await application.bot.delete_webhook()
    await application.bot.set_webhook(WEBHOOK_URL + "/telegram_webhook")

    app = web.Application()
    app.router.add_post("/telegram_webhook", telegram_webhook_handler)
    app.router.add_post("/api_update", handle_api_update)
    app["application"] = application

    scheduler.add_job(poll_apis, "interval", seconds=3600, args=[application])
    scheduler.start()

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    logger.info(f"服务器已启动，监听端口：{PORT}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
