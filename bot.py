import os
import asyncio
import html
import logging
import aiohttp
from aiohttp import web
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# 日志设置
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 从环境变量读取必要配置
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8443))

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN 环境变量未设置")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL 环境变量未设置")

# 内存数据存储结构
user_data = {}
user_data_lock = asyncio.Lock()

# 定时任务调度器
scheduler = AsyncIOScheduler()

# 命令处理函数
async def start_command(update: Update, context):
    logger.info(f"用户 {update.effective_chat.id} 使用了 /start")
    await update.message.reply_text("欢迎使用 Telegram Bot！\n发送 /help 查看可用命令。")

async def help_command(update: Update, context):
    logger.info(f"用户 {update.effective_chat.id} 使用了 /help")
    await update.message.reply_text(
        "可用命令：\n"
        "/start - 启动机器人\n"
        "/help - 获取帮助\n"
        "/addapi <API链接> - 添加一个 API\n"
        "/listapi - 查看所有已添加的 API\n"
        "/removeapi <编号> - 删除指定 API\n"
        "机器人会自动监控 API，并推送最新消息！"
    )

async def add_api(update: Update, context):
    chat_id = update.effective_chat.id
    logger.info(f"用户 {chat_id} 使用了 /addapi 命令")

    if len(context.args) != 1:
        await update.message.reply_text("请使用正确的格式：/addapi <API链接>")
        return

    api_link = context.args[0]
    async with user_data_lock:
        user_data.setdefault(chat_id, {"apis": []})["apis"].append({"url": api_link, "last_seen": None})
    await update.message.reply_text(f"成功添加 API：{api_link}")

async def list_api(update: Update, context):
    chat_id = update.effective_chat.id
    logger.info(f"用户 {chat_id} 使用了 /listapi 命令")

    async with user_data_lock:
        apis = user_data.get(chat_id, {}).get("apis", [])

    if not apis:
        await update.message.reply_text("你还没有添加任何 API。")
    else:
        reply_text = "你已添加的 API 列表：\n" + "\n".join(
            f"{idx + 1}. {html.escape(api['url'])}" for idx, api in enumerate(apis)
        )
        await update.message.reply_text(reply_text)

async def remove_api(update: Update, context):
    chat_id = update.effective_chat.id
    logger.info(f"用户 {chat_id} 使用了 /removeapi 命令")

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("请使用正确的格式：/removeapi <编号>")
        return

    api_index = int(context.args[0]) - 1
    async with user_data_lock:
        apis = user_data.get(chat_id, {}).get("apis", [])
        if 0 <= api_index < len(apis):
            removed = apis.pop(api_index)
            await update.message.reply_text(f"成功删除 API：{html.escape(removed['url'])}")
        else:
            await update.message.reply_text("无效的编号。")

# 定时任务：轮询 API
async def poll_apis(application):
    logger.info("开始轮询 API")
    async with aiohttp.ClientSession() as session:
        async with user_data_lock:
            for chat_id, data in user_data.items():
                apis = data.get("apis", [])
                for api in apis:
                    try:
                        async with session.get(api["url"]) as response:
                            if response.status == 200:
                                new_data = await response.json()
                                if "id" in new_data and api["last_seen"] != new_data["id"]:
                                    api["last_seen"] = new_data["id"]
                                    message = format_message(new_data)
                                    await send_message(application, chat_id, message)
                            else:
                                logger.error(f"API 请求失败：{api['url']}，状态码：{response.status}")
                    except Exception as e:
                        logger.error(f"轮询 API 出错：{api['url']}，错误：{e}")

def format_message(data):
    title = html.escape(data.get("title", "无标题"))
    content = html.escape(data.get("content", "无内容"))
    return f"<b>{title}</b>\n{content}"

async def send_message(application, chat_id, message):
    try:
        await application.bot.send_message(chat_id=chat_id, text=message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"发送消息失败给 {chat_id}，错误：{e}")

# Webhook 路由处理函数
async def handle_webhook(request):
    if request.method == 'GET':
        return web.Response(text="Webhook is active!")

    if request.method == 'POST':
        try:
            data = await request.json()
            logger.info(f"收到的 Webhook 数据：{data}")
            update = Update.de_json(data, request.app['application'].bot)
            await request.app['application'].process_update(update)
            return web.Response(text="OK")
        except Exception as e:
            logger.error(f"Webhook 处理失败：{e}")
            return web.Response(text=f"Error: {e}", status=500)

    return web.Response(status=405, text="Method Not Allowed")

# 主程序
async def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # 注册命令
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("addapi", add_api))
    application.add_handler(CommandHandler("listapi", list_api))
    application.add_handler(CommandHandler("removeapi", remove_api))

    # 设置 Webhook
    await application.bot.delete_webhook()
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook 已设置为：{WEBHOOK_URL}")

    # 初始化和启动应用程序，使其可处理更新
    await application.initialize()
    await application.start()

    # 启动定时任务
    scheduler.add_job(poll_apis, "interval", seconds=10, args=[application])
    scheduler.start()
    logger.info("定时任务调度器已启动")

    # 设置 aiohttp 应用
    app = web.Application()
    app.router.add_post("/webhook", handle_webhook)
    app['application'] = application

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    logger.info(f"服务器已启动，监听端口：{PORT}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("服务器已停止")
