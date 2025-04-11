import os

class Config:
    # Database configuration
    db_name = os.environ.get('POSTGRES_DB', 'impulsor_db')
    db_user = os.environ.get('POSTGRES_USER', 'impulsor')
    db_password = os.environ.get('POSTGRES_PASSWORD', 'impulsor')
    db_host = os.environ.get('POSTGRES_HOST', 'localhost')
    db_port = os.environ.get('POSTGRES_PORT', '5432')
    
    # RabbitMQ configuration
    rabbitmq_host = os.environ.get('RABBITMQ_HOST', 'localhost')
    rabbitmq_port = int(os.environ.get('RABBITMQ_PORT', '5672'))
    compounds_queue_name = 'compound-processing-queue'
    
    # Service configuration
    service_port = int(os.environ.get('COMPOUND_SERVICE_PORT', '8001'))
    debug = os.environ.get('DEBUG', 'True') == 'True'