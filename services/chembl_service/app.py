import logging
import threading
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import List, Optional
from pydantic import BaseModel

from config import Config
from chembl_service import ChEMBLService
import grpc_server

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="ChEMBL Service", description="Service for interacting with ChEMBL API")
config = Config()
service = ChEMBLService()

# Pydantic models for request/response
class SimilarityRequest(BaseModel):
    smiles: str
    similarity_threshold: int = 80

class MoleculeRequest(BaseModel):
    chembl_id: str

class ActivityRequest(BaseModel):
    chembl_id: str
    activity_types: List[str]

class ClassificationRequest(BaseModel):
    inchi_key: str

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "OK", "service": "ChEMBL Service"}

@app.get("/similarity/{smiles}")
def get_similarity(smiles: str, similarity: int = Query(80, ge=0, le=100)):
    """Get similar molecules based on SMILES."""
    try:
        results = service.get_similarity(smiles, similarity)
        if results:
            return results
        else:
            return {"message": "No similar molecules found"}, 404
    except Exception as e:
        logger.error(f"Error in similarity search: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error in similarity search: {str(e)}")

@app.get("/molecules/{chembl_id}")
def get_molecule(chembl_id: str):
    """Get molecule data by ChEMBL ID."""
    try:
        molecule = service.get_molecule_data(chembl_id)
        if molecule:
            return molecule
        else:
            raise HTTPException(status_code=404, detail="Molecule not found")
    except Exception as e:
        logger.error(f"Error retrieving molecule: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving molecule: {str(e)}")

@app.post("/search")
def search(search_params: dict):
    """Search for molecules with the specified parameters."""
    try:
        resource = search_params.get('resource', 'molecule')
        lookup_param = search_params.get('lookup_param')
        lookup_value = search_params.get('lookup_value')
        
        if not lookup_param or not lookup_value:
            raise HTTPException(status_code=400, detail="Missing lookup parameter or value")
        
        results = service.make_chembl_request(resource, lookup_param, lookup_value)
        if results:
            return results
        else:
            return JSONResponse(status_code=404, content={"message": "No results found"})
    except Exception as e:
        logger.error(f"Error in search: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error in search: {str(e)}")

@app.post("/activities")
def get_activities(request: ActivityRequest):
    """Get activities for a compound."""
    try:
        activities = service.get_activities(request.chembl_id, request.activity_types)
        return activities
    except Exception as e:
        logger.error(f"Error retrieving activities: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving activities: {str(e)}")

@app.post("/classification")
def get_classification(request: ClassificationRequest):
    """Get classification data for a compound."""
    try:
        classification = service.get_classification(request.inchi_key)
        return classification
    except Exception as e:
        logger.error(f"Error retrieving classification: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving classification: {str(e)}")

def start_grpc_server():
    """Start the gRPC server in a separate thread."""
    grpc_server.serve()

if __name__ == "__main__":
    # Start gRPC server in a separate thread
    grpc_thread = threading.Thread(target=start_grpc_server, daemon=True)
    grpc_thread.start()
    
    # Start FastAPI server
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.SERVICE_PORT)