import os
import math
import time
import json
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request, Form, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from datetime import date, datetime, timedelta
from collections import defaultdict
from . import models, schemas, crud, database, services
from .helper import calculate_relative_time, get_weeks_diff
from config import settings

# 配置日志
logger = logging.getLogger("uvicorn")

# 全局变量记录登录尝试
login_attempts = {}
locked_until = {}

# 启动时创建数据库表
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时创建数据库
    models.Base.metadata.create_all(bind=database.engine)

    # 启动所有后台任务
    asyncio.create_task(services.start_background_tasks())
    logger.info("应用启动成功")
    yield
    logger.info("应用停止成功")

app = FastAPI(title="内容管理系统", lifespan=lifespan)

# 检查并创建static目录
static_dir = "static"
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 添加 favicon 路由
@app.get("/favicon.ico")
async def favicon():
    return FileResponse("static/theme/images/favicon.ico")

# 管理后台 模板目录
admin_templates = Jinja2Templates(directory="src/admin")
admin_templates.env.trim_blocks = True
admin_templates.env.lstrip_blocks = True
admin_templates.env.auto_reload = False

# 网站前台 模板目录
public_templates = Jinja2Templates(directory="src/public")
public_templates.env.trim_blocks = True
public_templates.env.lstrip_blocks = True
public_templates.env.auto_reload = False

# 文章图片映射
@app.get("/network/upload/article/{file_name}")
async def image_page(
    request: Request,
    file_name: str, 
    db: Session = Depends(database.get_db)
):
    image = db.query(models.Image).filter(models.Image.network_url == f"network/upload/article/{file_name}").first()
    if not image:
        raise HTTPException(status_code=404, detail="文章图片不存在")
    
    return FileResponse(image.static_url)

# 密码验证中间件
async def verify_password(request: Request):
    password_cookie = request.cookies.get("password")
    if password_cookie == settings.PASSWORD:
        return True
    
    if request.url.path not in ["/kofkyo", "/kofkyo/login"]:
        raise HTTPException(status_code=303, headers={"Location": "/kofkyo"})
    
    return False

# 登录路由
@app.get("/kofkyo", response_class=HTMLResponse)
async def login_page(request: Request):
    return admin_templates.TemplateResponse("login.html", {"request": request})

@app.post("/kofkyo/login")
async def login(
    request: Request,
    password: str = Form(...),
    response: Response = None
):
    # 获取客户端IP
    client_ip = request.client.host
    
    # 清理过时的登录尝试记录（超过1小时）
    current_time = time.time()
    cleanup_threshold = current_time - 3600
    
    # 清理过时的登录记录
    for ip in list(login_attempts.keys()):
        if login_attempts[ip]['last_attempt'] < cleanup_threshold:
            del login_attempts[ip]
    
    # 清理过期的锁定记录
    for ip in list(locked_until.keys()):
        if locked_until[ip] < current_time:
            del locked_until[ip]
    
    # 检查该IP是否被锁定
    if client_ip in locked_until and current_time < locked_until[client_ip]:
        remaining = int((locked_until[client_ip] - current_time) / 60)
        logger.warning(f"{client_ip} 尝试登录但账户被锁定，剩余时间: {remaining}分钟")
        raise HTTPException(
            status_code=429, 
            detail=f"账户已锁定，请 {remaining} 分钟后再试"
        )
    
    if password == settings.PASSWORD:
        # 登录成功，重置该IP的尝试次数
        if client_ip in login_attempts:
            del login_attempts[client_ip]
        if client_ip in locked_until:
            del locked_until[client_ip]
        
        logger.info(f"{client_ip} 登录成功")
        response = RedirectResponse(url="/kofkyo/dashboard", status_code=303)
        response.set_cookie(key="password", value=password, httponly=True)
        return response
    else:
        # 登录失败，增加该IP的尝试次数
        if client_ip not in login_attempts:
            login_attempts[client_ip] = {'count': 0, 'last_attempt': current_time}
        
        login_attempts[client_ip]['count'] += 1
        login_attempts[client_ip]['last_attempt'] = current_time
        
        remaining_attempts = settings.MAX_LOGIN_ATTEMPTS - login_attempts[client_ip]['count']
        
        if login_attempts[client_ip]['count'] >= settings.MAX_LOGIN_ATTEMPTS:
            # 锁定该IP的账户
            locked_until[client_ip] = current_time + (settings.LOCKOUT_TIME * 60)
            logger.warning(f"{client_ip} 密码错误次数过多，账户已锁定")
            raise HTTPException(
                status_code=429, 
                detail="密码错误次数过多，账户已锁定15分钟"
            )
        
        logger.warning(f"{client_ip} 密码错误，剩余尝试次数: {remaining_attempts}")
        raise HTTPException(
            status_code=401, 
            detail=f"密码错误，还剩 {remaining_attempts} 次尝试机会"
        )


