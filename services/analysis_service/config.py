import os

class Config:
    # Database configuration
    POSTGRES_DB = os.environ.get('POSTGRES_DB', 'impulsor_db')
    POSTGRES_USER = os.environ.get('POSTGRES_USER', 'impulsor')
    POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', 'impulsor')
    POSTGRES_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
    POSTGRES_PORT = os.environ.get('POSTGRES_PORT', '5432')
    
    # MongoDB configuration
    MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
    MONGO_DB_NAME = os.environ.get('MONGO_DB_NAME', 'impulsor_db')
    
    # RabbitMQ configuration
    RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST', 'localhost')
    RABBITMQ_PORT = int(os.environ.get('RABBITMQ_PORT', '5672'))
    COMPOUND_QUEUE = 'compound-processing-queue'
    VISUALIZATION_QUEUE = 'visualization-queue'
    
    # ChEMBL Service gRPC configuration
    CHEMBL_SERVICE_GRPC_HOST = os.environ.get('CHEMBL_SERVICE_GRPC_HOST', 'localhost')
    CHEMBL_SERVICE_GRPC_PORT = int(os.environ.get('CHEMBL_SERVICE_GRPC_PORT', '50051'))
    
    # Service configuration
    SERVICE_PORT = int(os.environ.get('ANALYSIS_SERVICE_PORT', '8002'))
    MAX_WORKERS = int(os.environ.get('MAX_WORKERS', '4'))
    DEBUG = os.environ.get('DEBUG', 'True') == 'True'
    
    # Activity types to process
    ACTIVITY_TYPES = ['IC50', 'EC50', 'Ki', 'Kd', 'AC50', 'GI50', 'MIC']