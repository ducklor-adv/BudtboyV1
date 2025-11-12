#!/usr/bin/env python3
"""
Create initial BudtBoy user in the database
This user will be pre-approved and have all necessary permissions
"""
import bcrypt
import uuid
from datetime import datetime
from app.models.database import Database
from config.config import config
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def create_initial_user():
    """Create the initial budtboy user with pre-approved status"""

    # Get database configuration
    db_type = os.environ.get('DATABASE_TYPE', 'sqlite')

    if db_type == 'postgresql':
        db_url = os.environ.get('DATABASE_URL')
        db = Database(db_url=db_url, db_type='postgresql')
    else:
        db_path = os.environ.get('DATABASE_PATH', 'budtboy_local.db')
        db = Database(db_path=db_path, db_type='sqlite')

    # Check if budtboy user already exists
    existing_user = db.execute_query(
        "SELECT id, username FROM users WHERE username = ?",
        ('budtboy',)
    )

    if existing_user:
        print(f"[INFO] User 'budtboy' already exists with ID: {existing_user[0]['id']}")

        # Update to ensure it's approved
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.execute_update(
            """UPDATE users
               SET is_approved = ?,
                   approved_at = ?,
                   is_verified = ?,
                   referrer_approved = ?
               WHERE username = ?""",
            (True, now, True, True, 'budtboy')
        )
        print("[OK] Updated budtboy user to approved status")
        return

    # Create password hash
    password = 'BudtBoy2024!@#'
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # Generate referral code
    referral_code = str(uuid.uuid4())[:8].upper()

    # Current timestamp
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Insert budtboy user
    try:
        user_id = db.execute_insert(
            """INSERT INTO users (
                username,
                email,
                password_hash,
                is_grower,
                is_budtender,
                is_consumer,
                is_verified,
                is_approved,
                approved_at,
                referrer_approved,
                referrer_approved_at,
                referral_code,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                'budtboy',
                'budtboy@budtboy.com',
                password_hash,
                True,   # is_grower
                True,   # is_budtender
                True,   # is_consumer
                True,   # is_verified
                True,   # is_approved - PRE-APPROVED
                now,    # approved_at
                True,   # referrer_approved
                now,    # referrer_approved_at
                referral_code,
                now
            )
        )

        print("=" * 60)
        print("[SUCCESS] Initial BudtBoy user created successfully!")
        print("=" * 60)
        print(f"User ID:       {user_id}")
        print(f"Username:      budtboy")
        print(f"Email:         budtboy@budtboy.com")
        print(f"Password:      BudtBoy2024!@#")
        print(f"Referral Code: {referral_code}")
        print(f"Status:        [YES] PRE-APPROVED")
        print(f"Verified:      [YES]")
        print(f"Roles:         Grower, Budtender, Consumer")
        print("=" * 60)

    except Exception as e:
        print(f"[ERROR] Error creating user: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    create_initial_user()