# 仪表板
@app.get("/kofkyo/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    categories = db.query(models.Category).all()
    authors_count = crud.get_authors_count(db)
    templates_count = crud.get_templates_count(db)
    articles_count = crud.get_articles_count(db)
    subscribes_count = crud.get_subscribes_count(db)
    
    return admin_templates.TemplateResponse("dashboard.html", {
        "request": request,
        "categories": categories,
        "authors_count": authors_count,
        "templates_count": templates_count,
        "articles_count": articles_count,
        "subscribes_count": subscribes_count
    })

# 站点设置路由
@app.get("/kofkyo/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    # 获取所有站点设置
    settings = db.query(models.Settings).all()
    settings_dict = {setting.key: setting.value for setting in settings}
    
    return admin_templates.TemplateResponse("settings.html", {
        "request": request,
        "settings": settings_dict
    })

# 站点设置更新
@app.post("/kofkyo/settings")
async def update_settings(
    request: Request,
    site_name: str = Form(""),
    site_title: str = Form(""),
    site_description: str = Form(""),
    site_search: str = Form(""),
    site_distribute: str = Form(""),
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    site_name = site_name.strip()
    site_title = site_title.strip()
    site_description = site_description.strip()
    site_search = site_search.replace("，",",").strip()
    site_distribute = site_distribute.strip()

    # 更新或创建站点设置
    settings_to_update = {
        "site_name": site_name,
        "site_title": site_title,
        "site_description": site_description,
        "site_search": site_search,
        "site_distribute": site_distribute
    }
    
    for key, value in settings_to_update.items():
        setting = db.query(models.Settings).filter(models.Settings.key == key).first()
        if setting:
            setting.value = value
        else:
            setting = models.Settings(key=key, value=value)
            db.add(setting)
    
    db.commit()
    logger.info(f"{request.client.host} 更新站点设置")

    return RedirectResponse(url="/kofkyo/settings", status_code=303)

# 栏目管理路由
@app.get("/kofkyo/categories", response_class=HTMLResponse)
async def categories_page(
    request: Request,
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    categories = db.query(models.Category).all()
    return admin_templates.TemplateResponse("categories.html", {
        "request": request,
        "categories": categories
    })

@app.post("/kofkyo/categories")
async def create_category_endpoint(
    request: Request,
    name: str = Form(...),
    icon: str = Form(...),
    color: str = Form(...),
    publish_count: int = Form(10),
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    category = schemas.CategoryCreate(name=name, icon=icon, color=color, publish_count=publish_count)
    crud.create_category(db, category)
    logger.info(f"{request.client.host} 创建栏目 {name}")
    return RedirectResponse(url="/kofkyo/categories", status_code=303)

@app.post("/kofkyo/categories/edit")
async def edit_category_endpoint(
    request: Request,
    category_id: int = Form(...),
    name: str = Form(...),
    icon: str = Form(...),
    color: str = Form(...),
    publish_count: int = Form(...),
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    category = db.query(models.Category).filter(models.Category.id == category_id).first()
    if category:
        category.name = name
        category.icon = icon
        category.color = color
        category.publish_count = publish_count
        db.commit()
        logger.info(f"{request.client.host} 更新栏目信息 {name}")
    return RedirectResponse(url="/kofkyo/categories", status_code=303)

@app.post("/kofkyo/categories/{category_id}/toggle")
async def toggle_category(
    request: Request,
    category_id: int,
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    category = db.query(models.Category).filter(models.Category.id == category_id).first()
    if category:
        category.is_active = not category.is_active
        db.commit()
        logger.info(f"{request.client.host} 更新栏目状态 {category_id}")
    return RedirectResponse(url="/kofkyo/categories", status_code=303)

@app.post("/kofkyo/categories/{category_id}/delete")
async def delete_category_endpoint(
    request: Request,
    category_id: int,
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    crud.delete_category(db, category_id)
    logger.info(f"{request.client.host} 删除栏目 {category_id}")
    return RedirectResponse(url="/kofkyo/categories", status_code=303)

# 作者管理路由
@app.get("/kofkyo/authors")
async def authors_page(
    request: Request,
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    categories = db.query(models.Category).all()
    authors = db.query(models.Author).all()
    return admin_templates.TemplateResponse("authors.html", {
        "request": request,
        "categories": categories,
        "authors": authors
    })

@app.post("/kofkyo/authors")
async def create_author_endpoint(
    request: Request,
    category_id: int = Form(...),
    avatar_url: str = Form(...),
    name: str = Form(...),
    profession: str = Form(...),
    description: str = Form(...),
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    avatar_url = avatar_url.strip(' ').lstrip('/')
    name = name.strip(' ')
    profession = profession.strip(' ')
    description = description.strip(' ')
    author = schemas.AuthorCreate(category_id=category_id, avatar_url=avatar_url, name=name, profession=profession, description=description)
    crud.create_author(db, author)
    logger.info(f"{request.client.host} 创建作者 {name}")
    return RedirectResponse(url="/kofkyo/authors", status_code=303)

@app.post("/kofkyo/authors/edit")
async def edit_author_endpoint(
    request: Request,
    author_id: int = Form(...),
    category_id: int = Form(...),
    avatar_url: str = Form(...),
    name: str = Form(...),
    profession: str = Form(...),
    description: str = Form(...),
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    avatar_url = avatar_url.strip(' ').lstrip('/')
    name = name.strip(' ')
    profession = profession.strip(' ')
    description = description.strip(' ')
    author = db.query(models.Author).filter(models.Author.id == author_id).first()
    if author:
        author.category_id = category_id
        author.avatar_url = avatar_url
        author.name = name
        author.profession = profession
        author.description = description
        db.commit()
        logger.info(f"{request.client.host} 更新作者信息 {name}")
    return RedirectResponse(url="/kofkyo/authors", status_code=303)

@app.post("/kofkyo/authors/{author_id}/toggle")
async def toggle_author(
    request: Request,
    author_id: int,
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    author = db.query(models.Author).filter(models.Author.id == author_id).first()
    if author:
        author.is_active = not author.is_active
        db.commit()
        logger.info(f"{request.client.host} 更新作者状态 {author_id}")
    return RedirectResponse(url="/kofkyo/authors", status_code=303)

@app.post("/kofkyo/authors/{author_id}/delete")
async def delete_author_endpoint(
    request: Request,
    author_id: int,
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    crud.delete_author(db, author_id)
    logger.info(f"{request.client.host} 删除作者 {author_id}")
    return RedirectResponse(url="/kofkyo/authors", status_code=303)

# 模板管理路由
@app.get("/kofkyo/templates", response_class=HTMLResponse)
async def templates_page(
    request: Request,
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    categories = db.query(models.Category).all()
    templates = db.query(models.ArticleTemplate).all()
    return admin_templates.TemplateResponse("templates.html", {
        "request": request,
        "categories": categories,
        "templates": templates
    })

@app.post("/kofkyo/templates")
async def create_template_endpoint(
    request: Request,
    category_id: int = Form(...),
    thumbnail_url: str = Form(...),
    title: str = Form(...),
    subtitle: str = Form(...),
    content: str = Form(...),
    tags: str = Form(...),
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    thumbnail_url = thumbnail_url.strip(' ').lstrip('/')
    title = title.strip(' ')
    subtitle = subtitle.strip(' ')
    tags = tags.strip(' ')
    template = schemas.ArticleTemplateCreate(category_id=category_id, thumbnail_url=thumbnail_url, title=title, subtitle=subtitle, content=content, tags=tags)
    crud.create_template(db, template)
    logger.info(f"{request.client.host} 创建文章模板 {title}")
    return RedirectResponse(url="/kofkyo/templates", status_code=303)

@app.post("/kofkyo/templates/{template_id}/edit")
async def update_template_endpoint(
    request: Request,
    template_id: int,
    category_id: int = Form(...),
    thumbnail_url: str = Form(...),
    title: str = Form(...),
    subtitle: str = Form(...),
    content: str = Form(...),
    tags: str = Form(...),
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    thumbnail_url = thumbnail_url.strip(' ').lstrip('/')
    title = title.strip(' ')
    subtitle = subtitle.strip(' ')
    tags = tags.strip(' ')
    template = db.query(models.ArticleTemplate).filter(models.ArticleTemplate.id == template_id).first()
    if template:
        template.category_id = category_id
        template.thumbnail_url = thumbnail_url
        template.title = title
        template.subtitle = subtitle
        template.content = content
        template.tags = tags
        db.commit()
        logger.info(f"{request.client.host} 更新模板信息 {category_id}")
    return RedirectResponse(url="/kofkyo/templates", status_code=303)

@app.post("/kofkyo/templates/{template_id}/toggle")
async def toggle_template(
    request: Request,
    template_id: int,
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    template = db.query(models.ArticleTemplate).filter(models.ArticleTemplate.id == template_id).first()
    if template:
        template.is_active = not template.is_active
        db.commit()
        logger.info(f"{request.client.host} 更新模板状态 {template_id}")
    return RedirectResponse(url="/kofkyo/templates", status_code=303)

@app.post("/kofkyo/templates/{template_id}/delete")
async def delete_template_endpoint(
    request: Request,
    template_id: int,
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    crud.delete_template(db, template_id)
    logger.info(f"{request.client.host} 删除文章模板 {template_id}")
    return RedirectResponse(url="/kofkyo/templates", status_code=303)

# 文章管理路由
@app.get("/kofkyo/articles", response_class=HTMLResponse)
async def articles_page(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    # 计算分页
    total_articles = crud.get_articles_count(db)
    total_pages = (total_articles + per_page - 1) // per_page
    offset = (page - 1) * per_page
    
    articles = crud.get_articles(db, offset, per_page)
    
    return admin_templates.TemplateResponse("articles.html", {
        "request": request,
        "articles": articles,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total_articles": total_articles
    })

@app.get("/kofkyo/articles/{article_id}", response_class=HTMLResponse)
async def article_detail(
    request: Request,
    article_id: int,
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    article = db.query(models.Article).filter(models.Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    return admin_templates.TemplateResponse("article_detail.html", {
        "request": request,
        "article": article
    })

@app.post("/kofkyo/articles/{article_id}/delete")
async def delete_article_endpoint(
    request: Request,
    article_id: int,
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    article = db.query(models.Article).filter(models.Article.id == article_id).first()
    if article:
        # 检查是否是今天发布的文章
        if article.published_at.date() == date.today():
            # 减少栏目文章计数
            category = db.query(models.Category).filter(models.Category.id == article.category_id).first()
            if category and category.article_count > 0:
                category.article_count -= 1
        
        db.delete(article)
        db.commit()
        logger.info(f"{request.client.host} 删除文章 {article_id}")
    
    # 获取referer并重定向，如果没有referer则默认重定向到/articles
    referer = request.headers.get("referer", "/kofkyo/articles")
    return RedirectResponse(url=referer, status_code=303)

# 订阅管理路由
@app.get("/kofkyo/subscribes", response_class=HTMLResponse)
async def subscribes_page(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    # 计算分页
    total_subscribes = crud.get_subscribes_count(db)
    total_pages = (total_subscribes + per_page - 1) // per_page
    offset = (page - 1) * per_page
    
    subscribes = crud.get_subscribes(db, offset, per_page)
    
    return admin_templates.TemplateResponse("subscribes.html", {
        "request": request,
        "subscribes": subscribes,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total_subscribes": total_subscribes
    })

@app.post("/kofkyo/subscribes/{subscribe_id}/delete")
async def delete_subscribe_endpoint(
    request: Request,
    subscribe_id: int,
    db: Session = Depends(database.get_db),
    authenticated: bool = Depends(verify_password)
):
    subscribe = db.query(models.Subscribe).filter(models.Subscribe.id == subscribe_id).first()
    if subscribe:
        db.delete(subscribe)
        db.commit()
        logger.info(f"{request.client.host} 删除订阅 {subscribe_id}")
    
    # 获取referer并重定向，如果没有referer则默认重定向到/subscribes
    referer = request.headers.get("referer", "/kofkyo/subscribes")
    return RedirectResponse(url=referer, status_code=303)

# 退出登录
@app.get("/kofkyo/logout")
async def logout():
    response = RedirectResponse(url="/kofkyo")
    response.delete_cookie("password")
    return response

# 前台首页
@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request, db: Session = Depends(database.get_db)):
    # 获取站点设置
    settings = db.query(models.Settings).all()
    settings_dict = {setting.key: setting.value for setting in settings}
    site_name = settings_dict.get("site_name","网站名称")
    site_title = settings_dict.get("site_title","网站标题")
    site_description = settings_dict.get("site_description","网站描述")
    site_search = settings_dict.get("site_search","热门搜索")
    site_distribute = settings_dict.get("site_distribute","分发网址")

    # 启用的栏目
    categories = db.query(models.Category).filter(models.Category.is_active == True).order_by(models.Category.id.asc()).all()
    
    # 栏目的文章
    for category in categories:
        articles = db.query(models.Article).filter(
            models.Article.category_id == category.id
        ).order_by(models.Article.id.desc()).limit(5).all()
        
        # 计算每篇文章的相对时间
        for article in articles:
            article.read_time = calculate_relative_time(article.published_at)

        category.articles = articles
    
    # 热门标签（所有模板标签，去除重复）
    hot_tags = set()
    for category in categories:
        templates = db.query(models.ArticleTemplate).filter(
            models.ArticleTemplate.category_id == category.id,
            models.ArticleTemplate.is_active == True
        ).order_by(models.ArticleTemplate.id.asc()).all()
        
        for template in templates:
            hot_tags.update(tag.strip() for tag in template.tags.split(","))

    # 推荐作者（每个类目，最近发表文章的作者）
    authors = list()
    for category in categories:
        article = db.query(models.Article).filter(models.Article.category_id == category.id).order_by(models.Article.id.desc()).first()
        if article:
            authors.append(article.author)

    # 生成JSON-LD
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "@id": f"{request.base_url}#homepage",
                "name": site_name,
                "url": str(request.base_url),
                "inLanguage": "zh-CN"
            },
            {
                "@type": "WebSite",
                "@id": f"{request.base_url}#website",
                "url": str(request.base_url),
                "name": site_name,
                "inLanguage": "zh-CN",
                "publisher": {
                    "@type": "Organization",
                    "name": site_name,
                    "logo": {
                        "@type": "ImageObject",
                        "url": f"{request.base_url}static/theme/images/logo.png"
                    }
                },
                "potentialAction": {
                    "@type": "SearchAction",
                    "target": { "@type": "EntryPoint", "urlTemplate": f"{request.base_url}search?keyword={{search_term_string}}" },
                    "query-input": { "@type": "PropertyValueSpecification", "valueRequired": True, "valueName": "search_term_string" }
                }
            },
            {
                "@type": "Organization",
                "@id": f"{request.base_url}#organization",
                "name": site_name,
                "url": str(request.base_url),
                "logo": f"{request.base_url}static/theme/images/logo.png",
                "sameAs": [
                    str(request.base_url)
                ]
            },
            {
                "@type": "ItemList",
                "@id": f"{request.base_url}#hot-search",
                "name": "热门搜索",
                "itemListElement": [
                    {
                        "@type": "DefinedTerm",
                        "name": keyword,
                        "url": f"{request.base_url}search?keyword={keyword}"
                    }
                    for keyword in site_search.split(',')[:5]
                ]
            },
            {
                "@type": "ItemList",
                "@id": f"{request.base_url}#hot-tags",
                "name": "热门标签",
                "itemListElement": [
                    {
                        "@type": "DefinedTerm",
                        "name": hot_tag,
                        "url": f"{request.base_url}tags/{hot_tag}"
                    }
                    for hot_tag in list(hot_tags)[:5]
                ]
            },
            {
                "@type": "ItemList",
                "@id": f"{request.base_url}#authors",
                "name": "推荐作者",
                "itemListElement": [
                    {
                        "@type": "Person",
                        "name": author.name,
                        "url": f"{request.base_url}author/{author.id}",
                        "image": f"{request.base_url}{author.avatar_url}"
                    }
                    for author in authors[:5]
                ]
            },
        ] + [
            {
                "@type": "CollectionPage",
                "@id": f"{request.base_url}#category{category.id}",
                "name": category.name,
                "url": f"{request.base_url}categories/{category.id}",
                "inLanguage": "zh-CN",
                "mainEntity": {
                    "@type": "ItemList",
                    "itemListElement": [
                        {
                            "@type": "ListItem",
                            "position": i+1,
                            "url": f"{request.base_url}articles/{article.id}",
                            "name": article.title
                        }
                        for i, article in enumerate(category.articles)
                    ]
                }
            }
            for category in categories
        ]
    }

    return public_templates.TemplateResponse("index.html", {
        "request": request,
        "site_name": site_name,
        "site_title": site_title,
        "site_description": site_description,
        "site_search": site_search,
        "site_distribute": site_distribute,
        "categories": categories,
        "hot_tags": hot_tags,
        "authors": authors,
        "json_ld": json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    })

# 文章详情
@app.get("/articles/{article_id}", response_class=HTMLResponse)
async def article_detail_page(
    request: Request, 
    article_id: int,
    db: Session = Depends(database.get_db)
):
    # 获取站点设置
    settings = db.query(models.Settings).all()
    settings_dict = {setting.key: setting.value for setting in settings}
    site_name = settings_dict.get("site_name","网站名称")
    site_title = settings_dict.get("site_title","网站标题")
    site_description = settings_dict.get("site_description","网站描述")
    site_search = settings_dict.get("site_search","热门搜索")
    site_distribute = settings_dict.get("site_distribute","分发网址")

    # 启用的栏目
    categories = db.query(models.Category).filter(models.Category.is_active == True).order_by(models.Category.id.asc()).all()

    # 查找文章
    article = db.query(models.Article).filter(models.Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    # 文章标签
    article_tags = article.tags.split(",")

    # 上一篇（同类目的上一篇文章，没有则取最后一篇）
    prev_article = db.query(models.Article).filter(
        and_(
            models.Article.category_id == article.category_id,
            models.Article.id < article.id
        )
    ).order_by(models.Article.id.desc()).first()

    if not prev_article:
        prev_article = db.query(models.Article).filter(models.Article.category_id == article.category_id).order_by(models.Article.id.desc()).first()

    # 下一篇（同类目的下一篇文章，没有则取第一篇）
    next_article = db.query(models.Article).filter(
        and_(
            models.Article.category_id == article.category_id,
            models.Article.id > article.id
        )
    ).order_by(models.Article.id.asc()).first()

    if not next_article:
        next_article = db.query(models.Article).filter(models.Article.category_id == article.category_id).order_by(models.Article.id.asc()).first()
    
    # 相关文章（同类目最新10篇文章）
    related_articles = db.query(models.Article).filter(
        and_ 
            (
                models.Article.category_id == article.category_id, 
                models.Article.id != article.id
            )
        ).order_by(models.Article.id.desc()).limit(10).all()
    
    # 热门推荐（每个类目最新1篇文章）
    hot_articles = list()
    for category in categories:
        hot_article = db.query(models.Article).filter(
            and_ 
            (
                models.Article.category_id == category.id, 
                models.Article.id != article.id
            )
        ).order_by(models.Article.id.desc()).first()

        if hot_article:
            hot_articles.append(hot_article)
    
    # 热门标签（所有模板标签，去除重复）
    hot_tags = set()
    for category in categories:
        templates = db.query(models.ArticleTemplate).filter(
            models.ArticleTemplate.category_id == category.id,
            models.ArticleTemplate.is_active == True
        ).order_by(models.ArticleTemplate.id.asc()).all()
        
        for template in templates:
            hot_tags.update(tag.strip() for tag in template.tags.split(","))

    # 计算每篇文章的相对时间
    article.read_time = calculate_relative_time(article.published_at)
    prev_article.read_time = calculate_relative_time(prev_article.published_at)
    next_article.read_time = calculate_relative_time(next_article.published_at)
    
    # 计算每篇文章的相对时间
    for related_article in related_articles:
        related_article.read_time = calculate_relative_time(related_article.published_at)
    
    # 计算每篇文章的相对时间
    for hot_article in hot_articles:
        hot_article.read_time = calculate_relative_time(hot_article.published_at)

    # 页面标题
    site_title = f"{article.title} - {article.category.name} - {site_name}"

    # 页面描述
    site_description = article.subtitle

    # 生成JSON-LD
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "首页", "item": str(request.base_url)},
                    {"@type": "ListItem", "position": 2, "name": article.category.name, "item": f"{request.base_url}categories/{article.category_id}"},
                    {"@type": "ListItem", "position": 3, "name": article.title, "item": f"{request.base_url}articles/{article.id}"}
                ]
            },
            {
                "@type": "Article",
                "inLanguage": "zh-CN",
                "@id": f"{request.url}#article",
                "url": str(request.url),
                "headline": article.title,
                "description": article.subtitle,
                "image": f"{request.base_url}{article.thumbnail_url}",
                "author": {"@type": "Person", "name": article.author.name, "url": f"{request.base_url}author/{article.author.id}"},
                "publisher": {
                    "@type": "Organization",
                    "name": site_name,
                    "logo": {"@type": "ImageObject", "url": f"{request.base_url}static/theme/images/logo.png"}
                },
                "datePublished": article.published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                "mainEntityOfPage": {"@type": "WebPage", "@id": f"{request.base_url}articles/{article.id}"},
                "mentions": [
                    {
                        "@type": "Article",
                        "@id": f"{request.base_url}articles/{prev_article.id}",
                        "url": f"{request.base_url}articles/{prev_article.id}",
                        "headline": f"上一篇：{prev_article.title}"
                    },
                    {
                        "@type": "Article",
                        "@id": f"{request.base_url}articles/{next_article.id}",
                        "url": f"{request.base_url}articles/{next_article.id}",
                        "headline": f"下一篇：{next_article.title}"
                    }
                ],
                "isPartOf": {
                    "@id": f"{request.base_url}#website"
                }
            },
            {
                "@type": "ItemList",
                "@id": f"{request.url}#hot-tags",
                "name": "热门标签",
                "itemListElement": [
                    {
                        "@type": "DefinedTerm",
                        "name": hot_tag,
                        "url": f"{request.base_url}tags/{hot_tag}"
                    }
                    for hot_tag in list(hot_tags)[:5]
                ]
            },
            {
                "@type": "ItemList",
                "@id": f"{request.url}#related-articles",
                "name": "相关文章",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i+1,
                        "item": {
                            "@type": "Article",
                            "headline": related_article.title,
                            "url": f"{request.base_url}articles/{related_article.id}"
                        }
                    }
                    for i, related_article in enumerate(related_articles[:5])
                ]
            },
            {
                "@type": "ItemList",
                "@id": f"{request.url}#hot-articles",
                "name": "热门文章",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i+1,
                        "item": {
                            "@type": "Article",
                            "headline": hot_article.title,
                            "url": f"{request.base_url}articles/{hot_article.id}"
                        }
                    }
                    for i, hot_article in enumerate(hot_articles[:5])
                ]
            }
        ]
    }

    return public_templates.TemplateResponse("article_detail.html", {
        "request": request,
        "site_name": site_name,
        "site_title": site_title,
        "site_description": site_description,
        "site_search": site_search,
        "site_distribute": site_distribute,
        "categories": categories,
        "article": article,
        "prev_article": prev_article,
        "next_article": next_article,
        "article_tags": article_tags,
        "hot_tags": hot_tags,
        "related_articles" : related_articles,
        "hot_articles" : hot_articles,
        "json_ld": json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    })

# 作者详情
@app.get("/authors/{author_id}", response_class=HTMLResponse)
async def author_detail_page(
    request: Request, 
    author_id: int,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(database.get_db)
):
    # 获取站点设置
    settings = db.query(models.Settings).all()
    settings_dict = {setting.key: setting.value for setting in settings}
    site_name = settings_dict.get("site_name","网站名称")
    site_title = settings_dict.get("site_title","网站标题")
    site_description = settings_dict.get("site_description","网站描述")
    site_search = settings_dict.get("site_search","热门搜索")
    site_distribute = settings_dict.get("site_distribute","分发网址")

    # 启用的栏目
    categories = db.query(models.Category).filter(models.Category.is_active == True).order_by(models.Category.id.asc()).all()

    # 查找作者
    author = db.query(models.Author).filter(models.Author.id == author_id).first()
    if not author:
        raise HTTPException(status_code=404, detail="作者不存在")
    
    # 计算分页
    total_articles = db.query(models.Article).filter(models.Article.author_id == author_id).count()
    total_pages = (total_articles + per_page - 1) // per_page
    offset = (page - 1) * per_page

    # 作者文章
    articles = db.query(models.Article).filter(models.Article.author_id == author_id).order_by(models.Article.id.desc()).offset(offset).limit(per_page).all()
    
    # 热门推荐（每个类目最新2篇文章）
    hot_articles = list()
    for category in categories:
        hot_articles.extend(db.query(models.Article).filter(
            and_ 
            (
                models.Article.category_id == category.id, 
                models.Article.id != author.id
            )
        ).order_by(models.Article.id.desc()).limit(2).all())
    
    # 作者标签（栏目模板标签，去除重复）
    author_tags = set()
    templates = db.query(models.ArticleTemplate).filter(
            models.ArticleTemplate.category_id == author.category_id,
            models.ArticleTemplate.is_active == True
        ).order_by(models.ArticleTemplate.id.asc()).all()
        
    for template in templates:
        author_tags.update(tag.strip() for tag in template.tags.split(","))

    # 平均每周
    weeks_diff = get_weeks_diff(author.created_at)
    if weeks_diff > 0:
        avg_week_published = math.ceil(total_articles / weeks_diff)
    else:
        avg_week_published = 0

    # 本月发布
    # 获取本月第一天和下个月第一天
    today = datetime.now()
    first_day_of_curr_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    first_day_of_next_month = (first_day_of_curr_month + timedelta(days=32)).replace(day=1)
    curr_month_published = db.query(models.Article).filter(
        models.Article.author_id == author_id,
        models.Article.published_at >= first_day_of_curr_month,
        models.Article.published_at < first_day_of_next_month
    ).count()
    
    # 计算每篇文章的相对时间
    for article in articles:
        article.read_time = calculate_relative_time(article.published_at)
    
    # 计算每篇文章的相对时间
    for hot_article in hot_articles:
        hot_article.read_time = calculate_relative_time(hot_article.published_at)

    # 页面标题
    site_title = f"{author.name}的文章 - {author.category.name} - {site_name}"

    # 页面描述
    site_description = f"查看{author.name}在{site_name}的{author.category.name}发表的全部文章，{author.description}"

    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "ProfilePage",
                "@id": f"{request.base_url}authors/{author.id}#page",
                "name": author.name,
                "url": f"{request.base_url}authors/{author.id}",
                "inLanguage": "zh-CN",
                "isPartOf": {
                    "@id": f"{request.base_url}#website"
                }
            },
            {
                "@type": "Person",
                "@id": f"{request.base_url}authors/{author.id}#person",
                "name": author.name,
                "image": f"{request.base_url}{author.avatar_url}",
                "description": author.description,
                "url": f"{request.base_url}authors/{author.id}",
                "inLanguage": "zh-CN",
                "sameAs": [
                    str(request.base_url)
                ]
            },
            {
                "@type": "ItemList",
                "@id": f"{request.base_url}authors/{author.id}#hot-articles",
                "name": "热门文章",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i+1,
                        "item": {
                            "@type": "Article",
                            "headline": hot_article.title,
                            "url": f"{request.base_url}articles/{hot_article.id}"
                        }
                    }
                    for i, hot_article in enumerate(hot_articles[:5])
                ]
            },
            {
                "@type": "ItemList",
                "@id": f"{request.base_url}authors/{author.id}#hot-tags",
                "name": "作者标签",
                "itemListElement": [
                    {
                        "@type": "DefinedTerm",
                        "name": author_tag,
                        "url": f"{request.base_url}tags/{author_tag}"
                    }
                    for author_tag in list(author_tags)[:5]
                ]
            },
            {
                "@type": "ItemList",
                "@id": f"{request.base_url}authors/{author.id}?page={page}&per_page={per_page}#articles",
                "name": f"{author.name} 的最新文章 第{page}页",
                "numberOfItems": len(articles),
                "itemListOrder": "Descending",
                "itemListElement": [
                    {
                        "@type": "Article",
                        "@id": f"{request.base_url}articles/{article.id}",
                        "url": f"{request.base_url}articles/{article.id}",
                        "headline": article.title,
                        "image": f"{request.base_url}{article.thumbnail_url}",
                        "description": article.subtitle,
                        "mainEntityOfPage": {"@type": "WebPage", "@id": f"{request.base_url}articles/{article.id}"},
                        "datePublished": article.published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                        "author": {"@type": "Person", "name": article.author.name}
                    }
                    for article in articles
                ],
                **(
                    {"previous": f"{request.base_url}authors/{author.id}?page={page-1}&per_page={per_page}"}
                    if page > 1 else {}
                ),
                **(
                    {"next": f"{request.base_url}authors/{author.id}?page={page+1}&per_page={per_page}"}
                    if page < total_pages else {}
                )
            }
        ]
    }


    return public_templates.TemplateResponse("author_detail.html", {
        "request": request,
        "site_name": site_name,
        "site_title": site_title,
        "site_description": site_description,
        "site_search": site_search,
        "site_distribute": site_distribute,
        "categories": categories,
        "author": author,
        "articles": articles,
        "hot_articles" : hot_articles,
        "author_tags": author_tags,
        "avg_week_published": avg_week_published,
        "curr_month_published": curr_month_published,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total_articles": total_articles,
        "json_ld": json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    })


# 栏目文章
@app.get("/categories/{category_id}", response_class=HTMLResponse)
async def categories_detail_page(
    request: Request, 
    category_id: int,
    order_by: int = 0,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(database.get_db)
):
    # 获取站点设置
    settings = db.query(models.Settings).all()
    settings_dict = {setting.key: setting.value for setting in settings}
    site_name = settings_dict.get("site_name","网站名称")
    site_title = settings_dict.get("site_title","网站标题")
    site_description = settings_dict.get("site_description","网站描述")
    site_search = settings_dict.get("site_search","热门搜索")
    site_distribute = settings_dict.get("site_distribute","分发网址")

    # 启用的栏目
    categories = db.query(models.Category).filter(models.Category.is_active == True).order_by(models.Category.id.asc()).all()

    # 当前栏目
    category = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="栏目不存在")
    
    # 计算分页
    total_articles = db.query(models.Article).filter(models.Article.category_id == category_id).count()
    total_pages = (total_articles + per_page - 1) // per_page
    offset = (page - 1) * per_page

    # 文章列表
    if order_by == 0:
        articles = db.query(models.Article).filter(models.Article.category_id == category_id).order_by(models.Article.id.desc()).offset(offset).limit(per_page).all()
    else:
        articles = db.query(models.Article).filter(models.Article.category_id == category_id).order_by(models.Article.pageviews.desc()).offset(offset).limit(per_page).all()
    
    # 科学上网栏目
    category_vpn = db.query(models.Category).filter(models.Category.name == "科学上网").first()

    # 热门推荐（科学上网的最新10篇文章）
    if category_vpn:
        hot_articles = db.query(models.Article).filter(models.Article.category_id == category_vpn.id).order_by(models.Article.id.desc()).limit(10).all()

    # 热门标签（所有模板标签，去除重复）
    hot_tags = set()
    for category_hot in categories:
        templates = db.query(models.ArticleTemplate).filter(
            models.ArticleTemplate.category_id == category_hot.id,
            models.ArticleTemplate.is_active == True
        ).order_by(models.ArticleTemplate.id.asc()).all()
        
        for template in templates:
            hot_tags.update(tag.strip() for tag in template.tags.split(","))

    # 计算每篇文章的相对时间
    for article in articles:
        article.read_time = calculate_relative_time(article.published_at)
    
    # 页面标题
    site_title = f"{category.name} - {site_name}"

    # 页面描述
    site_description = f"探索{category.name}相关的最新资讯、技术文章和行业动态，掌握最前沿的{category.name}发展趋势。"

    # 生成JSON-LD
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "首页", "item": str(request.base_url)},
                    {"@type": "ListItem", "position": 2, "name": category.name, "item": f"{request.base_url}categories/{category.id}"}
                ]
            },
            {
                "@type": "ItemList",
                "@id": f"{request.url}#hot-tags",
                "name": "热门标签",
                "itemListElement": [
                    {
                        "@type": "DefinedTerm",
                        "name": hot_tag,
                        "url": f"{request.base_url}tags/{hot_tag}"
                    }
                    for hot_tag in list(hot_tags)[:5]
                ]
            },
            {
                "@type": "ItemList",
                "@id": f"{request.url}#hot-articles",
                "name": "热门推荐",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i+1,
                        "item": {
                            "@type": "Article",
                            "headline": hot_article.title,
                            "url": f"{request.base_url}articles/{hot_article.id}"
                        }
                    }
                    for i, hot_article in enumerate(hot_articles[:5])
                ]
            },
            {
                "@type": "ItemList",
                "@id": f"{request.base_url}categories/{category_id}?order_by={order_by}&page={page}&per_page={per_page}#list",
                "name": f"{category.name} 栏目的文章 第{page}页",
                "numberOfItems": len(articles),
                "itemListOrder": "Descending",
                "itemListElement": [
                    {
                        "@type": "Article",
                        "@id": f"{request.base_url}articles/{article.id}",
                        "url": f"{request.base_url}articles/{article.id}",
                        "headline": article.title,
                        "image": f"{request.base_url}{article.thumbnail_url}",
                        "description": article.subtitle,
                        "mainEntityOfPage": {"@type": "WebPage", "@id": f"{request.base_url}articles/{article.id}"},
                        "datePublished": article.published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                        "author": {"@type": "Person", "name": article.author.name}
                    }
                    for article in articles
                ],
                **(
                    {"previous": f"{request.base_url}categories/{category_id}?order_by={order_by}&page={page-1}&per_page={per_page}"}
                    if page > 1 else {}
                ),
                **(
                    {"next": f"{request.base_url}categories/{category_id}?order_by={order_by}&page={page+1}&per_page={per_page}"}
                    if page < total_pages else {}
                )
            }
        ]
    }

    return public_templates.TemplateResponse("category.html", {
        "request": request,
        "site_name": site_name,
        "site_title": site_title,
        "site_description": site_description,
        "site_search": site_search,
        "site_distribute": site_distribute,
        "categories": categories,
        "category": category,
        "articles": articles,
        "hot_articles": hot_articles,
        "hot_tags": hot_tags,
        "order_by": order_by,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total_articles": total_articles,
        "json_ld": json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    })

