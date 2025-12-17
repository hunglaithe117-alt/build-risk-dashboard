#!/usr/bin/env python3
"""
Script to set a user as admin in the database.

Usage:
    uv run python scripts/set_admin.py <email>
    uv run python scripts/set_admin.py --github-login <github_username>

Examples:
    uv run python scripts/set_admin.py admin@example.com
    uv run python scripts/set_admin.py --github-login octocat
"""

import argparse
import sys
from datetime import datetime, timezone

from pymongo import MongoClient

# Add parent directory to path for imports
sys.path.insert(0, ".")

from app.config import settings


def get_db():
    """Get MongoDB database connection."""
    client = MongoClient(settings.MONGODB_URI)
    return client[settings.MONGODB_DB_NAME]


def set_admin_by_email(email: str) -> bool:
    """Set user as admin by email."""
    db = get_db()
    result = db.users.update_one(
        {"email": email},
        {
            "$set": {
                "role": "admin",
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    return result.modified_count > 0


def set_admin_by_github_login(github_login: str) -> bool:
    """Set user as admin by GitHub login (looks up via oauth_identities)."""
    db = get_db()

    # Find OAuth identity by GitHub login
    identity = db.oauth_identities.find_one({"account_login": github_login})
    if not identity:
        print(f"❌ No GitHub account found with login: {github_login}")
        return False

    user_id = identity.get("user_id")
    if not user_id:
        print(f"❌ OAuth identity found but no user_id linked")
        return False

    result = db.users.update_one(
        {"_id": user_id},
        {
            "$set": {
                "role": "admin",
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    return result.modified_count > 0


def list_users():
    """List all users with their roles."""
    db = get_db()
    users = db.users.find({}, {"email": 1, "name": 1, "role": 1, "created_at": 1})

    print("\n📋 Current Users:")
    print("-" * 60)
    for user in users:
        role_badge = "👑 ADMIN" if user.get("role") == "admin" else "👤 User"
        print(
            f"  {role_badge} | {user.get('email', 'N/A')} | {user.get('name', 'N/A')}"
        )
    print("-" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Set a user as admin in the Build Risk Dashboard"
    )
    parser.add_argument(
        "email",
        nargs="?",
        help="Email address of the user to make admin",
    )
    parser.add_argument(
        "--github-login",
        "-g",
        help="GitHub username to make admin (alternative to email)",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List all users and their roles",
    )

    args = parser.parse_args()

    if args.list:
        list_users()
        return

    if not args.email and not args.github_login:
        parser.print_help()
        print("\n❌ Error: Please provide either an email or --github-login")
        sys.exit(1)

    if args.github_login:
        print(f"🔍 Looking up user with GitHub login: {args.github_login}")
        success = set_admin_by_github_login(args.github_login)
        identifier = args.github_login
    else:
        print(f"🔍 Looking up user with email: {args.email}")
        success = set_admin_by_email(args.email)
        identifier = args.email

    if success:
        print(f"✅ Successfully set {identifier} as admin!")
        list_users()
    else:
        print(f"❌ User not found: {identifier}")
        print("   Make sure the user has logged in at least once via GitHub OAuth.")
        sys.exit(1)


if __name__ == "__main__":
    main()
