"""Base repository pattern for MongoDB operations"""

from abc import ABC
from typing import Any, Dict, Generic, List, Optional, TypeVar

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.collection import Collection
from pymongo.database import Database

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    """Base repository providing common CRUD operations for MongoDB collections"""

    def __init__(self, db: Database, collection_name: str):
        self.db = db
        self.collection: Collection = db[collection_name]

    def find_by_id(self, entity_id: str | ObjectId) -> Optional[Dict[str, Any]]:
        """Find a document by its ID"""
        identifier = self._to_object_id(entity_id)
        if identifier is None:
            return None
        return self.collection.find_one({"_id": identifier})

    def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single document matching the query"""
        return self.collection.find_one(query)

    def find_many(
        self,
        query: Dict[str, Any],
        sort: Optional[List[tuple]] = None,
        skip: int = 0,
        limit: int = 0,
    ) -> List[Dict[str, Any]]:
        """Find multiple documents matching the query"""
        cursor = self.collection.find(query)
        if sort:
            cursor = cursor.sort(sort)
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)

    def insert_one(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a single document"""
        result = self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    def insert_many(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Insert multiple documents"""
        result = self.collection.insert_many(documents)
        for i, doc in enumerate(documents):
            doc["_id"] = result.inserted_ids[i]
        return documents

    def update_one(
        self, entity_id: str | ObjectId, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a document by ID"""
        identifier = self._to_object_id(entity_id)
        if identifier is None:
            return None
        self.collection.update_one({"_id": identifier}, {"$set": updates})
        return self.find_by_id(identifier)

    def update_many(self, query: Dict[str, Any], updates: Dict[str, Any]) -> int:
        """Update multiple documents matching the query"""
        result = self.collection.update_many(query, {"$set": updates})
        return result.modified_count

    def delete_one(self, entity_id: str | ObjectId) -> bool:
        """Delete a document by ID"""
        identifier = self._to_object_id(entity_id)
        if identifier is None:
            return False
        result = self.collection.delete_one({"_id": identifier})
        return result.deleted_count > 0

    def delete_many(self, query: Dict[str, Any]) -> int:
        """Delete multiple documents matching the query"""
        result = self.collection.delete_many(query)
        return result.deleted_count

    def count(self, query: Dict[str, Any] = None) -> int:
        """Count documents matching the query"""
        if query is None:
            query = {}
        return self.collection.count_documents(query)

    def aggregate(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute an aggregation pipeline"""
        return list(self.collection.aggregate(pipeline))

    @staticmethod
    def _to_object_id(value: str | ObjectId | None) -> ObjectId | None:
        """Convert a string ID to ObjectId"""
        if value is None:
            return None
        if isinstance(value, ObjectId):
            return value
        if isinstance(value, str):
            try:
                return ObjectId(value)
            except (InvalidId, TypeError):
                return None
        return None
