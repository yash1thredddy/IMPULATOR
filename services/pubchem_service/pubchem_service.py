import os
import logging
import redis
import json
import time
import pubchempy as pcp
from config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

class PubChemService:
    def __init__(self, config):
        """
        Initializes the PubChem Service with configuration and sets up a Redis connection.

        Args:
            config (Config): The configuration object containing necessary settings.
        """
        self.config = config
        self.redis_client = self.connect_to_redis()

    def connect_to_redis(self):
        """
        Establishes a connection to Redis using parameters from the configuration.

        Returns:
            redis.Redis: A Redis client instance.
        """
        try:
            redis_client = redis.Redis(
                host=self.config.REDIS_HOST,
                port=self.config.REDIS_PORT,
                db=self.config.REDIS_DB,
            )
            redis_client.ping()  # Check connection
            logging.info("Connected to Redis successfully")
            return redis_client
        except redis.exceptions.ConnectionError as e:
            logging.error(f"Failed to connect to Redis: {e}")
            raise

    def get_compound_by_smiles(self, smiles):
        """
        Retrieves compound information from PubChem by SMILES string.

        Args:
            smiles (str): The SMILES string of the compound.

        Returns:
            dict: A dictionary containing the compound information or None if not found.
        """
        try:
            cache_key = f"pubchem:smiles:{smiles}"
            cached_data = self.check_cache(cache_key)
            if cached_data:
                logging.info(f"Cache hit for compound with SMILES: {smiles}")
                return json.loads(cached_data)

            compounds = pcp.get_compounds(smiles, "smiles")
            if compounds:
                compound = compounds[0]
                result = {
                    "cid": compound.cid,
                    "molecular_formula": compound.molecular_formula,
                    "molecular_weight": compound.molecular_weight,
                    "canonical_smiles": compound.canonical_smiles,
                    "isomeric_smiles": compound.isomeric_smiles,
                }
                self.cache_result(cache_key, json.dumps(result))
                logging.info(f"Retrieved and cached compound with SMILES: {smiles}")
                return result
            else:
                logging.info(f"No compound found in PubChem for SMILES: {smiles}")
                return None

        except pcp.PubChemHTTPError as e:
            logging.error(f"Error querying PubChem API: {e}")
            return None
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")
            return None

    def get_compound_by_cid(self, cid):
        """
        Retrieves compound information from PubChem by CID.

        Args:
            cid (int): The PubChem CID of the compound.

        Returns:
            dict: A dictionary containing the compound information or None if not found.
        """
        try:
            cache_key = f"pubchem:cid:{cid}"
            cached_data = self.check_cache(cache_key)
            if cached_data:
                logging.info(f"Cache hit for compound with CID: {cid}")
                return json.loads(cached_data)

            compound = pcp.Compound.from_cid(cid)
            if compound:
                result = {
                    "cid": compound.cid,
                    "molecular_formula": compound.molecular_formula,
                    "molecular_weight": compound.molecular_weight,
                    "canonical_smiles": compound.canonical_smiles,
                    "isomeric_smiles": compound.isomeric_smiles,
                }
                self.cache_result(cache_key, json.dumps(result))
                logging.info(f"Retrieved and cached compound with CID: {cid}")
                return result
            else:
                logging.info(f"No compound found in PubChem for CID: {cid}")
                return None
        except pcp.PubChemHTTPError as e:
            logging.error(f"Error querying PubChem API: {e}")
            return None
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")
            return None

    def map_to_chembl(self, cid):
        """
        Attempts to map a PubChem CID to a ChEMBL ID.

        Args:
            cid (int): The PubChem CID.

        Returns:
            str: The mapped ChEMBL ID or None if not found.
        """
        try:
            cache_key = f"pubchem:map_to_chembl:{cid}"
            cached_data = self.check_cache(cache_key)
            if cached_data:
                logging.info(f"Cache hit for mapping PubChem CID {cid} to ChEMBL ID")
                return json.loads(cached_data)

            # This is a placeholder as direct mapping is not available.
            # You need to implement a robust mapping service or external library for this.
            logging.warning(
                "Direct PubChem to ChEMBL mapping not implemented. Using placeholder logic."
            )
            chembl_id = f"CHEMBL_PLACEHOLDER_{cid}"
            self.cache_result(cache_key, json.dumps(chembl_id))
            logging.info(f"Mapped PubChem CID {cid} to ChEMBL ID: {chembl_id}")
            return chembl_id

        except Exception as e:
            logging.error(f"Error mapping PubChem CID to ChEMBL ID: {e}")
            return None

    def check_cache(self, key):
        """
        Checks if data for the given key exists in the Redis cache.

        Args:
            key (str): The cache key.

        Returns:
            str: The cached data if found, otherwise None.
        """
        try:
            data = self.redis_client.get(key)
            return data.decode() if data else None
        except redis.exceptions.RedisError as e:
            logging.error(f"Redis error: {e}")
            return None

    def cache_result(self, key, data, expiration=3600):
        """
        Caches data in Redis with an optional expiration time.

        Args:
            key (str): The cache key.
            data (str): The data to be cached.
            expiration (int): The expiration time in seconds (default is 1 hour).
        """
        try:
            self.redis_client.set(key, data, ex=expiration)
            logging.info(f"Cached data with key: {key}")
        except redis.exceptions.RedisError as e:
            logging.error(f"Redis error: {e}")

