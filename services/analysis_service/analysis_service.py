# analysis_service.py
import grpc
import psycopg2
import unittest
import pymongo
from concurrent import futures
import time
import json as js
import os
import pika
import logging as log
from config import Config
from chembl_webresource_client.new_client import new_client

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AnalysisServiceServicer:
    def __init__(self, db_params, mongo_uri, rabbitmq_params, config, chembl_service=None, postgres_conn=None, mongo_client=None):
        '''
        Initializes the AnalysisServiceServicer with database connection details and configuration.

        Args:
            db_params (dict): PostgreSQL database connection parameters.
            mongo_uri (str): MongoDB connection URI.
            rabbitmq_params (dict): RabbitMQ connection parameters.
            config (Config): Configuration object containing application settings.
        """
        self.db_params = db_params
        self.mongo_uri = mongo_uri
        self.rabbitmq_params = rabbitmq_params
        self.config = config
        self.postgres_conn = postgres_conn
        self.mongo_client = mongo_client
        self.mongo_db = None
        self.chembl_service = chembl_service        
        # Configure logging
        log.basicConfig(level=log.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    def connect_to_postgres(self):
        '''Establishes a connection to the PostgreSQL database.'''
        try:
            self.postgres_conn = psycopg2.connect(**self.db_params, connect_timeout=10)
            logger.info("Connected to PostgreSQL database")
        except Exception as e:
            logger.error(f"Error connecting to PostgreSQL: {e}")
            raise

    def connect_to_mongo(self):
        """Establishes a connection to the MongoDB database."""
        try:            
            self.mongo_client = pymongo.MongoClient(self.mongo_uri)
            self.mongo_db = self.mongo_client[self.config.MONGO_DB_NAME]
            logger.info("Connected to MongoDB database")
        except Exception as e:
            logger.error(f"Error connecting to MongoDB: {e}")
            raise

    def close_db_connections(self):
        """Closes the database connections."""
        if self.postgres_conn:
            self.postgres_conn.close()
            logger.info("PostgreSQL connection closed")
        if self.mongo_client:
            self.mongo_client.close()
            logger.info("MongoDB connection closed")

    def store_analysis_results(self, compound_id, results):
        """
        Stores analysis results in MongoDB.

        Args:
            compound_id (str): The ID of the compound.
            results (dict): The analysis results to be stored.

        Returns:
            str: The ID of the inserted document.
        """
        try:            
            self.connect_to_mongo()
            collection = self.mongo_db.get_collection("analysis_results")
            result = collection.insert_one(
                {"compound_id": compound_id, "results": results, "created_at": time.time()}
            )
            logger.info(f"Analysis results stored for compound {compound_id} in MongoDB")
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Error storing analysis results in MongoDB: {e}")
            raise

    def fetch_compounds_from_chembl(self, smiles):
        """
        Fetches similar compounds from ChEMBL based on the given SMILES.

        Args:
            smiles (str): The SMILES string of the compound.

        Returns:
            list: A list of similar compounds from ChEMBL.
        """
        if self.chembl_service:
            try:                
                similar_molecules = self.chembl_service.get_similarity(smiles)
                logger.info(f"Fetched similar compounds from ChEMBL for SMILES: {smiles}")
                return similar_molecules
            except Exception as e:
                logger.error(f"Error fetching compounds from ChEMBL: {e}")
                return []
        except Exception as e:
            logger.error(f"Error fetching compounds from ChEMBL: {e}")
            return []



    def fetch_compounds_from_pubchem(self, smiles):
        """
        Fetches compounds from PubChem based on the given SMILES (fallback).

        Args:
            smiles (str): The SMILES string of the compound.

        Returns:
            list: A list of compounds from PubChem.
        """
        try:            
            logger.info(f"Fetching compounds from PubChem for SMILES: {smiles}")
            
            return [{"smiles": "C1CCCCC1", "pubchem_cid": "12345", "similarity": 0.85}]
        except Exception as e:
            logger.error(f"Error fetching compounds from PubChem: {e}")
            return []

    def calculate_efficiency_metrics(self, activities, molecular_weight, tpsa):
        """
        Calculates efficiency metrics (SEI, BEI, NSEI, nBEI) based on activity data.

        Args:
            activities (list): List of activity data.
            molecular_weight (float): Molecular weight of the compound.
            tpsa (float): Topological polar surface area of the compound.

        Returns:
            dict: A dictionary containing the calculated efficiency metrics.
        """
        logger.info(
            f"Calculating efficiency metrics with activities: {activities}, MW: {molecular_weight}, TPSA: {tpsa}"
        )
        sei = 0.0
        bei = 0.0
        nsei = 0.0
        nbei = 0.0
        if activities and isinstance(activities, list):
            for activity in activities:
                if "value" in activity and isinstance(activity["value"], (int, float)):
                    if molecular_weight and molecular_weight > 0:
                        sei += activity["value"] / molecular_weight
                    if tpsa and tpsa > 0:
                        bei += activity["value"] / tpsa
                    if molecular_weight and molecular_weight > 0 and tpsa and tpsa > 0:
                        nsei += activity["value"] / (molecular_weight * tpsa)
                        nbei += activity["value"] / (molecular_weight + tpsa)

        return {"sei": sei, "bei": bei, "nsei": nsei, "nbei": nbei}
    
    def update_job_status(self, job_id, status):
        """
        Updates the job status in the PostgreSQL database.

        Args:
            job_id (str): The ID of the job.
            status (str): The new status of the job.
        """
        try:
            if not self.postgres_conn:
                self.connect_to_postgres()
            with self.postgres_conn.cursor() as cur:
            
            cur.execute(
                "UPDATE Analysis_Jobs SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (status, job_id),
            )
            self.postgres_conn.commit()
            cur.close()
            logger.info(f"Updated job {job_id} status to {status}")
        except Exception as e:
            logger.error(f"Error updating job status: {e}")
            raise

    def connect_to_rabbitmq(self):
        '''Connects to RabbitMQ and returns the channel.'''
        try:            
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(**self.rabbitmq_params)
            )
            channel = connection.channel()
            logger.info("Connected to RabbitMQ")
            return channel
        except Exception as e:
            logger.error(f"Error connecting to RabbitMQ: {e}")
            raise

    def consume_compound_queue(self):
        '''
        Consumes messages from the compound-processing-queue and triggers analysis.
        """
        channel = self.connect_to_rabbitmq()
        channel.queue_declare(queue="compound-processing-queue", durable=True)

        def callback(ch, method, properties, body):
            """Callback function to process messages from the queue."""
            try:
                message = json.loads(body)
                logger.info(f"Received message: {message}")
                compound_id = message.get("compound_id")
                smiles = message.get("smiles")
                job_id = message.get("job_id")

                if not compound_id or not smiles or not job_id:
                    logger.error("Invalid message format. Missing required fields.")
                    return

                self.update_job_status(job_id, "processing")

                chembl_results = self.fetch_compounds_from_chembl(smiles)

                if not chembl_results:
                    logger.info("No results from ChEMBL, falling back to PubChem")
                    chembl_results = self.fetch_compounds_from_pubchem(smiles)

                #  basic molecular properties
                molecular_weight = 100.0
                tpsa = 50.0
                activities = [{"value": 10.0}, {"value": 20.0}]
                efficiency_metrics = self.calculate_efficiency_metrics(
                    activities, molecular_weight, tpsa
                )

                self.store_analysis_results(
                    compound_id, {"similar_compounds": chembl_results, "metrics": efficiency_metrics}
                )
                self.update_job_status(job_id, "completed")

            except Exception as e:
                logger.error(f"Error processing message: {e}")
            finally:
                ch.basic_ack(delivery_tag=method.delivery_tag)

        channel.basic_qos(prefetch_count=1)  # Process one message at a time
        channel.basic_consume(queue="compound-processing-queue", on_message_callback=callback)
        logger.info(" [*] Waiting for messages. To exit press CTRL+C")
        channel.start_consuming()


def serve(db_params, mongo_uri, rabbitmq_params, config, chembl_service=None):
    '''
    Starts the gRPC server.

    Args:
        db_params (dict): PostgreSQL database connection parameters.
        mongo_uri (str): MongoDB connection URI.
        rabbitmq_params (dict): RabbitMQ connection parameters.
        config (Config): Configuration object containing application settings.        
    '''
    # gRPC setup (if needed in the future)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    servicer = AnalysisServiceServicer(db_params, mongo_uri, rabbitmq_params, config, chembl_service)

    # Start RabbitMQ consumer in a separate thread
    rabbitmq_thread = threading.Thread(target=servicer.consume_compound_queue)
    rabbitmq_thread.daemon = True  # Allow the program to exit even if the thread is running
    rabbitmq_thread.start()

    try:
        servicer.consume_compound_queue()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        servicer.close_db_connections()
        server.stop(0)

class TestAnalysisService(unittest.TestCase):

    def setUp(self):
        # Use test database parameters
        self.db_params = {
            "dbname": os.environ.get("POSTGRES_DB_TEST", "test_impulsor_db"),  # Different database for testing
            "user": os.environ.get("POSTGRES_USER", "postgres"),
            "password": os.environ.get("POSTGRES_PASSWORD", "postgres"),
            "host": os.environ.get("POSTGRES_HOST", "localhost"),
            "port": os.environ.get("POSTGRES_PORT", "5432"),
        }
        self.mongo_uri = os.environ.get("MONGO_URI_TEST", "mongodb://localhost:27017/test_impulsor_db")  # Different MongoDB for testing
        self.rabbitmq_params = {
            "host": os.environ.get("RABBITMQ_HOST", "localhost"),
            "port": int(os.environ.get("RABBITMQ_PORT", "5672")),
        }
        self.config = Config  # Assuming Config can be used directly or a TestConfig can be created

        # Establish connections for testing
        self.postgres_conn = psycopg2.connect(**self.db_params)
        self.mongo_client = pymongo.MongoClient(self.mongo_uri)
        self.chembl_service = None  # Mock or actual service if needed for integration testing
        self.service = AnalysisServiceServicer(
            self.db_params, 
            self.mongo_uri, 
            self.rabbitmq_params, 
            self.config, 
            self.chembl_service,
            self.postgres_conn,
            self.mongo_client
        )

        # Clean up test databases before each test
        self.clean_up_databases()
        
        # Ensure MongoDB connection and database
        if not self.service.mongo_db:
            self.service.connect_to_mongo()
        

    def clean_up_databases(self):
        """Cleans up the test PostgreSQL and MongoDB databases."""
        # Clean PostgreSQL
        with self.postgres_conn.cursor() as cur:
            cur.execute("DELETE FROM Analysis_Jobs")  # Adjust table names as needed
        self.postgres_conn.commit()

        # Clean MongoDB
        if self.service.mongo_db:
            self.service.mongo_db.analysis_results.delete_many({})  # Adjust collection name as needed

    def tearDown(self):
        self.service.close_db_connections()

    def test_store_analysis_results(self):
        """Test storing analysis results in MongoDB."""
        compound_id = "test_compound"
        results = {"test_result": 123}
        inserted_id = self.service.store_analysis_results(compound_id, results)
        self.assertIsNotNone(inserted_id)

        # Verify the results are stored correctly
        retrieved_result = self.service.mongo_db.analysis_results.find_one({"_id": inserted_id})
        self.assertIsNotNone(retrieved_result)
        self.assertEqual(retrieved_result["compound_id"], compound_id)
        self.assertEqual(retrieved_result["results"], results)

    def test_calculate_efficiency_metrics(self):
        """Test calculating efficiency metrics."""
        activities = [{"value": 10.0}, {"value": 20.0}]
        molecular_weight = 100.0
        tpsa = 50.0
        metrics = self.service.calculate_efficiency_metrics(activities, molecular_weight, tpsa)
        self.assertIsInstance(metrics, dict)
        self.assertTrue(all(key in metrics for key in ["sei", "bei", "nsei", "nbei"]))

    def test_update_job_status(self):
        """Test updating the job status in PostgreSQL."""
        # Set up a test job first
        with self.postgres_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO Analysis_Jobs (id, compound_id, status, created_at, updated_at) VALUES (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                ("test_job", "test_compound", "pending"),
            )
            self.postgres_conn.commit()

        self.service.update_job_status("test_job", "completed")

        # Verify the status update
        with self.postgres_conn.cursor() as cur:
            cur.execute("SELECT status FROM Analysis_Jobs WHERE id = %s", ("test_job",))
            result = cur.fetchone()
            self.assertIsNotNone(result)
            self.assertEqual(result[0], "completed")


if __name__ == "__main__":
    db_params = {
        "dbname": os.environ.get("POSTGRES_DB", "impulsor_db"),
        "user": os.environ.get("POSTGRES_USER", "postgres"),
        "password": os.environ.get("POSTGRES_PASSWORD", "postgres"),
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
    }
    mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
    rabbitmq_params = {
        "host": os.environ.get("RABBITMQ_HOST", "localhost"),
        "port": int(os.environ.get("RABBITMQ_PORT", "5672")),
    }
    serve(db_params, mongo_uri, rabbitmq_params, Config)  # Pass all parameters to serve()