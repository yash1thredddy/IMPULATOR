import logging
import json
import os

import psycopg2
import pika
from typing import Dict, Tuple, Any

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
                host=self.config.db_host
            )
            logger.info("Connected to PostgreSQL database")
        except psycopg2.Error as e:
            logger.error(f"Error connecting to database: {e}")
            self.db_conn = None

    def _disconnect_db(self) -> None:
        """Disconnects from the PostgreSQL database."""
        if self.db_conn:
            self.db_conn.close()
            logger.info("Disconnected from PostgreSQL database")

    def _connect_rabbitmq(self) -> None:
        """Connects to the RabbitMQ server."""
        try:
            self.mq_connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=self.config.rabbitmq_host)
            )
            self.mq_channel = self.mq_connection.channel()
            logger.info("Connected to RabbitMQ")
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"Error connecting to RabbitMQ: {e}")
            self.mq_channel = None
            self.mq_connection = None

    def _disconnect_rabbitmq(self) -> None:
        """Disconnects from the RabbitMQ server."""
        if self.mq_connection:
            self.mq_connection.close()
            logger.info("Disconnected from RabbitMQ")

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
        # Add more validation as needed, e.g., using RDKit to validate SMILES
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

        try:
            with self.db_conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO Compounds (user_id, name, smiles, inchi_key, pubchem_cid, molecular_weight, tpsa, hbd, hba, num_atoms, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (
                    compound_data["user_id"], 
                    compound_data["name"], 
                    compound_data["smiles"],
                    compound_data.get("inchi_key"),
                    compound_data.get("pubchem_cid"),
                    compound_data.get("molecular_weight"),
                    compound_data.get("tpsa"),
                    compound_data.get("hbd"),
                    compound_data.get("hba"),
                    compound_data.get("num_atoms"),
                    "pending"  # Initial status
                ))
                compound_id = cur.fetchone()[0]
                self.db_conn.commit()
                logger.info(f"Compound '{compound_data['name']}' created with ID: {compound_id}")

                # Publish message to RabbitMQ
                if self.mq_channel:
                    self.mq_channel.queue_declare(queue=self.config.compounds_queue_name)
                    message = json.dumps({"compound_id": compound_id, "smiles": compound_data["smiles"]})
                    self.mq_channel.basic_publish(
                        exchange='',
                        routing_key=self.config.compounds_queue_name,
                        body=message
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
                cur.execute("SELECT * FROM Compounds WHERE id = %s;", (compound_id,))
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
            with self.db_conn.cursor() as cur:
                set_clause = ", ".join([f"{key} = %s" for key in compound_data.keys()])
                values = list(compound_data.values()) + [compound_id]
                cur.execute(f"UPDATE Compounds SET {set_clause} WHERE id = %s;", values)
                self.db_conn.commit()
                logger.info(f"Updated compound with ID: {compound_id}")
                return True, None
        except psycopg2.Error as e:
            if self.db_conn:
                self.db_conn.rollback()
            logger.error(f"Error updating compound: {e}")
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
                cur.execute("DELETE FROM Compounds WHERE id = %s;", (compound_id,))
                self.db_conn.commit()
                logger.info(f"Deleted compound with ID: {compound_id}")
                return True, None
        except psycopg2.Error as e:
            if self.db_conn:
                self.db_conn.rollback()
            logger.error(f"Error deleting compound: {e}")
            return False, str(e)


import unittest
from unittest.mock import patch, MagicMock

class TestCompoundService(unittest.TestCase):

    def setUp(self):
        self.service = CompoundService()
        self.test_compound = {
            "user_id": "test_user",
            "name": "Test Compound",
            "smiles": "C1=CC=CC=C1",
            "inchi_key": "TESTINCHIKEY",
            "pubchem_cid": "12345",
            "molecular_weight": 78.11,
            "tpsa": 0.0,
            "hbd": 0,
            "hba": 0,
            "num_atoms": 6
        }

    @patch.object(CompoundService, '_connect_db')
    @patch.object(CompoundService, '_disconnect_db')
    def test_validate_compound(self, mock_disconnect, mock_connect):
        # Test valid compound data
        is_valid, error = self.service._validate_compound(self.test_compound)
        self.assertTrue(is_valid)
        self.assertIsNone(error)

        # Test missing SMILES
        invalid_compound = self.test_compound.copy()
        invalid_compound["smiles"] = ""
        is_valid, error = self.service._validate_compound(invalid_compound)
        self.assertFalse(is_valid)
        self.assertEqual(error, "SMILES is required")

        # Test missing name
        invalid_compound = self.test_compound.copy()
        invalid_compound["name"] = ""
        is_valid, error = self.service._validate_compound(invalid_compound)
        self.assertFalse(is_valid)
        self.assertEqual(error, "Name is required")

    @patch.object(CompoundService, '_connect_db')
    @patch.object(CompoundService, '_disconnect_db')
    @patch.object(CompoundService, '_connect_rabbitmq')
    @patch.object(CompoundService, '_disconnect_rabbitmq')
    def test_create_compound(self, mock_disconnect_rabbitmq, mock_connect_rabbitmq, mock_disconnect_db, mock_connect_db):
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = (1,)  # Mock compound ID
        self.service.db_conn = mock_conn

        # Mock RabbitMQ channel
        mock_channel = MagicMock()
        self.service.mq_channel = mock_channel

        # Test successful compound creation
        success, result = self.service.create_compound(self.test_compound)
        self.assertTrue(success)
        self.assertEqual(result, 1)
        mock_cur.execute.assert_called()
        mock_conn.commit.assert_called()
        mock_channel.basic_publish.assert_called()

        # Test database error
        mock_cur.execute.side_effect = psycopg2.Error("Database error")
        success, result = self.service.create_compound(self.test_compound)
        self.assertFalse(success)
        self.assertEqual(result, "Database error")
        mock_conn.rollback.assert_called()

        # Test invalid compound data
        invalid_compound = self.test_compound.copy()
        invalid_compound["smiles"] = ""
        success, result = self.service.create_compound(invalid_compound)
        self.assertFalse(success)
        self.assertEqual(result, "SMILES is required")

    @patch.object(CompoundService, '_connect_db')
    @patch.object(CompoundService, '_disconnect_db')
    def test_read_compound(self, mock_disconnect_db, mock_connect_db):
        pass  # Add tests for read_compound

    @patch.object(CompoundService, '_connect_db')
    @patch.object(CompoundService, '_disconnect_db')
    def test_update_compound(self, mock_disconnect_db, mock_connect_db):
        pass  # Add tests for update_compound

    @patch.object(CompoundService, '_connect_db')
    @patch.object(CompoundService, '_disconnect_db')
    def test_delete_compound(self, mock_disconnect_db, mock_connect_db):
        pass  # Add tests for delete_compound