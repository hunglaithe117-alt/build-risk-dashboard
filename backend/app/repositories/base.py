"""Base repository pattern for MongoDB operations"""

from abc import ABC
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union

from bson import ObjectId
from bson.errors import InvalidId
from pydantic import BaseModel
from pymongo.collection import Collection
from pymongo.database import Database

T = TypeVar("T", bound=BaseModel)


class BaseRepository(ABC, Generic[T]):
    """Base repository providing common CRUD operations for MongoDB collections"""

    def __init__(self, db: Database, collection_name: str, model_class: Type[T]):
        self.db = db
        self.collection: Collection = db[collection_name]
        self.model_class = model_class

    def find_by_id(self, entity_id: str | ObjectId) -> Optional[T]:
        """Find a document by its ID"""
        identifier = self._to_object_id(entity_id)
        if identifier is None:
            return None
        doc = self.collection.find_one({"_id": identifier})
        return self._to_model(doc)

    def find_one(self, query: Dict[str, Any]) -> Optional[T]:
        """Find a single document matching the query"""
        doc = self.collection.find_one(query)
        return self._to_model(doc)

    def find_many(
        self,
        query: Dict[str, Any],
        sort: Optional[List[tuple]] = None,
        skip: int = 0,
        limit: int = 0,
    ) -> List[T]:
        """Find multiple documents matching the query"""
        cursor = self.collection.find(query)
        if sort:
            cursor = cursor.sort(sort)
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        return [self._to_model(doc) for doc in cursor if doc]

    def paginate(
        self,
        query: Dict[str, Any],
        sort: Optional[List[tuple]] = None,
        skip: int = 0,
        limit: int = 0,
    ) -> tuple[List[T], int]:
        """Return paginated results plus total count for the query."""
        items = self.find_many(query, sort=sort, skip=skip, limit=limit)
        total = self.count(query)
        return items, total

    def insert_one(self, document: Union[T, Dict[str, Any]]) -> T:
        """Insert a single document"""
        if isinstance(document, BaseModel):
            doc_dict = document.model_dump(by_alias=True, exclude_none=True)
        else:
            doc_dict = document

        result = self.collection.insert_one(doc_dict)
        doc_dict["_id"] = result.inserted_id
        return self._to_model(doc_dict)

    def insert_many(self, documents: List[Union[T, Dict[str, Any]]]) -> List[T]:
        """Insert multiple documents"""
        if not documents:
            return []

        doc_dicts = []
        for doc in documents:
            if isinstance(doc, BaseModel):
                doc_dicts.append(doc.model_dump(by_alias=True, exclude_none=True))
            else:
                doc_dicts.append(doc)

        result = self.collection.insert_many(doc_dicts)

        models = []
        for i, doc_dict in enumerate(doc_dicts):
            doc_dict["_id"] = result.inserted_ids[i]
            models.append(self._to_model(doc_dict))

        return models

    def update_one(
        self, entity_id: str | ObjectId, updates: Dict[str, Any]
    ) -> Optional[T]:
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

    def _to_model(self, doc: Optional[Dict[str, Any]]) -> Optional[T]:
        """Convert a dictionary to a model instance"""
        if not doc:
            return None
        return self.model_class.model_validate(doc)

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
