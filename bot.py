import os
import asyncio
from aiohttp import web
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

# 从环境变量中读取 Telegram Token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# 存储用户的 API 和信息映射
user_data = {}

# ----------------- 处理消息的函数 -----------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    full_name = f"{user.first_name} {user.last_name}".strip()

    if user.id not in user_data or not user_data[user.id]['apis']:
        await update.message.reply_text(
            "你好！欢迎使用本机器人！\n\n"
            "你还没有设置任何 API。请使用以下命令：\n"
            "/addapi <API链接> - 添加一个 API\n"
            "/removeapi <编号> - 删除指定 API\n"
            "/listapi - 查看所有已添加的 API\n"
            "/help - 查看帮助信息"
        )
        return

    content = "以下是你已添加的 API 列表：\n"
    for idx, api in enumerate(user_data[user.id]['apis'], start=1):
        content += f"{idx}. {api}\n"

    formatted_content = (
        f"<b>你好，{full_name}！</b>\n\n"
        f"<i>你的 API 列表：</i>\n"
        f"{content}\n"
        "你可以使用以下命令：\n"
        "/addapi <API链接> - 添加一个 API\n"
        "/removeapi <编号> - 删除指定 API\n"
        "/listapi - 查看所有已添加的 API\n"
        "/help - 查看帮助信息"
    )
    await update.message.reply_text(formatted_content, parse_mode=ParseMode.HTML)

async def add_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if len(context.args) != 1:
        await update.message.reply_text("请使用正确的格式：/addapi <你的API链接>")
        return

    api_link = context.args[0]
    if user.id not in user_data:
        user_data[user.id] = {'apis': [], 'username': user.username, 'full_name': f"{user.first_name} {user.last_name}".strip()}

    user_data[user.id]['apis'].append(api_link)
    await update.message.reply_text(f"成功添加 API：{api_link}")

async def remove_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id not in user_data or not user_data[user.id]['apis']:
        await update.message.reply_text("你还没有添加任何 API，无法删除。")
        return

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("请使用正确的格式：/removeapi <API编号>")
        return

    api_index = int(context.args[0]) - 1
    if api_index < 0 or api_index >= len(user_data[user.id]['apis']):
        await update.message.reply_text("无效的 API 编号。")
        return

    removed_api = user_data[user.id]['apis'].pop(api_index)
    await update.message.reply_text(f"成功删除 API：{removed_api}")

async def list_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id not in user_data or not user_data[user.id]['apis']:
        await update.message.reply_text("你还没有添加任何 API。")
        return

    content = "以下是你已添加的 API 列表：\n"
    for idx, api in enumerate(user_data[user.id]['apis'], start=1):
        content += f"{idx}. {api}\n"

    await update.message.reply_text(content)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "欢迎使用本机器人！以下是可用命令：\n"
        "/addapi <API链接> - 添加一个 API\n"
        "/removeapi <编号> - 删除指定 API\n"
        "/listapi - 查看所有已添加的 API\n"
        "/help - 查看帮助信息"
    )

# ----------------- 创建 Web 服务器以监听端口 -----------------

async def health_check(request):
    return web.Response(text="OK")

async def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("addapi", add_api))
    application.add_handler(CommandHandler("removeapi", remove_api))
    application.add_handler(CommandHandler("listapi", list_api))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    webhook_url = os.getenv("WEBHOOK_URL")

    try:
        await application.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT", 8443)),
            url_path="",
            webhook_url=webhook_url
        )
    except RuntimeError as e:
        if "already running" in str(e):
            print("事件循环已在运行，跳过重复启动。")
        else:
            raise

if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    except RuntimeError as e:
        if "already running" in str(e):
            print("检测到事件循环冲突，服务可能已启动。")
        else:
            raise
    except Exception as e:
        print(f"程序启动失败: {e}")