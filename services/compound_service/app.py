import os
import logging
import json
import uuid
from flask import Flask, request, jsonify, g
from compound_service import CompoundService
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
service = CompoundService()
config = Config()

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "OK", "service": "Compound Service"}), 200

@app.route('/compounds', methods=['POST'])
def create_compound():
    """Create a new compound."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    # Generate UUID for the compound if not provided
    if 'id' not in data:
        data['id'] = str(uuid.uuid4())
    
    # Set default user_id if not provided (for testing)
    if 'user_id' not in data:
        data['user_id'] = 'test_user'
    
    success, result = service.create_compound(data)
    if success:
        return jsonify({"id": result}), 201
    else:
        return jsonify({"error": result}), 400

@app.route('/compounds/<compound_id>', methods=['GET'])
def get_compound(compound_id):
    """Get a compound by ID."""
    compound, error = service.read_compound(compound_id)
    if compound:
        return jsonify(compound), 200
    else:
        return jsonify({"error": error}), 404

@app.route('/compounds/<compound_id>', methods=['PUT'])
def update_compound(compound_id):
    """Update a compound."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    success, error = service.update_compound(compound_id, data)
    if success:
        return jsonify({"message": "Compound updated successfully"}), 200
    else:
        return jsonify({"error": error}), 400

@app.route('/compounds/<compound_id>', methods=['DELETE'])
def delete_compound(compound_id):
    """Delete a compound."""
    success, error = service.delete_compound(compound_id)
    if success:
        return jsonify({"message": "Compound deleted successfully"}), 200
    else:
        return jsonify({"error": error}), 400

@app.route('/compounds', methods=['GET'])
def list_compounds():
    """List all compounds."""
    compounds, error = service.list_compounds()
    if compounds is not None:
        return jsonify(compounds), 200
    else:
        return jsonify({"error": error}), 400

@app.teardown_appcontext
def shutdown_session(exception=None):
    """Close resources when the application shuts down."""
    if hasattr(service, 'db_conn') and service.db_conn:
        service._disconnect_db()
    if hasattr(service, 'mq_connection') and service.mq_connection:
        service._disconnect_rabbitmq()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=config.service_port, debug=config.debug)