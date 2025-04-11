import os
import logging
import json
import time
import uuid
import math
import requests
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Union

import psycopg2
import pymongo
import pika
import numpy as np
from rdkit import Chem
from rdkit.Chem import Descriptors, Lipinski

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AnalysisServicer:
    def __init__(self, 
                 db_params: Dict[str, str], 
                 mongo_uri: str,
                 mongo_db_name: str,
                 rabbitmq_params: Dict[str, Any],
                 chembl_service_url: str,
                 queue_name: str,
                 config: Any):
        """
        Initialize the Analysis Service with configuration parameters.
        
        Args:
            db_params: PostgreSQL connection parameters
            mongo_uri: MongoDB connection URI
            mongo_db_name: MongoDB database name
            rabbitmq_params: RabbitMQ connection parameters
            chembl_service_url: URL for the ChEMBL Service
            queue_name: Name of the RabbitMQ queue to consume
            config: Configuration object
        """
        self.db_params = db_params
        self.mongo_uri = mongo_uri
        self.mongo_db_name = mongo_db_name
        self.rabbitmq_params = rabbitmq_params
        self.chembl_service_url = chembl_service_url
        self.queue_name = queue_name
        self.config = config
        
        # Initialize connections to None
        self.postgres_conn = None
        self.mongo_client = None
        self.mongo_db = None
        self.rabbitmq_connection = None
        self.rabbitmq_channel = None
        
    def connect_to_postgres(self):
        """Connect to PostgreSQL database."""
        try:
            if self.postgres_conn is None or self.postgres_conn.closed:
                self.postgres_conn = psycopg2.connect(**self.db_params)
                logger.info("Connected to PostgreSQL database")
        except Exception as e:
            logger.error(f"Error connecting to PostgreSQL: {e}")
            raise
            
    def connect_to_mongo(self):
        """Connect to MongoDB database."""
        try:
            if self.mongo_client is None:
                self.mongo_client = pymongo.MongoClient(self.mongo_uri)
                self.mongo_db = self.mongo_client[self.mongo_db_name]
                logger.info("Connected to MongoDB")
        except Exception as e:
            logger.error(f"Error connecting to MongoDB: {e}")
            raise
            
    def connect_to_rabbitmq(self):
        """Connect to RabbitMQ."""
        try:
            if self.rabbitmq_connection is None or self.rabbitmq_connection.is_closed:
                self.rabbitmq_connection = pika.BlockingConnection(
                    pika.ConnectionParameters(
                        host=self.rabbitmq_params.get('host', 'localhost'),
                        port=self.rabbitmq_params.get('port', 5672),
                        heartbeat=600,  # 10 minutes heartbeat
                        blocked_connection_timeout=300  # 5 minutes timeout
                    )
                )
                self.rabbitmq_channel = self.rabbitmq_connection.channel()
                
                # Declare the queue
                self.rabbitmq_channel.queue_declare(
                    queue=self.queue_name,
                    durable=True  # Make sure the queue survives a RabbitMQ restart
                )
                
                # Set QoS - Only process one message at a time
                self.rabbitmq_channel.basic_qos(prefetch_count=1)
                
                logger.info("Connected to RabbitMQ")
        except Exception as e:
            logger.error(f"Error connecting to RabbitMQ: {e}")
            raise
            
    def close_connections(self):
        """Close all connections."""
        try:
            if self.postgres_conn is not None and not self.postgres_conn.closed:
                self.postgres_conn.close()
                logger.info("PostgreSQL connection closed")
        except Exception as e:
            logger.error(f"Error closing PostgreSQL connection: {e}")
            
        try:
            if self.mongo_client is not None:
                self.mongo_client.close()
                logger.info("MongoDB connection closed")
        except Exception as e:
            logger.error(f"Error closing MongoDB connection: {e}")
            
        try:
            if self.rabbitmq_connection is not None and self.rabbitmq_connection.is_open:
                self.rabbitmq_connection.close()
                logger.info("RabbitMQ connection closed")
        except Exception as e:
            logger.error(f"Error closing RabbitMQ connection: {e}")
            
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of an analysis job.
        
        Args:
            job_id: The ID of the job
            
        Returns:
            Optional[Dict[str, Any]]: Job information including status, or None if not found
        """
        try:
            self.connect_to_postgres()
            
            with self.postgres_conn.cursor() as cur:
                cur.execute(
                    "SELECT id, compound_id, status, progress, created_at, updated_at FROM Analysis_Jobs WHERE id = %s",
                    (job_id,)
                )
                job = cur.fetchone()
                
                if job:
                    columns = ['id', 'compound_id', 'status', 'progress', 'created_at', 'updated_at']
                    job_data = dict(zip(columns, job))
                    
                    # Convert datetime objects to ISO format strings
                    for date_field in ['created_at', 'updated_at']:
                        if job_data[date_field] and isinstance(job_data[date_field], datetime):
                            job_data[date_field] = job_data[date_field].isoformat()
                            
                    return job_data
                return None
                
        except Exception as e:
            logger.error(f"Error getting job status: {str(e)}")
            return None
            
    def get_analysis_results(self, compound_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the analysis results for a compound.
        
        Args:
            compound_id: The ID of the compound
            
        Returns:
            Optional[Dict[str, Any]]: Analysis results or None if not found
        """
        try:
            self.connect_to_mongo()
                
            collection = self.mongo_db.get_collection("analysis_results")
            result = collection.find_one({"compound_id": compound_id})
            
            if result:
                # Convert ObjectId to string for JSON serialization
                result['_id'] = str(result['_id'])
                return result
            return None
            
        except Exception as e:
            logger.error(f"Error getting analysis results: {str(e)}")
            return None
            
    def calculate_efficiency_metrics(self, activities: List[Dict[str, Any]], molecular_weight: float, tpsa: float) -> Dict[str, float]:
        """
        Calculate efficiency metrics (SEI, BEI, NSEI, nBEI, etc.).
        
        Args:
            activities: List of activity data
            molecular_weight: Molecular weight of the compound
            tpsa: Topological polar surface area of the compound
            
        Returns:
            Dict[str, float]: Calculated efficiency metrics
        """
        logger.info(f"Calculating efficiency metrics for MW: {molecular_weight}, TPSA: {tpsa}")
        
        # Initialize metrics
        sei = 0.0
        bei = 0.0
        nsei = 0.0
        nbei = 0.0
        
        try:
            # Calculate average pActivity (-log(Activity in M))
            pActivity = 0.0
            activity_count = 0
            
            for activity_data in activities:
                if 'value' in activity_data and isinstance(activity_data['value'], (int, float)):
                    # Convert to nM if not already
                    activity_nM = float(activity_data['value'])
                    
                    # Convert nM to M (1 nM = 1e-9 M)
                    activity_M = activity_nM * 1e-9
                    
                    # Calculate pActivity (-log10(activity in M))
                    if activity_M > 0:
                        pActivity -= math.log10(activity_M)
                        activity_count += 1
            
            # Calculate average pActivity
            if activity_count > 0:
                pActivity /= activity_count
                
                # Calculate efficiency metrics
                if molecular_weight and molecular_weight > 0:
                    bei = pActivity / (molecular_weight / 1000)  # Scale by MW/1000
                
                if tpsa and tpsa > 0:
                    sei = pActivity / (tpsa / 100)  # Scale by PSA/100
                
                # Calculate normalized indices
                if molecular_weight and tpsa and molecular_weight > 0 and tpsa > 0:
                    # Get heavy atom count (approximation)
                    heavy_atoms = molecular_weight / 13.0  # Approximate for organic compounds
                    
                    # Number of polar atoms (approximation)
                    polar_atoms = tpsa / 30.0  # Approximate based on typical PSA contributions
                    
                    if polar_atoms > 0:
                        nsei = sei / polar_atoms
                    
                    if heavy_atoms > 0:
                        nbei = bei - (0.23 * heavy_atoms)  # nBEI formula
        
        except Exception as e:
            logger.error(f"Error calculating efficiency metrics: {str(e)}")
            
        # Return metrics dict
        return {
            "sei": round(sei, 3),
            "bei": round(bei, 3),
            "nsei": round(nsei, 3),
            "nbei": round(nbei, 3)
        }
        
    def update_job_status(self, job_id: str, status: str, progress: float = None) -> bool:
        """
        Update the status of an analysis job.
        
        Args:
            job_id: The ID of the job
            status: The new status
            progress: Optional progress percentage (0-100)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.connect_to_postgres()
            
            with self.postgres_conn.cursor() as cur:
                if progress is not None:
                    cur.execute(
                        "UPDATE Analysis_Jobs SET status = %s, progress = %s, updated_at = NOW() WHERE id = %s",
                        (status, progress, job_id)
                    )
                else:
                    cur.execute(
                        "UPDATE Analysis_Jobs SET status = %s, updated_at = NOW() WHERE id = %s",
                        (status, job_id)
                    )
                
                self.postgres_conn.commit()
                logger.info(f"Updated job {job_id} status to {status}" + (f" ({progress:.1f}%)" if progress is not None else ""))
                return True
                
        except Exception as e:
            logger.error(f"Error updating job status: {str(e)}")
            if self.postgres_conn:
                try:
                    self.postgres_conn.rollback()
                except:
                    pass
            return False
            
    def store_analysis_results(self, compound_id: str, results: Dict[str, Any]) -> Optional[str]:
        """
        Store analysis results in MongoDB.
        
        Args:
            compound_id: The ID of the compound
            results: Analysis results to store
            
        Returns:
            Optional[str]: ID of the inserted document or None if failed
        """
        try:
            self.connect_to_mongo()
            
            # Check if results already exist for this compound
            collection = self.mongo_db.get_collection("analysis_results")
            existing = collection.find_one({"compound_id": compound_id})
            
            if existing:
                # Update existing results
                result = collection.update_one(
                    {"compound_id": compound_id},
                    {"$set": {"results": results, "updated_at": datetime.now()}}
                )
                logger.info(f"Updated analysis results for compound {compound_id}")
                return str(existing["_id"])
            else:
                # Insert new results
                result = collection.insert_one({
                    "compound_id": compound_id,
                    "results": results,
                    "created_at": datetime.now(),
                    "updated_at": datetime.now()
                })
                logger.info(f"Stored analysis results for compound {compound_id}")
                return str(result.inserted_id)
                
        except Exception as e:
            logger.error(f"Error storing analysis results: {str(e)}")
            return None
            
    def fetch_similar_compounds(self, smiles: str, similarity_threshold: int = 80) -> List[Dict[str, Any]]:
        """
        Fetch similar compounds from the ChEMBL Service.
        
        Args:
            smiles: SMILES string of the compound
            similarity_threshold: Similarity threshold (0-100)
            
        Returns:
            List[Dict[str, Any]]: List of similar compounds
        """
        try:
            url = f"{self.chembl_service_url}/similarity/{smiles}"
            params = {"similarity": similarity_threshold}
            
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                compounds = response.json()
                logger.info(f"Found {len(compounds)} similar compounds for {smiles}")
                return compounds
            else:
                logger.warning(f"ChEMBL Service returned status code {response.status_code}")
                return []
                
        except requests.RequestException as e:
            logger.error(f"Error fetching similar compounds: {str(e)}")
            return []
        
    def process_compound(self, compound_id: str, smiles: str, job_id: str) -> bool:
        """
        Process a compound by fetching similar compounds and calculating efficiency metrics.
        
        Args:
            compound_id: The ID of the compound
            smiles: SMILES string of the compound
            job_id: The ID of the analysis job
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Update job status to processing
            self.update_job_status(job_id, "processing", 0.0)
            
            # Fetch similar compounds from ChEMBL Service
            similar_compounds = self.fetch_similar_compounds(smiles)
            
            # Update progress
            self.update_job_status(job_id, "processing", 40.0)
            
            # Process each similar compound
            for i, compound in enumerate(similar_compounds):
                # Calculate proportion complete
                progress = 40.0 + (40.0 * (i + 1) / len(similar_compounds))
                self.update_job_status(job_id, "processing", progress)
                
                # Get molecule data for this compound
                chembl_id = compound.get("molecule_chembl_id")
                if not chembl_id:
                    continue
                    
                try:
                    # Fetch molecule data
                    url = f"{self.chembl_service_url}/molecules/{chembl_id}"
                    response = requests.get(url, timeout=30)
                    
                    if response.status_code == 200:
                        molecule_data = response.json()
                        
                        # Extract properties
                        compound["properties"] = {
                            "molecular_weight": molecule_data.get("molecule_properties", {}).get("full_mwt"),
                            "tpsa": molecule_data.get("molecule_properties", {}).get("psa"),
                            "hba": molecule_data.get("molecule_properties", {}).get("hba"),
                            "hbd": molecule_data.get("molecule_properties", {}).get("hbd"),
                            "num_ro5_violations": molecule_data.get("molecule_properties", {}).get("num_ro5_violations")
                        }
                        
                        # Extract activities (placeholder - in real implementation, would fetch from activities endpoint)
                        compound["activities"] = [
                            {"type": "IC50", "value": 50.0},  # Example values
                            {"type": "Ki", "value": 10.0}
                        ]
                        
                        # Calculate efficiency metrics
                        compound["metrics"] = self.calculate_efficiency_metrics(
                            compound["activities"],
                            float(compound["properties"]["molecular_weight"] or 0),
                            float(compound["properties"]["tpsa"] or 0)
                        )
                        
                except Exception as e:
                    logger.error(f"Error processing similar compound {chembl_id}: {str(e)}")
                    # Continue with next compound
            
            # Store results
            results = {
                "similar_compounds": similar_compounds,
                "analysis_date": datetime.now().isoformat()
            }
            
            result_id = self.store_analysis_results(compound_id, results)
            
            # Update job status to completed
            self.update_job_status(job_id, "completed", 100.0)
            
            return result_id is not None
            
        except Exception as e:
            logger.error(f"Error processing compound {compound_id}: {str(e)}")
            # Update job status to failed
            self.update_job_status(job_id, "failed")
            return False
    
    def start_consuming(self):
        """Start consuming messages from the RabbitMQ queue."""
        try:
            self.connect_to_rabbitmq()
            
            def callback(ch, method, properties, body):
                """
                Process messages from the queue.
                
                Args:
                    ch: Channel
                    method: Method
                    properties: Properties
                    body: Message body
                """
                try:
                    # Parse message
                    message = json.loads(body)
                    logger.info(f"Received message: {message}")
                    
                    compound_id = message.get("compound_id")
                    smiles = message.get("smiles")
                    job_id = message.get("job_id")
                    
                    if not all([compound_id, smiles, job_id]):
                        logger.error("Invalid message: missing required fields")
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                        return
                    
                    # Create analysis job record
                    self.connect_to_postgres()
                    with self.postgres_conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO Analysis_Jobs (id, compound_id, user_id, status, progress, similarity_threshold)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO UPDATE SET 
                                status = EXCLUDED.status,
                                progress = EXCLUDED.progress,
                                updated_at = NOW()
                            """,
                            (job_id, compound_id, "test_user", "pending", 0.0, 80)
                        )
                        self.postgres_conn.commit()
                    
                    # Process the compound
                    success = self.process_compound(compound_id, smiles, job_id)
                    
                    # Acknowledge message
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                    
                    logger.info(f"Processed message for compound {compound_id}" + (" successfully" if success else " with errors"))
                    
                except Exception as e:
                    logger.error(f"Error processing message: {str(e)}")
                    # Acknowledge message even if processing failed
                    # In a production system, you might want to use a dead-letter queue instead
                    ch.basic_ack(delivery_tag=method.delivery_tag)
            
            # Register the callback
            self.rabbitmq_channel.basic_consume(
                queue=self.queue_name,
                on_message_callback=callback
            )
            
            logger.info(f"Started consuming from queue: {self.queue_name}")
            
            # Start consuming (blocking)
            self.rabbitmq_channel.start_consuming()
            
        except Exception as e:
            logger.error(f"Error starting consumer: {str(e)}")
            # Try to reconnect
            time.sleep(5)
            self.start_consuming()