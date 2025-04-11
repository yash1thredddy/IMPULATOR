import logging
import redis
import json
from chembl_webresource_client.new_client import new_client
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChEMBLService:
    def __init__(self):
        """Initializes the ChEMBLService with a Redis connection."""
        config = Config()
        self.redis_client = redis.Redis(
            host=config.REDIS_HOST, port=config.REDIS_PORT, db=config.REDIS_DB
        )
        self.cache_expiry = config.CACHE_EXPIRY
        self.molecule_resource = new_client.molecule
        self.similarity_resource = new_client.similarity
        self.activity_resource = new_client.activity

    def _handle_chembl_error(self, e, message="ChEMBL API error"):
        """Handles ChEMBL API errors."""
        logger.error(f"{message}: {e}")
        return None

    def _handle_redis_error(self, e, message="Redis error"):
        """Handles Redis errors."""
        logger.error(f"{message}: {e}")
        return None

    def make_chembl_request(self, resource, lookup_param, lookup_value):
        """
        Makes a request to the ChEMBL API.

        Args:
            resource (str): The ChEMBL resource to access (e.g., 'molecule').
            lookup_param (str): The parameter to use for lookup (e.g., 'molecule_chembl_id', 'smiles').
            lookup_value (str): The value to search for.

        Returns:
            list or None: A list of results from the ChEMBL API, or None if an error occurs.
        """
        cache_key = f"chembl:{resource}:{lookup_param}:{lookup_value}"
        cached_result = self.check_cache(cache_key)
        if cached_result:
            return cached_result
            
        try:
            logger.info(
                f"Querying ChEMBL for {resource} with {lookup_param} = {lookup_value}"
            )

            if resource == "molecule":
                if lookup_param == "molecule_chembl_id":
                    self.molecule_resource.set_format("json")
                    response = self.molecule_resource.filter(
                        molecule_chembl_id=lookup_value
                    )
                    results = list(response)
                    self.cache_result(cache_key, results)
                    return results

                elif lookup_param == "smiles":
                    self.molecule_resource.set_format("json")
                    response = self.molecule_resource.filter(
                        molecule_structures__canonical_smiles=lookup_value
                    )
                    results = list(response)
                    self.cache_result(cache_key, results)
                    return results
                else:
                    logger.error(
                        f"Invalid lookup parameter for molecule resource: {lookup_param}"
                    )
                    return None
            elif resource == "activity":
                if lookup_param == "molecule_chembl_id":
                    self.activity_resource.set_format("json")
                    response = self.activity_resource.filter(
                        molecule_chembl_id=lookup_value
                    )
                    results = list(response)
                    self.cache_result(cache_key, results)
                    return results
                else:
                    logger.error(
                        f"Invalid lookup parameter for activity resource: {lookup_param}"
                    )
                    return None
            else:
                logger.error(f"Invalid resource: {resource}")
                return None

        except Exception as e:
            return self._handle_chembl_error(e)

    def get_similarity(self, smiles, similarity=90):
        """
        Fetches molecules from ChEMBL that are similar to the given SMILES string.

        Args:
            smiles (str): The SMILES string to find similar molecules for.
            similarity (int): The similarity percentage threshold.

        Returns:
            list or None: A list of similar molecules from ChEMBL, or None if an error occurs.
        """
        cache_key = f"chembl:similarity:{smiles}:{similarity}"
        cached_result = self.check_cache(cache_key)
        if cached_result:
            logger.info(
                f"Retrieved similar molecules for SMILES '{smiles}' with similarity {similarity}% from cache."
            )
            return cached_result

        try:
            logger.info(
                f"Querying ChEMBL for molecules similar to SMILES '{smiles}' with similarity >= {similarity}%"
            )
            self.similarity_resource.set_format("json")
            sim_mols = self.similarity_resource.filter(
                smiles=smiles,
                similarity=similarity
            )

            if sim_mols:
                # Convert the results (generator) to a list before caching
                result_list = list(sim_mols)
                
                # Add additional information to each molecule
                enhanced_results = []
                for mol in result_list:
                    mol_chembl_id = mol.get('molecule_chembl_id')
                    if mol_chembl_id:
                        # Get more details for this molecule
                        mol_details = self.get_molecule_data(mol_chembl_id)
                        if mol_details:
                            # Enhance the molecule with additional details
                            enhanced_mol = {**mol}
                            
                            # Add molecular properties if available
                            if 'molecule_properties' in mol_details:
                                props = mol_details['molecule_properties']
                                
                                enhanced_mol['properties'] = {
                                    'molecular_weight': float(props.get('full_mwt', 0) or 0),
                                    'alogp': float(props.get('alogp', 0) or 0),
                                    'hba': int(props.get('hba', 0) or 0),
                                    'hbd': int(props.get('hbd', 0) or 0),
                                    'psa': float(props.get('psa', 0) or 0),
                                    'rtb': int(props.get('rtb', 0) or 0),
                                    'ro5_violations': int(props.get('num_ro5_violations', 0) or 0)
                                }
                            
                            # Add smiles if available
                            if 'molecule_structures' in mol_details:
                                enhanced_mol['smiles'] = mol_details['molecule_structures'].get('canonical_smiles')
                            
                            enhanced_results.append(enhanced_mol)
                        else:
                            enhanced_results.append(mol)
                    else:
                        enhanced_results.append(mol)
                
                self.cache_result(cache_key, enhanced_results)
                logger.info(
                    f"Found {len(enhanced_results)} similar molecules for SMILES '{smiles}' and cached the result."
                )
                return enhanced_results
            else:
                logger.info(
                    f"No molecules found similar to SMILES '{smiles}' with similarity >= {similarity}%"
                )
                return []  # Return an empty list when no similar molecules are found

        except Exception as e:
            return self._handle_chembl_error(
                e, f"Error fetching similar molecules for SMILES: {smiles}"
            )

    def get_molecule_data(self, chembl_id):
        """
        Retrieves molecule data from ChEMBL based on ChEMBL ID.

        Args:
            chembl_id (str): The ChEMBL ID of the molecule.

        Returns:
            dict or None: Molecule data from ChEMBL, or None if an error occurs.
        """
        cache_key = f"chembl:molecule:{chembl_id}"
        cached_result = self.check_cache(cache_key)
        if cached_result:
            logger.info(f"Retrieved molecule data for ChEMBL ID '{chembl_id}' from cache.")
            return cached_result

        try:
            logger.info(f"Querying ChEMBL for molecule data with ChEMBL ID: {chembl_id}")
            self.molecule_resource.set_format("json")
            results = self.molecule_resource.filter(molecule_chembl_id=chembl_id)

            # Convert the results (generator) to a list and get the first item if available
            result_list = list(results)
            if result_list:
                molecule_data = result_list[0]
                self.cache_result(cache_key, molecule_data)
                logger.info(
                    f"Found and cached molecule data for ChEMBL ID '{chembl_id}'."
                )
                return molecule_data
            else:
                logger.info(f"No molecule data found for ChEMBL ID '{chembl_id}'.")
                return None

        except Exception as e:
            return self._handle_chembl_error(
                e, f"Error fetching molecule data for ChEMBL ID: {chembl_id}"
            )

    def check_cache(self, key):
        """
        Checks if a result is cached in Redis.

        Args:
            key (str): The cache key to check.

        Returns:
            The cached data if found, otherwise None.
        """
        try:
            cached_data = self.redis_client.get(key)
            if cached_data:
                logger.info(f"Cache hit for key: {key}")
                return json.loads(cached_data)
            logger.info(f"Cache miss for key: {key}")
            return None
        except redis.exceptions.RedisError as e:
            return self._handle_redis_error(e, f"Error checking cache for key: {key}")

    def cache_result(self, key, data):
        """
        Caches a result in Redis.

        Args:
            key (str): The cache key.
            data: The data to cache (must be JSON serializable).
        """
        try:
            self.redis_client.set(key, json.dumps(data), ex=self.cache_expiry)
            logger.info(f"Cached data with key: {key} (expires in {self.cache_expiry} seconds)")
        except redis.exceptions.RedisError as e:
            self._handle_redis_error(e, f"Error caching data with key: {key}")