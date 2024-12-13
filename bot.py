import os
import asyncio
from aiohttp import web
from telegram import Update, ParseMode
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

# 从环境变量中读取 Telegram Token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# 存储用户的 API 和信息映射
user_data = {}

# ----------------- 处理消息的函数 -----------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # 获取用户昵称或全名
    full_name = f"{user.first_name} {user.last_name}".strip()

    # 检查用户是否注册了 API
    if user.id not in user_data or not user_data[user.id]['apis']:
        await update.message.reply_text("你还没有设置 API，请发送 /addapi <你的API链接> 来添加。")
        return

    # 示例接收内容并以富文本形式展示
    content = "以下是你已添加的 API 列表：\n"
    for idx, api in enumerate(user_data[user.id]['apis'], start=1):
        content += f"{idx}. {api}\n"

    formatted_content = (
        f"<b>你好，{full_name}！</b>\n\n"
        f"<i>你的 API 列表：</i>\n"
        f"{content}"
    )
    await update.message.reply_text(formatted_content, parse_mode=ParseMode.HTML)

# 处理 /addapi 命令
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

# 处理 /removeapi 命令
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

# 群组或频道发送消息的函数
async def send_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    chat_type = chat.type

    if chat_type in ["group", "supergroup", "channel"]:
        await update.message.reply_text(f"你好，这是一个 {chat_type}，标题为：{chat.title}。")

# 用户更新信息的功能
async def update_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id in user_data:
        user_data[user.id]['username'] = user.username
        user_data[user.id]['full_name'] = f"{user.first_name} {user.last_name}".strip()
        await update.message.reply_text("用户信息已更新。")
    else:
        await update.message.reply_text("你还没有设置 API，请发送 /addapi <你的API链接> 来添加。")

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

    # 注册命令处理器和消息处理器
    application.add_handler(CommandHandler("addapi", add_api))
    application.add_handler(CommandHandler("removeapi", remove_api))
    application.add_handler(CommandHandler("updateinfo", update_user_info))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.CHAT, send_to_group))

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
