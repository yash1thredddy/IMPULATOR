import logging
import grpc
import redis
import json
import requests
from concurrent import futures
from chembl_webresource_client.new_client import new_client

# Import the generated protobuf code
import chembl_service_pb2
import chembl_service_pb2_grpc
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ChEMBLServicer(chembl_service_pb2_grpc.ChEMBLServiceServicer):
    """Implementation of the gRPC ChEMBL Service."""
    
    def __init__(self):
        """Initialize the ChEMBL Servicer with Redis connection and ChEMBL client."""
        config = Config()
        self.redis_client = redis.Redis(
            host=config.REDIS_HOST, 
            port=config.REDIS_PORT, 
            db=config.REDIS_DB
        )
        self.cache_expiry = config.CACHE_EXPIRY
        self.molecule_resource = new_client.molecule
        self.similarity_resource = new_client.similarity
        self.activity_resource = new_client.activity
        self.classyfire_base_url = "http://classyfire.wishartlab.com/entities"
        
    def GetSimilarCompounds(self, request, context):
        """
        Implements the GetSimilarCompounds RPC method.
        
        Args:
            request: SimilarityRequest with SMILES and similarity threshold
            context: gRPC context
            
        Returns:
            CompoundList containing similar compounds
        """
        try:
            logger.info(f"GetSimilarCompounds called with SMILES: {request.smiles}, threshold: {request.similarity_threshold}")
            
            # Check cache
            cache_key = f"chembl:similarity:{request.smiles}:{request.similarity_threshold}"
            cached_result = self._check_cache(cache_key)
            
            if cached_result:
                # Convert cached result to gRPC response
                return self._convert_to_compound_list(cached_result)
            
            # Perform similarity search
            self.similarity_resource.set_format("json")
            similar_compounds = self.similarity_resource.filter(
                smiles=request.smiles,
                similarity=request.similarity_threshold
            )
            
            # Process results
            result_list = list(similar_compounds)
            enhanced_results = []
            
            for compound in result_list:
                chembl_id = compound.get('molecule_chembl_id')
                if chembl_id:
                    # Get detailed molecule data
                    molecule_data = self._get_molecule_data_internal(chembl_id)
                    if molecule_data:
                        # Enhance the compound with additional data
                        enhanced_compound = {
                            'chembl_id': chembl_id,
                            'molecule_name': molecule_data.get('pref_name', ''),
                            'canonical_smiles': molecule_data.get('molecule_structures', {}).get('canonical_smiles', ''),
                            'similarity': compound.get('similarity', 0),
                            'properties': self._extract_properties(molecule_data)
                        }
                        enhanced_results.append(enhanced_compound)
            
            # Cache results
            self._cache_result(cache_key, enhanced_results)
            
            # Convert to gRPC response
            return self._convert_to_compound_list(enhanced_results)
            
        except Exception as e:
            logger.error(f"Error in GetSimilarCompounds: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Error processing similarity search: {str(e)}")
            return chembl_service_pb2.CompoundList()
    
    def GetMoleculeData(self, request, context):
        """
        Implements the GetMoleculeData RPC method.
        
        Args:
            request: MoleculeRequest with ChEMBL ID
            context: gRPC context
            
        Returns:
            MoleculeData containing detailed molecule information
        """
        try:
            logger.info(f"GetMoleculeData called for ChEMBL ID: {request.chembl_id}")
            
            # Check cache
            cache_key = f"chembl:molecule:{request.chembl_id}"
            cached_result = self._check_cache(cache_key)
            
            if cached_result:
                # Convert cached result to gRPC response
                return self._convert_to_molecule_data(cached_result)
            
            # Get molecule data
            molecule_data = self._get_molecule_data_internal(request.chembl_id)
            
            if not molecule_data:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Molecule not found for ChEMBL ID: {request.chembl_id}")
                return chembl_service_pb2.MoleculeData()
            
            # Cache result
            self._cache_result(cache_key, molecule_data)
            
            # Convert to gRPC response
            return self._convert_to_molecule_data(molecule_data)
            
        except Exception as e:
            logger.error(f"Error in GetMoleculeData: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Error retrieving molecule data: {str(e)}")
            return chembl_service_pb2.MoleculeData()
    
    def GetCompoundActivities(self, request, context):
        """
        Implements the GetCompoundActivities RPC method.
        
        Args:
            request: ActivityRequest with ChEMBL ID and activity types
            context: gRPC context
            
        Returns:
            ActivityList containing activities for the compound
        """
        try:
            logger.info(f"GetCompoundActivities called for ChEMBL ID: {request.chembl_id}")
            
            # Check cache
            activity_types_str = ",".join(request.activity_types)
            cache_key = f"chembl:activities:{request.chembl_id}:{activity_types_str}"
            cached_result = self._check_cache(cache_key)
            
            if cached_result:
                # Convert cached result to gRPC response
                return self._convert_to_activity_list(cached_result)
            
            # Get activities
            activities = []
            for activity_type in request.activity_types:
                try:
                    self.activity_resource.set_format("json")
                    results = self.activity_resource.filter(
                        molecule_chembl_id=request.chembl_id,
                        standard_type=activity_type
                    )
                    activities.extend(list(results))
                except Exception as e:
                    logger.error(f"Error fetching activities of type {activity_type}: {str(e)}")
            
            # Process activities
            processed_activities = []
            for activity in activities:
                if all(key in activity for key in ['standard_value', 'standard_units', 'standard_type']):
                    # Add type checking before converting to float
                    standard_value = 0.0
                    if activity.get('standard_value') is not None:
                        try:
                            standard_value = float(activity.get('standard_value'))
                        except (ValueError, TypeError):
                            continue  # Skip activities with invalid values
                            
                    processed_activity = {
                        'chembl_id': request.chembl_id,
                        'target_id': activity.get('target_id', ''),
                        'activity_type': activity.get('standard_type', ''),
                        'relation': activity.get('standard_relation', '='),
                        'value': standard_value,
                        'units': activity.get('standard_units', '')
                    }
                    processed_activities.append(processed_activity)
            # Cache results
            self._cache_result(cache_key, processed_activities)
            
            # Convert to gRPC response
            return self._convert_to_activity_list(processed_activities)
            
        except Exception as e:
            logger.error(f"Error in GetCompoundActivities: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Error retrieving compound activities: {str(e)}")
            return chembl_service_pb2.ActivityList()
    
    def GetCompoundClassification(self, request, context):
        """
        Implements the GetCompoundClassification RPC method.
        
        Args:
            request: ClassificationRequest with InChIKey
            context: gRPC context
            
        Returns:
            ClassificationData containing compound classification
        """
        try:
            logger.info(f"GetCompoundClassification called for InChIKey: {request.inchi_key}")
            
            # Check cache
            cache_key = f"classyfire:{request.inchi_key}"
            cached_result = self._check_cache(cache_key)
            
            if cached_result:
                # Convert cached result to gRPC response
                return self._convert_to_classification_data(cached_result)
            
            # Get classification from ClassyFire
            url = f"{self.classyfire_base_url}/{request.inchi_key}.json"
            response = requests.get(url, timeout=30)
            
            if response.status_code != 200:
                logger.warning(f"ClassyFire API returned status code {response.status_code}")
                return chembl_service_pb2.ClassificationData()
            
            classification_data = response.json()
            
            # Extract relevant data
            result = {
                'kingdom': classification_data.get('kingdom', {}).get('name', '') if classification_data.get('kingdom') else '',
                'superclass': classification_data.get('superclass', {}).get('name', '') if classification_data.get('superclass') else '',
                'class': classification_data.get('class', {}).get('name', '') if classification_data.get('class') else '',
                'subclass': classification_data.get('subclass', {}).get('name', '') if classification_data.get('subclass') else ''
            }
            
            # Cache results
            self._cache_result(cache_key, result)
            
            # Convert to gRPC response
            return self._convert_to_classification_data(result)
            
        except Exception as e:
            logger.error(f"Error in GetCompoundClassification: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Error retrieving classification data: {str(e)}")
            return chembl_service_pb2.ClassificationData()
    
    def _get_molecule_data_internal(self, chembl_id):
        """
        Get molecule data from ChEMBL.
        
        Args:
            chembl_id: ChEMBL ID of the molecule
            
        Returns:
            dict: Molecule data or None if not found
        """
        try:
            self.molecule_resource.set_format("json")
            results = self.molecule_resource.filter(molecule_chembl_id=chembl_id)
            result_list = list(results)
            
            if result_list:
                return result_list[0]
            return None
        except Exception as e:
            logger.error(f"Error getting molecule data for {chembl_id}: {str(e)}")
            return None
    
    def _extract_properties(self, molecule_data):
        """
        Extract molecular properties from molecule data.
        
        Args:
            molecule_data: Molecule data from ChEMBL
            
        Returns:
            dict: Extracted properties
        """
        if not molecule_data or 'molecule_properties' not in molecule_data:
            return {}
        
        props = molecule_data['molecule_properties']
        return {
            'molecular_weight': float(props.get('full_mwt', 0)) if props.get('full_mwt') else 0,
            'psa': float(props.get('psa', 0)) if props.get('psa') else 0,
            'hba': int(props.get('hba', 0)) if props.get('hba') else 0,
            'hbd': int(props.get('hbd', 0)) if props.get('hbd') else 0,
            'num_ro5_violations': int(props.get('num_ro5_violations', 0)) if props.get('num_ro5_violations') else 0,
            'alogp': float(props.get('alogp', 0)) if props.get('alogp') else 0,
            'rtb': int(props.get('rtb', 0)) if props.get('rtb') else 0,
            'num_heavy_atoms': int(props.get('heavy_atoms', 0)) if props.get('heavy_atoms') else 0
        }
    
    def _check_cache(self, key):
        """
        Check if a key exists in the Redis cache.
        
        Args:
            key: Cache key
            
        Returns:
            dict: Cached data or None if not found
        """
        try:
            cached_data = self.redis_client.get(key)
            if cached_data:
                logger.info(f"Cache hit for key: {key}")
                return json.loads(cached_data)
            logger.info(f"Cache miss for key: {key}")
            return None
        except Exception as e:
            logger.error(f"Error checking cache: {str(e)}")
            return None
    
    def _cache_result(self, key, data):
        """
        Cache data in Redis.
        
        Args:
            key: Cache key
            data: Data to cache
        """
        try:
            self.redis_client.set(key, json.dumps(data), ex=self.cache_expiry)
            logger.info(f"Cached data with key: {key}")
        except Exception as e:
            logger.error(f"Error caching data: {str(e)}")
    #sss
    
    # In the _convert_to_compound_list method, add proper type conversion:

    def _convert_to_compound_list(self, compounds):
        """
        Convert compound data to gRPC CompoundList message.
        """
        result = chembl_service_pb2.CompoundList()
        
        for compound in compounds:
            # Create safe version with type conversion
            compound_data = chembl_service_pb2.CompoundData(
                chembl_id=compound.get('chembl_id', ''),
                molecule_name=compound.get('molecule_name', ''),
                canonical_smiles=compound.get('canonical_smiles', '')
            )
            
            # Safely convert similarity to float
            try:
                compound_data.similarity = float(compound.get('similarity', 0))
            except (TypeError, ValueError):
                compound_data.similarity = 0.0
            
            # Add properties if available
            if 'properties' in compound and compound['properties']:
                props = compound['properties']
                
                # Safely set molecular properties with type conversion
                try:
                    compound_data.properties.molecular_weight = float(props.get('molecular_weight', 0))
                except (TypeError, ValueError):
                    compound_data.properties.molecular_weight = 0.0
                    
                try:
                    compound_data.properties.psa = float(props.get('psa', 0))
                except (TypeError, ValueError):
                    compound_data.properties.psa = 0.0
                    
                try:
                    compound_data.properties.hba = int(props.get('hba', 0))
                except (TypeError, ValueError):
                    compound_data.properties.hba = 0
                    
                try:
                    compound_data.properties.hbd = int(props.get('hbd', 0))
                except (TypeError, ValueError):
                    compound_data.properties.hbd = 0
                    
                try:
                    compound_data.properties.num_ro5_violations = int(props.get('num_ro5_violations', 0))
                except (TypeError, ValueError):
                    compound_data.properties.num_ro5_violations = 0
                    
                try:
                    compound_data.properties.alogp = float(props.get('alogp', 0))
                except (TypeError, ValueError):
                    compound_data.properties.alogp = 0.0
                    
                try:
                    compound_data.properties.rtb = int(props.get('rtb', 0))
                except (TypeError, ValueError):
                    compound_data.properties.rtb = 0
                    
                try:
                    compound_data.properties.num_heavy_atoms = int(props.get('num_heavy_atoms', 0))
                except (TypeError, ValueError):
                    compound_data.properties.num_heavy_atoms = 0
            
            result.compounds.append(compound_data)
        
        return result
        
    def _convert_to_molecule_data(self, molecule):
        """
        Convert molecule data to gRPC MoleculeData message.
        
        Args:
            molecule: Molecule dictionary
            
        Returns:
            MoleculeData: gRPC message
        """
        result = chembl_service_pb2.MoleculeData(
            chembl_id=molecule.get('molecule_chembl_id', ''),
            molecule_name=molecule.get('pref_name', ''),
            canonical_smiles=molecule.get('molecule_structures', {}).get('canonical_smiles', '') if 'molecule_structures' in molecule else '',
            inchi_key=molecule.get('molecule_structures', {}).get('standard_inchi_key', '') if 'molecule_structures' in molecule else ''
        )
        
        # Add properties
        properties = self._extract_properties(molecule)
        result.properties.molecular_weight = properties.get('molecular_weight', 0)
        result.properties.psa = properties.get('psa', 0)
        result.properties.hba = properties.get('hba', 0)
        result.properties.hbd = properties.get('hbd', 0)
        result.properties.num_ro5_violations = properties.get('num_ro5_violations', 0)
        result.properties.alogp = properties.get('alogp', 0)
        result.properties.rtb = properties.get('rtb', 0)
        result.properties.num_heavy_atoms = properties.get('num_heavy_atoms', 0)
        
        return result
    
    def _convert_to_activity_list(self, activities):
        """
        Convert activity data to gRPC ActivityList message.
        
        Args:
            activities: List of activity dictionaries
            
        Returns:
            ActivityList: gRPC message
        """
        result = chembl_service_pb2.ActivityList()
        
        for activity in activities:
            activity_data = chembl_service_pb2.ActivityData(
                chembl_id=activity.get('chembl_id', ''),
                target_id=activity.get('target_id', ''),
                activity_type=activity.get('activity_type', ''),
                relation=activity.get('relation', '='),
                value=activity.get('value', 0),
                units=activity.get('units', '')
            )
            result.activities.append(activity_data)
        
        return result
    
    def _convert_to_classification_data(self, classification):
        """
        Convert classification data to gRPC ClassificationData message.
        
        Args:
            classification: Classification dictionary
            
        Returns:
            ClassificationData: gRPC message
        """
        return chembl_service_pb2.ClassificationData(
            kingdom=classification.get('kingdom', ''),
            superclass=classification.get('superclass', ''),
            class_=classification.get('class', ''),  # Using class_ to avoid reserved keyword
            subclass=classification.get('subclass', '')
        )
        
def serve():
    """Start the gRPC server."""
    config = Config()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    chembl_service_pb2_grpc.add_ChEMBLServiceServicer_to_server(ChEMBLServicer(), server)
    
    # Get the port from config
    port = config.GRPC_PORT
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    logger.info(f"ChEMBL Service gRPC server started on port {port}")
    
    # Keep the server running
    server.wait_for_termination()

if __name__ == '__main__':
    serve()