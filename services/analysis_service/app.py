import os
import logging
import json
import uuid
import threading
from flask import Flask, request, jsonify
from analysis_service import AnalysisServicer
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Create database connection parameters
db_params = {
    "dbname": Config.POSTGRES_DB,
    "user": Config.POSTGRES_USER,
    "password": Config.POSTGRES_PASSWORD,
    "host": Config.POSTGRES_HOST
}

# Initialize the service
service = AnalysisServicer(
    db_params=db_params,
    mongo_uri=Config.MONGO_URI,
    mongo_db_name=Config.MONGO_DB_NAME,
    rabbitmq_params={
        "host": Config.RABBITMQ_HOST,
        "port": Config.RABBITMQ_PORT
    },
    chembl_service_url=Config.CHEMBL_SERVICE_URL,
    queue_name=Config.COMPOUND_QUEUE,
    config=Config
)

# Start the RabbitMQ consumer in a separate thread
consumer_thread = threading.Thread(target=service.start_consuming)
consumer_thread.daemon = True  # Allow the thread to exit when the main thread exits
consumer_thread.start()

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "OK", "service": "Analysis Service"}), 200

@app.route('/analysis/<job_id>', methods=['GET'])
def get_analysis_job(job_id):
    """Get the status and results of an analysis job."""
    try:
        job = service.get_job_status(job_id)
        if job:
            return jsonify(job), 200
        else:
            return jsonify({"error": "Job not found"}), 404
    except Exception as e:
        logger.error(f"Error retrieving job {job_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/analysis/<compound_id>/results', methods=['GET'])
def get_analysis_results(compound_id):
    """Get the analysis results for a compound."""
    try:
        results = service.get_analysis_results(compound_id)
        if results:
            return jsonify(results), 200
        else:
            return jsonify({"message": "No results found for this compound"}), 404
    except Exception as e:
        logger.error(f"Error retrieving results for compound {compound_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/analysis/calculate-metrics', methods=['POST'])
def calculate_metrics():
    """Calculate efficiency metrics for the provided data."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    try:
        activities = data.get('activities', [])
        molecular_weight = data.get('molecular_weight')
        tpsa = data.get('tpsa')
        
        metrics = service.calculate_efficiency_metrics(activities, molecular_weight, tpsa)
        return jsonify(metrics), 200
    except Exception as e:
        logger.error(f"Error calculating metrics: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.teardown_appcontext
def shutdown_session(exception=None):
    """Clean up resources when the application shuts down."""
    service.close_connections()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=Config.SERVICE_PORT, debug=Config.DEBUG)