import logging
import requests
from flask import Flask, request, jsonify, g
import jwt
from api_gateway import register_user, login_user, update_user, validate_jwt_token, close_db_connection
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
config = Config()

# Endpoints that don't require authentication
PUBLIC_ENDPOINTS = [
    '/auth/register',
    '/auth/login',
    '/health'
]

@app.before_request
def authenticate():
    """Authenticate requests."""
    if request.path in PUBLIC_ENDPOINTS:
        return
        
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "Authorization header missing or invalid"}), 401
        
    token = auth_header.split(' ')[1]
    payload, status_code = validate_jwt_token(token)
    
    if status_code != 200:
        return jsonify(payload), status_code
        
    g.user = payload

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "OK", "service": "API Gateway"}), 200

# Authentication endpoints
@app.route('/auth/register', methods=['POST'])
def register():
    """Register a new user."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
        
    result, status_code = register_user(data)
    return jsonify(result), status_code

@app.route('/auth/login', methods=['POST'])
def login():
    """Login a user."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
        
    result, status_code = login_user(data)
    return jsonify(result), status_code

@app.route('/auth/user', methods=['PUT'])
def update_user_profile():
    """Update user profile."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
        
    user_id = g.user['user_id']
    result, status_code = update_user(user_id, data)
    return jsonify(result), status_code

# Compound Service Proxy
@app.route('/compounds', methods=['GET', 'POST'])
def compound_proxy():
    """Proxy for Compound Service."""
    url = f"{config.COMPOUND_SERVICE_URL}/compounds"
    
    if request.method == 'GET':
        response = requests.get(url, headers=filter_headers(request.headers))
    else:  # POST
        response = requests.post(url, json=request.get_json(), headers=filter_headers(request.headers))
        
    return jsonify(response.json()), response.status_code

@app.route('/compounds/<compound_id>', methods=['GET', 'PUT', 'DELETE'])
def compound_detail_proxy(compound_id):
    """Proxy for Compound Service detail endpoints."""
    url = f"{config.COMPOUND_SERVICE_URL}/compounds/{compound_id}"
    
    if request.method == 'GET':
        response = requests.get(url, headers=filter_headers(request.headers))
    elif request.method == 'PUT':
        response = requests.put(url, json=request.get_json(), headers=filter_headers(request.headers))
    else:  # DELETE
        response = requests.delete(url, headers=filter_headers(request.headers))
        
    return jsonify(response.json()), response.status_code

# Analysis Service Proxy
@app.route('/analysis/<job_id>', methods=['GET'])
def analysis_job_proxy(job_id):
    """Proxy for Analysis Service job status."""
    url = f"{config.ANALYSIS_SERVICE_URL}/analysis/{job_id}"
    response = requests.get(url, headers=filter_headers(request.headers))
    return jsonify(response.json()), response.status_code

@app.route('/analysis/<compound_id>/results', methods=['GET'])
def analysis_results_proxy(compound_id):
    """Proxy for Analysis Service results."""
    url = f"{config.ANALYSIS_SERVICE_URL}/analysis/{compound_id}/results"
    response = requests.get(url, headers=filter_headers(request.headers))
    return jsonify(response.json()), response.status_code

@app.route('/analysis/calculate-metrics', methods=['POST'])
def calculate_metrics_proxy():
    """Proxy for Analysis Service metrics calculation."""
    url = f"{config.ANALYSIS_SERVICE_URL}/analysis/calculate-metrics"
    response = requests.post(url, json=request.get_json(), headers=filter_headers(request.headers))
    return jsonify(response.json()), response.status_code

# ChEMBL Service Proxy
@app.route('/chembl/similarity/<smiles>', methods=['GET'])
def chembl_similarity_proxy(smiles):
    """Proxy for ChEMBL Service similarity search."""
    url = f"{config.CHEMBL_SERVICE_URL}/similarity/{smiles}"
    params = {k: v for k, v in request.args.items()}
    response = requests.get(url, params=params, headers=filter_headers(request.headers))
    return jsonify(response.json()), response.status_code

@app.route('/chembl/molecules/<chembl_id>', methods=['GET'])
def chembl_molecule_proxy(chembl_id):
    """Proxy for ChEMBL Service molecule data."""
    url = f"{config.CHEMBL_SERVICE_URL}/molecules/{chembl_id}"
    response = requests.get(url, headers=filter_headers(request.headers))
    return jsonify(response.json()), response.status_code

# Visualization Service Proxy
@app.route('/visualizations/<compound_id>/efficiency-plots', methods=['GET'])
def visualization_efficiency_plots_proxy(compound_id):
    """Proxy for Visualization Service efficiency plots."""
    url = f"{config.VISUALIZATION_SERVICE_URL}/visualizations/{compound_id}/efficiency-plots"
    response = requests.get(url, headers=filter_headers(request.headers))
    return jsonify(response.json()), response.status_code

@app.route('/visualizations/<compound_id>/scatter-plot', methods=['POST'])
def visualization_scatter_plot_proxy(compound_id):
    """Proxy for Visualization Service scatter plot."""
    url = f"{config.VISUALIZATION_SERVICE_URL}/visualizations/{compound_id}/scatter-plot"
    response = requests.post(url, json=request.get_json(), headers=filter_headers(request.headers))
    return jsonify(response.json()), response.status_code

def filter_headers(headers):
    """Filter headers to forward."""
    allowed_headers = ['Authorization', 'Content-Type']
    return {k: v for k, v in headers.items() if k in allowed_headers}

@app.teardown_appcontext
def close_connection(exception=None):
    """Close database connection when app context ends."""
    close_db_connection(None)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=config.API_GATEWAY_PORT, debug=config.DEBUG)