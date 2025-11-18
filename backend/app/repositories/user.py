"""User repository for database operations"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from pymongo.database import Database

from .base import BaseRepository


class UserRepository(BaseRepository):
    """Repository for user entities"""

    def __init__(self, db: Database):
        super().__init__(db, "users")

    def find_by_email(self, email: str) -> Optional[Dict]:
        """Find a user by email"""
        return self.find_one({"email": email})

    def list_all(self) -> List[Dict]:
        """List all users sorted by creation date"""
        return self.find_many({}, sort=[("created_at", -1)])

    def create_user(self, email: str, name: Optional[str], role: str = "user") -> Dict:
        """Create a new user"""
        now = datetime.now(timezone.utc)
        user_doc = {
            "email": email,
            "name": name,
            "role": role,
            "created_at": now,
        }
        return self.insert_one(user_doc)
