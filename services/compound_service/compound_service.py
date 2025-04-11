import logging
import json
import os
import uuid
from typing import Dict, List, Tuple, Any

import psycopg2
import pika
from rdkit import Chem
from rdkit.Chem import Descriptors, Lipinski

from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CompoundService:
    def __init__(self):
        self.config = Config()
        self.db_conn = None
        self.mq_channel = None
        self.mq_connection = None

    def _connect_db(self) -> None:
        """Connects to the PostgreSQL database."""
        try:
            self.db_conn = psycopg2.connect(
                dbname=self.config.db_name, 
                user=self.config.db_user, 
                password=self.config.db_password, 
                host=self.config.db_host,
                port=self.config.db_port
            )
            logger.info("Connected to PostgreSQL database")
        except psycopg2.Error as e:
            logger.error(f"Error connecting to database: {e}")
            self.db_conn = None
            raise

    def _disconnect_db(self) -> None:
        """Disconnects from the PostgreSQL database."""
        if self.db_conn:
            self.db_conn.close()
            self.db_conn = None
            logger.info("Disconnected from PostgreSQL database")

    def _connect_rabbitmq(self) -> None:
        """Connects to the RabbitMQ server."""
        try:
            self.mq_connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=self.config.rabbitmq_host,
                    port=self.config.rabbitmq_port
                )
            )
            self.mq_channel = self.mq_connection.channel()
            # Declare the queue
            self.mq_channel.queue_declare(queue=self.config.compounds_queue_name, durable=True)
            logger.info("Connected to RabbitMQ")
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"Error connecting to RabbitMQ: {e}")
            self.mq_channel = None
            self.mq_connection = None
            raise

    def _disconnect_rabbitmq(self) -> None:
        """Disconnects from the RabbitMQ server."""
        if self.mq_connection and self.mq_connection.is_open:
            self.mq_connection.close()
            self.mq_channel = None
            self.mq_connection = None
            logger.info("Disconnected from RabbitMQ")

    def _calculate_molecular_properties(self, smiles: str) -> Dict[str, Any]:
        """Calculates molecular properties using RDKit.
        
        Args:
            smiles (str): SMILES string of the molecule
            
        Returns:
            Dict[str, Any]: Dictionary of calculated properties
        """
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                logger.warning(f"Invalid SMILES string: {smiles}")
                return {}
                
            properties = {
                'molecular_weight': Descriptors.MolWt(mol),
                'tpsa': Descriptors.TPSA(mol),
                'hbd': Lipinski.NumHDonors(mol),
                'hba': Lipinski.NumHAcceptors(mol),
                'num_atoms': mol.GetNumAtoms(),
                'inchi_key': Chem.inchi.MolToInchiKey(mol) if hasattr(Chem, 'inchi') else None
            }
            
            return properties
        except Exception as e:
            logger.error(f"Error calculating molecular properties: {e}")
            return {}

    def _validate_compound(self, compound_data: Dict) -> Tuple[bool, str]:
        """Validates compound data.

        Args:
            compound_data (Dict): Dictionary containing compound data.

        Returns:
            Tuple[bool, str]: (True, None) if valid, (False, error message) otherwise.
        """
        if not compound_data.get("smiles"):
            return False, "SMILES is required"
        if not compound_data.get("name"):
            return False, "Name is required"
            
        # Validate SMILES using RDKit
        mol = Chem.MolFromSmiles(compound_data.get("smiles", ""))
        if mol is None:
            return False, "Invalid SMILES string"
            
        return True, None

    def create_compound(self, compound_data: Dict) -> Tuple[bool, Any]:
        """Creates a new compound in the database.

        Args:
            compound_data (Dict): Dictionary containing compound data.

        Returns:
            Tuple[bool, Any]: (True, compound_id) if successful, (False, error message) otherwise.
        """
        if not self.db_conn:
            self._connect_db()
        if not self.mq_channel:
            self._connect_rabbitmq()
            
        is_valid, error_message = self._validate_compound(compound_data)
        if not is_valid:
            logger.warning(f"Invalid compound data: {error_message}")
            return False, error_message

        # Calculate molecular properties if not provided
        if "smiles" in compound_data:
            properties = self._calculate_molecular_properties(compound_data["smiles"])
            for key, value in properties.items():
                if key not in compound_data or not compound_data[key]:
                    compound_data[key] = value

        try:
            with self.db_conn.cursor() as cur:
                # Check if compound with same ID already exists
                if "id" in compound_data:
                    cur.execute("SELECT id FROM Compounds WHERE id = %s", (compound_data["id"],))
                    if cur.fetchone():
                        return False, "Compound with this ID already exists"
                
                # Prepare columns and values for insertion
                columns = ["id", "user_id", "name", "smiles", "status"]
                values = [
                    compound_data.get("id", str(uuid.uuid4())),
                    compound_data.get("user_id"),
                    compound_data.get("name"),
                    compound_data.get("smiles"),
                    compound_data.get("status", "pending")
                ]
                
                # Add optional fields if present
                optional_fields = [
                    "inchi_key", "pubchem_cid", "molecular_weight", 
                    "tpsa", "hbd", "hba", "num_atoms"
                ]
                
                for field in optional_fields:
                    if field in compound_data and compound_data[field] is not None:
                        columns.append(field)
                        values.append(compound_data[field])
                
                # Build the SQL query
                placeholders = ", ".join(["%s"] * len(columns))
                column_names = ", ".join(columns)
                
                # Execute the query
                cur.execute(
                    f"INSERT INTO Compounds ({column_names}) VALUES ({placeholders}) RETURNING id",
                    values
                )
                compound_id = cur.fetchone()[0]
                self.db_conn.commit()
                logger.info(f"Compound '{compound_data['name']}' created with ID: {compound_id}")

                # Publish message to RabbitMQ
                if self.mq_channel:
                    message = json.dumps({
                        "compound_id": compound_id, 
                        "smiles": compound_data["smiles"],
                        "job_id": str(uuid.uuid4())  # Generate a new UUID for the analysis job
                    })
                    self.mq_channel.basic_publish(
                        exchange='',
                        routing_key=self.config.compounds_queue_name,
                        body=message,
                        properties=pika.BasicProperties(
                            delivery_mode=2,  # Make message persistent
                        )
                    )
                    logger.info(f"Published message to '{self.config.compounds_queue_name}' for compound ID: {compound_id}")
                else:
                    logger.warning(f"Failed to publish message: Not connected to RabbitMQ")

                return True, compound_id
        except psycopg2.Error as e:
            if self.db_conn:
                self.db_conn.rollback()
            logger.error(f"Error creating compound: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Unexpected error creating compound: {e}")
            return False, str(e)

    def read_compound(self, compound_id: str) -> Tuple[Dict, str]:
        """Reads a compound from the database by ID.

        Args:
            compound_id (str): The ID of the compound to read.

        Returns:
            Tuple[Dict, str]: (compound data, None) if successful, (None, error message) otherwise.
        """
        if not self.db_conn:
            self._connect_db()
        try:
            with self.db_conn.cursor() as cur:
                cur.execute("SELECT * FROM Compounds WHERE id = %s", (compound_id,))
                compound = cur.fetchone()
                if compound:
                    columns = [desc[0] for desc in cur.description]
                    compound_data = dict(zip(columns, compound))
                    logger.info(f"Read compound with ID: {compound_id}")
                    return compound_data, None
                else:
                    logger.warning(f"Compound with ID '{compound_id}' not found")
                    return None, "Compound not found"
        except psycopg2.Error as e:
            logger.error(f"Error reading compound: {e}")
            return None, str(e)
        except Exception as e:
            logger.error(f"Unexpected error reading compound: {e}")
            return None, str(e)

    def update_compound(self, compound_id: str, compound_data: Dict) -> Tuple[bool, str]:
        """Updates a compound in the database.

        Args:
            compound_id (str): The ID of the compound to update.
            compound_data (Dict): Dictionary containing the data to update.

        Returns:
            Tuple[bool, str]: (True, None) if successful, (False, error message) otherwise.
        """
        if not self.db_conn:
            self._connect_db()
        try:
            # Check if the compound exists
            with self.db_conn.cursor() as cur:
                cur.execute("SELECT id FROM Compounds WHERE id = %s", (compound_id,))
                if not cur.fetchone():
                    return False, "Compound not found"
                
                # Don't allow updating the ID
                if "id" in compound_data:
                    del compound_data["id"]
                
                # Don't update created_at
                if "created_at" in compound_data:
                    del compound_data["created_at"]
                
                # If SMILES is updated, recalculate molecular properties
                if "smiles" in compound_data:
                    is_valid, error = self._validate_compound({"smiles": compound_data["smiles"], "name": "temp"})
                    if not is_valid:
                        return False, error
                    
                    properties = self._calculate_molecular_properties(compound_data["smiles"])
                    for key, value in properties.items():
                        compound_data[key] = value
                
                if not compound_data:
                    return True, None  # Nothing to update
                
                # Build update query
                set_clause = ", ".join([f"{key} = %s" for key in compound_data.keys()])
                set_clause += ", updated_at = NOW()"  # Always update the updated_at timestamp
                
                values = list(compound_data.values())
                values.append(compound_id)  # For the WHERE clause
                
                cur.execute(f"UPDATE Compounds SET {set_clause} WHERE id = %s", values)
                self.db_conn.commit()
                
                if cur.rowcount > 0:
                    logger.info(f"Updated compound with ID: {compound_id}")
                    return True, None
                else:
                    logger.warning(f"No changes made to compound with ID: {compound_id}")
                    return False, "No changes made"
                    
        except psycopg2.Error as e:
            if self.db_conn:
                self.db_conn.rollback()
            logger.error(f"Error updating compound: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Unexpected error updating compound: {e}")
            return False, str(e)

    def delete_compound(self, compound_id: str) -> Tuple[bool, str]:
        """Deletes a compound from the database by ID.

        Args:
            compound_id (str): The ID of the compound to delete.

        Returns:
            Tuple[bool, str]: (True, None) if successful, (False, error message) otherwise.
        """
        if not self.db_conn:
            self._connect_db()
        try:
            with self.db_conn.cursor() as cur:
                # Check if the compound exists
                cur.execute("SELECT id FROM Compounds WHERE id = %s", (compound_id,))
                if not cur.fetchone():
                    return False, "Compound not found"
                
                # Delete related records in other tables
                # For now, just delete the compound - in a real system, you might want cascade deletes
                cur.execute("DELETE FROM Compounds WHERE id = %s", (compound_id,))
                self.db_conn.commit()
                
                if cur.rowcount > 0:
                    logger.info(f"Deleted compound with ID: {compound_id}")
                    return True, None
                else:
                    logger.warning(f"Failed to delete compound with ID: {compound_id}")
                    return False, "Delete operation failed"
                    
        except psycopg2.Error as e:
            if self.db_conn:
                self.db_conn.rollback()
            logger.error(f"Error deleting compound: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Unexpected error deleting compound: {e}")
            return False, str(e)
            
    def list_compounds(self) -> Tuple[List[Dict], str]:
        """Lists all compounds from the database.

        Returns:
            Tuple[List[Dict], str]: (list of compounds, None) if successful, (None, error message) otherwise.
        """
        if not self.db_conn:
            self._connect_db()
        try:
            with self.db_conn.cursor() as cur:
                cur.execute("SELECT * FROM Compounds;")
                compounds = cur.fetchall()
                if compounds:
                    columns = [desc[0] for desc in cur.description]
                    compound_list = [dict(zip(columns, compound)) for compound in compounds]
                    logger.info(f"Retrieved {len(compound_list)} compounds")
                    return compound_list, None
                else:
                    logger.info("No compounds found")
                    return [], None
        except psycopg2.Error as e:
            logger.error(f"Error listing compounds: {e}")
            return None, str(e)
        except Exception as e:
            logger.error(f"Unexpected error listing compounds: {e}")
            return None, str(e)