# 社区作者
@app.get("/authors", response_class=HTMLResponse)
async def authors_detail_page(
    request: Request, 
    category_id: int = None,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(database.get_db)
):
    # 获取站点设置
    settings = db.query(models.Settings).all()
    settings_dict = {setting.key: setting.value for setting in settings}
    site_name = settings_dict.get("site_name","网站名称")
    site_title = settings_dict.get("site_title","网站标题")
    site_description = settings_dict.get("site_description","网站描述")
    site_search = settings_dict.get("site_search","热门搜索")
    site_distribute = settings_dict.get("site_distribute","分发网址")

    # 启用的栏目
    categories = db.query(models.Category).filter(models.Category.is_active == True).order_by(models.Category.id.asc()).all()

    # 选择的栏目
    category = None
    category_url = f"?"
    if category_id:
        category = db.query(models.Category).filter(models.Category.id == category_id).first()
        category_url = f"?category_id={category_id}&"
    
    # 计算分页
    if category_id:
        total_authors = db.query(models.Author).filter(models.Author.category_id == category_id).count()
    else:
        total_authors = db.query(models.Author).count()
    
    total_pages = (total_authors + per_page - 1) // per_page
    offset = (page - 1) * per_page

    # 作者列表
    if category:
        authors = db.query(models.Author).filter(models.Author.category_id == category_id).order_by(models.Author.id.asc()).offset(offset).limit(per_page).all()
    else:
        authors = db.query(models.Author).order_by(models.Author.id.asc()).offset(offset).limit(per_page).all()
    
    # 科学上网栏目
    category_vpn = db.query(models.Category).filter(models.Category.name == "科学上网").first()

    # 热门推荐（科学上网的最新10篇文章）
    if category_vpn:
        hot_articles = db.query(models.Article).filter(models.Article.category_id == category_vpn.id).order_by(models.Article.id.desc()).limit(10).all()
    else:
        hot_articles = None

    # 热门标签（所有模板标签，去除重复）
    hot_tags = set()
    for category_vpn in categories:
        templates = db.query(models.ArticleTemplate).filter(
            models.ArticleTemplate.category_id == category_vpn.id,
            models.ArticleTemplate.is_active == True
        ).order_by(models.ArticleTemplate.id.asc()).all()
        
        for template in templates:
            hot_tags.update(tag.strip() for tag in template.tags.split(","))
    
    # 页面标题
    site_title = f"社区作者 - {site_name}"

    # 页面描述
    site_description = f"查看{site_name}的社区作者，了解每位作者职业与简介，及其最新发表的文章。"

    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "首页", "item": str(request.base_url)},
                    {"@type": "ListItem", "position": 2, "name": "社区作者", "item": f"{request.base_url}authors"}
                ]
            },
            {
                "@type": "ItemList",
                "@id": f"{request.base_url}authors#categories",
                "name": "作者分类",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": "全部栏目",
                        "url": f"{request.base_url}authors"
                    },
                ] + [
                    {
                        "@type": "ListItem",
                        "position": i + 2,
                        "name": category.name,
                        "url": f"{request.base_url}authors?category_id={category.id}"
                    }
                    for i, category in enumerate(categories)
                ]
            },
            {
                "@type": "ItemList",
                "@id": f"{request.base_url}authors#hot-tags",
                "name": "热门标签",
                "itemListElement": [
                    {
                        "@type": "DefinedTerm",
                        "name": hot_tag,
                        "url": f"{request.base_url}authors/{hot_tag}"
                    }
                    for hot_tag in list(hot_tags)[:5]
                ]
            },
            {
                "@type": "ItemList",
                "@id": f"{request.base_url}authors{category_url}page={page}&per_page={per_page}#authors",
                "name": f"所有栏目作者 第{page}页" if not category else f"{category.name}栏目作者 第{page}页",
                "numberOfItems": len(authors),
                "itemListOrder": "Descending",
                "itemListElement": [
                    {
                        "@type": "Person",
                        "name": author.name,
                        "jobTitle": author.profession,
                        "url": f"{request.base_url}authors/{author.id}",
                        "image": f"{request.base_url}{author.avatar_url}",
                        "description": author.description
                    }
                    for author in authors
                ],
                **(
                    {"previous": f"{request.base_url}authors{category_url}page={page-1}&per_page={per_page}"}
                    if page > 1 else {}
                ),
                **(
                    {"next": f"{request.base_url}authors{category_url}page={page+1}&per_page={per_page}"}
                    if page < total_pages else {}
                )
            }
        ]
    }

    return public_templates.TemplateResponse("author.html", {
        "request": request,
        "site_name": site_name,
        "site_title": site_title,
        "site_description": site_description,
        "site_search": site_search,
        "site_distribute": site_distribute,
        "categories": categories,
        "category": category,
        "authors": authors,
        "hot_articles": hot_articles,
        "hot_tags": hot_tags,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total_authors": total_authors,
        "json_ld": json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    })

