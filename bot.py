import os
import asyncio
from aiohttp import web
from telegram import Update, Chat
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# 从环境变量中获取 Telegram Token 和 Webhook URL
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8443))  # Render 动态分配端口

# 数据存储，支持多用户和多群组
group_data = {}  # 群组数据：{group_id: {"users": {user_id: {"apis": []}}}}
user_data = {}   # 私聊用户数据：{user_id: {"apis": []}}

# ----------------- 命令处理器 -----------------

async def add_api(update: Update, context):
    """添加用户的 API"""
    chat = update.effective_chat
    user = update.effective_user
    if len(context.args) != 1:
        await update.message.reply_text("请使用正确的格式：/addapi <API链接>")
        return

    api_link = context.args[0]

    if chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        # 群组中的操作
        group_data.setdefault(chat.id, {"users": {}})
        group_data[chat.id]["users"].setdefault(user.id, {"apis": []})["apis"].append(api_link)
        await update.message.reply_text(f"成功在群组中添加 API：{api_link}")
    elif chat.type == Chat.PRIVATE:
        # 私聊中的操作
        user_data.setdefault(user.id, {"apis": []})["apis"].append(api_link)
        await update.message.reply_text(f"成功添加 API：{api_link}")

async def remove_api(update: Update, context):
    """删除用户的 API"""
    chat = update.effective_chat
    user = update.effective_user
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("请使用正确的格式：/removeapi <编号>")
        return

    api_index = int(context.args[0]) - 1

    if chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        # 群组中的操作
        apis = group_data.get(chat.id, {}).get("users", {}).get(user.id, {}).get("apis", [])
    elif chat.type == Chat.PRIVATE:
        # 私聊中的操作
        apis = user_data.get(user.id, {}).get("apis", [])
    else:
        apis = []

    if 0 <= api_index < len(apis):
        removed = apis.pop(api_index)
        await update.message.reply_text(f"成功删除 API：{removed}")
    else:
        await update.message.reply_text("无效的编号。")

async def list_api(update: Update, context):
    """列出用户的所有 API"""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        # 群组中的操作
        apis = group_data.get(chat.id, {}).get("users", {}).get(user.id, {}).get("apis", [])
    elif chat.type == Chat.PRIVATE:
        # 私聊中的操作
        apis = user_data.get(user.id, {}).get("apis", [])
    else:
        apis = []

    if not apis:
        await update.message.reply_text("你还没有添加任何 API。")
    else:
        reply_text = "你已添加的 API 列表：\n" + "\n".join(
            f"{idx + 1}. {api}" for idx, api in enumerate(apis)
        )
        await update.message.reply_text(reply_text)

async def handle_message(update: Update, context):
    """处理普通消息"""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        apis = group_data.get(chat.id, {}).get("users", {}).get(user.id, {}).get("apis", [])
    elif chat.type == Chat.PRIVATE:
        apis = user_data.get(user.id, {}).get("apis", [])
    else:
        apis = []

    if not apis:
        await update.message.reply_text(
            "你还没有设置任何 API。\n"
            "请使用以下命令：\n"
            "/addapi <API链接> - 添加一个 API\n"
            "/removeapi <编号> - 删除指定 API\n"
            "/listapi - 查看所有已添加的 API"
        )
    else:
        await update.message.reply_text(
            f"你当前的 API 列表：\n" + "\n".join(f"{idx + 1}. {api}" for idx, api in enumerate(apis))
        )

# ----------------- Webhook 路由 -----------------

async def handle_webhook(request):
    """处理 Telegram Webhook 请求"""
    try:
        data = await request.json()  # 获取 Telegram POST 请求的数据
        update = Update.de_json(data, bot_context.bot)
        await bot_context.process_update(update)  # 处理更新
        return web.Response(text="OK")
    except Exception as e:
        print(f"处理 Webhook 请求时出错: {e}")
        return web.Response(text="Error", status=500)

# ----------------- 主程序 -----------------

async def main():
    """启动 Telegram 应用和 Aiohttp 服务器"""
    if not TELEGRAM_TOKEN:
        print("错误：TELEGRAM_TOKEN 未设置！")
        return

    global bot_context
    bot_context = Application.builder().token(TELEGRAM_TOKEN).build()

    # 注册命令和消息处理器
    bot_context.add_handler(CommandHandler("addapi", add_api))
    bot_context.add_handler(CommandHandler("removeapi", remove_api))
    bot_context.add_handler(CommandHandler("listapi", list_api))
    bot_context.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await bot_context.bot.delete_webhook()

    if not WEBHOOK_URL:
        print("错误：WEBHOOK_URL 未设置！")
        return
    await bot_context.bot.set_webhook(WEBHOOK_URL)

    app = web.Application()
    app.router.add_post("/", handle_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    print(f"服务器正在运行，监听端口：{PORT}")
    await site.start()

    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"程序运行失败：{e}")
