import os
import logging
import requests
import json
from io import BytesIO
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext
from PIL import Image
from fastapi import FastAPI, Request
from threading import Thread
import uvicorn

# 配置日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 从环境变量读取 Bot Token 和 Webhook URL
token = os.getenv("YOUR_BOT_TOKEN")
webhook_url = os.getenv("WEBHOOK_URL")
if not token:
    raise ValueError("Bot token is not set in environment variables")
if not webhook_url:
    raise ValueError("Webhook URL is not set in environment variables")

# 存储 API 绑定的字典（内存替代数据库）
user_apis = {}
group_settings = {}

# Telegram Bot 逻辑
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("欢迎使用电报机器人！输入 /add_api 绑定 API，/remove_api 删除 API，/call_api 调用 API，/block_api 和 /unblock_api 管理群组屏蔾。")

async def help(update: Update, context: CallbackContext) -> None:
    help_text = (
        "欢迎使用本 Bot！以下是您可以使用的命令：\n\n"
        "/start - 启动 Bot\n"
        "/help - 查看帮助信息\n"
        "/add_api <名称> <API_URL> - 绑定一个 API\n"
        "/remove_api <名称> - 删除已绑定的 API\n"
        "/call_api <名称> - 调用已绑定的 API\n"
        "/block_api <API名称> - 屏蔾某个 API（仅群组有效）\n"
        "/unblock_api <API名称> - 解除对某个 API 的屏蔾（仅群组有效）\n"
    )
    await update.message.reply_text(help_text)

async def add_api(update: Update, context: CallbackContext) -> None:
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("用法: /add_api <名称> <API_URL>")
        return
    name, api_url = args[0], args[1]
    user_id = str(update.effective_user.id)
    
    # 保存 API 绑定（在内存中）
    if user_id not in user_apis:
        user_apis[user_id] = {}
    
    user_apis[user_id][name] = api_url
    await update.message.reply_text(f"API {name} 已绑定！")

async def remove_api(update: Update, context: CallbackContext) -> None:
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("用法: /remove_api <名称>")
        return
    name = args[0]
    user_id = str(update.effective_user.id)

    # 移除 API 绑定（在内存中）
    if user_id in user_apis and name in user_apis[user_id]:
        del user_apis[user_id][name]
        await update.message.reply_text(f"API {name} 已移除！")
    else:
        await update.message.reply_text(f"未找到名为 {name} 的 API！")

async def call_api(update: Update, context: CallbackContext) -> None:
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("用法: /call_api <名称>")
        return
    name = args[0]
    user_id = str(update.effective_user.id)

    # 获取 API URL（从内存中）
    if user_id not in user_apis or name not in user_apis[user_id]:
        await update.message.reply_text(f"未找到名为 {name} 的 API！")
        return
    
    api_url = user_apis[user_id][name]
    response = requests.get(api_url)
    
    if response.status_code == 200:
        try:
            content_type = response.headers.get('Content-Type', '').lower()
            if 'image' in content_type:
                # 推送图片
                image = Image.open(BytesIO(response.content))
                bio = BytesIO()
                bio.name = f"{name}.png"
                image.save(bio, 'PNG')
                bio.seek(0)
                await context.bot.send_photo(chat_id=update.effective_user.id, photo=bio, caption=f"API {name} 返回的图片")
            elif 'video' in content_type:
                # 推送视频
                bio = BytesIO(response.content)
                bio.name = f"{name}.mp4"
                await context.bot.send_video(chat_id=update.effective_user.id, video=bio, caption=f"API {name} 返回的视频")
            elif 'audio' in content_type:
                # 推送音频
                bio = BytesIO(response.content)
                bio.name = f"{name}.mp3"
                await context.bot.send_audio(chat_id=update.effective_user.id, audio=bio, caption=f"API {name} 返回的音频")
            elif 'application' in content_type or 'octet-stream' in content_type:
                # 推送文件
                bio = BytesIO(response.content)
                bio.name = f"{name}_file"
                await context.bot.send_document(chat_id=update.effective_user.id, document=bio, caption=f"API {name} 返回的文件")
            elif 'text' in content_type or 'json' in content_type:
                # 处理文本或 JSON
                data = response.json() if 'json' in content_type else response.text
                await update.message.reply_text(f"API 返回:\n{json.dumps(data, indent=2) if isinstance(data, dict) else data}")
            else:
                await update.message.reply_text(f"未知内容类型: {content_type}")
        except Exception as e:
            await update.message.reply_text(f"API 数据处理失败: {str(e)}")
    else:
        await update.message.reply_text(f"API 调用失败，状态码: {response.status_code}")

# 管理群组屏蔾
async def block_api(update: Update, context: CallbackContext) -> None:
    if update.effective_chat.type != "group":
        await update.message.reply_text("此命令只能在群组中使用。")
        return
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("用法: /block_api <API名称>")
        return
    group_id = str(update.effective_chat.id)
    api_name = args[0]

    if group_id not in group_settings:
        group_settings[group_id] = {}

    # 将 API 名称加入到屏蔾列表
    if api_name not in group_settings[group_id]:
        group_settings[group_id][api_name] = "blocked"
        await update.message.reply_text(f"API {api_name} 已被屏蔾！")
    else:
        await update.message.reply_text(f"API {api_name} 已经在屏蔾列表中！")

async def unblock_api(update: Update, context: CallbackContext) -> None:
    if update.effective_chat.type != "group":
        await update.message.reply_text("此命令只能在群组中使用。")
        return
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("用法: /unblock_api <API名称>")
        return
    group_id = str(update.effective_chat.id)
    api_name = args[0]

    if group_id in group_settings and api_name in group_settings[group_id]:
        del group_settings[group_id][api_name]
        await update.message.reply_text(f"API {api_name} 已解除屏蔾！")
    else:
        await update.message.reply_text(f"API {api_name} 不在屏蔾列表中！")

# FastAPI 设置 webhook
app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()
    update = Update.de_json(payload, bot)
    await app.bot.process_update(update)
    return {"status": "ok"}

# 启动应用
def run():
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    # 启动 FastAPI 线程
    thread = Thread(target=run)
    thread.start()

    # 设置 Webhook URL
    bot = Bot(token=token)
    bot.set_webhook(url=webhook_url)  # 设置 Webhook URL（此处只调用一次）

    # 不使用轮询，只使用 Webhook
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help))  # 添加 help 命令
    app.add_handler(CommandHandler("add_api", add_api))
    app.add_handler(CommandHandler("remove_api", remove_api))
    app.add_handler(CommandHandler("call_api", call_api))
    app.add_handler(CommandHandler("block_api", block_api))
    app.add_handler(CommandHandler("unblock_api", unblock_api))

    # 只使用 Webhook，不再调用 app.run_polling()