# 标签文章
@app.get("/tags/{tag}", response_class=HTMLResponse)
async def tags_page(
    request: Request, 
    tag: str,
    order_by: int = 0,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(database.get_db)
):
    # 获取站点设置
    settings = db.query(models.Settings).all()
    settings_dict = {setting.key: setting.value for setting in settings}
    site_name = settings_dict.get("site_name","网站名称")
    site_title = settings_dict.get("site_title","网站标题")
    site_description = settings_dict.get("site_description","网站描述")
    site_search = settings_dict.get("site_search","热门搜索")
    site_distribute = settings_dict.get("site_distribute","分发网址")

    # 启用的栏目
    categories = db.query(models.Category).filter(models.Category.is_active == True).order_by(models.Category.id.asc()).all()

    # 热门标签（所有模板标签，去除重复）
    hot_tags = set()

    # 栏目标签（栏目所有文章模板的标签，去除重复）
    for category in categories:
        templates = db.query(models.ArticleTemplate).filter(
            models.ArticleTemplate.category_id == category.id,
            models.ArticleTemplate.is_active == True
        ).order_by(models.ArticleTemplate.id.asc()).all()
        
        # 文章模板标签
        template_tags = set()
        for template in templates:
            template_tags.update(tag.strip() for tag in template.tags.split(","))
            hot_tags.update(tag.strip() for tag in template.tags.split(","))
        
        category.template_tags = template_tags

    # 查询条件
    if tag == "所有标签":
        filter = models.Article.tags.like(f"%,%")
    else:
        filter = models.Article.tags.like(f"%{tag}%")
    
    # 计算分页
    total_articles = db.query(models.Article).filter(filter).count()
    total_pages = (total_articles + per_page - 1) // per_page
    offset = (page - 1) * per_page

    # 文章列表
    if order_by == 0:
        articles = db.query(models.Article).filter(filter).order_by(models.Article.id.desc()).offset(offset).limit(per_page).all()
    else:
        articles = db.query(models.Article).filter(filter).order_by(models.Article.pageviews.desc()).offset(offset).limit(per_page).all()
    
    # 科学上网栏目
    category_vpn = db.query(models.Category).filter(models.Category.name == "科学上网").first()

    # 热门推荐（科学上网的最新10篇文章）
    if category_vpn:
        hot_articles = db.query(models.Article).filter(models.Article.category_id == category_vpn.id).order_by(models.Article.id.desc()).limit(10).all()

    # 计算每篇文章的相对时间
    for article in articles:
        article.read_time = calculate_relative_time(article.published_at)
    
    # 页面标题
    site_title = f"{tag}相关文章与教程 - {site_name}"

    # 页面描述
    site_description = f"收录{tag}相关的文章和教程，包括最新技术、实用工具与行业趋势，帮你全面了解{tag}。"

    # 生成JSON-LD
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "首页", "item": str(request.base_url)},
                    {"@type": "ListItem", "position": 2, "name": "所有标签", "item": f"{request.base_url}tags/所有标签"},
                    {"@type": "ListItem", "position": 3, "name": tag, "item": f"{request.base_url}tags/{tag}"}
                ]
            },
            {
                "@type": "ItemList",
                "@id": f"{request.base_url}tags/{tag}?order_by={order_by}&page={page}&per_page={per_page}#articles",
                "name": f"{tag} 标签的文章 第{page}页",
                "numberOfItems": len(articles),
                "itemListOrder": "Descending",
                "itemListElement": [
                    {
                        "@type": "Article",
                        "@id": f"{request.base_url}articles/{article.id}",
                        "url": f"{request.base_url}articles/{article.id}",
                        "headline": article.title,
                        "image": f"{request.base_url}{article.thumbnail_url}",
                        "description": article.subtitle,
                        "mainEntityOfPage": {"@type": "WebPage", "@id": f"{request.base_url}articles/{article.id}"},
                        "datePublished": article.published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                        "author": {"@type": "Person", "name": article.author.name}
                    }
                    for article in articles
                ],
                **(
                    {"previous": f"{request.base_url}tags/{tag}?order_by={order_by}&page={page-1}&per_page={per_page}"}
                    if page > 1 else {}
                ),
                **(
                    {"next": f"{request.base_url}tags/{tag}?order_by={order_by}&page={page+1}&per_page={per_page}"}
                    if page < total_pages else {}
                )
            },
            {
                "@type": "ItemList",
                "@id": f"{request.base_url}tags#hot-tags",
                "name": "热门标签",
                "itemListElement": [
                    {
                        "@type": "DefinedTerm",
                        "name": hot_tag,
                        "url": f"{request.base_url}tags/{hot_tag}"
                    }
                    for hot_tag in list(hot_tags)[:5]
                ]
            },
        ] + [
            {
                "@type": "ItemList",
                "@id": f"{request.base_url}tags#tags-{category.id}",
                "name": f"{category.name}栏目的标签",
                "itemListElement": [
                    {
                        "@type": "DefinedTerm",
                        "name": template_tag,
                        "url": f"{request.base_url}tags/{template_tag}"
                    }
                    for template_tag in list(category.template_tags)[:5]
                ]
            }
            for category in categories
        ]
    }

    return public_templates.TemplateResponse("tag.html", {
        "request": request,
        "site_name": site_name,
        "site_title": site_title,
        "site_description": site_description,
        "site_search": site_search,
        "site_distribute": site_distribute,
        "categories": categories,
        "tag": tag,
        "articles": articles,
        "hot_articles": hot_articles,
        "hot_tags": hot_tags,
        "order_by": order_by,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total_articles": total_articles,
        "json_ld": json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    })


