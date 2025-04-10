import os
import logging
import redis
from Bio.PDB import PDBList
from Bio import Entrez
from config import Config
import requests
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



class PDBService:
    def __init__(self, config):
        """
        Initializes the PDBService with configuration parameters and establishes a Redis connection.
        """
        self.config = config
        self.redis_client = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, db=config.REDIS_DB)
        Entrez.email = config.ENTREZ_EMAIL

    def check_cache(self, key):
        """
        Checks if a value exists in the Redis cache.

        Args:
            key (str): The key to check.

        Returns:
            str or None: The value associated with the key if it exists, otherwise None.
        """
        try:
            value = self.redis_client.get(key)
            if value:
                logger.info(f"Cache hit for key: {key}")
                return value.decode('utf-8')
            logger.info(f"Cache miss for key: {key}")
            return None
        except redis.exceptions.ConnectionError as e:
            logger.error(f"Redis connection error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error checking cache: {e}")
            return None

    def cache_result(self, key, data, expiration=3600):
        """
        Caches a result in Redis with an expiration time.

        Args:
            key (str): The key to store the data under.
            data (str): The data to store.
            expiration (int): The expiration time in seconds (default: 3600).
        """
        try:
            self.redis_client.setex(key, expiration, data)
            logger.info(f"Cached result for key: {key}")
        except redis.exceptions.ConnectionError as e:
            logger.error(f"Redis connection error: {e}")
        except Exception as e:
            logger.error(f"Error caching result: {e}")

    def get_protein(self, pdb_id):
        """
        Retrieves protein structure from PDB by PDB ID.

        Args:
            pdb_id (str): The PDB ID of the protein.

        Returns:
            dict or None: The protein structure data in JSON format, or None if an error occurs.
        """
        cache_key = f"pdb:protein:{pdb_id}"
        cached_data = self.check_cache(cache_key)
        if cached_data:
            return json.loads(cached_data)

        try:
            logger.info(f"Fetching protein data for PDB ID: {pdb_id}")
            pdbl = PDBList()
            file_path = pdbl.retrieve_pdb_file(pdb_id, pdir=".", file_format="pdb")
            with open(file_path, "r") as file:
                protein_data = file.read()
            os.remove(file_path)
            
            result = {"pdb_id": pdb_id, "protein_data": protein_data}
            self.cache_result(cache_key, json.dumps(result))
            return result

        except Exception as e:
            logger.error(f"Error fetching protein data for PDB ID {pdb_id}: {e}")
            return None

    def get_target_to_pdb(self, target_id):
        """
        Maps a ChEMBL target to PDB entries.

        Args:
            target_id (str): The ChEMBL target ID.

        Returns:
            list or None: A list of PDB IDs associated with the target, or None if an error occurs.
        """
        cache_key = f"pdb:target:{target_id}"
        cached_data = self.check_cache(cache_key)
        if cached_data:
            return json.loads(cached_data)

        try:
            logger.info(f"Mapping ChEMBL target to PDB entries for target ID: {target_id}")
            handle = Entrez.elink(dbfrom="chembl", db="pdb", id=target_id, linkname="chembl_pdb")
            records = Entrez.read(handle)
            handle.close()
            pdb_ids = []
            if records and records[0].get("LinkSetDb"):
                for link in records[0]["LinkSetDb"]:
                    for link_id in link["Link"]:
                        pdb_ids.append(link_id["Id"])

            result = list(set(pdb_ids))
            self.cache_result(cache_key, json.dumps(result))
            return result

        except Exception as e:
            logger.error(f"Error mapping ChEMBL target {target_id} to PDB entries: {e}")
            return None

import unittest
from unittest.mock import patch, MagicMock, mock_open


class TestPDBService(unittest.TestCase):
    def setUp(self):
        """
        Set up for the test class.
        Creates an instance of the PDBService and sets a mock Redis client.
        """
        self.config = Config()
        self.pdb_service = PDBService(
            self.config)  # Pass the config instance to PDBService
        self.mock_redis_client = MagicMock()
        self.pdb_service.redis_client = self.mock_redis_client

    def tearDown(self):
        """
        Clean up after tests by resetting the Redis client mock.
        """
        self.pdb_service.redis_client = None

    def test_check_cache(self):
        """
        Test the check_cache method.
        Verifies that the method correctly interacts with the Redis client
        and returns cached data or None as expected.
        """
        # Test cache hit
        self.mock_redis_client.get.return_value = b'{"test": "data"}'
        result = self.pdb_service.check_cache("test_key")
        self.assertEqual(result, '{"test": "data"}')
        self.mock_redis_client.get.assert_called_once_with("test_key")

        # Test cache miss
        self.mock_redis_client.get.return_value = None
        result = self.pdb_service.check_cache("another_key")
        self.assertIsNone(result)
        self.mock_redis_client.get.assert_called_with("another_key")

    def test_cache_result(self):
        """
        Test the cache_result method.
        Verifies that the method correctly sets data in the Redis cache with
        the specified key, data, and expiration time.
        """
        self.pdb_service.cache_result("new_key", "some value", 3600)
        self.mock_redis_client.setex.assert_called_once_with("new_key", 3600, "some value")

    @patch("requests.get")
    def test_get_protein(self, mock_get):
        """
        Test the get_protein method.
        Mocks the requests.get to simulate fetching data from the PDB API.
        Verifies that the method correctly processes the data and caches the results.
        """
        # Load mock response from file
        with open("mock_pdb_response.txt", "r") as f:
            mock_response_content = f.read()

        # Create a mock response object
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = mock_response_content
        mock_get.return_value = mock_response

        # Call the method with a sample PDB ID
        pdb_id = "4AKE"
        result = self.pdb_service.get_protein(pdb_id)

        # Assertions to check if the method behaves as expected
        self.assertIsNotNone(result)
        self.assertEqual(result["pdb_id"], pdb_id)
        self.assertIn("ATOM", result["protein_data"])  # Check for part of the PDB content
        self.mock_redis_client.setex.assert_called_once()  # Verify that caching was attempted

    @patch("requests.get")
    def test_get_target_to_pdb(self, mock_get):
        """
        Test the get_target_to_pdb method.
        Mocks the requests.get to simulate fetching data from the PDB API.
        Verifies that the method correctly processes the data and caches the results.
        """
        # Define a mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"pdb_ids": ["1ABC", "2DEF"]}
        mock_get.return_value = mock_response

        # Call the method with a sample target ID
        target_id = "T12345"
        result = self.pdb_service.get_target_to_pdb(target_id)

        # Assertions
        self.assertEqual(result, ["1ABC", "2DEF"])
        expected_url = f"{self.config.PDB_API_BASE_URL}/mappings/{target_id}"
        mock_get.assert_called_once_with(expected_url)
        self.mock_redis_client.setex.assert_called_once()


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()