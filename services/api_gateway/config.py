import os

class Config:
    # Database configuration
    POSTGRES_DB = os.environ.get('POSTGRES_DB', 'impulsor_db')
    POSTGRES_USER = os.environ.get('POSTGRES_USER', 'impulsor')
    POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', 'impulsor')
    POSTGRES_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
    POSTGRES_PORT = os.environ.get('POSTGRES_PORT', '5432')
    
    # JWT configuration
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'dev_secret_key')
    JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')
    JWT_EXPIRATION_TIME = int(os.environ.get('JWT_EXPIRATION_TIME', '24'))
    
    # RabbitMQ configuration
    RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST', 'localhost')
    RABBITMQ_PORT = int(os.environ.get('RABBITMQ_PORT', '5672'))
    
    # Service URLs
    COMPOUND_SERVICE_URL = os.environ.get('COMPOUND_SERVICE_URL', 'http://compound_service:8001')
    ANALYSIS_SERVICE_URL = os.environ.get('ANALYSIS_SERVICE_URL', 'http://analysis_service:8002')
    CHEMBL_SERVICE_URL = os.environ.get('CHEMBL_SERVICE_URL', 'http://chembl_service:8003')
    VISUALIZATION_SERVICE_URL = os.environ.get('VISUALIZATION_SERVICE_URL', 'http://visualization_service:8004')
    
    # API Gateway configuration
    API_GATEWAY_PORT = int(os.environ.get('API_GATEWAY_PORT', '8000'))
    DEBUG = os.environ.get('DEBUG', 'True') == 'True'