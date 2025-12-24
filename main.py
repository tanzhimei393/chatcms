import os
import uvicorn

# 确保日志目录存在
os.makedirs("./logs", exist_ok=True)

# 自定义日志配置
LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        },
        "access": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        }
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "./logs/app.log",
            "maxBytes": 1024 * 1024 * 10,
            "backupCount": 1,
            "encoding": "utf-8"
        },
        "access": {
            "formatter": "access",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "./logs/access.log",
            "maxBytes": 1024 * 1024 * 10,
            "backupCount": 1,
            "encoding": "utf-8"
        }
    },
    "loggers": {
        "uvicorn": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": False
        },
        "uvicorn.error": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": False
        },
        "uvicorn.access": {
            "handlers": ["access"],
            "level": "INFO",
            "propagate": False
        }
    }
}

if __name__ == "__main__":
    uvicorn.run("src.controller:app", host="0.0.0.0", port=8000, reload=True)