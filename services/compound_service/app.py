import os
import logging
import json
import uuid
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from compound_service import CompoundService
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Compound Service", description="Service for managing compounds")
config = Config()
service = CompoundService()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class CompoundCreate(BaseModel):
    name: str
    smiles: str
    user_id: str
    similarity_threshold: Optional[int] = 80

class CompoundUpdate(BaseModel):
    name: Optional[str] = None
    smiles: Optional[str] = None
    status: Optional[str] = None

class CompoundResponse(BaseModel):
    id: str
    name: str
    smiles: str
    user_id: str
    status: str
    molecular_weight: Optional[float] = None
    tpsa: Optional[float] = None
    analysis_job_id: Optional[str] = None
    created_at: str
    updated_at: str

# Authentication dependency (placeholder - would be implemented with proper JWT validation)
async def get_current_user(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        return "test_user"  # Default for testing
    
    # In a real implementation, you would validate the JWT token
    return "test_user"  # Return user ID

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "OK", "service": "Compound Service"}

@app.post("/compounds", response_model=dict)
async def create_compound(compound: CompoundCreate, current_user: str = Depends(get_current_user)):
    """Create a new compound."""
    try:
        # Convert Pydantic model to dict
        compound_data = compound.model_dump()
        
        # Use the authenticated user if not specified
        if not compound_data.get("user_id"):
            compound_data["user_id"] = current_user
        
        success, result = service.create_compound(compound_data)
        if success:
            return {"id": result}
        else:
            logger.error(f"Failed to create compound: {result}")
            raise HTTPException(status_code=400, detail=result)
    except Exception as e:
        logger.error(f"Error creating compound: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/compounds/{compound_id}", response_model=dict)
async def get_compound(compound_id: str, current_user: str = Depends(get_current_user)):
    """Get a compound by ID."""
    try:
        compound, error = service.read_compound(compound_id)
        if compound:
            return compound
        else:
            logger.error(f"Failed to get compound: {error}")
            raise HTTPException(status_code=404, detail=error)
    except Exception as e:
        logger.error(f"Error getting compound: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/compounds/{compound_id}", response_model=dict)
async def update_compound(compound_id: str, compound: CompoundUpdate, current_user: str = Depends(get_current_user)):
    """Update a compound."""
    try:
        # Convert Pydantic model to dict, excluding None values
        update_data = {k: v for k, v in compound.model_dump().items() if v is not None}
        
        success, error = service.update_compound(compound_id, update_data)
        if success:
            return {"message": "Compound updated successfully"}
        else:
            logger.error(f"Failed to update compound: {error}")
            if error == "Compound not found":
                raise HTTPException(status_code=404, detail=error)
            else:
                raise HTTPException(status_code=400, detail=error)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating compound: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/compounds/{compound_id}", response_model=dict)
async def delete_compound(compound_id: str, current_user: str = Depends(get_current_user)):
    """Delete a compound."""
    try:
        success, error = service.delete_compound(compound_id)
        if success:
            return {"message": "Compound deleted successfully"}
        else:
            logger.error(f"Failed to delete compound: {error}")
            if error == "Compound not found":
                raise HTTPException(status_code=404, detail=error)
            else:
                raise HTTPException(status_code=400, detail=error)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting compound: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/compounds", response_model=List[dict])
async def list_compounds(current_user: str = Depends(get_current_user)):
    """List all compounds."""
    try:
        compounds, error = service.list_compounds()
        if compounds is not None:
            return compounds
        else:
            logger.error(f"Failed to list compounds: {error}")
            raise HTTPException(status_code=400, detail=error)
    except Exception as e:
        logger.error(f"Error listing compounds: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users/{user_id}/compounds", response_model=List[dict])
async def list_user_compounds(user_id: str, current_user: str = Depends(get_current_user)):
    """List all compounds for a specific user."""
    try:
        # In a real implementation, you would verify that the current user has permission to access this user's compounds
        compounds, error = service.list_user_compounds(user_id)
        if compounds is not None:
            return compounds
        else:
            logger.error(f"Failed to list compounds for user {user_id}: {error}")
            raise HTTPException(status_code=400, detail=error)
    except Exception as e:
        logger.error(f"Error listing compounds for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.service_port)