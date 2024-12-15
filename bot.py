import os
import logging
import requests
import json
from io import BytesIO
from telegram import Update, Chat
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext
from fastapi import FastAPI, Request
import uvicorn

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 从环境变量读取 Bot Token 和 Webhook URL
token = os.getenv("YOUR_BOT_TOKEN")
webhook_url = os.getenv("WEBHOOK_URL")
if not token:
    raise ValueError("Bot token is not set in environment variables")
if not webhook_url:
    raise ValueError("Webhook URL is not set in environment variables")

# 数据存储结构
api_store = {
    "users": {},  # 每个用户的数据，键是 user_id
    "groups": {},  # 每个群组的数据，键是 group_id
    "channels": {}  # 每个频道的数据，键是 channel_id
}

# 初始化 Bot 实例
application = ApplicationBuilder().token(token).build()

# Telegram Bot 命令逻辑
async def start(update: Update, context: CallbackContext) -> None:
    chat_type = update.effective_chat.type
    if chat_type == Chat.PRIVATE:
        await update.message.reply_text(
            "欢迎使用 Telegram 机器人！支持绑定 API 并调用。\n"
            "发送 /help 查看详细命令列表。"
        )
    elif chat_type in [Chat.GROUP, Chat.SUPERGROUP]:
        await update.message.reply_text(
            "我是群组助手，可以帮助您绑定和调用 API。\n"
            "管理员可使用 /help 查看命令。"
        )
    elif chat_type == Chat.CHANNEL:
        await update.message.reply_text("我是频道助手，请将我设置为管理员以启用功能。")

async def help(update: Update, context: CallbackContext) -> None:
    help_text = (
        "命令列表：\n\n"
        "/start - 启动机器人\n"
        "/help - 查看帮助信息\n"
        "/add_api <名称> <API_URL> - 绑定一个 API\n"
        "/remove_api <名称> - 删除已绑定的 API\n"
        "/call_api <名称> - 调用已绑定的 API\n"
        "/list_apis - 查看已绑定的 API 列表\n"
    )
    await update.message.reply_text(help_text)

async def add_api(update: Update, context: CallbackContext) -> None:
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("用法: /add_api <名称> <API_URL>")
        return
    name, api_url = args[0], args[1]
    chat_type = update.effective_chat.type
    chat_id = str(update.effective_chat.id)

    if chat_type == Chat.PRIVATE:
        if chat_id not in api_store["users"]:
            api_store["users"][chat_id] = {}
        api_store["users"][chat_id][name] = api_url
        await update.message.reply_text(f"已为您绑定 API：{name}")
    elif chat_type in [Chat.GROUP, Chat.SUPERGROUP]:
        if not await check_admin(update, context):
            await update.message.reply_text("只有管理员可以管理群组 API。")
            return
        if chat_id not in api_store["groups"]:
            api_store["groups"][chat_id] = {}
        api_store["groups"][chat_id][name] = api_url
        await update.message.reply_text(f"已为本群组绑定 API：{name}")
    elif chat_type == Chat.CHANNEL:
        if not await check_admin(update, context):
            await update.message.reply_text("只有频道管理员可以管理 API。")
            return
        if chat_id not in api_store["channels"]:
            api_store["channels"][chat_id] = {}
        api_store["channels"][chat_id][name] = api_url
        await update.message.reply_text(f"已为本频道绑定 API：{name}")

async def remove_api(update: Update, context: CallbackContext) -> None:
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("用法: /remove_api <名称>")
        return
    name = args[0]
    chat_type = update.effective_chat.type
    chat_id = str(update.effective_chat.id)

    if chat_type == Chat.PRIVATE:
        if chat_id in api_store["users"] and name in api_store["users"][chat_id]:
            del api_store["users"][chat_id][name]
            await update.message.reply_text(f"已删除 API：{name}")
        else:
            await update.message.reply_text(f"未找到名为 {name} 的 API。")
    elif chat_type in [Chat.GROUP, Chat.SUPERGROUP]:
        if not await check_admin(update, context):
            await update.message.reply_text("只有管理员可以管理群组 API。")
            return
        if chat_id in api_store["groups"] and name in api_store["groups"][chat_id]:
            del api_store["groups"][chat_id][name]
            await update.message.reply_text(f"已删除 API：{name}")
        else:
            await update.message.reply_text(f"未找到名为 {name} 的 API。")
    elif chat_type == Chat.CHANNEL:
        if not await check_admin(update, context):
            await update.message.reply_text("只有频道管理员可以管理 API。")
            return
        if chat_id in api_store["channels"] and name in api_store["channels"][chat_id]:
            del api_store["channels"][chat_id][name]
            await update.message.reply_text(f"已删除 API：{name}")
        else:
            await update.message.reply_text(f"未找到名为 {name} 的 API。")

async def call_api(update: Update, context: CallbackContext) -> None:
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("用法: /call_api <名称>")
        return
    name = args[0]
    chat_type = update.effective_chat.type
    chat_id = str(update.effective_chat.id)

    if chat_type == Chat.PRIVATE:
        api_data = api_store["users"].get(chat_id, {})
    elif chat_type in [Chat.GROUP, Chat.SUPERGROUP]:
        api_data = api_store["groups"].get(chat_id, {})
    elif chat_type == Chat.CHANNEL:
        api_data = api_store["channels"].get(chat_id, {})
    else:
        api_data = {}

    if name not in api_data:
        await update.message.reply_text(f"未找到名为 {name} 的 API。")
        return

    api_url = api_data[name]
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        await update.message.reply_text(f"API {name} 返回：\n{response.text}")
    except Exception as e:
        await update.message.reply_text(f"API 调用失败：{str(e)}")

async def list_apis(update: Update, context: CallbackContext) -> None:
    chat_type = update.effective_chat.type
    chat_id = str(update.effective_chat.id)

    if chat_type == Chat.PRIVATE:
        apis = api_store["users"].get(chat_id, {})
    elif chat_type in [Chat.GROUP, Chat.SUPERGROUP]:
        apis = api_store["groups"].get(chat_id, {})
    elif chat_type == Chat.CHANNEL:
        apis = api_store["channels"].get(chat_id, {})
    else:
        apis = {}

    if not apis:
        await update.message.reply_text("当前没有绑定的 API。")
    else:
        api_list = "\n".join([f"- {name}: {url}" for name, url in apis.items()])
        await update.message.reply_text(f"已绑定的 API：\n{api_list}")

async def check_admin(update: Update, context: CallbackContext) -> bool:
    """检查是否为管理员"""
    user = update.effective_user
    chat = update.effective_chat
    member = await context.bot.get_chat_member(chat.id, user.id)
    return member.status in ["administrator", "creator"]

# FastAPI 设置
app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    try:
        payload = await request.json()
        update = Update.de_json(payload, application.bot)
        await application.process_update(update)
    except Exception as e:
        logger.error(f"Webhook 错误: {str(e)}")
    return {"status": "ok"}

# 注册命令处理器
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help))
application.add_handler(CommandHandler("add_api", add_api))
application.add_handler(CommandHandler("remove_api", remove_api))
application.add_handler(CommandHandler("call_api", call_api))
application.add_handler(CommandHandler("list_apis", list_apis))

if __name__ == "__main__":
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        webhook_url=webhook_url
    )
