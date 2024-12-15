import os
import json
import html
import logging
import asyncio
import xml.etree.ElementTree as ET
from aiohttp import web, ClientSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 从环境变量中读取配置
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8443))

if not TELEGRAM_TOKEN or not WEBHOOK_URL:
    raise ValueError("请确保 TELEGRAM_TOKEN 和 WEBHOOK_URL 环境变量已设置！")

# 用户数据存储 {chat_id: {"apis": [{"url": "url", "last_data": None}, ...]}}
user_data = {}
user_data_lock = asyncio.Lock()

scheduler = AsyncIOScheduler()

# ============ 数据解析与发送 ============
async def send_parsed_update(application, chat_id, raw_data, content_type):
    """ 解析任意格式的数据并发送到 Telegram """
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

        await send_dynamic_content(application, chat_id, data)
    except Exception as e:
        logger.error(f"数据解析失败：{e}")
        await application.bot.send_message(chat_id=chat_id, text="数据解析失败，请稍后再试。")

async def send_dynamic_content(application, chat_id, data):
    """ 发送动态内容（文本、图片、文件等） """
    try:
        media_sent = False
        message_parts = []

        for key, value in data.items():
            if isinstance(value, str) and value.startswith("http"):
                if any(value.endswith(ext) for ext in [".jpg", ".jpeg", ".png"]):
                    await application.bot.send_photo(chat_id=chat_id, photo=value, caption=f"<b>{key}</b>", parse_mode=ParseMode.HTML)
                    media_sent = True
                elif any(value.endswith(ext) for ext in [".mp4", ".mov"]):
                    await application.bot.send_video(chat_id=chat_id, video=value, caption=f"<b>{key}</b>", parse_mode=ParseMode.HTML)
                    media_sent = True
                elif any(value.endswith(ext) for ext in [".pdf", ".txt", ".docx"]):
                    await application.bot.send_document(chat_id=chat_id, document=value, caption=f"<b>{key}</b>", parse_mode=ParseMode.HTML)
                    media_sent = True
                else:
                    message_parts.append(f"<b>{key}:</b> <a href='{value}'>点击查看</a>")
            else:
                message_parts.append(f"<b>{key}:</b> {html.escape(str(value))}")

        if message_parts and not media_sent:
            await application.bot.send_message(chat_id=chat_id, text="\n".join(message_parts), parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"发送动态内容失败：{e}")

# ============ 命令处理器 ============
async def start_command(update: Update, context):
    await update.message.reply_text("欢迎！使用 /help 查看详细命令列表。")

async def help_command(update: Update, context):
    await update.message.reply_text(
        "命令列表：\n"
        "/start - 启动机器人\n"
        "/help - 查看帮助信息\n"
        "/addapi <API链接> - 添加一个 API 数据源\n"
        "/listapi - 列出已添加的 API\n"
        "/removeapi <编号> - 删除指定的 API 数据源\n\n"
        "功能说明：\n"
        "1. 支持 JSON、XML、纯文本等数据格式。\n"
        "2. 支持图片、视频、文件自动发送。\n"
        "3. 支持 API 主动推送和定时轮询更新。"
    )

async def add_api(update: Update, context):
    chat_id = update.effective_chat.id
    if len(context.args) != 1:
        await update.message.reply_text("格式：/addapi <API链接>")
        return
    api_link = context.args[0]
    async with user_data_lock:
        user_data.setdefault(chat_id, {"apis": []})["apis"].append({"url": api_link, "last_data": None})
    await update.message.reply_text(f"成功添加 API：{api_link}")

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
            await update.message.reply_text(f"成功删除 API：{removed['url']}")
        else:
            await update.message.reply_text("无效编号。")

# ============ 轮询任务 ============
async def poll_apis(application):
    async with user_data_lock:
        for chat_id, data in user_data.items():
            for api in data.get("apis", []):
                await check_api_update(application, chat_id, api)

async def check_api_update(application, chat_id, api):
    try:
        async with ClientSession() as session:
            async with session.get(api["url"]) as resp:
                content_type = resp.headers.get("Content-Type", "").lower()
                raw_data = await resp.text()
                if raw_data != api.get("last_data"):
                    api["last_data"] = raw_data
                    await send_parsed_update(application, chat_id, raw_data, content_type)
    except Exception as e:
        logger.error(f"轮询失败：{e}")

# ============ 主动推送 ============
async def handle_api_update(request):
    if request.method == 'POST':
        try:
            content_type = request.headers.get("Content-Type", "").lower()
            raw_data = await request.text()
            chat_id = 123456789  # 替换为动态用户ID
            await send_parsed_update(request.app['application'], chat_id, raw_data, content_type)
            return web.Response(text="更新已发送！")
        except Exception as e:
            logger.error(f"处理失败：{e}")
            return web.Response(text="处理失败", status=500)
    return web.Response(status=405, text="Method Not Allowed")

# ============ 主程序入口 ============
async def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("addapi", add_api))
    application.add_handler(CommandHandler("listapi", list_api))
    application.add_handler(CommandHandler("removeapi", remove_api))

    scheduler.add_job(poll_apis, "interval", seconds=3600, args=[application])
    scheduler.start()

    await application.bot.delete_webhook()
    await application.bot.set_webhook(WEBHOOK_URL)

    app = web.Application()
    app.router.add_post("/api_update", handle_api_update)
    app['application'] = application

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()

    logger.info(f"服务器已启动，监听端口 {PORT}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
