from sqlalchemy.orm import Session
from . import models, schemas

# Category CRUD operations
def get_categories(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Category).offset(skip).limit(limit).all()

def get_categories_count(db: Session):
    return db.query(models.Category).count()

def create_category(db: Session, category: schemas.CategoryCreate):
    db_category = models.Category(**category.model_dump())
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category

def update_category(db: Session, category_id: int, category: schemas.CategoryCreate):
    db_category = db.query(models.Category).filter(models.Category.id == category_id).first()
    if db_category:
        for key, value in category.model_dump().items():
            setattr(db_category, key, value)
        db.commit()
        db.refresh(db_category)
    return db_category

def delete_category(db: Session, category_id: int):
    db_category = db.query(models.Category).filter(models.Category.id == category_id).first()
    if db_category:
        db.delete(db_category)
        db.commit()
    return db_category

# Author CRUD operations
def get_authors(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Author).offset(skip).limit(limit).all()

def get_authors_count(db: Session):
    return db.query(models.Author).count()

def create_author(db: Session, author: schemas.AuthorCreate):
    db_author = models.Author(**author.model_dump())
    db.add(db_author)
    db.commit()
    db.refresh(db_author)
    return db_author

def update_author(db: Session, author_id: int, author: schemas.AuthorCreate):
    db_author = db.query(models.Author).filter(models.Author.id == author_id).first()
    if db_author:
        for key, value in author.model_dump().items():
            setattr(db_author, key, value)
        db.commit()
        db.refresh(db_author)
    return db_author

def delete_author(db: Session, author_id: int):
    db_author = db.query(models.Author).filter(models.Author.id == author_id).first()
    if db_author:
        db.delete(db_author)
        db.commit()
    return db_author

# ArticleTemplate CRUD operations
def get_templates(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.ArticleTemplate).offset(skip).limit(limit).all()

def get_templates_count(db: Session):
    return db.query(models.ArticleTemplate).count()

def create_template(db: Session, template: schemas.ArticleTemplateCreate):
    db_template = models.ArticleTemplate(**template.model_dump())
    db.add(db_template)
    db.commit()
    db.refresh(db_template)
    return db_template

def update_template(db: Session, template_id: int, template: schemas.ArticleTemplateCreate):
    db_template = db.query(models.ArticleTemplate).filter(models.ArticleTemplate.id == template_id).first()
    if db_template:
        for key, value in template.model_dump().items():
            setattr(db_template, key, value)
        db.commit()
        db.refresh(db_template)
    return db_template

def delete_template(db: Session, template_id: int):
    db_template = db.query(models.ArticleTemplate).filter(models.ArticleTemplate.id == template_id).first()
    if db_template:
        db.delete(db_template)
        db.commit()
    return db_template

# Article CRUD operations
def get_articles(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Article).offset(skip).limit(limit).all()

def get_articles_count(db: Session):
    return db.query(models.Article).count()

def create_article(db: Session, article: schemas.ArticleCreate):
    db_article = models.Article(**article.model_dump())
    db.add(db_article)
    db.commit()
    db.refresh(db_article)
    return db_article

def delete_article(db: Session, article_id: int):
    db_article = db.query(models.Article).filter(models.Article.id == article_id).first()
    if db_article:
        db.delete(db_article)
        db.commit()
    return db_article

# Subscribe CRUD operations
def get_subscribes(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Subscribe).offset(skip).limit(limit).all()

def get_subscribes_count(db: Session):
    return db.query(models.Subscribe).count()

def create_subscribe(db: Session, subscribe: schemas.SubscribeCreate):
    db_subscribe = models.Subscribe(**subscribe.model_dump())
    db.add(db_subscribe)
    db.commit()
    db.refresh(db_subscribe)
    return db_subscribe

def delete_subscribe(db: Session, subscribe_id: int):
    db_subscribe = db.query(models.Subscribe).filter(models.Subscribe.id == subscribe_id).first()
    if db_subscribe:
        db.delete(db_subscribe)
        db.commit()
    return db_subscribe