# 搜索文章
@app.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request, 
    keyword: str = '',
    order_by: int = 0,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(database.get_db)
):
    # 获取站点设置
    settings = db.query(models.Settings).all()
    settings_dict = {setting.key: setting.value for setting in settings}
    site_name = settings_dict.get("site_name","网站名称")
    site_title = settings_dict.get("site_title","网站标题")
    site_description = settings_dict.get("site_description","网站描述")
    site_search = settings_dict.get("site_search","热门搜索")
    site_distribute = settings_dict.get("site_distribute","分发网址")

    # 启用的栏目
    categories = db.query(models.Category).filter(models.Category.is_active == True).order_by(models.Category.id.asc()).all()

    # 查询条件
    if keyword:
        filter = or_(
            models.Article.title.like(f"%{keyword}%") ,
            models.Article.subtitle.like(f"%{keyword}%"),
            models.Article.content.like(f"%{keyword}%")
        )
    else:
        filter = models.Article.id > 0
    
    # 计算分页
    total_articles = db.query(models.Article).filter(filter).count()
    total_pages = (total_articles + per_page - 1) // per_page
    offset = (page - 1) * per_page

    # 文章列表
    if order_by == 0:
        articles = db.query(models.Article).filter(filter).order_by(models.Article.id.desc()).offset(offset).limit(per_page).all()
    else:
        articles = db.query(models.Article).filter(filter).order_by(models.Article.pageviews.desc()).offset(offset).limit(per_page).all()
    
    # 科学上网栏目
    category_vpn = db.query(models.Category).filter(models.Category.name == "科学上网").first()

    # 热门推荐（科学上网的最新10篇文章）
    if category_vpn:
        hot_articles = db.query(models.Article).filter(models.Article.category_id == category_vpn.id).order_by(models.Article.id.desc()).limit(10).all()
    else:
        hot_articles = None
    
    # 热门标签（所有模板标签，去除重复）
    hot_tags = set()
    for category in categories:
        templates = db.query(models.ArticleTemplate).filter(
            models.ArticleTemplate.category_id == category.id,
            models.ArticleTemplate.is_active == True
        ).order_by(models.ArticleTemplate.id.asc()).all()
        
        for template in templates:
            hot_tags.update(tag.strip() for tag in template.tags.split(","))

    # 计算每篇文章的相对时间
    for article in articles:
        article.read_time = calculate_relative_time(article.published_at)
    
    if keyword:
        # 页面标题
        site_title = f"关于“{keyword}”的搜索结果 - {site_name}"

        # 页面描述
        site_description = f"搜索结果：关于“{keyword}”的相关文章、教程和资讯，让你快速找到相关内容。"
    else:
        # 页面标题
        site_title = f"搜索文章、教程和资讯 - {site_name}"

        # 页面描述
        site_description = f"搜索文章、教程和资讯，让你快速找到相关内容。"
    
    # 生成JSON-LD
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "首页", "item": str(request.base_url)},
                    {"@type": "ListItem", "position": 2, "name": "搜索", "item": f"{request.base_url}search"}
                ]
            },
            {
                "@type": "ItemList",
                "@id": f"{request.base_url}#hot-search",
                "name": "热门搜索",
                "itemListElement": [
                    {
                        "@type": "DefinedTerm",
                        "name": keyword,
                        "url": f"{request.base_url}search?keyword={keyword}"
                    }
                    for keyword in site_search.split(',')[:5]
                ]
            },
            {
                "@type": "ItemList",
                "@id": f"{request.base_url}search#hot-tags",
                "name": "热门标签",
                "itemListElement": [
                    {
                        "@type": "DefinedTerm",
                        "name": hot_tag,
                        "url": f"{request.base_url}tags/{hot_tag}"
                    }
                    for hot_tag in list(hot_tags)[:5]
                ]
            },
            {
                "@type": "ItemList",
                "@id": f"{request.base_url}search#hot-articles",
                "name": "热门推荐",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i+1,
                        "item": {
                            "@type": "Article",
                            "headline": hot_article.title,
                            "url": f"{request.base_url}articles/{hot_article.id}"
                        }
                    }
                    for i, hot_article in enumerate(hot_articles[:5])
                ]
            },
            {
                "@type": "SearchResultsPage",
                "name": f"搜索：{keyword}",
                "url": str(request.url),
                "inLanguage": "zh-CN",
                "isPartOf": {
                    "@id": f"{request.base_url}#website"
                },
                "mainEntity": {
                    "@type": "ItemList",
                    "name": f"搜索结果：{keyword}",
                    "itemListOrder": "Descending",
                    "numberOfItems": len(articles),
                    "itemListElement": [
                        {
                            "@type": "ListItem",
                            "position": offset + i + 1,
                            "item": {
                                "@type": "Article",
                                "@id": f"{request.base_url}articles/{article.id}",
                                "url": f"{request.base_url}articles/{article.id}",
                                "headline": article.title,
                                "datePublished": article.published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                                "author": {"@type": "Person", "name": article.author.name}
                            }
                        }
                        for i, article in enumerate(articles)
                    ]
                },
                **(
                    {"previous": f"{request.base_url}search?keyword={keyword}?page={page-1}&per_page={per_page}"}
                    if page > 1 else {}
                ),
                **(
                    {"next": f"{request.base_url}search?keyword={keyword}?page={page+1}&per_page={per_page}"}
                    if page < total_pages else {}
                )
            }
        ]
    }

    return public_templates.TemplateResponse("search.html", {
        "request": request,
        "site_name": site_name,
        "site_title": site_title,
        "site_description": site_description,
        "site_search": site_search,
        "site_distribute": site_distribute,
        "categories": categories,
        "keyword": keyword,
        "articles": articles,
        "hot_articles": hot_articles,
        "hot_tags": hot_tags,
        "order_by": order_by,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total_articles": total_articles,
        "json_ld": json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    })

