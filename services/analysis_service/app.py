import logging
import threading
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from analysis_service import AnalysisServicer
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Analysis Service", description="Service for analyzing compounds")
config = Config()

# Create database connection parameters
db_params = {
    "dbname": config.POSTGRES_DB,
    "user": config.POSTGRES_USER,
    "password": config.POSTGRES_PASSWORD,
    "host": config.POSTGRES_HOST,
    "port": config.POSTGRES_PORT
}

# Initialize the service
service = AnalysisServicer(
    db_params=db_params,
    mongo_uri=config.MONGO_URI,
    mongo_db_name=config.MONGO_DB_NAME,
    rabbitmq_params={
        "host": config.RABBITMQ_HOST,
        "port": config.RABBITMQ_PORT
    },
    queue_name=config.COMPOUND_QUEUE,
    config=config
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
class ActivityRequest(BaseModel):
    activity_value: float
    molecular_weight: float
    tpsa: float
    num_heavy_atoms: int
    num_polar_atoms: int

# Authentication dependency (placeholder - would be implemented with proper JWT validation)
async def get_current_user(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        return "test_user"  # Default for testing
    
    # In a real implementation, you would validate the JWT token
    return "test_user"  # Return user ID

# Start the RabbitMQ consumer in a separate thread
def start_consumer():
    try:
        service.start_consuming()
    except Exception as e:
        logger.error(f"Error in consumer thread: {e}")

consumer_thread = threading.Thread(target=start_consumer, daemon=True)
consumer_thread.start()

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "OK", "service": "Analysis Service"}

@app.get("/analysis/{job_id}")
async def get_analysis_job(job_id: str, current_user: str = Depends(get_current_user)):
    """Get the status and results of an analysis job."""
    try:
        job = service.get_job_status(job_id)
        if job:
            return job
        else:
            raise HTTPException(status_code=404, detail="Job not found")
    except Exception as e:
        logger.error(f"Error retrieving job {job_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# In analysis_service/app.py, update the get_analysis_results function:

@app.get("/analysis/{compound_id}/results")
async def get_analysis_results(compound_id: str, current_user: str = Depends(get_current_user)):
    """Get the analysis results for a compound."""
    try:
        # First try to find if this compound is a primary compound in a job
        job = None
        with service.postgres_conn.cursor() as cur:
            cur.execute(
                """
                SELECT j.id 
                FROM Analysis_Jobs j 
                WHERE j.compound_id = %s
                """,
                (compound_id,)
            )
            job = cur.fetchone()
        
        if job:
            # Found a job where this compound is primary
            job_id = job[0]
            results = service.get_analysis_results(job_id)
            if results:
                return results
        
        # If not found as primary compound, try to find it in any job
        with service.postgres_conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.job_id  
                FROM Compound_Job_Relations r
                WHERE r.compound_id = %s
                """,
                (compound_id,)
            )
            relation = cur.fetchone()
            
            if relation:
                job_id = relation[0]
                # Now get the analysis results by job_id
                service.connect_to_mongo()
                collection = service.mongo_db["analysis_results"]
                
                # Look for this compound in the primary_compound
                result = collection.find_one({
                    "job_id": job_id,
                    "$or": [
                        {"primary_compound.compound_id": compound_id},
                        {"similar_compounds.compound_id": compound_id}
                    ]
                })
                
                if result:
                    # Extract just the data for this compound
                    if result.get("primary_compound", {}).get("compound_id") == compound_id:
                        return result["primary_compound"]
                    else:
                        # Find in similar compounds
                        for comp in result.get("similar_compounds", []):
                            if comp.get("compound_id") == compound_id:
                                return comp
        
        # If we get here, no results were found
        logger.warning(f"No results found for compound {compound_id}")
        raise HTTPException(status_code=404, detail="No results found for this compound")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving results for compound {compound_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analysis/calculate-metrics")
async def calculate_metrics(request: ActivityRequest, current_user: str = Depends(get_current_user)):
    """Calculate efficiency metrics for the provided data."""
    try:
        metrics = service.calculate_efficiency_metrics(
            activity_value=request.activity_value,
            molecular_weight=request.molecular_weight,
            tpsa=request.tpsa,
            num_heavy_atoms=request.num_heavy_atoms,
            num_polar_atoms=request.num_polar_atoms
        )
        return metrics
    except Exception as e:
        logger.error(f"Error calculating metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analysis/{job_id}/process")
async def process_job(job_id: str, current_user: str = Depends(get_current_user)):
    """Manually trigger processing for a job."""
    try:
        # Get job details
        job = service.get_job_status(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Get compound details
        compound_id = job.get("compound_id")
        if not compound_id:
            raise HTTPException(status_code=400, detail="Job has no associated compound")
        
        # Process the job
        success = service.process_activities(job_id, compound_id)
        
        if success:
            return {"message": "Job processing initiated successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to process job")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing job {job_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Graceful shutdown
@app.on_event("shutdown")
def shutdown_event():
    service.close_connections()
    logger.info("Application shutdown. Closed all connections.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.SERVICE_PORT)