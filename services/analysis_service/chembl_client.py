import logging
import grpc
from typing import List, Dict, Any, Optional
import os
import time

# Import the generated protobuf code
import chembl_service_pb2
import chembl_service_pb2_grpc
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ChEMBLClient:
    """Client for interacting with the ChEMBL Service via gRPC."""
    
    def __init__(self):
        """Initialize the ChEMBL client with configuration."""
        self.config = Config()
        self.channel = None
        self.stub = None
        self.connect()
    
    def connect(self):
        """Establish a connection to the ChEMBL Service gRPC server."""
        host = self.config.CHEMBL_SERVICE_GRPC_HOST
        port = self.config.CHEMBL_SERVICE_GRPC_PORT
        try:
            # Create a gRPC channel
            self.channel = grpc.insecure_channel(f"{host}:{port}")
            
            # Create a stub (client)
            self.stub = chembl_service_pb2_grpc.ChEMBLServiceStub(self.channel)
            logger.info(f"Connected to ChEMBL Service gRPC at {host}:{port}")
        except Exception as e:
            logger.error(f"Failed to connect to ChEMBL Service: {e}")
            # Retry logic can be implemented here if needed
    
    def close(self):
        """Close the gRPC channel."""
        if self.channel:
            self.channel.close()
            logger.info("Closed connection to ChEMBL Service")
    
    def _ensure_connection(self):
        """Ensure that the gRPC connection is established."""
        if not self.stub:
            logger.info("No connection to ChEMBL Service, attempting to connect...")
            self.connect()
            if not self.stub:
                raise ConnectionError("Could not establish connection to ChEMBL Service")
    
    def get_similar_compounds(self, smiles: str, similarity_threshold: int = 80) -> List[Dict[str, Any]]:
        """
        Get compounds similar to the provided SMILES string.
        
        Args:
            smiles: SMILES string of the compound
            similarity_threshold: Similarity threshold (0-100)
            
        Returns:
            List of similar compounds with their properties
        """
        self._ensure_connection()
        
        try:
            # Prepare request
            request = chembl_service_pb2.SimilarityRequest(
                smiles=smiles,
                similarity_threshold=similarity_threshold
            )
            
            # Call the service
            response = self.stub.GetSimilarCompounds(request)
            
            # Process response
            similar_compounds = []
            for compound in response.compounds:
                # Extract properties
                properties = {
                    'molecular_weight': compound.properties.molecular_weight,
                    'psa': compound.properties.psa,
                    'hba': compound.properties.hba,
                    'hbd': compound.properties.hbd,
                    'num_ro5_violations': compound.properties.num_ro5_violations,
                    'alogp': compound.properties.alogp,
                    'rtb': compound.properties.rtb,
                    'num_heavy_atoms': compound.properties.num_heavy_atoms
                }
                
                # Create compound object
                similar_compound = {
                    'chembl_id': compound.chembl_id,
                    'molecule_name': compound.molecule_name,
                    'canonical_smiles': compound.canonical_smiles,
                    'similarity': compound.similarity,
                    'properties': properties
                }
                
                similar_compounds.append(similar_compound)
            
            logger.info(f"Found {len(similar_compounds)} similar compounds for SMILES: {smiles}")
            return similar_compounds
            
        except grpc.RpcError as e:
            logger.error(f"RPC error when getting similar compounds: {e.code()}: {e.details()}")
            # Implement retry logic if needed
            return []
        except Exception as e:
            logger.error(f"Error getting similar compounds: {e}")
            return []
    
    def get_molecule_data(self, chembl_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a molecule by ChEMBL ID.
        
        Args:
            chembl_id: ChEMBL ID of the molecule
            
        Returns:
            Dictionary with molecule data or None if not found
        """
        self._ensure_connection()
        
        try:
            # Prepare request
            request = chembl_service_pb2.MoleculeRequest(chembl_id=chembl_id)
            
            # Call the service
            response = self.stub.GetMoleculeData(request)
            
            # Check if we got a valid response
            if not response.chembl_id:
                logger.warning(f"No molecule data found for ChEMBL ID: {chembl_id}")
                return None
            
            # Extract properties
            properties = {
                'molecular_weight': response.properties.molecular_weight,
                'psa': response.properties.psa,
                'hba': response.properties.hba,
                'hbd': response.properties.hbd,
                'num_ro5_violations': response.properties.num_ro5_violations,
                'alogp': response.properties.alogp,
                'rtb': response.properties.rtb,
                'num_heavy_atoms': response.properties.num_heavy_atoms
            }
            
            # Create molecule object
            molecule_data = {
                'chembl_id': response.chembl_id,
                'molecule_name': response.molecule_name,
                'canonical_smiles': response.canonical_smiles,
                'inchi_key': response.inchi_key,
                'properties': properties
            }
            
            logger.info(f"Retrieved molecule data for ChEMBL ID: {chembl_id}")
            return molecule_data
            
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                logger.warning(f"Molecule not found for ChEMBL ID: {chembl_id}")
                return None
            logger.error(f"RPC error when getting molecule data: {e.code()}: {e.details()}")
            return None
        except Exception as e:
            logger.error(f"Error getting molecule data: {e}")
            return None
    
    def get_compound_activities(self, chembl_id: str, activity_types: List[str]) -> List[Dict[str, Any]]:
        """
        Get activities for a compound.
        
        Args:
            chembl_id: ChEMBL ID of the compound
            activity_types: List of activity types to retrieve
            
        Returns:
            List of activities
        """
        self._ensure_connection()
        
        try:
            # Prepare request
            request = chembl_service_pb2.ActivityRequest(
                chembl_id=chembl_id,
                activity_types=activity_types
            )
            
            # Call the service
            response = self.stub.GetCompoundActivities(request)
            
            # Process response
            activities = []
            for activity in response.activities:
                activity_data = {
                    'chembl_id': activity.chembl_id,
                    'target_id': activity.target_id,
                    'activity_type': activity.activity_type,
                    'relation': activity.relation,
                    'value': activity.value,
                    'units': activity.units
                }
                activities.append(activity_data)
            
            logger.info(f"Retrieved {len(activities)} activities for ChEMBL ID: {chembl_id}")
            return activities
            
        except grpc.RpcError as e:
            logger.error(f"RPC error when getting compound activities: {e.code()}: {e.details()}")
            return []
        except Exception as e:
            logger.error(f"Error getting compound activities: {e}")
            return []
    
    def get_compound_classification(self, inchi_key: str) -> Optional[Dict[str, str]]:
        """
        Get classification data for a compound.
        
        Args:
            inchi_key: InChIKey of the compound
            
        Returns:
            Dictionary with classification data or None if not found
        """
        self._ensure_connection()
        
        try:
            # Prepare request
            request = chembl_service_pb2.ClassificationRequest(inchi_key=inchi_key)
            
            # Call the service
            response = self.stub.GetCompoundClassification(request)
            
            # Check if we got a valid response
            if not response.kingdom and not response.superclass and not response.class_ and not response.subclass:
                logger.warning(f"No classification found for InChIKey: {inchi_key}")
                return None
            
            # Create classification object
            classification = {
                'kingdom': response.kingdom,
                'superclass': response.superclass,
                'class': response.class_,  # Note the underscore due to 'class' being a Python keyword
                'subclass': response.subclass
            }
            
            logger.info(f"Retrieved classification for InChIKey: {inchi_key}")
            return classification
            
        except grpc.RpcError as e:
            logger.error(f"RPC error when getting classification: {e.code()}: {e.details()}")
            return None
        except Exception as e:
            logger.error(f"Error getting classification: {e}")
            return None