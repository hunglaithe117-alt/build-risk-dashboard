"""User repository for database operations"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from pymongo.database import Database

from app.entities.user import User
from .base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for user entities"""

    def __init__(self, db: Database):
        super().__init__(db, "users", User)

    def find_by_email(self, email: str) -> Optional[User]:
        """Find a user by email"""
        return self.find_one({"email": email})

    def list_all(self) -> List[User]:
        """List all users sorted by creation date"""
        return self.find_many({}, sort=[("created_at", -1)])

    def create_user(self, email: str, name: Optional[str], role: str = "user") -> User:
        """Create a new user"""
        now = datetime.now(timezone.utc)
        user_doc = {
            "email": email,
            "name": name,
            "role": role,
            "created_at": now,
        }
        return self.insert_one(user_doc)

    def update_user(self, user_id: str, updates: Dict) -> Optional[User]:
        """Update a user's profile"""
        from bson import ObjectId

        updates["updated_at"] = datetime.now(timezone.utc)
        result = self.collection.find_one_and_update(
            {"_id": ObjectId(user_id)},
            {"$set": updates},
            return_document=True,
        )
        return User(**result) if result else None

    def update_role(self, user_id: str, role: str) -> Optional[User]:
        """Update a user's role"""
        return self.update_user(user_id, {"role": role})

    def delete_user(self, user_id: str) -> bool:
        """Delete a user by ID"""
        from bson import ObjectId

        result = self.collection.delete_one({"_id": ObjectId(user_id)})
        return result.deleted_count > 0

    def count_admins(self) -> int:
        """Count total admin users"""
        return self.collection.count_documents({"role": "admin"})
