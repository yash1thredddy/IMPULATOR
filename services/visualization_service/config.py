import os

class Config:
    # MongoDB configuration
    MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
    MONGO_DB_NAME = os.environ.get('MONGO_DB_NAME', 'impulsor_db')
    
    # RabbitMQ configuration
    RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST', 'localhost')
    RABBITMQ_PORT = int(os.environ.get('RABBITMQ_PORT', '5672'))
    VISUALIZATION_QUEUE = 'visualization-queue'
    
    # Service configuration
    SERVICE_PORT = int(os.environ.get('VISUALIZATION_SERVICE_PORT', '8004'))
    PLOT_DEFAULT_WIDTH = int(os.environ.get('PLOT_DEFAULT_WIDTH', '900'))
    PLOT_DEFAULT_HEIGHT = int(os.environ.get('PLOT_DEFAULT_HEIGHT', '600'))
    DEBUG = os.environ.get('DEBUG', 'True') == 'True'