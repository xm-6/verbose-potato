import os
import asyncio
import logging
import requests
import json
from io import BytesIO
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from PIL import Image

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 数据库模型和配置
Base = declarative_base()

class UserAPI(Base):
    __tablename__ = "user_apis"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False)
    api_name = Column(String, nullable=False)
    api_url = Column(String, nullable=False)

class GroupSettings(Base):
    __tablename__ = "group_settings"
    id = Column(Integer, primary_key=True)
    group_id = Column(String, nullable=False)
    blocked_api = Column(String, nullable=True)

class APIState(Base):
    __tablename__ = "api_states"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False)
    api_name = Column(String, nullable=False)
    last_data = Column(String, nullable=True)

# 从环境变量读取 Bot Token 和数据库连接
token = os.getenv("YOUR_BOT_TOKEN")
if not token:
    raise ValueError("Bot token is not set in environment variables")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot.db")
db_engine = create_engine(DATABASE_URL)
Base.metadata.create_all(db_engine)
Session = sessionmaker(bind=db_engine)

# Telegram Bot 逻辑
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("欢迎使用电报机器人！输入 /add_api 绑定 API，/remove_api 删除 API，/block_api 和 /unblock_api 管理群组屏蔽。")

async def add_api(update: Update, context: CallbackContext) -> None:
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("用法: /add_api <名称> <API_URL>")
        return
    name, api_url = args[0], args[1]
    with Session() as session:
        new_api = UserAPI(user_id=str(update.effective_user.id), api_name=name, api_url=api_url)
        session.add(new_api)
        session.commit()
    await update.message.reply_text(f"API {name} 已绑定！")

async def remove_api(update: Update, context: CallbackContext) -> None:
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("用法: /remove_api <名称>")
        return
    name = args[0]
    user_id = str(update.effective_user.id)
    with Session() as session:
        api = session.query(UserAPI).filter_by(user_id=user_id, api_name=name).first()
        if api:
            session.delete(api)
            session.commit()
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
    with Session() as session:
        api = session.query(UserAPI).filter_by(user_id=user_id, api_name=name).first()
        if not api:
            await update.message.reply_text(f"未找到名为 {name} 的 API！")
            return
        response = requests.get(api.api_url)
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
                    await context.bot.send_photo(chat_id=user_id, photo=bio, caption=f"API {name} 返回的图片")
                elif 'video' in content_type:
                    # 推送视频
                    bio = BytesIO(response.content)
                    bio.name = f"{name}.mp4"
                    await context.bot.send_video(chat_id=user_id, video=bio, caption=f"API {name} 返回的视频")
                elif 'audio' in content_type:
                    # 推送音频
                    bio = BytesIO(response.content)
                    bio.name = f"{name}.mp3"
                    await context.bot.send_audio(chat_id=user_id, audio=bio, caption=f"API {name} 返回的音频")
                elif 'application' in content_type or 'octet-stream' in content_type:
                    # 推送文件
                    bio = BytesIO(response.content)
                    bio.name = f"{name}_file"
                    await context.bot.send_document(chat_id=user_id, document=bio, caption=f"API {name} 返回的文件")
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
    with Session() as session:
        blocked = session.query(GroupSettings).filter_by(group_id=group_id, blocked_api=api_name).first()
        if not blocked:
            new_block = GroupSettings(group_id=group_id, blocked_api=api_name)
            session.add(new_block)
            session.commit()
            await update.message.reply_text(f"API {api_name} 已被屏蔽！")
        else:
            await update.message.reply_text(f"API {api_name} 已经在屏蔽列表中！")

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
    with Session() as session:
        blocked = session.query(GroupSettings).filter_by(group_id=group_id, blocked_api=api_name).first()
        if blocked:
            session.delete(blocked)
            session.commit()
            await update.message.reply_text(f"API {api_name} 已解除屏蔽！")
        else:
            await update.message.reply_text(f"API {api_name} 不在屏蔽列表中！")

# 获取并保存最后的数据状态
def get_last_state(user_id, api_name):
    with Session() as session:
        state = session.query(APIState).filter_by(user_id=user_id, api_name=api_name).first()
        return state.last_data if state else None

def save_last_state(user_id, api_name, data):
    with Session() as session:
        state = session.query(APIState).filter_by(user_id=user_id, api_name=api_name).first()
        if state:
            state.last_data = data
        else:
            state = APIState(user_id=user_id, api_name=api_name, last_data=data)
            session.add(state)
        session.commit()

# 检查 API 更新
async def check_api_updates():
    while True:
        await asyncio.sleep(60)
        with Session() as session:
            apis = session.query(UserAPI).all()
            for api in apis:
                try:
                    response = requests.get(api.api_url)
                    if response.status_code == 200:
                        last_state = get_last_state(api.user_id, api.api_name)
                        content_type = response.headers.get('Content-Type', '').lower()
                        if 'image' in content_type:
                            if response.content != last_state:
                                image = Image.open(BytesIO(response.content))
                                bio = BytesIO()
                                bio.name = f"{api.api_name}.png"
                                image.save(bio, 'PNG')
                                bio.seek(0)
                                await bot.send_photo(chat_id=api.user_id, photo=bio, caption=f"API {api.api_name} 更新的图片")
                                save_last_state(api.user_id, api.api_name, response.content)
                        elif 'video' in content_type:
                            if response.content != last_state:
                                bio = BytesIO(response.content)
                                bio.name = f"{api.api_name}.mp4"
                                await bot.send_video(chat_id=api.user_id, video=bio, caption=f"API {api.api_name} 更新的视频")
                                save_last_state(api.user_id, api.api_name, response.content)
                        elif 'audio' in content_type:
                            if response.content != last_state:
                                bio = BytesIO(response.content)
                                bio.name = f"{api.api_name}.mp3"
                                await bot.send_audio(chat_id=api.user_id, audio=bio, caption=f"API {api.api_name} 更新的音频")
                                save_last_state(api.user_id, api.api_name, response.content)
                        elif 'application' in content_type or 'octet-stream' in content_type:
                            if response.content != last_state:
                                bio = BytesIO(response.content)
                                bio.name = f"{api.api_name}_file"
                                await bot.send_document(chat_id=api.user_id, document=bio, caption=f"API {api.api_name} 更新的文件")
                                save_last_state(api.user_id, api.api_name, response.content)
                        elif 'text' in content_type or 'json' in content_type:
                            data = response.json() if 'json' in content_type else response.text
                            if data != last_state:
                                await bot.send_message(chat_id=api.user_id, text=f"API {api.api_name} 有新更新:\n{json.dumps(data, indent=2) if isinstance(data, dict) else data}")
                                save_last_state(api.user_id, api.api_name, data)
                        else:
                            logger.warning(f"未知内容类型: {content_type}")
                except Exception as e:
                    logger.error(f"调用 API {api.api_name} 失败: {e}")

# 启动应用
async def main():
    loop = asyncio.get_event_loop()  # 获取事件循环
    loop.create_task(check_api_updates())  # 创建异步任务

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add_api", add_api))
    app.add_handler(CommandHandler("remove_api", remove_api))
    app.add_handler(CommandHandler("call_api", call_api))
    app.add_handler(CommandHandler("block_api", block_api))
    app.add_handler(CommandHandler("unblock_api", unblock_api))

    global bot
    bot = Bot(token=token)

    # 启动后台任务
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
