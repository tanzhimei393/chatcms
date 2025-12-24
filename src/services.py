import uuid
import httpx
import asyncio
import random
import logging
from pathlib import Path
from datetime import datetime, time, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session
from . import models, crud, database
from config import settings
from google.auth.transport.requests import Request
from google.oauth2 import service_account

# logger
logger = logging.getLogger("uvicorn")

async def submit_to_google_indexing(url: str):
    """提交URL到Google索引API"""
    try:
        # 加载服务账号
        credentials = service_account.Credentials.from_service_account_file(
            "google_service_account.json", scopes=["https://www.googleapis.com/auth/indexing"]
        )

        # 刷新并获取 access_token
        request = Request()
        credentials.refresh(request)
        access_token = credentials.token

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }

         # 支持 URL_UPDATED/URL_DELETED
        payload = {
            "url": url,
            "type": "URL_UPDATED"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://indexing.googleapis.com/v3/urlNotifications:publish",
                headers=headers,
                json=payload,
                timeout=30.0
            )

            if response.status_code == 200:
                logger.info(f"成功提交到Google索引: {url}")
                return True
            else:
                logger.info(f"Google提交索引失败: {response.status_code} - {response.text}")
                return False

    except Exception as e:
        logger.info(f"Google索引提交错误: {e}")
        return False

