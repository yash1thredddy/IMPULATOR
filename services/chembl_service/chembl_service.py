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
        self.redis_client = redis.Redis(
            host=Config.REDIS_HOST, port=Config.REDIS_PORT, db=Config.REDIS_DB
        )
        self.molecule_resource = new_client.molecule

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
                    return list(response)

                elif lookup_param == "smiles":
                    self.molecule_resource.set_format("json")
                    response = self.molecule_resource.filter(
                        preferred_compound_names__iregex=lookup_value
                    )
                    return list(response)
                else:
                    logger.error(
                        f"Invalid lookup parameter for molecule resource: {lookup_param}"
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
            molecule = new_client.molecule
            molecule.set_format("json")
            sim_mols = molecule.filter(
                similarity__gt=similarity,  # Greater than or equal to the threshold
                molecules__molecule_structures__canonical_smiles=smiles,
            )

            if sim_mols:
                # Convert the results (generator) to a list before caching
                result_list = list(sim_mols)
                self.cache_result(cache_key, result_list)
                logger.info(
                    f"Found {len(result_list)} similar molecules for SMILES '{smiles}' and cached the result."
                )
                return result_list
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
            molecule = new_client.molecule
            molecule.set_format("json")
            results = molecule.filter(molecule_chembl_id=chembl_id)

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

    def cache_result(self, key, data, expiration=3600):
        """
        Caches a result in Redis.

        Args:
            key (str): The cache key.
            data: The data to cache (must be JSON serializable).
            expiration (int, optional): The cache expiration time in seconds (default is 1 hour).
        """
        try:
            self.redis_client.set(key, json.dumps(data), ex=expiration)
            logger.info(f"Cached data with key: {key} (expires in {expiration} seconds)")
        except redis.exceptions.RedisError as e:
            self._handle_redis_error(e, f"Error caching data with key: {key}")


import unittest
from unittest.mock import patch, MagicMock


class TestChEMBLService(unittest.TestCase):
    def setUp(self):
        # Initialize ChEMBLService
        self.chembl_service = ChEMBLService()

        # Mock the Redis client to avoid actual cache interactions during tests
        self.mock_redis_client = MagicMock()
        self.chembl_service.redis_client = self.mock_redis_client

    @patch("chembl_webresource_client.new_client.new_client.molecule")
    def test_make_chembl_request_success(self, mock_molecule):
        # Test a successful ChEMBL API request for a molecule
        mock_response = [{"molecule_chembl_id": "CHEMBL123"}]
        mock_molecule.filter.return_value = mock_response

        result = self.chembl_service.make_chembl_request(
            "molecule", "molecule_chembl_id", "CHEMBL123"
        )
        self.assertEqual(result, mock_response)
        mock_molecule.filter.assert_called_once_with(molecule_chembl_id="CHEMBL123")

    @patch("chembl_webresource_client.new_client.new_client.molecule")
    def test_make_chembl_request_failure(self, mock_molecule):
        # Test a failed ChEMBL API request
        mock_molecule.filter.side_effect = Exception("API Error")

        result = self.chembl_service.make_chembl_request(
            "molecule", "molecule_chembl_id", "CHEMBL123"
        )
        self.assertIsNone(result)
        mock_molecule.filter.assert_called_once_with(molecule_chembl_id="CHEMBL123")

    @patch("chembl_webresource_client.new_client.new_client.molecule")
    def test_get_similarity_success_from_api(self, mock_molecule):
        # Test fetching similar molecules successfully from the API
        mock_response = [{"molecule_chembl_id": "CHEMBL456", "similarity": 95}]
        mock_molecule.filter.return_value = mock_response
        self.mock_redis_client.get.return_value = None  # Simulate cache miss

        result = self.chembl_service.get_similarity("CC(=O)Oc1ccccc1C(=O)O", 90)
        self.assertEqual(result, mock_response)
        self.mock_redis_client.get.assert_called_once()
        self.mock_redis_client.set.assert_called_once()  # Ensure result is cached
        mock_molecule.filter.assert_called_once()

    def test_get_similarity_success_from_cache(self):
        # Test retrieving similar molecules successfully from the cache
        cached_data = [{"molecule_chembl_id": "CHEMBL789", "similarity": 92}]
        self.mock_redis_client.get.return_value = json.dumps(
            cached_data
        )  # Simulate cache hit

        result = self.chembl_service.get_similarity("CC(=O)Oc1ccccc1C(=O)O", 90)
        self.assertEqual(result, cached_data)
        self.mock_redis_client.get.assert_called_once()

    @patch("chembl_webresource_client.new_client.new_client.molecule")
    def test_get_similarity_no_results(self, mock_molecule):
        # Test when no similar molecules are found
        mock_molecule.filter.return_value = []
        self.mock_redis_client.get.return_value = None

        result = self.chembl_service.get_similarity("Invalid SMILES", 90)
        self.assertEqual(result, [])
        self.mock_redis_client.get.assert_called_once()
        mock_molecule.filter.assert_called_once()

    @patch("chembl_webresource_client.new_client.new_client.molecule")
    def test_get_molecule_data_success_from_api(self, mock_molecule):
        # Test fetching molecule data successfully from the API
        mock_response = {"molecule_chembl_id": "CHEMBL123", "pref_name": "Aspirin"}
        mock_molecule.filter.return_value = [mock_response]
        self.mock_redis_client.get.return_value = None  # Simulate cache miss

        result = self.chembl_service.get_molecule_data("CHEMBL123")
        self.assertEqual(result, mock_response)
        self.mock_redis_client.get.assert_called_once()
        self.mock_redis_client.set.assert_called_once()  # Ensure result is cached
        mock_molecule.filter.assert_called_once_with(molecule_chembl_id="CHEMBL123")

    def test_get_molecule_data_success_from_cache(self):
        # Test retrieving molecule data successfully from the cache
        cached_data = {"molecule_chembl_id": "CHEMBL456", "pref_name": "Ibuprofen"}
        self.mock_redis_client.get.return_value = json.dumps(
            cached_data
        )  # Simulate cache hit

        result = self.chembl_service.get_molecule_data("CHEMBL456")
        self.assertEqual(result, cached_data)
        self.mock_redis_client.get.assert_called_once()

    @patch("chembl_webresource_client.new_client.new_client.molecule")
    def test_get_molecule_data_not_found(self, mock_molecule):
        # Test when no molecule data is found
        mock_molecule.filter.return_value = []
        self.mock_redis_client.get.return_value = None

        result = self.chembl_service.get_molecule_data("CHEMBL999")
        self.assertIsNone(result)
        self.mock_redis_client.get.assert_called_once()
        mock_molecule.filter.assert_called_once_with(molecule_chembl_id="CHEMBL999")

    def test_check_cache(self):
        # Test the check_cache method
        self.mock_redis_client.get.return_value = json.dumps({"key": "value"})
        result = self.chembl_service.check_cache("test_key")
        self.assertEqual(result, {"key": "value"})
        self.mock_redis_client.get.assert_called_once_with("test_key")

    def test_cache_result(self):
        # Test the cache_result method
        self.chembl_service.cache_result("test_key", {"key": "value"})
        self.mock_redis_client.set.assert_called_once()