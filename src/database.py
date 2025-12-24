from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import settings

# 增加连接池配置
engine = create_engine(
    settings.DATABASE_URL, 
    connect_args={"check_same_thread": False},
    pool_size=20,           # 增加连接池大小
    max_overflow=30,        # 增加最大溢出连接数
    pool_pre_ping=True,     # 启用连接健康检查
    pool_recycle=3600       # 每小时回收连接
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()