async def submit_to_bing_indexing(url: str):
    """提交URL到Bing索引API"""
    if not settings.BING_API_KEY:
        logger.info("Bing API密钥未配置，跳过提交")
        return False
    
    payload = {
        "siteUrl": settings.SITE_URL.rstrip('/'),
        "urlList": [url]
    }
    
    api_url = f"https://ssl.bing.com/webmaster/api.svc/json/SubmitUrlbatch?apikey={settings.BING_API_KEY}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30.0
            )
            
            if response.status_code == 200:
                logger.info(f"成功提交到Bing索引: {url}")
                return True
            else:
                logger.error(f"Bing索引提交失败: {response.status_code} - {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"Bing索引提交错误: {e}")
        return False

async def submit_to_search_engines():
    """每隔24小时提交搜索引擎"""
    while True:
        try:
            # 检查是否是本地地址，避免提交测试环境
            if "localhost" in settings.SITE_URL or "127.0.0.1" in settings.SITE_URL:
                logger.info(f"检测到本地环境 {settings.SITE_URL}，跳过搜索引擎提交")
                return
            
            # 为每个任务创建新的数据库会话
            db = database.SessionLocal()
            try:
                # 获取没有提交Google的文章
                submit_google_articles = db.query(models.Article).filter(models.Article.is_submit_google == False).order_by(models.Article.id.asc()).all()
                for submit_google_article  in submit_google_articles:
                    if await submit_to_google_indexing(f"{settings.SITE_URL.rstrip('/')}/articles/{submit_google_article.id}"):
                        submit_google_article.is_submit_google=True
                        db.commit()

                    await asyncio.sleep(1)

                # 获取没有提交Bing的文章
                submit_bing_articles = db.query(models.Article).filter(models.Article.is_submit_bing == False).order_by(models.Article.id.asc()).all()
                for submit_bing_article  in submit_bing_articles:
                    if await submit_to_bing_indexing(f"{settings.SITE_URL.rstrip('/')}/articles/{submit_bing_article.id}"):
                        submit_bing_article.is_submit_bing=True
                        db.commit()

                    await asyncio.sleep(1)
            finally:
                # 确保关闭数据库会话
                db.close()
            
            # 等待24小时
            await asyncio.sleep(86400)
            
        except Exception as e:
            logger.error(f"搜索引擎提交任务出错: {e}")

            # 出错后等待1小时再重试
            await asyncio.sleep(3600)

async def generate_content_with_deepseek(prompt: str) -> str:
    """调用DeepSeek API生成内容"""
    headers = {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是一个文章创作助手。"},
            {"role": "user", "content": prompt}
        ],
        "stream": False
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(settings.DEEPSEEK_API_URL, json=payload, headers=headers, timeout=300.0)
            response.raise_for_status()
            result = response.json()

            logger.debug(f"DeepSeek API响应状态: {response.status_code}")
            logger.debug(f"DeepSeek API响应内容: {result}")

            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]
            else:
                logger.warning(f"DeepSeek API返回异常: {result}")
        return None

    except httpx.HTTPStatusError as e:
        logger.error(f"DeepSeek API HTTP错误: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"DeepSeek API请求错误: {e}")
        return None
    except Exception as e:
        logger.error(f"DeepSeek API调用失败: {e}")
        return None

async def reset_daily_article_counts():
    """每天0点1分重置所有栏目的文章计数"""
    while True:
        try:
            now = datetime.now()
            # 计算到明天0点1分的等待时间
            target_time = datetime.combine(now.date(), time(0, 1))
            if now > target_time:
                # 使用 timedelta 安全地添加天数
                target_time = target_time + timedelta(days=1)
            
            wait_seconds = (target_time - now).total_seconds()
            await asyncio.sleep(wait_seconds)
            
            # 为每个任务创建新的数据库会话
            db = database.SessionLocal()
            try:
                # 重置所有栏目的文章计数
                db.query(models.Category).update({models.Category.article_count: 0})
                db.commit()
                logger.info(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 已重置所有栏目的文章计数")
            finally:
                db.close()
            
        except Exception as e:
            logger.error(f"重置文章计数任务出错: {e}")
            # 出错后等待1小时再重试
            await asyncio.sleep(3600)

async def auto_publish_articles():
    """自动发布文章任务"""
    while True:
        try:
            # 为每个循环创建新的数据库会话
            db = database.SessionLocal()
            
            try:
                # 启用的栏目
                categories = db.query(models.Category).filter(models.Category.is_active == True).order_by(models.Category.id.asc()).all()
                for category in categories:
                    # 栏目是否存在文章模板
                    if db.query(models.ArticleTemplate).filter(models.ArticleTemplate.category_id == category.id, models.ArticleTemplate.is_active == True).count() <= 0:
                        logger.debug(f"栏目 {category.name} 没有启用的文章模板，跳过")
                        continue

                    # 栏目是否需要发布新文章
                    if category.article_count >= category.publish_count:
                        logger.debug(f"栏目 {category.name} 已达到每日发布限制 ({category.article_count}/{category.publish_count})，跳过")
                        continue

                    # 文章模板
                    template = None

                    # 栏目上一次发布的文章
                    last_article = db.query(models.Article).filter(models.Article.category_id == category.id).order_by(models.Article.id.desc()).first()
                    if last_article:
                        # 获取下一个文章模板
                        template = db.query(models.ArticleTemplate).filter(
                            models.ArticleTemplate.category_id == category.id,
                            models.ArticleTemplate.is_active == True,
                            models.ArticleTemplate.id > last_article.template_id
                        ).order_by(models.ArticleTemplate.id.asc()).first()

                    # 没有发布文章或者最后一个模板发布文章后，使用第一个模板
                    if not template:
                        template = db.query(models.ArticleTemplate).filter(
                            models.ArticleTemplate.category_id == category.id,
                            models.ArticleTemplate.is_active == True
                        ).order_by(models.ArticleTemplate.id.asc()).first()

                    if not template:
                        logger.warning(f"栏目 {category.name} 没有找到可用的文章模板")
                        continue

                    # 随机获取栏目的作者
                    author = db.query(models.Author).filter(
                        models.Author.category_id == category.id,
                        models.Author.is_active == True
                    ).order_by(func.random()).first()

                    if author:
                        logger.info(f"开始生成文章 栏目: {category.name} 模板: {template.title} 作者: {author.name}")
                    else:
                        logger.info(f"停止生成文章 栏目: {category.name} 模板: {template.title} 没有启用的作者")
                        continue

                    # 生成同义正文
                    prompt = f"请为以下文章的正文生成一个同义文章正文，格式为Html的Quill富文本，html标签不要使用ql-editor类，不要使用换行符：'\n'，并在正文上方生成文章目录及其锚定，不要回复其他内容：{template.content}"
                    new_content = await generate_content_with_deepseek(prompt)
                    if not new_content:
                        logger.error(f"生成文章正文失败，栏目: {category.name}")
                        continue

                    # 根据同义正文生成标题
                    prompt = f"请根据以下文章的正文取一个该文章的标题，不要回复其他内容：{new_content}"
                    new_title = await generate_content_with_deepseek(prompt)
                    if not new_title:
                        logger.error(f"生成文章标题失败，栏目: {category.name}")
                        continue

                    # 生成同义副标题
                    prompt = f"请根据以下文章的正文生成一个文章的副标题，长度必须为30至50个字，不要回复其他内容：{new_content}"
                    new_subtitle = await generate_content_with_deepseek(prompt)
                    if not new_subtitle:
                        logger.error(f"生成文章副标题失败，栏目: {category.name}")
                        continue

                    # 根据同义正文生成标签
                    prompt = f"请根据以下文章的正文生成5至10个关键字，关键字之间用逗号分开，不要回复其他内容：{new_content}"
                    new_tags = await generate_content_with_deepseek(prompt)
                    if not new_tags:
                        logger.error(f"生成文章标签失败，栏目: {category.name}")
                        continue

                    # 生成文章图片
                    image = models.Image(
                        network_url=f"network/upload/article/{uuid.uuid4().hex}{Path(template.thumbnail_url).suffix}",
                        static_url=template.thumbnail_url
                    )

                    # 创建新的文章
                    article = models.Article(
                        category_id=category.id,
                        author_id=author.id,
                        template_id=template.id,
                        thumbnail_url=image.network_url,
                        title=new_title,
                        subtitle=new_subtitle,
                        content=new_content,
                        tags=",".join(dict.fromkeys(tag.strip() for tag in f"{template.tags},{new_tags}".replace("，", ",").split(",") if tag.strip())),
                        pageviews=random.randint(3000, 10000),
                        published_at=datetime.now(),
                        is_submit_google=False,
                        is_submit_bing=False
                    )

                    # 获取article ID但不提交事务
                    db.add(image)
                    db.add(article)
                    db.flush()

                    # 更新栏目文章计数
                    category.article_count += 1

                    db.commit()
                    logger.info(f"已发布新文章: {article.title} ID: {article.id}")
                    
            finally:
                # 确保关闭数据库会话
                db.close()

            # 每分钟检查一次
            await asyncio.sleep(60)

        except Exception as e:
            logger.error(f"自动发布任务出错: {e}")

            # 确保出错时也关闭会话
            try:
                db.close()
            except:
                pass

            # 每分钟检查一次
            await asyncio.sleep(60)

# 启动自动任务
async def start_background_tasks():
    """启动所有后台任务"""
    logger.info("启动后台任务...")
    await asyncio.gather(
        reset_daily_article_counts(),
        auto_publish_articles(),
        submit_to_search_engines()
    )