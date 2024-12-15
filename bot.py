import os
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import signal

# 环境变量：从 Render 或本地读取
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8443))

# 存储用户 API 数据
user_data = {}

# ----------------- 命令处理器 -----------------

async def handle_message(update: Update, context):
    """处理用户的普通消息"""
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

    apis = user_data[user.id]['apis']
    reply_text = "你已添加的 API 列表：\n" + "\n".join(
        f"{idx + 1}. {api}" for idx, api in enumerate(apis)
    )
    await update.message.reply_text(reply_text)

async def add_api(update: Update, context):
    """添加用户的 API"""
    user = update.effective_user
    if len(context.args) != 1:
        await update.message.reply_text("请使用正确的格式：/addapi <API链接>")
        return

    api_link = context.args[0]
    user_data.setdefault(user.id, {'apis': []})['apis'].append(api_link)
    await update.message.reply_text(f"成功添加 API：{api_link}")

async def remove_api(update: Update, context):
    """删除用户的 API"""
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
    """列出用户的所有 API"""
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
    """显示帮助信息"""
    await update.message.reply_text(
        "以下是可用命令：\n"
        "/addapi <API链接> - 添加一个 API\n"
        "/removeapi <编号> - 删除指定 API\n"
        "/listapi - 查看所有已添加的 API\n"
        "/help - 查看帮助信息"
    )

# ----------------- 健康检查 -----------------

async def health_check(request):
    """Render 健康检查接口"""
    return web.Response(text="OK")

# ----------------- 主程序 -----------------

def shutdown():
    loop = asyncio.get_event_loop()
    loop.stop()
    print("事件循环已强制关闭！")

async def main():
    """主程序入口"""
    # 检查环境变量
    if not TELEGRAM_TOKEN:
        print("错误：TELEGRAM_TOKEN 未设置！请检查环境变量。")
        return
    if not WEBHOOK_URL:
        print("错误：WEBHOOK_URL 未设置！请检查环境变量。")
        return

    print(f"启动 Webhook，URL: {WEBHOOK_URL}")

    # 初始化 Telegram 应用
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # 删除现有 Webhook 配置
    await application.bot.delete_webhook(drop_pending_updates=True)
    print("已清除旧的 Webhook 配置。")

    # 注册处理器
    application.add_handler(CommandHandler("addapi", add_api))
    application.add_handler(CommandHandler("removeapi", remove_api))
    application.add_handler(CommandHandler("listapi", list_api))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # 健康检查服务
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    # 启动 Webhook
    async with application:
        await application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=WEBHOOK_URL,
        )

    # 停止健康检查服务
    await runner.cleanup()

if __name__ == "__main__":
    # 注册信号处理器，确保事件循环正确关闭
    signal.signal(signal.SIGINT, lambda s, f: shutdown())
    signal.signal(signal.SIGTERM, lambda s, f: shutdown())

    # 检查事件循环状态并运行主程序
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            print("事件循环已在运行，直接使用当前循环...")
            loop.create_task(main())
        else:
            asyncio.run(main())
    except Exception as e:
        print(f"程序启动失败: {e}")
