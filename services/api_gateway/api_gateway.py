import os
import jwt
import psycopg2
import bcrypt
import logging
from datetime import datetime, timedelta
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Function to connect to the PostgreSQL database
def connect_to_db():
    """Connects to the PostgreSQL database using configuration parameters."""
    try:
        conn = psycopg2.connect(
            dbname=Config.POSTGRES_DB,
            user=Config.POSTGRES_USER,
            password=Config.POSTGRES_PASSWORD,
            host=Config.POSTGRES_HOST,
            port=Config.POSTGRES_PORT,
        )
        return conn
    except psycopg2.Error as e:
        print(f"Error connecting to database: {e}")
        return None

def register_user(user_data):
    """Registers a new user with the provided data."""
    try:
        conn = connect_to_db()
        if not conn:
            return {"error": "Database connection failed"}, 500

        with conn.cursor() as cur:
            # Check if user already exists
            cur.execute("SELECT id FROM users WHERE email = %s", (user_data['email'],))
            if cur.fetchone():
                logger.warning(f"Registration failed: User with email {user_data['email']} already exists.")
                return {"error": "User already exists"}, 400

            # Hash the password
            hashed_password = bcrypt.hashpw(user_data['password'].encode('utf-8'), bcrypt.gensalt())

            # Insert the new user
            cur.execute(
                "INSERT INTO users (username, email, password_hash, role, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (user_data['username'], user_data['email'], hashed_password.decode('utf-8'), user_data.get('role', 'user'), datetime.now(), datetime.now())
            )
            user_id = cur.fetchone()[0]
            conn.commit()
            logger.info(f"User {user_data['username']} registered successfully with ID: {user_id}.")
            return {"message": "User registered successfully", "user_id": user_id}, 201
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error during registration: {e}")
        return {"error": str(e)}, 500
    except Exception as e:
        logger.error(f"An unexpected error occurred during registration: {e}")
        return {"error": str(e)}, 500
    finally:
        if conn:
            close_db_connection(conn)


def login_user(user_data):
    """Logs in a user with the provided credentials."""
    try:
        conn = connect_to_db()
        if not conn:
            return {"error": "Database connection failed"}, 500

        with conn.cursor() as cur:
            cur.execute("SELECT id, password_hash, role FROM users WHERE email = %s", (user_data['email'],))
            user = cur.fetchone()

            if not user:
                logger.warning(f"Login failed: User with email {user_data['email']} not found.")
                return {"error": "Invalid email or password"}, 401

            user_id, hashed_password, role = user

            if not bcrypt.checkpw(user_data['password'].encode('utf-8'), hashed_password.encode('utf-8')):
                logger.warning(f"Login failed: Incorrect password for user {user_data['email']}.")
                return {"error": "Invalid email or password"}, 401

            token = generate_jwt_token(user_id, role)
            logger.info(f"User {user_data['email']} logged in successfully.")
            return {"token": token}, 200

    except psycopg2.Error as e:
        logger.error(f"Database error during login: {e}")
        return {"error": str(e)}, 500
    except Exception as e:
        logger.error(f"An unexpected error occurred during login: {e}")
        return {"error": str(e)}, 500
    finally:
        if conn:
            close_db_connection(conn)


def update_user(user_id, user_data):
    """Updates an existing user's information."""
    try:
        conn = connect_to_db()
        if not conn:
            return {"error": "Database connection failed"}, 500

        with conn.cursor() as cur:
            update_fields = []
            values = []
            for key, value in user_data.items():
                if key not in ['id', 'created_at', 'password']:  # Exclude id, created_at, and password from updates
                    update_fields.append(f"{key} = %s")
                    values.append(value)
                elif key == 'password':  # If password is being updated, hash it
                    hashed_password = bcrypt.hashpw(value.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    update_fields.append("password_hash = %s")  # Use password_hash column
                    values.append(hashed_password)

            if not update_fields:  # If no fields to update
                return {"message": "No fields to update"}, 200

            values.append(datetime.now())  # Add updated_at timestamp
            values.append(user_id)  # Add user_id for the WHERE clause
            update_query = "UPDATE users SET " + ", ".join(update_fields) + ", updated_at = %s WHERE id = %s"
            cur.execute(update_query, tuple(values))
            conn.commit()
            logger.info(f"User with ID {user_id} updated successfully.")
            return {"message": "User updated successfully"}, 200

    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error during user update: {e}")
        return {"error": str(e)}, 500
    except Exception as e:
        logger.error(f"An unexpected error occurred during user update: {e}")
        return {"error": str(e)}, 500
    finally:
        if conn:
            close_db_connection(conn)


def generate_jwt_token(user_id, role):
    """Generates a JWT token for a given user ID and role."""
    payload = {
        'user_id': user_id,
        'role': role,
        'exp': datetime.utcnow() + timedelta(hours=Config.JWT_EXPIRATION_TIME)
    }
    token = jwt.encode(payload, Config.JWT_SECRET_KEY, algorithm=Config.JWT_ALGORITHM)
    logger.debug(f"Generated JWT token for user ID: {user_id}, Role: {role}.")
    return token


def validate_jwt_token(token):
    """Validates a JWT token and returns the payload if valid."""
    try:
        payload = jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=[Config.JWT_ALGORITHM])
        logger.debug(f"Validated JWT token. Payload: {payload}")
        return payload, 200  # Return payload and success status
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token has expired.")
        return {"error": "Token has expired"}, 401
    except jwt.InvalidTokenError:
        logger.error("Invalid JWT token.")
        return {"error": "Invalid token"}, 401
    except Exception as e:
        logger.error(f"An unexpected error occurred during token validation: {e}")
        return {"error": str(e)}, 500


