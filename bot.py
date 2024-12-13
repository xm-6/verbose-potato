from telegram.ext import Updater, MessageHandler, Filters

# 从环境变量中读取 Telegram Token
import os
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# 初始化机器人
updater = Updater(TELEGRAM_TOKEN, use_context=True)

# 处理消息
def handle_message(update, context):
    chat = update.message.chat
    chat_type = chat.type  # 消息来源类型
    chat_id = chat.id

    if chat_type == "private":
        update.message.reply_text(f"你好，{chat.username or '用户'}！")
    elif chat_type in ["group", "supergroup"]:
        context.bot.send_message(chat_id=chat_id, text=f"大家好，这里是群组 {chat.title}！")
    elif chat_type == "channel":
        context.bot.send_message(chat_id=chat_id, text=f"欢迎关注频道 {chat.title}！")

# 注册消息处理器
dispatcher = updater.dispatcher
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

# 启动机器人
updater.start_polling()
updater.idle()
