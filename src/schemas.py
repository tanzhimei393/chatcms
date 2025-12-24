from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class CategoryBase(BaseModel):
    name: str
    icon: str
    color: str
    publish_count: int = 10

class CategoryCreate(CategoryBase):
    pass

class Category(CategoryBase):
    id: int
    is_active: bool
    article_count: int
    
    class Config:
        from_attributes = True

class AuthorBase(BaseModel):
    category_id: int
    avatar_url: str
    name: str
    profession: str
    description: str

class AuthorCreate(AuthorBase):
    pass

class Author(AuthorBase):
    id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class ArticleTemplateBase(BaseModel):
    category_id: int
    thumbnail_url: str
    title: str
    subtitle: str
    content: str
    tags: str

class ArticleTemplateCreate(ArticleTemplateBase):
    pass

class ArticleTemplate(ArticleTemplateBase):
    id: int
    is_active: bool
    
    class Config:
        from_attributes = True

class ArticleBase(BaseModel):
    category_id: int
    author_id: int
    template_id: int
    thumbnail_url: str
    title: str
    subtitle: str
    content: str
    tags: str

class ArticleCreate(ArticleBase):
    pass

class Article(ArticleBase):
    id: int
    pageviews : int
    published_at: datetime
    is_submit_google : bool
    is_submit_bing : bool
    
    class Config:
        from_attributes = True

class SubscribeBase(BaseModel):
    ip_address: str
    browser_fingerprint: str
    email: str

class SubscribeCreate(SubscribeBase):
    pass

class Subscribe(SubscribeBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True