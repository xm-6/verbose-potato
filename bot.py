import os
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# 从环境变量中读取配置
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8443))

# 存储用户 API 数据
user_data = {}

# ----------------- 命令处理器 -----------------

async def handle_message(update: Update, context):
    user = update.effective_user
    if user.id not in user_data or not user_data[user.id].get('apis'):
        await update.message.reply_text(
            "欢迎使用本机器人！\n\n"
            "你还没有设置任何 API。请使用以下命令：\n"
            "/addapi <API链接> - 添加一个 API\n"
            "/removeapi <编号> - 删除指定 API\n"
            "/listapi - 查看所有已添加的 API\n"
            "/help - 查看帮助信息"
        )
        return

    # 显示用户的 API 列表
    apis = user_data[user.id]['apis']
    reply_text = "你已添加的 API 列表：\n" + "\n".join(
        f"{idx + 1}. {api}" for idx, api in enumerate(apis)
    )
    await update.message.reply_text(reply_text)

async def add_api(update: Update, context):
    user = update.effective_user
    if len(context.args) != 1:
        await update.message.reply_text("请使用正确的格式：/addapi <API链接>")
        return

    api_link = context.args[0]
    user_data.setdefault(user.id, {'apis': []})['apis'].append(api_link)
    await update.message.reply_text(f"成功添加 API：{api_link}")

async def remove_api(update: Update, context):
    user = update.effective_user
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("请使用正确的格式：/removeapi <编号>")
        return

    api_index = int(context.args[0]) - 1
    apis = user_data.get(user.id, {}).get('apis', [])
    if 0 <= api_index < len(apis):
        removed = apis.pop(api_index)
        await update.message.reply_text(f"成功删除 API：{removed}")
    else:
        await update.message.reply_text("无效的编号。")

async def list_api(update: Update, context):
    user = update.effective_user
    apis = user_data.get(user.id, {}).get('apis', [])
    if not apis:
        await update.message.reply_text("你还没有添加任何 API。")
    else:
        reply_text = "你已添加的 API 列表：\n" + "\n".join(
            f"{idx + 1}. {api}" for idx, api in enumerate(apis)
        )
        await update.message.reply_text(reply_text)

async def help_command(update: Update, context):
    await update.message.reply_text(
        "以下是可用命令：\n"
        "/addapi <API链接> - 添加一个 API\n"
        "/removeapi <编号> - 删除指定 API\n"
        "/listapi - 查看所有已添加的 API\n"
        "/help - 查看帮助信息"
    )

# ----------------- 健康检查 -----------------

async def health_check(request):
    return web.Response(text="OK")

# ----------------- 主程序 -----------------

async def main():
    """主程序入口"""
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # 添加命令处理器
    application.add_handler(CommandHandler("addapi", add_api))
    application.add_handler(CommandHandler("removeapi", remove_api))
    application.add_handler(CommandHandler("listapi", list_api))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # 启动 Webhook
    webhook_url = os.getenv("WEBHOOK_URL")
    print(f"启动 Webhook，URL: {webhook_url}")

    try:
        await application.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT", 8443)),
            url_path="",
            webhook_url=webhook_url,
        )
    except RuntimeError as e:
        if "already running" in str(e):
            print("事件循环已在运行，跳过重复启动。")
        else:
            raise

if __name__ == "__main__":
    try:
        # 检查是否有事件循环在运行
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                print("事件循环已在运行，直接使用当前循环。")
                loop.run_until_complete(main())
            else:
                print("创建新事件循环...")
                loop.run_until_complete(main())
        except RuntimeError:
            print("没有事件循环，创建新的事件循环...")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(main())
    except Exception as e:
        print(f"程序启动失败: {e}")
