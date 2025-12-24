from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    key = Column(String, unique=True, index=True)
    value = Column(Text)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    name = Column(String, unique=True, index=True)
    icon = Column(String)
    color = Column(String)
    is_active = Column(Boolean, default=True)
    publish_count = Column(Integer, default=10)
    article_count = Column(Integer, default=0)

    templates = relationship("ArticleTemplate", back_populates="category")
    authors = relationship("Author", back_populates="category")
    articles = relationship("Article", back_populates="category")

class Author(Base):
    __tablename__ = "authors"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"))
    avatar_url = Column(String)
    name = Column(String, index=True)
    profession = Column(String)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

    category = relationship("Category", back_populates="authors")
    articles = relationship("Article", back_populates="author")

    @property
    def total_pageviews(self):
        """计算该作者所有文章的总阅读量"""
        if self.articles:
            return sum(article.pageviews for article in self.articles)
        return 0

class ArticleTemplate(Base):
    __tablename__ = "article_templates"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"))
    thumbnail_url = Column(String)
    title = Column(String)
    subtitle = Column(String)
    content = Column(Text)
    tags = Column(String)
    is_active = Column(Boolean, default=True)

    category = relationship("Category", back_populates="templates")
    articles = relationship("Article", back_populates="template")

class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"))
    author_id = Column(Integer, ForeignKey("authors.id"))
    template_id = Column(Integer, ForeignKey("article_templates.id"))
    thumbnail_url = Column(String)
    title = Column(String)
    subtitle = Column(String)
    content = Column(Text)
    tags = Column(String)
    pageviews = Column(Integer, default=0)
    published_at = Column(DateTime, default=datetime.now)
    is_submit_google = Column(Boolean, default=False)
    is_submit_bing = Column(Boolean, default=False)

    category = relationship("Category", back_populates="articles")
    author = relationship("Author", back_populates="articles")
    template = relationship("ArticleTemplate", back_populates="articles")

class Image(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    network_url = Column(String, unique=True, index=True)
    static_url = Column(String)

class Subscribe(Base):
    __tablename__ = "subscribe"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    ip_address = Column(String, index=True)
    browser_fingerprint = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.now)