import os
import logging
import json
import time
import uuid
import math
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Union

import psycopg2
import pymongo
import pika
from rdkit import Chem
from rdkit.Chem import Descriptors

from chembl_client import ChEMBLClient
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AnalysisServicer:
    def __init__(self, 
                 db_params: Dict[str, str], 
                 mongo_uri: str,
                 mongo_db_name: str,
                 rabbitmq_params: Dict[str, Any],
                 chembl_service_url: Optional[str] = None,
                 queue_name: str = "compound-processing-queue",
                 config: Optional[Any] = None):
        """
        Initialize the Analysis Service with configuration parameters.
        
        Args:
            db_params: PostgreSQL connection parameters
            mongo_uri: MongoDB connection URI
            mongo_db_name: MongoDB database name
            rabbitmq_params: RabbitMQ connection parameters
            chembl_service_url: URL for the ChEMBL Service (legacy)
            queue_name: Name of the RabbitMQ queue to consume
            config: Configuration object
        """
        self.db_params = db_params
        self.mongo_uri = mongo_uri
        self.mongo_db_name = mongo_db_name
        self.rabbitmq_params = rabbitmq_params
        self.chembl_service_url = chembl_service_url
        self.queue_name = queue_name
        self.config = config or Config()
        
        # Initialize connections to None
        self.postgres_conn = None
        self.mongo_client = None
        self.mongo_db = None
        self.rabbitmq_connection = None
        self.rabbitmq_channel = None
        
        # Initialize ChEMBL client
        self.chembl_client = ChEMBLClient()
        
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
                
                # Declare the queues
                self.rabbitmq_channel.queue_declare(
                    queue=self.queue_name,
                    durable=True  # Make sure the queue survives a RabbitMQ restart
                )
                
                # Declare visualization queue
                self.rabbitmq_channel.queue_declare(
                    queue=self.config.VISUALIZATION_QUEUE,
                    durable=True
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
            
        try:
            if hasattr(self, 'chembl_client') and self.chembl_client:
                self.chembl_client.close()
                logger.info("ChEMBL client connection closed")
        except Exception as e:
            logger.error(f"Error closing ChEMBL client connection: {e}")
            
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
                    "SELECT id, compound_id, user_id, status, progress, created_at, updated_at FROM Analysis_Jobs WHERE id = %s",
                    (job_id,)
                )
                job = cur.fetchone()
                
                if job:
                    columns = ['id', 'compound_id', 'user_id', 'status', 'progress', 'created_at', 'updated_at']
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
                
            collection = self.mongo_db["analysis_results"]
            result = collection.find_one({"compound_id": compound_id})
            
            if result:
                # Convert ObjectId to string for JSON serialization
                result['_id'] = str(result['_id'])
                return result
            return None
            
        except Exception as e:
            logger.error(f"Error getting analysis results: {str(e)}")
            return None
            
    def calculate_efficiency_metrics(self, activity_value: float, molecular_weight: float, tpsa: float, 
                                    num_heavy_atoms: int, num_polar_atoms: int) -> Dict[str, float]:
        """
        Calculate efficiency metrics (SEI, BEI, NSEI, nBEI).
        
        Args:
            activity_value: Activity value in nM
            molecular_weight: Molecular weight
            tpsa: Topological polar surface area
            num_heavy_atoms: Number of heavy atoms
            num_polar_atoms: Number of polar atoms
            
        Returns:
            Dict[str, float]: Dictionary of efficiency metrics
        """
        try:
            # Convert nM to M
            activity_M = activity_value * 1e-9
            
            # Calculate pActivity (-log10(activity in M))
            pActivity = -math.log10(activity_M) if activity_M > 0 else 0
            
            # Calculate efficiency metrics
            sei = pActivity / (tpsa / 100) if tpsa and tpsa > 0 else 0
            bei = pActivity / (molecular_weight / 1000) if molecular_weight and molecular_weight > 0 else 0
            
            # Calculate normalized indices
            nsei = sei / num_polar_atoms if num_polar_atoms > 0 else 0
            nbei = bei - (0.23 * num_heavy_atoms) if bei > 0 else 0
            
            return {
                "sei": round(sei, 3),
                "bei": round(bei, 3),
                "nsei": round(nsei, 3),
                "nbei": round(nbei, 3),
                "pActivity": round(pActivity, 3)
            }
        except Exception as e:
            logger.error(f"Error calculating efficiency metrics: {str(e)}")
            return {
                "sei": 0,
                "bei": 0,
                "nsei": 0,
                "nbei": 0,
                "pActivity": 0
            }
        
    def update_job_status(self, job_id: str, status: str, progress: Optional[float] = None) -> bool:
        """
        Update the status of an analysis job.
        
        Args:
            job_id: The ID of the job
            status: The new status
            progress: Optional progress percentage (0-1)
            
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
            collection = self.mongo_db["analysis_results"]
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
            
    def process_activities(self, job_id: str, compound_id: str, chembl_id: Optional[str] = None):
        """
        Process activities for a compound.
        
        Args:
            job_id: The job ID
            compound_id: The compound ID
            chembl_id: Optional ChEMBL ID if already known
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.connect_to_postgres()
            self.connect_to_mongo()
            
            # Update job status to processing
            self.update_job_status(job_id, "processing", 0.2)
            
            # Get the compound details from the database
            with self.postgres_conn.cursor() as cur:
                if chembl_id:
                    cur.execute(
                        """
                        SELECT id, smiles, molecular_weight, tpsa, num_heavy_atoms, chembl_id
                        FROM Compounds 
                        WHERE chembl_id = %s
                        """,
                        (chembl_id,)
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, smiles, molecular_weight, tpsa, num_heavy_atoms, chembl_id
                        FROM Compounds 
                        WHERE id = %s
                        """,
                        (compound_id,)
                    )
                    
                compound = cur.fetchone()
                if not compound:
                    logger.error(f"Compound not found: {compound_id}")
                    self.update_job_status(job_id, "failed")
                    return False
                
                # Extract compound details
                c_id, smiles, molecular_weight, tpsa, num_heavy_atoms, chembl_id = compound
                
                # Check if we have a ChEMBL ID
                if not chembl_id:
                    logger.error(f"No ChEMBL ID found for compound: {compound_id}")
                    self.update_job_status(job_id, "failed")
                    return False
                
                # Get activities from ChEMBL
                activities = self.chembl_client.get_compound_activities(
                    chembl_id=chembl_id,
                    activity_types=self.config.ACTIVITY_TYPES
                )
                
                if not activities:
                    logger.warning(f"No activities found for compound: {compound_id}")
                    self.update_job_status(job_id, "completed", 1.0)
                    return True
                
                # Update job status
                self.update_job_status(job_id, "processing", 0.5)
                
                # Process each activity
                processed_activities = []
                
                # Approximate number of polar atoms based on TPSA
                num_polar_atoms = int(tpsa / 20) if tpsa else 1  # Rough estimate
                
                for activity in activities:
                    try:
                        # Check if we have a valid activity value
                        if 'value' in activity and activity['value'] > 0:
                            # Calculate efficiency metrics
                            metrics = self.calculate_efficiency_metrics(
                                activity_value=activity['value'],
                                molecular_weight=molecular_weight,
                                tpsa=tpsa,
                                num_heavy_atoms=num_heavy_atoms,
                                num_polar_atoms=num_polar_atoms
                            )
                            
                            # Create processed activity
                            processed_activity = {
                                "target_id": activity.get('target_id', ''),
                                "activity_type": activity.get('activity_type', ''),
                                "relation": activity.get('relation', '='),
                                "value": activity.get('value', 0),
                                "units": activity.get('units', 'nM'),
                                "metrics": metrics
                            }
                            
                            processed_activities.append(processed_activity)
                    except Exception as activity_error:
                        logger.error(f"Error processing activity: {activity_error}")
                        # Continue with other activities
                
                # Store results in MongoDB
                results = {
                    "compound_id": compound_id,
                    "chembl_id": chembl_id,
                    "activities": processed_activities,
                    "processing_date": datetime.now().isoformat()
                }
                
                self.store_analysis_results(compound_id, results)
                
                # Update job status
                self.update_job_status(job_id, "processing", 0.8)
                
                # Send message to visualization queue
                self.send_to_visualization_queue(job_id, compound_id)
                
                # Update job status to completed
                self.update_job_status(job_id, "completed", 1.0)
                return True
                
        except Exception as e:
            logger.error(f"Error processing activities: {str(e)}")
            self.update_job_status(job_id, "failed")
            return False
            
    def send_to_visualization_queue(self, job_id: str, compound_id: str):
        """
        Send a message to the visualization queue.
        
        Args:
            job_id: The job ID
            compound_id: The compound ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.connect_to_rabbitmq()
            
            message = json.dumps({
                "job_id": job_id,
                "compound_id": compound_id
            })
            
            self.rabbitmq_channel.basic_publish(
                exchange='',
                routing_key=self.config.VISUALIZATION_QUEUE,
                body=message,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                )
            )
            
            logger.info(f"Sent message to visualization queue for job {job_id}")
            return True
        except Exception as e:
            logger.error(f"Error sending message to visualization queue: {str(e)}")
            return False
            
    def process_message(self, message_body: str):
        """
        Process a message from the RabbitMQ queue.
        
        Args:
            message_body: The message body
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Parse message
            message = json.loads(message_body)
            logger.info(f"Processing message: {message}")
            
            job_id = message.get("job_id")
            compound_id = message.get("compound_id")
            smiles = message.get("smiles")
            similarity_threshold = message.get("similarity_threshold", 80)
            
            if not all([job_id, compound_id]):
                logger.error("Invalid message: missing required fields")
                return False
            
            # Process activities for the compound
            success = self.process_activities(job_id, compound_id)
            
            # Get similar compounds from the database
            self.connect_to_postgres()
            with self.postgres_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT c.id, c.chembl_id 
                    FROM Compounds c 
                    JOIN Analysis_Jobs j ON c.user_id = j.user_id 
                    WHERE j.id = %s AND c.id != %s
                    """,
                    (job_id, compound_id)
                )
                similar_compounds = cur.fetchall()
            
            # Process activities for each similar compound
            for sim_id, sim_chembl_id in similar_compounds:
                if sim_chembl_id:  # Skip compounds without ChEMBL ID
                    self.process_activities(job_id, sim_id, sim_chembl_id)
            
            return success
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
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
                    # Process the message
                    success = self.process_message(body)
                    
                    # Acknowledge message
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                    
                    logger.info(f"Processed message" + (" successfully" if success else " with errors"))
                    
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