import os
import logging
import json
from flask import Flask, request, jsonify
from visualization_service import VisualizationService
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
service = VisualizationService(
    mongo_uri=Config.MONGO_URI,
    mongo_db_name=Config.MONGO_DB_NAME,
    plot_width=Config.PLOT_DEFAULT_WIDTH,
    plot_height=Config.PLOT_DEFAULT_HEIGHT
)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "OK", "service": "Visualization Service"}), 200

@app.route('/visualizations/<compound_id>/efficiency-plots', methods=['GET'])
def get_efficiency_plots(compound_id):
    """Get efficiency plots for a compound."""
    try:
        plots = service.generate_efficiency_plots(compound_id)
        if plots:
            return jsonify(plots), 200
        else:
            return jsonify({"message": "No plot data available"}), 404
    except Exception as e:
        logger.error(f"Error generating efficiency plots: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/visualizations/<compound_id>/scatter-plot', methods=['POST'])
def create_scatter_plot(compound_id):
    """Create a custom scatter plot."""
    try:
        data = service.get_visualization_data(compound_id)
        if not data:
            return jsonify({"message": "No data available for this compound"}), 404
            
        plot_params = request.get_json()
        if not plot_params:
            return jsonify({"error": "No plot parameters provided"}), 400
            
        x_field = plot_params.get('x_field')
        y_field = plot_params.get('y_field')
        color_field = plot_params.get('color_field')
        title = plot_params.get('title')
        
        if not x_field or not y_field:
            return jsonify({"error": "x_field and y_field are required"}), 400
        
        # Extract data for the plot
        plot_data = service.extract_plot_data(data, x_field, y_field, color_field)
        
        if plot_data:
            plot = service.generate_scatter_plot(
                data=plot_data,
                x_field=x_field,
                y_field=y_field,
                color_field=color_field,
                title=title
            )
            
            if plot:
                return jsonify(plot), 200
            else:
                return jsonify({"message": "Failed to generate plot"}), 500
        else:
            return jsonify({"message": "No valid data for plotting"}), 404
            
    except Exception as e:
        logger.error(f"Error creating scatter plot: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/visualizations/<compound_id>/activity-plot', methods=['GET'])
def get_activity_plot(compound_id):
    """Get activity distribution plot for a compound."""
    try:
        plot = service.generate_activity_plot(compound_id)
        if plot:
            return jsonify(plot), 200
        else:
            return jsonify({"message": "No activity data available"}), 404
    except Exception as e:
        logger.error(f"Error generating activity plot: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.teardown_appcontext
def shutdown_session(exception=None):
    """Close connections when the application shuts down."""
    service.close_connections()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=Config.SERVICE_PORT, debug=Config.DEBUG)