@app.post('/subscribe')
async def subscribe_page(
    request: Request,
    db: Session = Depends(database.get_db)
):
    form_data = await request.form()
    email = form_data.get('email')
    browser_fingerprint = form_data.get('fingerprint')
    ip_address = request.client.host
    
    # 验证邮箱格式
    if not email or '@' not in email:
        logger.warning(f"{ip_address} 无效邮箱订阅尝试 {email}")
        return JSONResponse({'success': False, 'message': '请输入有效的邮箱地址'})
    
    # 检查重复订阅
    existing = db.query(models.Subscribe).filter(
        (models.Subscribe.email == email) | 
        (models.Subscribe.browser_fingerprint == browser_fingerprint)
    ).first()
    
    if existing:
        logger.info(f"{ip_address} 重复订阅 {email}")
        return JSONResponse({'success': True, 'message': '订阅成功！'})
    
    # 检查订阅频率
    recent_count = db.query(models.Subscribe).filter(
        models.Subscribe.ip_address == ip_address,
        models.Subscribe.created_at > datetime.now() - timedelta(hours=24)
    ).count()
    
    if recent_count >= 5:
        logger.warning(f"{ip_address} 订阅频率过高")
        return JSONResponse({'success': True, 'message': '订阅成功！'})
    
    # 保存订阅
    subscribe = models.Subscribe(
        email=email,
        browser_fingerprint=browser_fingerprint,
        ip_address=ip_address
    )
    
    db.add(subscribe)
    db.commit()
    logger.info(f"{ip_address} 订阅成功 {email}")
    
    return JSONResponse({'success': True, 'message': '订阅成功！'})

