import os
import asyncio
import html
import logging
import aiohttp
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8443))

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN 未设置")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL 未设置")

# 用户数据存储：
# user_data = {
#   chat_id: {
#       "apis": [
#           {
#               "url": "http://example.com/api",
#               "last_id": None
#               # 根据需求可存更多字段
#           },
#       ]
#   },
#   ...
# }
user_data = {}
user_data_lock = asyncio.Lock()

scheduler = AsyncIOScheduler()

# ============ 命令处理器 ============

async def start_command(update: Update, context):
    await update.message.reply_text("机器人已启动！使用 /help 查看帮助。")

async def help_command(update: Update, context):
    await update.message.reply_text(
        "/start - 启动\n"
        "/help - 帮助信息\n"
        "/addapi <API链接> - 添加 API\n"
        "/listapi - 列出已添加的 API\n"
        "/removeapi <编号> - 删除指定 API\n\n"
        "机器人会：\n"
        "1. 定期轮询你的 API（可设为1小时）以检测更新\n"
        "2. 可通过 /api_update 路由接收API主动推送更新（需API支持）\n"
        "一旦检测到新内容（ID或其他字段变化）就会通知你。\n"
        "支持HTML、Markdown富文本格式、发送图片、按钮等高级功能。"
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
        await update.message.reply_text("你还没有添加任何API。")
    else:
        lines = [f"{i+1}. {api['url']}" for i, api in enumerate(apis)]
        await update.message.reply_text("已添加的API列表：\n" + "\n".join(lines))

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

# ============ 定时轮询逻辑（备用方案） ============
# 每隔一段时间检查 API 是否有更新（如 1 小时）
# 将 seconds=10 改为 seconds=3600 即 1 小时
async def poll_apis(application):
    logger.info("开始轮询 API")
    async with aiohttp.ClientSession() as session:
        async with user_data_lock:
            for chat_id, data in user_data.items():
                for api in data.get("apis", []):
                    await check_and_notify(application, chat_id, api, session)

async def check_and_notify(application, chat_id, api, session):
    try:
        async with session.get(api["url"]) as resp:
            if resp.status == 200:
                data = await resp.json()

                # 假设 API 返回的JSON如下：
                # {
                #   "id": "唯一标识新内容的字段",
                #   "title": "可选标题",
                #   "content": "可选内容",
                #   "image_url": "如有图片则提供链接"
                # }
                
                new_id = data.get("id")
                old_id = api.get("last_id")

                if new_id is not None and new_id != old_id:
                    # 更新记录
                    api["last_id"] = new_id
                    # 根据数据决定发送什么内容
                    await send_update_to_user(application, chat_id, data)
            else:
                logger.error(f"请求失败：{api['url']} 状态码：{resp.status}")
    except Exception as e:
        logger.error(f"轮询出错：{api['url']} 错误：{e}")

# ============ 发送消息的函数 ============
async def send_update_to_user(application, chat_id, data):
    # 自定义消息格式与逻辑
    title = data.get("title", "无标题")
    content = data.get("content", "无内容")
    image_url = data.get("image_url")  # 如果有图片字段
    
    # 使用HTML格式发送文本
    message_text = f"<b>{html.escape(title)}</b>\n{html.escape(content)}"

    # 可选：添加 InlineKeyboard 按钮
    # keyboard = [
    #     [InlineKeyboardButton("查看详情", url="https://example.com")],
    #     [InlineKeyboardButton("下一条", callback_data='next')]
    # ]
    # reply_markup = InlineKeyboardMarkup(keyboard)

    # 如果有图片，就先发送图片，再发送文字说明
    if image_url:
        await application.bot.send_photo(
            chat_id=chat_id,
            photo=image_url,
            caption=message_text,
            parse_mode=ParseMode.HTML
            # reply_markup=reply_markup  # 如果需要按钮
        )
    else:
        # 没有图片则直接发送文本消息
        await application.bot.send_message(
            chat_id=chat_id,
            text=message_text,
            parse_mode=ParseMode.HTML
            # reply_markup=reply_markup  # 如果需要按钮
        )

# ============ API 主动推送更新（可选） ============
# 当API支持更新时主动POST数据到 /api_update
# 你可在这里根据接收到的数据立刻通知用户，无需等待轮询
async def handle_api_update(request):
    if request.method == 'POST':
        try:
            data = await request.json()
            # 此处根据 data 中信息决定要通知哪些用户
            # 假设所有用户都订阅这个更新，或根据 data 决定特定用户列表
            # 这里简单示例通知所有用户（实际请根据需要筛选）
            async with user_data_lock:
                for chat_id, info in user_data.items():
                    for api in info.get("apis", []):
                        # 如有字段data['id']匹配api状态，才发送给该用户
                        # 简单示例直接发给所有用户
                        await send_update_to_user(request.app['application'], chat_id, data)
            return web.Response(text="OK")
        except Exception as e:
            logger.error(f"handle_api_update错误：{e}")
            return web.Response(text=str(e), status=500)
    else:
        return web.Response(status=405, text="Method Not Allowed")

# ============ Telegram Webhook 路由 ============
async def handle_webhook(request):
    if request.method == 'GET':
        return web.Response(text="Webhook is active!")
    elif request.method == 'POST':
        try:
            data = await request.json()
            logger.info(f"Webhook数据：{data}")
            update = Update.de_json(data, request.app['application'].bot)
            await request.app['application'].process_update(update)
            return web.Response(text="OK")
        except Exception as e:
            logger.error(f"Webhook处理失败：{e}")
            return web.Response(text=str(e), status=500)
    else:
        return web.Response(status=405, text="Method Not Allowed")

# ============ 主程序入口 ============
async def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # 注册命令
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("addapi", add_api))
    application.add_handler(CommandHandler("listapi", list_api))
    application.add_handler(CommandHandler("removeapi", remove_api))

    # 设置Telegram Webhook
    await application.bot.delete_webhook()
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook已设置：{WEBHOOK_URL}")

    await application.initialize()
    await application.start()

    # 启动定时器（间隔可设长，如1小时）
    scheduler.add_job(poll_apis, "interval", seconds=3600, args=[application])
    scheduler.start()
    logger.info("定时任务调度器已启动")

    app = web.Application()
    app.router.add_get("/webhook", handle_webhook)
    app.router.add_post("/webhook", handle_webhook)

    # 可选：API主动更新接口
    app.router.add_post("/api_update", handle_api_update)

    app['application'] = application

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    logger.info(f"服务器已启动，监听端口：{PORT}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