def close_db_connection(conn):
    """Closes the database connection."""
    try:
        if conn and not conn.closed:
            conn.close()
            logger.info("Database connection closed successfully.")
    except psycopg2.Error as e:
        logger.error(f"Error closing database connection: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while closing the database connection: {e}")


def main():
    """Main function to run the API Gateway logic (if needed)."""
    # This function can be expanded to include API Gateway functionalities like request routing,
    # authentication enforcement, etc., depending on how you structure your overall application.
    # For example, if using a framework like Flask or FastAPI, you would define your routes and
    # middleware here.  If using gRPC, this might involve starting a gRPC server.

    # For this example, we'll simply log a message indicating the gateway is ready.
    logger.info("API Gateway is ready and awaiting requests.")

    # Example usage (for testing purposes, remove or adapt for your application):
    # In a real application, you would likely integrate this with a web framework or gRPC server.
    # For instance, with Flask:
    #
    # from flask import Flask, request, jsonify
    # app = Flask(__name__)
    #
    # @app.route('/register', methods=['POST'])
    # def register():
    #     user_data = request.get_json()
    #     result, status_code = register_user(user_data)
    #     return jsonify(result), status_code
    #
    # # ... other routes (login, update, etc.) ...
    #
    # if __name__ == '__main__':
    #     app.run(debug=True, port=Config.API_GATEWAY_PORT)  # Use port from config
    pass


if __name__ == "__main__":
    main()


import unittest
from unittest.mock import patch

class TestAPIGateway(unittest.TestCase):

    def setUp(self):
        # Set up a test database connection (you might want to use an in-memory database for testing)
        self.conn = connect_to_db()
        # You can also mock the database connection if you don't want to interact with a real database during tests
        # For example:
        # with patch('psycopg2.connect') as mock_connect:
        #     mock_conn = mock_connect.return_value
        #     mock_conn.cursor.return_value = MagicMock()  # Mock the cursor object
        #     self.conn = mock_conn

    def tearDown(self):
        # Close the test database connection
        if self.conn:
            close_db_connection(self.conn)
        # If you mocked the connection, you might need to clean up the mock here

    def test_register_user(self):
        # Test user registration
        user_data = {"username": "testuser", "email": "test@example.com", "password": "password"}
        result, status_code = register_user(user_data)
        self.assertEqual(status_code, 201)
        self.assertIn("message", result)

    def test_register_existing_user(self):
        # Test registration attempt with an existing email
        user_data = {"username": "testuser", "email": "existing@example.com", "password": "password"}
        # Assuming you have a way to pre-populate the database for testing, or you can run test_register_user first
        result, status_code = register_user(user_data)
        self.assertEqual(status_code, 400)
        self.assertIn("error", result)

    def test_login_user(self):
        # Test user login
        user_data = {"email": "test@example.com", "password": "password"}  # Use the same email as in test_register_user
        # Assuming the user from test_register_user exists in the database
        result, status_code = login_user(user_data)
        self.assertEqual(status_code, 200)
        self.assertIn("token", result)

    def test_login_invalid_user(self):
        # Test login with invalid credentials
        user_data = {"email": "invalid@example.com", "password": "wrongpassword"}
        result, status_code = login_user(user_data)
        self.assertEqual(status_code, 401)
        self.assertIn("error", result)

    def test_update_user(self):
        # Test updating user information
        # Assuming you have a way to get a valid user_id (e.g., from a pre-populated database or after registering a user)
        # For this example, we'll assume user_id 1 exists
        user_id = 1  # Replace with a valid user ID
        update_data = {"username": "updateduser"}
        result, status_code = update_user(user_id, update_data)
        if status_code == 500:  # Handle potential database error during setup
            self.skipTest(f"Could not perform user update test due to database error: {result['error']}")
        self.assertEqual(status_code, 200)
        self.assertIn("message", result)

    def test_update_user_password(self):
        # Test updating user password
        user_id = 1  # Replace with a valid user ID
        update_data = {"password": "newpassword"}
        result, status_code = update_user(user_id, update_data)
        if status_code == 500:
            self.skipTest(f"Could not perform password update test due to database error: {result['error']}")
        self.assertEqual(status_code, 200)
        self.assertIn("message", result)

    def test_generate_jwt_token(self):
        # Test JWT token generation
        user_id = 1
        role = "user"
        token = generate_jwt_token(user_id, role)
        self.assertIsInstance(token, str)

    def test_validate_jwt_token(self):
        # Test JWT token validation
        user_id = 1
        role = "user"
        token = generate_jwt_token(user_id, role)
        payload, status_code = validate_jwt_token(token)
        self.assertEqual(status_code, 200)
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload['user_id'], user_id)
        self.assertEqual(payload['role'], role)

    def test_validate_expired_jwt_token(self):
        # Test validation of an expired JWT token
        # Create a token with a past expiration time for testing
        payload = {
            'user_id': 1,
            'role': 'user',
            'exp': datetime.utcnow() - timedelta(hours=1)  # Token expired 1 hour ago
        }
        expired_token = jwt.encode(payload, Config.JWT_SECRET_KEY, algorithm=Config.JWT_ALGORITHM)
        result, status_code = validate_jwt_token(expired_token)
        self.assertEqual(status_code, 401)
        self.assertIn("error", result)

    def test_validate_invalid_jwt_token(self):
        # Test validation of an invalid JWT token
        invalid_token = "thisisnotavalidtoken"
        result, status_code = validate_jwt_token(invalid_token)
        self.assertEqual(status_code, 401)
        self.assertIn("error", result)


# To run the tests, you can use:
# if __name__ == '__main__':
#     unittest.main()