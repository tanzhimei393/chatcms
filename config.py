class Settings:
    # 从环境变量获取配置，如果不存在则使用默认值
    PASSWORD = "123456"
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_TIME = 15
    DATABASE_URL = "sqlite:///./data/cms.db"
    DEEPSEEK_API_KEY = ""
    DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
    SITE_URL = "https://127.0.0.1"
    BING_API_KEY = ""

settings = Settings()