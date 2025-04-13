import logging
import json
import pika
import threading
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from visualization_service import VisualizationService
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Visualization Service", description="Service for generating visualizations")
config = Config()

# Initialize the service
service = VisualizationService(
    mongo_uri=config.MONGO_URI,
    mongo_db_name=config.MONGO_DB_NAME,
    plot_width=config.PLOT_DEFAULT_WIDTH,
    plot_height=config.PLOT_DEFAULT_HEIGHT
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class PlotRequest(BaseModel):
    x_field: str
    y_field: str
    color_field: Optional[str] = None
    title: Optional[str] = None

# Authentication dependency (placeholder - would be implemented with proper JWT validation)
async def get_current_user(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        return "test_user"  # Default for testing
    
    # In a real implementation, you would validate the JWT token
    return "test_user"  # Return user ID

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "OK", "service": "Visualization Service"}

@app.get("/visualizations/{compound_id}/efficiency-plots")
async def get_efficiency_plots(compound_id: str, current_user: str = Depends(get_current_user)):
    """Get efficiency plots for a compound."""
    try:
        plots = service.generate_efficiency_plots(compound_id)
        if plots:
            return plots
        else:
            raise HTTPException(status_code=404, detail="No plot data available")
    except Exception as e:
        logger.error(f"Error generating efficiency plots: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/visualizations/{compound_id}/activity-plot")
async def get_activity_plot(compound_id: str, current_user: str = Depends(get_current_user)):
    """Get activity distribution plot for a compound."""
    try:
        plot = service.generate_activity_plot(compound_id)
        if plot:
            return plot
        else:
            raise HTTPException(status_code=404, detail="No activity data available")
    except Exception as e:
        logger.error(f"Error generating activity plot: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/visualizations/{compound_id}/scatter-plot")
async def create_scatter_plot(compound_id: str, plot_request: PlotRequest, current_user: str = Depends(get_current_user)):
    """Create a custom scatter plot."""
    try:
        plot = service.generate_custom_plot(
            compound_id=compound_id,
            x_field=plot_request.x_field,
            y_field=plot_request.y_field,
            color_field=plot_request.color_field,
            title=plot_request.title
        )
        
        if plot:
            return plot
        else:
            raise HTTPException(status_code=404, detail="No valid data for plotting")
    except Exception as e:
        logger.error(f"Error creating scatter plot: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def start_visualization_queue_consumer():
    """
    Start a consumer for the visualization queue to process visualization requests.
    In a real implementation, this would handle more complex visualization tasks.
    """
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=config.RABBITMQ_HOST)
        )
        channel = connection.channel()
        
        queue_name = config.VISUALIZATION_QUEUE
        channel.queue_declare(queue=queue_name, durable=True)
                
        def callback(ch, method, properties, body):
            try:
                message = json.loads(body)
                logger.info(f"Processing visualization message: {message}")
                
                # Get compound ID and job ID from message
                compound_id = message.get("compound_id")
                job_id = message.get("job_id")  # Make sure to use job_id from the message
                
                if not compound_id or not job_id:
                    logger.error("Invalid message: missing compound_id or job_id")
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                    return
                
                # Generate and cache visualizations - use job_id instead of compound_id for data retrieval
                service.generate_efficiency_plots(job_id, compound_id)  # Pass both job_id and compound_id
                service.generate_activity_plot(job_id, compound_id)     # Pass both job_id and compound_id
                
                # Acknowledge message
                ch.basic_ack(delivery_tag=method.delivery_tag)
                logger.info(f"Successfully processed visualization for compound {compound_id}")
                
            except Exception as e:
                logger.error(f"Error processing visualization message: {str(e)}")
                ch.basic_ack(delivery_tag=method.delivery_tag)
        
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue=queue_name, on_message_callback=callback)
        
        logger.info(f"Starting visualization queue consumer on {queue_name}")
        channel.start_consuming()
        
    except Exception as e:
        logger.error(f"Error starting visualization queue consumer: {str(e)}")

# Start the queue consumer in a separate thread
consumer_thread = threading.Thread(target=start_visualization_queue_consumer, daemon=True)
consumer_thread.start()

# Graceful shutdown
@app.on_event("shutdown")
def shutdown_event():
    service.close_connections()
    logger.info("Application shutdown. Closed all connections.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.SERVICE_PORT)