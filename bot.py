import os
import asyncio
import requests
from aiohttp import web
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# 从环境变量中获取配置
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8443))  # Render 动态分配端口

# 用户数据存储
user_data = {}  # {user_id: {"apis": [{"url": "API链接", "last_seen": "上次获取的最新数据ID/时间"}]}}

# 定时任务调度器
scheduler = AsyncIOScheduler()

# ----------------- 命令处理器 -----------------

async def start_command(update: Update, context):
    """处理 /start 命令"""
    await update.message.reply_text("欢迎使用 Telegram Bot！")

async def add_api(update: Update, context):
    """添加用户的 API"""
    user = update.effective_user
    if len(context.args) != 1:
        await update.message.reply_text("请使用正确的格式：/addapi <API链接>")
        return

    api_link = context.args[0]
    user_data.setdefault(user.id, {"apis": []})["apis"].append({"url": api_link, "last_seen": None})
    await update.message.reply_text(f"成功添加 API：{api_link}")

async def list_api(update: Update, context):
    """列出用户的所有 API"""
    user = update.effective_user
    apis = user_data.get(user.id, {}).get("apis", [])

    if not apis:
        await update.message.reply_text("你还没有添加任何 API。")
    else:
        reply_text = "你已添加的 API 列表：\n" + "\n".join(
            f"{idx + 1}. {api['url']}" for idx, api in enumerate(apis)
        )
        await update.message.reply_text(reply_text)

async def remove_api(update: Update, context):
    """删除用户的 API"""
    user = update.effective_user
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("请使用正确的格式：/removeapi <编号>")
        return

    api_index = int(context.args[0]) - 1
    apis = user_data.get(user.id, {}).get("apis", [])

    if 0 <= api_index < len(apis):
        removed = apis.pop(api_index)
        await update.message.reply_text(f"成功删除 API：{removed['url']}")
    else:
        await update.message.reply_text("无效的编号。")

# ----------------- 定时任务 -----------------

async def poll_apis():
    """轮询用户的 API，并推送新消息"""
    for user_id, data in user_data.items():
        apis = data.get("apis", [])
        for api in apis:
            try:
                response = requests.get(api["url"])
                if response.status_code == 200:
                    new_data = response.json()
                    if "id" in new_data and api["last_seen"] != new_data["id"]:
                        api["last_seen"] = new_data["id"]
                        message = format_message(new_data)
                        await send_message(user_id, message)
                else:
                    print(f"API 请求失败：{api['url']}，状态码：{response.status_code}")
            except Exception as e:
                print(f"轮询 API 出错：{api['url']}，错误：{e}")

def format_message(data):
    """格式化消息，支持富文本"""
    title = data.get("title", "无标题")
    content = data.get("content", "无内容")
    return f"<b>{title}</b>\n{content}"

async def send_message(user_id, message):
    """发送消息给用户"""
    bot = bot_context.bot
    await bot.send_message(chat_id=user_id, text=message, parse_mode=ParseMode.HTML)

# ----------------- Webhook 路由 -----------------

async def handle_webhook(request):
    """处理 Telegram Webhook 请求"""
    try:
        data = await request.json()
        update = Update.de_json(data, bot_context.bot)
        await bot_context.process_update(update)
        return web.Response(text="OK")
    except Exception as e:
        print(f"Webhook 处理失败：{e}")
        return web.Response(text=f"Error: {e}", status=500)

# ----------------- 主程序 -----------------

async def main():
    global bot_context
    bot_context = Application.builder().token(TELEGRAM_TOKEN).build()

    bot_context.add_handler(CommandHandler("start", start_command))
    bot_context.add_handler(CommandHandler("addapi", add_api))
    bot_context.add_handler(CommandHandler("listapi", list_api))
    bot_context.add_handler(CommandHandler("removeapi", remove_api))

    await bot_context.bot.delete_webhook()
    await bot_context.bot.set_webhook(WEBHOOK_URL)

    scheduler.add_job(poll_apis, "interval", seconds=10)
    scheduler.start()

    app = web.Application()
    app.router.add_post("/", handle_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"程序运行失败：{e}")