import unittest
from unittest.mock import patch, MagicMock

class TestPubChemService(unittest.TestCase):
    def setUp(self):
        # Initialize PubChemService with a mock config
        self.config = MagicMock()
        self.config.REDIS_HOST = "localhost"
        self.config.REDIS_PORT = 6379
        self.config.REDIS_DB = 0
        self.pubchem_service = PubChemService(self.config)

    def tearDown(self):
        # Close the Redis connection after each test
        if self.pubchem_service.redis_client:
            self.pubchem_service.redis_client.close()

    @patch("pubchempy.get_compounds")
    def test_get_compound_by_smiles(self, mock_get_compounds):
        # Test retrieving compound by SMILES
        mock_compound = MagicMock()
        mock_compound.cid = 1234
        mock_compound.molecular_formula = "C2H6O"
        mock_compound.molecular_weight = 46.07
        mock_compound.canonical_smiles = "CCO"
        mock_compound.isomeric_smiles = "CCO"
        mock_get_compounds.return_value = [mock_compound]

        result = self.pubchem_service.get_compound_by_smiles("CCO")
        self.assertIsNotNone(result)
        self.assertEqual(result["cid"], 1234)
        self.assertEqual(result["molecular_formula"], "C2H6O")

    @patch("pubchempy.Compound.from_cid")
    def test_get_compound_by_cid(self, mock_from_cid):
        # Test retrieving compound by CID
        mock_compound = MagicMock()
        mock_compound.cid = 1234
        mock_compound.molecular_formula = "C2H6O"
        mock_compound.molecular_weight = 46.07
        mock_compound.canonical_smiles = "CCO"
        mock_compound.isomeric_smiles = "CCO"
        mock_from_cid.return_value = mock_compound

        result = self.pubchem_service.get_compound_by_cid(1234)
        self.assertIsNotNone(result)
        self.assertEqual(result["cid"], 1234)
        self.assertEqual(result["molecular_formula"], "C2H6O")

    def test_map_to_chembl(self):
        # Test mapping PubChem CID to ChEMBL ID (currently placeholder)
        result = self.pubchem_service.map_to_chembl(1234)
        self.assertIsNotNone(result)
        self.assertEqual(result, "CHEMBL_PLACEHOLDER_1234")  # Assuming placeholder logic

    # Add more tests as needed, e.g., for cache hits/misses

if __name__ == "__main__":
    unittest.main()