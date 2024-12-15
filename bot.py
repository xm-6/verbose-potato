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

# ============ 动态解析与发送内容 ============

async def download_file(url):
    """下载文件并返回内容"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
                else:
                    logger.error(f"下载失败：{url}，状态码：{resp.status}")
    except Exception as e:
        logger.error(f"下载文件失败：{e}")
    return None

async def parse_and_send_content(application, chat_id, raw_data, content_type):
    """根据数据类型解析并发送消息"""
    try:
        if content_type == "application/json":
            data = json.loads(raw_data)
        elif content_type in ["application/xml", "text/xml"]:
            root = ET.fromstring(raw_data)
            data = {child.tag: child.text for child in root}
        elif content_type in ["text/html", "text/plain"]:
            data = {"content": raw_data}
        else:
            data = {"raw_data": raw_data}

        await format_and_send(application, chat_id, data)
    except Exception as e:
        logger.error(f"解析数据失败：{e}")
        await application.bot.send_message(chat_id=chat_id, text="数据解析失败，请稍后再试。")

async def format_and_send(application, chat_id, data):
    """格式化数据并发送，支持图片、视频、文本等"""
    message_parts = []
    media_sent = False

    for key, value in data.items():
        if isinstance(value, str) and value.startswith("http"):
            if any(value.endswith(ext) for ext in [".jpg", ".jpeg", ".png"]):
                file_content = await download_file(value)
                if file_content:
                    await application.bot.send_photo(
                        chat_id=chat_id,
                        photo=file_content,
                        caption=f"<b>{key}</b>",
                        parse_mode=ParseMode.HTML
                    )
                    media_sent = True
            elif any(value.endswith(ext) for ext in [".mp4", ".mov"]):
                await application.bot.send_video(chat_id=chat_id, video=value, caption=f"<b>{key}</b>", parse_mode=ParseMode.HTML)
                media_sent = True
            else:
                message_parts.append(f"<b>{key}:</b> {value}")
        else:
            message_parts.append(f"<b>{key}:</b> {value}")

    if message_parts and not media_sent:
        await application.bot.send_message(chat_id=chat_id, text="\n".join(message_parts), parse_mode=ParseMode.HTML)

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
    await application.bot.set_webhook(WEBHOOK_URL)

    app = web.Application()
    app.router.add_post("/api_update", handle_api_update)
    app['application'] = application

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
