import os
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# 从环境变量中读取 Telegram Token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# ----------------- 处理消息的函数 -----------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    chat_type = chat.type  # 消息来源类型
    chat_id = chat.id

    if chat_type == "private":
        await update.message.reply_text(f"你好，{chat.username or '用户'}！")
    elif chat_type in ["group", "supergroup"]:
        await context.bot.send_message(chat_id=chat_id, text=f"大家好，这里是群组 {chat.title}！")
    elif chat_type == "channel":
        await context.bot.send_message(chat_id=chat_id, text=f"欢迎关注频道 {chat.title}！")

# ----------------- 创建 Web 服务器以监听端口 -----------------

async def health_check(request):
    """健康检查端点，Render 平台会期望监听一个端口"""
    return web.Response(text="OK")

async def start_web_server():
    """启动 Web 服务器以满足 Render 平台对端口监听的要求"""
    port = int(os.getenv("PORT", 8080))  # Render 会通过 PORT 环境变量分配端口
    app = web.Application()
    app.router.add_get("/", health_check)  # 健康检查接口
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# ----------------- 主函数 -----------------

async def main():
    # 初始化 Telegram Application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # 注册消息处理器
    message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    application.add_handler(message_handler)

    # 启动 Web 服务和 Telegram Bot
    await asyncio.gather(
        start_web_server(),  # 启动 Web 服务监听端口
        application.initialize()  # 初始化 Telegram Application
    )

    # 独立启动 run_polling（非阻塞）
    await application.start()
    await application.updater.start_polling()

    # 等待终止信号
    try:
        await asyncio.Future()  # 保持程序运行
    finally:
        await application.updater.stop()
        await application.stop()

# ----------------- 显式管理事件循环 -----------------

if __name__ == "__main__":
    try:
        # 设置事件循环，兼容 Render 环境
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    except RuntimeError as e:
        if "already running" in str(e):
            print("事件循环已在运行，跳过重复启动。")
        else:
            raise
    except Exception as e:
        print(f"程序启动失败: {e}")
