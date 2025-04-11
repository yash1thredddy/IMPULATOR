import logging
from flask import Flask, request, jsonify
from chembl_service import ChEMBLService
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
service = ChEMBLService()
config = Config()

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "OK", "service": "ChEMBL Service"}), 200

@app.route('/similarity/<smiles>', methods=['GET'])
def get_similarity(smiles):
    """Get similar molecules based on SMILES."""
    try:
        similarity = request.args.get('similarity', 90, type=int)
        results = service.get_similarity(smiles, similarity)
        if results:
            return jsonify(results), 200
        else:
            return jsonify({"message": "No similar molecules found"}), 404
    except Exception as e:
        logger.error(f"Error in similarity search: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/molecules/<chembl_id>', methods=['GET'])
def get_molecule(chembl_id):
    """Get molecule data by ChEMBL ID."""
    try:
        molecule = service.get_molecule_data(chembl_id)
        if molecule:
            return jsonify(molecule), 200
        else:
            return jsonify({"error": "Molecule not found"}), 404
    except Exception as e:
        logger.error(f"Error retrieving molecule: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/search', methods=['POST'])
def search():
    """Search for molecules with the specified parameters."""
    try:
        params = request.get_json()
        resource = params.get('resource', 'molecule')
        lookup_param = params.get('lookup_param')
        lookup_value = params.get('lookup_value')
        
        if not lookup_param or not lookup_value:
            return jsonify({"error": "Missing lookup parameter or value"}), 400
        
        results = service.make_chembl_request(resource, lookup_param, lookup_value)
        if results:
            return jsonify(results), 200
        else:
            return jsonify({"message": "No results found"}), 404
    except Exception as e:
        logger.error(f"Error in search: {e}")
        return jsonify({"error": str(e)}), 500

@app.teardown_appcontext
def shutdown_session(exception=None):
    """Clean up resources when the application shuts down."""
    if hasattr(service, 'redis_client'):
        try:
            service.redis_client.close()
            logger.info("Redis connection closed")
        except:
            pass

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=config.SERVICE_PORT, debug=config.DEBUG)