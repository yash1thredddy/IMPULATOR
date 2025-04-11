import os
import jwt
import psycopg2
import bcrypt
import logging
from datetime import datetime, timedelta
from config import Config
import uuid
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Function to connect to the PostgreSQL database
def connect_to_db():
    """Connects to the PostgreSQL database using configuration parameters."""
    try:
        config = Config()
        conn = psycopg2.connect(
            dbname=config.POSTGRES_DB,
            user=config.POSTGRES_USER,
            password=config.POSTGRES_PASSWORD,
            host=config.POSTGRES_HOST,
            port=config.POSTGRES_PORT,
        )
        return conn
    except psycopg2.Error as e:
        logger.error(f"Error connecting to database: {e}")
        return None

def register_user(user_data):
    """Registers a new user with the provided data."""
    conn = None
    try:
        conn = connect_to_db()
        if not conn:
            return {"error": "Database connection failed"}, 500

        with conn.cursor() as cur:
            # Check if user already exists
            cur.execute("SELECT id FROM Users WHERE email = %s", (user_data['email'],))
            if cur.fetchone():
                logger.warning(f"Registration failed: User with email {user_data['email']} already exists.")
                return {"error": "User already exists"}, 400

            # Hash the password
            hashed_password = bcrypt.hashpw(user_data['password'].encode('utf-8'), bcrypt.gensalt())

            # Generate UUID for user
            user_id = os.environ.get('USER_ID_FOR_TESTING', str(uuid.uuid4()))

            # Insert the new user
            cur.execute(
                """
                INSERT INTO Users (id, username, email, password_hash, role, created_at, updated_at) 
                VALUES (%s, %s, %s, %s, %s, %s, %s) 
                RETURNING id
                """,
                (user_id, user_data['username'], user_data['email'], 
                 hashed_password.decode('utf-8'), user_data.get('role', 'user'), 
                 datetime.now(), datetime.now())
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
        close_db_connection(conn)


def login_user(user_data):
    """Logs in a user with the provided credentials."""
    conn = None
    try:
        conn = connect_to_db()
        if not conn:
            return {"error": "Database connection failed"}, 500

        with conn.cursor() as cur:
            cur.execute("SELECT id, password_hash, role FROM Users WHERE email = %s", (user_data['email'],))
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
        close_db_connection(conn)


def update_user(user_id, user_data):
    """Updates an existing user's information."""
    conn = None
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
            update_query = "UPDATE Users SET " + ", ".join(update_fields) + ", updated_at = %s WHERE id = %s"
            cur.execute(update_query, tuple(values))
            
            # Check if update affected any rows
            if cur.rowcount == 0:
                return {"error": "User not found"}, 404
                
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
        close_db_connection(conn)


def generate_jwt_token(user_id, role):
    """Generates a JWT token for a given user ID and role."""
    config = Config()
    payload = {
        'user_id': user_id,
        'role': role,
        'exp': datetime.utcnow() + timedelta(hours=24)  # Token expires in 24 hours
    }
    token = jwt.encode(payload, config.JWT_SECRET_KEY, algorithm='HS256')
    logger.debug(f"Generated JWT token for user ID: {user_id}, Role: {role}.")
    return token


def validate_jwt_token(token):
    """Validates a JWT token and returns the payload if valid."""
    config = Config()
    try:
        payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=['HS256'])
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
            logger.debug("Database connection closed successfully.")
    except psycopg2.Error as e:
        logger.error(f"Error closing database connection: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while closing the database connection: {e}")

# Import uuid here to avoid NameError in register_user
