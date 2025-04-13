import logging
import json
import os
import uuid
from typing import Dict, List, Tuple, Any, Optional

import psycopg2
import pika
from rdkit import Chem
from rdkit.Chem import Descriptors, Lipinski, QED, Crippen, MolSurf

from config import Config
from chembl_client import ChEMBLClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CompoundService:
    def __init__(self):
        self.config = Config()
        self.db_conn = None
        self.mq_channel = None
        self.mq_connection = None
        self.chembl_client = ChEMBLClient()

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
        """
        Calculates molecular properties using RDKit.
        
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
                'tpsa': MolSurf.TPSA(mol),
                'hbd': Lipinski.NumHDonors(mol),
                'hba': Lipinski.NumHAcceptors(mol),
                'num_atoms': mol.GetNumAtoms(),
                'num_heavy_atoms': mol.GetNumHeavyAtoms(),
                'num_rotatable_bonds': Lipinski.NumRotatableBonds(mol),
                'num_rings': Chem.rdMolDescriptors.CalcNumRings(mol),
                'qed': QED.qed(mol),
                'logp': Crippen.MolLogP(mol),
                'inchi_key': Chem.inchi.MolToInchiKey(mol) if hasattr(Chem, 'inchi') else None
            }
            
            logger.info(f"Calculated properties for SMILES: {smiles}")
            return properties
        except Exception as e:
            logger.error(f"Error calculating molecular properties: {e}")
            return {}

    def _validate_compound(self, compound_data: Dict) -> Tuple[bool, str]:
        """
        Validates compound data.

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

    def _check_compound_exists(self, smiles: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a compound with the given SMILES already exists.
        
        Args:
            smiles: SMILES string of the compound
            
        Returns:
            Tuple[bool, Optional[str]]: (True, compound_id) if exists, (False, None) otherwise
        """
        if not self.db_conn:
            self._connect_db()
            
        try:
            with self.db_conn.cursor() as cur:
                cur.execute("SELECT id FROM Compounds WHERE smiles = %s", (smiles,))
                result = cur.fetchone()
                if result:
                    logger.info(f"Compound with SMILES {smiles} already exists with ID: {result[0]}")
                    return True, result[0]
                return False, None
        except Exception as e:
            logger.error(f"Error checking if compound exists: {e}")
            return False, None

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
        
        # Check if the compound already exists
        exists, existing_id = self._check_compound_exists(compound_data["smiles"])
        if exists:
            # Check if there's already an analysis job for this compound
            with self.db_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT j.id, j.status 
                    FROM Analysis_Jobs j 
                    JOIN Compound_Job_Relations r ON j.id = r.job_id
                    WHERE r.compound_id = %s AND r.is_primary = TRUE
                    """,
                    (existing_id,)
                )
                existing_job = cur.fetchone()
                
                if existing_job and existing_job[1] in ['completed', 'processing']:
                    # Return the existing job ID instead of creating a new one
                    logger.info(f"Found existing analysis job {existing_job[0]} for compound {existing_id}")
                    return True, existing_id
            
            # Return the existing compound ID
            return True, existing_id

        # Calculate molecular properties
        properties = self._calculate_molecular_properties(compound_data["smiles"])
        for key, value in properties.items():
            compound_data[key] = value
        
        # Try to find ChEMBL ID for the compound
        if 'inchi_key' in properties and properties['inchi_key']:
            # The get_molecule_data_by_inchi_key method doesn't exist
            # Instead, we'll use the get_similar_compounds method with a high similarity threshold
            similar_compounds = self.chembl_client.get_similar_compounds(
                smiles=compound_data["smiles"],
                similarity_threshold=100  # Exact match only
            )
            if similar_compounds and len(similar_compounds) > 0:
                compound_data['chembl_id'] = similar_compounds[0]['chembl_id']

        try:
            with self.db_conn.cursor() as cur:
                # Generate ID if not provided
                if "id" not in compound_data:
                    compound_data["id"] = str(uuid.uuid4())
                
                # Prepare columns and values for insertion
                columns = ["id", "user_id", "name", "smiles", "status"]
                values = [
                    compound_data.get("id"),
                    compound_data.get("user_id"),
                    compound_data.get("name"),
                    compound_data.get("smiles"),
                    compound_data.get("status", "pending")
                ]
                
                # Add optional fields if present
                optional_fields = [
                    "inchi_key", "pubchem_cid", "molecular_weight", 
                    "tpsa", "hbd", "hba", "num_atoms", "num_heavy_atoms",
                    "num_rotatable_bonds", "num_rings", "qed", "logp",
                    "kingdom", "superclass", "class", "subclass", "chembl_id"
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

                # Create a new analysis job
                job_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO Analysis_Jobs 
                    (id, compound_id, user_id, status, progress, similarity_threshold) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (job_id, compound_id, compound_data.get("user_id"), "pending", 0.0, 
                    compound_data.get("similarity_threshold", 80))
                )
                self.db_conn.commit()
                logger.info(f"Created analysis job with ID: {job_id} for compound ID: {compound_id}")
                
                # Create relation between compound and job (primary compound)
                cur.execute(
                    """
                    INSERT INTO Compound_Job_Relations 
                    (compound_id, job_id, is_primary, created_at) 
                    VALUES (%s, %s, %s, NOW())
                    """,
                    (compound_id, job_id, True)
                )
                self.db_conn.commit()

                # Get similar compounds using ChEMBL Service
                similar_compounds = self.chembl_client.get_similar_compounds(
                    smiles=compound_data["smiles"],
                    similarity_threshold=compound_data.get("similarity_threshold", 80)
                )
                
                # Store each similar compound in the database
                for similar_compound in similar_compounds:
                    # Extract and update properties
                    similar_properties = similar_compound.get('properties', {})
                    similar_compound_id = str(uuid.uuid4())
                    similar_data = {
                        "id": similar_compound_id,
                        "user_id": compound_data.get("user_id"),
                        "name": similar_compound.get('molecule_name', 'Unknown'),
                        "smiles": similar_compound.get('canonical_smiles'),
                        "status": "completed",
                        "chembl_id": similar_compound.get('chembl_id'),
                        "molecular_weight": similar_properties.get('molecular_weight'),
                        "tpsa": similar_properties.get('psa'),
                        "hbd": similar_properties.get('hbd'),
                        "hba": similar_properties.get('hba'),
                        "num_heavy_atoms": similar_properties.get('num_heavy_atoms')
                    }
                    
                    # Skip if SMILES is missing
                    if not similar_data["smiles"]:
                        continue
                    
                    # Calculate any missing properties with RDKit
                    if not all(key in similar_properties for key in ['molecular_weight', 'psa', 'hbd', 'hba']):
                        missing_props = self._calculate_molecular_properties(similar_data["smiles"])
                        for key, value in missing_props.items():
                            if key not in similar_data or not similar_data[key]:
                                similar_data[key] = value
                    
                    # Get classification if InChIKey is available
                    if 'inchi_key' in similar_data and similar_data['inchi_key']:
                        classification = self.chembl_client.get_compound_classification(similar_data['inchi_key'])
                        if classification:
                            similar_data.update(classification)
                    
                    # Prepare columns and values for insertion
                    sim_columns = []
                    sim_values = []
                    for key, value in similar_data.items():
                        if value is not None:
                            sim_columns.append(key)
                            sim_values.append(value)
                    
                    # Build and execute query
                    sim_placeholders = ", ".join(["%s"] * len(sim_columns))
                    sim_column_names = ", ".join(sim_columns)
                    
                    try:
                        cur.execute(
                            f"INSERT INTO Compounds ({sim_column_names}) VALUES ({sim_placeholders}) RETURNING id",
                            sim_values
                        )
                        
                        # Get the ID of the inserted similar compound
                        inserted_similar_id = cur.fetchone()[0]
                        
                        # Create a relationship between this similar compound and the original job
                        cur.execute(
                            """
                            INSERT INTO Compound_Job_Relations 
                            (compound_id, job_id, is_primary, created_at) 
                            VALUES (%s, %s, %s, NOW())
                            """,
                            (inserted_similar_id, job_id, False)
                        )
                        
                    except Exception as e:
                        logger.error(f"Error inserting similar compound: {e}")
                        # Continue with other compounds
                        continue
                
                self.db_conn.commit()
                logger.info(f"Stored {len(similar_compounds)} similar compounds for compound ID: {compound_id}")

                # Publish message to RabbitMQ for further analysis
                if self.mq_channel:
                    message = json.dumps({
                        "job_id": job_id,
                        "compound_id": compound_id,
                        "smiles": compound_data["smiles"],
                        "similarity_threshold": compound_data.get("similarity_threshold", 80)
                    })
                    self.mq_channel.basic_publish(
                        exchange='',
                        routing_key=self.config.compounds_queue_name,
                        body=message,
                        properties=pika.BasicProperties(
                            delivery_mode=2,  # Make message persistent
                        )
                    )
                    logger.info(f"Published message to '{self.config.compounds_queue_name}' for job ID: {job_id}")
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
                    
                    # Get associated analysis job
                    cur.execute("SELECT id FROM Analysis_Jobs WHERE compound_id = %s", (compound_id,))
                    job = cur.fetchone()
                    if job:
                        compound_data['analysis_job_id'] = job[0]
                    
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
            
    def list_user_compounds(self, user_id: str) -> Tuple[List[Dict], str]:
        """Lists all compounds for a specific user from the database.

        Args:
            user_id (str): The ID of the user.

        Returns:
            Tuple[List[Dict], str]: (list of compounds, None) if successful, (None, error message) otherwise.
        """
        if not self.db_conn:
            self._connect_db()
        try:
            with self.db_conn.cursor() as cur:
                cur.execute("""
                    SELECT c.*, j.id as job_id, j.status as job_status 
                    FROM Compounds c 
                    LEFT JOIN Analysis_Jobs j ON c.id = j.compound_id 
                    WHERE c.user_id = %s
                """, (user_id,))
                compounds = cur.fetchall()
                if compounds:
                    columns = [desc[0] for desc in cur.description]
                    compound_list = [dict(zip(columns, compound)) for compound in compounds]
                    logger.info(f"Retrieved {len(compound_list)} compounds for user {user_id}")
                    return compound_list, None
                else:
                    logger.info(f"No compounds found for user {user_id}")
                    return [], None
        except psycopg2.Error as e:
            logger.error(f"Error listing compounds for user {user_id}: {e}")
            return None, str(e)
        except Exception as e:
            logger.error(f"Unexpected error listing compounds for user {user_id}: {e}")
            return None, str(e)