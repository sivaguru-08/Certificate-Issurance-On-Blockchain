from pymongo import MongoClient, ASCENDING
import logging

logger = logging.getLogger(__name__)

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "blockchain_certs"

CERT_COLLECTION = "certificates"
HISTORY_COLLECTION = "history"
ADMINS_COLLECTION = "admins"

_client = None

def get_db():
    """Return the MongoDB database object. Returns None on failure."""
    global _client
    try:
        if _client is None:
            _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # Verify connection is alive
        _client.server_info()
        db = _client[DB_NAME]
        # Ensure indexes
        db[CERT_COLLECTION].create_index([("hash", ASCENDING)], unique=True)
        db[HISTORY_COLLECTION].create_index([("hash", ASCENDING)])
        db[ADMINS_COLLECTION].create_index([("username", ASCENDING)], unique=True)
        return db
    except Exception as e:
        logger.error(f"MongoDB connection failed: {e}")
        _client = None
        return None