# 错误处理中间件
@app.exception_handler(404)
async def not_found_exception_handler(request: Request, exc: HTTPException):
    logger.warning(f"{request.client.host} 404错误 {request.url.path}")
    
    # 获取数据库连接以获取站点设置
    db = next(database.get_db())
    try:
        # 获取站点设置
        settings = db.query(models.Settings).all()
        settings_dict = {setting.key: setting.value for setting in settings}
        site_name = settings_dict.get("site_name","网站名称")
        site_title = settings_dict.get("site_title","网站标题")
        site_description = settings_dict.get("site_description","网站描述")
        site_search = settings_dict.get("site_search","热门搜索")
        site_distribute = settings_dict.get("site_distribute","分发网址")
        
        # 启用的栏目
        categories = db.query(models.Category).filter(models.Category.is_active == True).order_by(models.Category.id.asc()).all()

        # 科学上网栏目
        category_vpn = db.query(models.Category).filter(models.Category.name == "科学上网").first()

        # 热门推荐（科学上网的最新10篇文章）
        if category_vpn:
            hot_articles = db.query(models.Article).filter(models.Article.category_id == category_vpn.id).order_by(models.Article.id.desc()).limit(10).all()
        
        return public_templates.TemplateResponse("404.html", {
            "request": request,
            "site_name": site_name,
            "site_title": site_title,
            "site_description": site_description,
            "site_search": site_search,
            "site_distribute": site_distribute,
            "categories": categories,
            "hot_articles": hot_articles
        })
    except Exception as e:
        logger.error(f"{request.client.host} 404页面渲染错误 {str(e)}")
        # 如果渲染404.html失败，返回简单的404页面
        return HTMLResponse(
            content="<h1>404 - 页面未找到</h1><p>您访问的页面不存在。</p>",
            status_code=404
        )
    finally:
        db.close()

@app.exception_handler(500)
async def internal_exception_handler(request: Request, exc: HTTPException):
    logger.warning(f"{request.client.host} 500错误 {request.url.path} {str(exc)}")
    
    # 获取数据库连接以获取站点设置
    db = next(database.get_db())
    try:
        # 获取站点设置
        settings = db.query(models.Settings).all()
        settings_dict = {setting.key: setting.value for setting in settings}
        site_name = settings_dict.get("site_name","网站名称")
        site_title = settings_dict.get("site_title","网站标题")
        site_description = settings_dict.get("site_description","网站描述")
        site_search = settings_dict.get("site_search","热门搜索")
        site_distribute = settings_dict.get("site_distribute","分发网址")
        
        # 启用的栏目
        categories = db.query(models.Category).filter(models.Category.is_active == True).order_by(models.Category.id.asc()).all()

        # 科学上网栏目
        category_vpn = db.query(models.Category).filter(models.Category.name == "科学上网").first()

        # 热门推荐（科学上网的最新10篇文章）
        if category_vpn:
            hot_articles = db.query(models.Article).filter(models.Article.category_id == category_vpn.id).order_by(models.Article.id.desc()).limit(10).all()
        
        return public_templates.TemplateResponse("500.html", {
            "request": request,
            "site_name": site_name,
            "site_title": site_title,
            "site_description": site_description,
            "site_search": site_search,
            "site_distribute": site_distribute,
            "categories": categories,
            "exception": str(exc),
            "hot_articles": hot_articles
        })
    except Exception as e:
        logger.error(f"{request.client.host} 500页面渲染错误 {str(e)}")
        # 如果渲染500.html失败，返回简单的500页面
        return HTMLResponse(
            content="<h1>500 - 服务器内部错误</h1><p>服务器发生错误。</p>",
            status_code=500
        )
    finally:
        db.close()

# robots.txt
@app.get("/robots.txt", include_in_schema=False)
@app.head("/robots.txt", include_in_schema=False)
async def robots_page(request: Request):
    content = f"""# START SEO BLOCK
# ---------------------------
User-agent: *
Disallow:

Sitemap: {request.base_url}sitemap_index.xml
# ---------------------------
# END SEO BLOCK
"""

    return PlainTextResponse(content)

