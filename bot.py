from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# 从环境变量中读取 Telegram Token
import os
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# 处理消息的函数
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

# 主函数
def main():
    # 初始化 Application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # 注册消息处理器
    message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    application.add_handler(message_handler)

    # 启动机器人
    application.run_polling()

if __name__ == "__main__":
    main()
