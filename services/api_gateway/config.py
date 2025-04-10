# API Gateway configuration

import os

class Config:
    DEBUG = False
    TESTING = False
    API_VERSION = os.getenv("API_VERSION", "v1")
    PORT = int(os.getenv("PORT", 8000))
    HOST = os.getenv("HOST", "0.0.0.0")

class DevelopmentConfig(Config):
    DEBUG = True

class TestingConfig(Config):
    TESTING = True

class ProductionConfig(Config):
    pass

config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}

current_config = os.getenv("FLASK_ENV", "development")
app_config = config.get(current_config, DevelopmentConfig)