import os

class Config:
    # Redis configuration
    REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.environ.get('REDIS_PORT', '6379'))
    REDIS_DB = int(os.environ.get('REDIS_DB', '0'))
    
    # Service configuration
    SERVICE_PORT = int(os.environ.get('CHEMBL_SERVICE_PORT', '8003'))
    CACHE_EXPIRY = int(os.environ.get('CACHE_EXPIRY', '3600'))  # 1 hour
    DEBUG = os.environ.get('DEBUG', 'True') == 'True'