# Sitemap 索引
@app.get("/sitemap.xml", include_in_schema=False)
@app.head("/sitemap.xml", include_in_schema=False)
@app.get("/sitemap_index.xml", include_in_schema=False)
@app.head("/sitemap_index.xml", include_in_schema=False)
async def sitemap_index_page(
    request: Request, 
    db: Session = Depends(database.get_db)
):
    # 所有文章
    articles = db.query(models.Article).order_by(models.Article.id.desc()).all()

    # 栏目索引
    sitemap_items = f"""<sitemap>
        <loc>{request.base_url}category-sitemap.xml</loc>
        <lastmod>{articles[0].published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")}</lastmod>
    </sitemap>"""

    # 作者索引
    sitemap_items += f"""<sitemap>
        <loc>{request.base_url}author-sitemap.xml</loc>
        <lastmod>{articles[0].published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")}</lastmod>
    </sitemap>"""

    # 标签索引
    sitemap_items += f"""
    <sitemap>
        <loc>{request.base_url}tags-sitemap.xml</loc>
        <lastmod>{articles[0].published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")}</lastmod>
    </sitemap>"""

    # 搜索索引
    site_search_setting = db.query(models.Settings).filter(models.Settings.key == "site_search").first()
    if site_search_setting and site_search_setting.value:
        site_searchs = [keyword.strip() for keyword in site_search_setting.value.split(',') if keyword.strip()]
        
        if site_searchs:
            # 创建OR查询条件
            site_search_filter = or_(*[
                models.Article.tags.like(f"%{keyword}%") for keyword in site_searchs
            ])
            
            # 获取最新文章
            article = db.query(models.Article).filter(site_search_filter).order_by(models.Article.id.desc()).first()
            if article:
                sitemap_items += f"""
    <sitemap>
        <loc>{request.base_url}search-sitemap.xml</loc>
        <lastmod>{article.published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")}</lastmod>
    </sitemap>"""
    
    # 文章分组（按年月）
    grouped = defaultdict(list)
    for article in articles:
        year = article.published_at.year
        month = article.published_at.month
        key = (year, month)
        grouped[key].append(article)
    
    # 文章索引
    for (year, month), group in sorted(grouped.items(), key=lambda x: (x[0][0], x[0][1]), reverse=True):
        loc = f"{request.base_url}article-{year}-{month:02d}.xml"
        lastmod = max(article.published_at for article in group)
        sitemap_items += f"""
    <sitemap>
        <loc>{loc}</loc>
        <lastmod>{lastmod.strftime("%Y-%m-%dT%H:%M:%S+00:00")}</lastmod>
    </sitemap>"""

    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    {sitemap_items}
</sitemapindex>"""
    return Response(content=xml_content, media_type="application/xml")

# sitemap 栏目索引
@app.get("/category-sitemap.xml", include_in_schema=False)
@app.head("/category-sitemap.xml", include_in_schema=False)
async def sitemap_category_page(
    request: Request, 
    db: Session = Depends(database.get_db)
):
    # 首页
    article = db.query(models.Article).order_by(models.Article.id.desc()).first()
    url_items = f"""
    <url>
        <loc>{request.base_url}</loc>
        <lastmod>{article.published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")}</lastmod>
        <changefreq>daily</changefreq>
        <priority>1.0</priority>
    </url>"""

    # 启用的栏目
    categories = db.query(models.Category).filter(models.Category.is_active == True).order_by(models.Category.id.asc()).all()
    for category in categories:
        article = db.query(models.Article).filter(models.Article.category_id == category.id).order_by(models.Article.id.desc()).first()
        if not article:
            continue
        loc = f"{request.base_url}categories/{category.id}"
        # 转换为 ISO 8601 UTC 格式时间 (2022-03-26T16:19:01+00:00)
        lastmod = article.published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        url_items += f"""
    <url>
        <loc>{loc}</loc>
        <lastmod>{lastmod}</lastmod>
        <changefreq>daily</changefreq>
        <priority>0.6</priority>
    </url>"""
    
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9 http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd">{url_items}
</urlset>"""
    return Response(content=xml_content, media_type="application/xml")

# sitemap 作者索引
@app.get("/author-sitemap.xml", include_in_schema=False)
@app.head("/author-sitemap.xml", include_in_schema=False)
async def sitemap_author_page(
    request: Request, 
    db: Session = Depends(database.get_db)
):
    # 首页
    article = db.query(models.Article).order_by(models.Article.id.desc()).first()
    url_items = f"""
    <url>
        <loc>{request.base_url}</loc>
        <lastmod>{article.published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")}</lastmod>
        <changefreq>daily</changefreq>
        <priority>1.0</priority>
    </url>"""

    # 启用的作者
    authors = db.query(models.Author).filter(models.Author.is_active == True).order_by(models.Author.id.asc()).all()
    for author in authors:
        article = db.query(models.Article).filter(models.Article.author_id == author.id).order_by(models.Article.id.desc()).first()
        if not article:
            continue
        loc = f"{request.base_url}authors/{author.id}"
        # 转换为 ISO 8601 UTC 格式时间 (2022-03-26T16:19:01+00:00)
        lastmod = article.published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        url_items += f"""
    <url>
        <loc>{loc}</loc>
        <lastmod>{lastmod}</lastmod>
        <changefreq>daily</changefreq>
        <priority>0.6</priority>
    </url>"""
    
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9 http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd">{url_items}
</urlset>"""
    return Response(content=xml_content, media_type="application/xml")

# sitemap 标签索引
@app.get("/tags-sitemap.xml", include_in_schema=False)
@app.head("/tags-sitemap.xml", include_in_schema=False)
async def sitemap_tags_page(
    request: Request, 
    db: Session = Depends(database.get_db)
):
    # 首页
    article = db.query(models.Article).order_by(models.Article.id.desc()).first()
    url_items = f"""
    <url>
        <loc>{request.base_url}</loc>
        <lastmod>{article.published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")}</lastmod>
        <changefreq>daily</changefreq>
        <priority>1.0</priority>
    </url>"""

    # 所有标签
    url_items += f"""
    <url>
        <loc>{request.base_url}tags/所有标签</loc>
        <lastmod>{article.published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")}</lastmod>
        <changefreq>daily</changefreq>
        <priority>0.6</priority>
    </url>"""

    # 模板标签
    tags = set()

    # 文章模板
    templates = db.query(models.ArticleTemplate).filter(
        models.ArticleTemplate.is_active == True
    ).order_by(models.ArticleTemplate.id.asc()).all()
    for template in templates:
        tags.update(tag.strip() for tag in template.tags.split(","))

    for tag in tags:
        article = db.query(models.Article).filter(models.Article.tags.like(f"%{tag}%")).order_by(models.Article.id.desc()).first()
        loc = f"{request.base_url}tags/{tag}"
        # 转换为 ISO 8601 UTC 格式时间 (2022-03-26T16:19:01+00:00)
        lastmod = article.published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        url_items += f"""
    <url>
        <loc>{loc}</loc>
        <lastmod>{lastmod}</lastmod>
        <changefreq>daily</changefreq>
        <priority>0.6</priority>
    </url>"""
    
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9 http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd">{url_items}
</urlset>"""
    return Response(content=xml_content, media_type="application/xml")

# sitemap 搜索索引
@app.get("/search-sitemap.xml", include_in_schema=False)
@app.head("/search-sitemap.xml", include_in_schema=False)
async def sitemap_search_page(
    request: Request, 
    db: Session = Depends(database.get_db)
):
    # 首页
    article = db.query(models.Article).order_by(models.Article.id.desc()).first()
    url_items = f"""
    <url>
        <loc>{request.base_url}</loc>
        <lastmod>{article.published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")}</lastmod>
        <changefreq>daily</changefreq>
        <priority>1.0</priority>
    </url>"""

    # 搜索
    url_items += f"""
    <url>
        <loc>{request.base_url}search</loc>
        <lastmod>{article.published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")}</lastmod>
        <changefreq>daily</changefreq>
        <priority>0.6</priority>
    </url>"""
    
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9 http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd">{url_items}
</urlset>"""
    return Response(content=xml_content, media_type="application/xml")

# sitemap 文章索引
@app.get("/article-{year}-{month}.xml", include_in_schema=False)
@app.head("/article-{year}-{month}.xml", include_in_schema=False)
async def sitemap_article_page(
    request: Request,
    year: int,
    month: int,
    db: Session = Depends(database.get_db)
):
    # 查询指定年月的文章
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)
    
    articles = db.query(models.Article).filter(
        models.Article.published_at >= start_date,
        models.Article.published_at < end_date
    ).order_by(models.Article.id.desc()).all()
    
    # 首页
    url_items = f"""
    <url>
        <loc>{request.base_url}</loc>
        <lastmod>{articles[0].published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")}</lastmod>
        <changefreq>daily</changefreq>
        <priority>1.0</priority>
    </url>"""
    
    # 文章
    for article in articles:
        loc = f"{request.base_url}articles/{article.id}"
        # 转换为 ISO 8601 UTC 格式时间 (2022-03-26T16:19:01+00:00)
        lastmod = article.published_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        url_items += f"""
    <url>
        <loc>{loc}</loc>
        <lastmod>{lastmod}</lastmod>
        <image:image>
            <image:loc>{request.base_url}{article.thumbnail_url}</image:loc>
        </image:image>
        <changefreq>daily</changefreq>
        <priority>0.9</priority>
    </url>"""
    
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1" xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9 http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd http://www.google.com/schemas/sitemap-image/1.1 http://www.google.com/schemas/sitemap-image/1.1/sitemap-image.xsd">{url_items}
</urlset>"""
    return Response(content=xml_content, media_type="application/xml")