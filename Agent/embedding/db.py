from pymongo import MongoClient
from pymongo.collection import Collection
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import numpy as np

from . import config

_client: Optional[MongoClient] = None
_db = None

def init_db():
    global _client, _db
    if _client is None:
        print("Connecting to MongoDB Atlas...")
        _client = MongoClient(config.MONGO_URI)
        _db = _client[config.MONGO_DB_NAME]
        
        try:
            _client.admin.command('ping')
            print("MongoDB connection successful.")
        except Exception as e:
            print(f"MongoDB connection failed: {e}")
            raise

def get_chunks_collection() -> Collection:
    if _db is None:
        init_db()
    return _db["chunks"]

def get_profiles_collection() -> Collection:
    if _db is None:
        init_db()
    return _db["profiles"]

def get_profile_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    collection = get_profiles_collection()
    return collection.find_one({"user_id": user_id})

def create_or_update_profile(profile_data: Dict[str, Any]) -> bool:
    if not profile_data or "user_id" not in profile_data:
        return False
        
    collection = get_profiles_collection()
    try:
        collection.update_one(
            {"user_id": profile_data["user_id"]},
            {"$set": profile_data},
            upsert=True
        )
        return True
    except Exception as e:
        print(f"Error creating/updating profile: {e}")
        return False

def store_chunk(chunk_id: str, user_id: str, namespace: str, section_id: Optional[str],
                source_type: str, source_id: str, text: str, embedding_vector: np.ndarray) -> None:
    collection = get_chunks_collection()
    
    document = {
        "_id": chunk_id,
        "user_id": user_id,
        "index_namespace": namespace,
        "section_id": section_id,
        "source_type": source_type,
        "source_id": source_id,
        "text": text,
        "embedding": embedding_vector.tolist(),
        "created_at": datetime.now(timezone.utc)
    }
    
    collection.update_one(
        {"_id": chunk_id},
        {"$set": document},
        upsert=True
    )

def get_chunk_by_id(chunk_id: str) -> Optional[Dict[str, Any]]:
    collection = get_chunks_collection()
    return collection.find_one({"_id": chunk_id})

def delete_chunks_by_section_id(user_id: str, section_id: str) -> int:
    collection = get_chunks_collection()
    result = collection.delete_many({"user_id": user_id, "section_id": section_id})
    return result.deleted_count

def delete_user_chunks(user_id: str, namespace: str) -> int:
    collection = get_chunks_collection()
    result = collection.delete_many({"user_id": user_id, "index_namespace": namespace})
    return result.deleted_count

def search_chunks_vector(
    user_id: str,
    namespace: str,
    query_vector: List[float],
    top_k: int,
    filter_by_section_ids: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    collection = get_chunks_collection()

    search_filter = {
        "user_id": user_id,
        "index_namespace": namespace,
    }

    if filter_by_section_ids:
        search_filter["section_id"] = {"$in": filter_by_section_ids}

    pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index",
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": top_k * 10,
                "limit": top_k,
                "filter": search_filter,
            }
        },
        {
            "$project": {
                "_id": 1,
                "user_id": 1,
                "index_namespace": 1,
                "section_id": 1,
                "source_type": 1,
                "source_id": 1,
                "text": 1,
                "created_at": 1,
                "score": {"$meta": "vectorSearchScore"}
            }
        }
    ]
    
    results = list(collection.aggregate(pipeline))
    return results

def get_users_collection() -> Collection:
    if _db is None:
        init_db()
    return _db["users"]

def mark_user_indexed(user_id: str) -> None:
    users_collection = get_users_collection()
    users_collection.update_one(
        {"_id": user_id},
        {"$set": {"embeddings_last_updated": datetime.now(timezone.utc)}},
        upsert=True
    )

def get_user_index_status(user_id: str) -> Optional[datetime]:
    users_collection = get_users_collection()
    user_doc = users_collection.find_one(
        {"_id": user_id},
        {"embeddings_last_updated": 1}
    )
    return user_doc.get("embeddings_last_updated") if user_doc else None