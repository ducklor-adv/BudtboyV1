import sqlite3
import threading
from contextlib import contextmanager
import sys


class Database:
    """Database manager for SQLite"""

    def __init__(self, db_path):
        self.db_path = db_path
        self.local = threading.local()

    @contextmanager
    def get_connection(self):
        """Get database connection with context manager"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def execute_query(self, query, params=None):
        """Execute a query and return results"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.fetchall()

    def execute_insert(self, query, params=None):
        """Execute insert and return last row id"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.lastrowid

    def execute_update(self, query, params=None):
        """Execute update/delete and return affected rows"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.rowcount

    def init_db(self):
        """Initialize database schema"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT,
                    is_grower BOOLEAN DEFAULT FALSE,
                    is_budtender BOOLEAN DEFAULT FALSE,
                    is_consumer BOOLEAN DEFAULT FALSE,
                    grow_license_file_url TEXT,
                    birth_year INTEGER,
                    profile_image_url TEXT,
                    is_verified BOOLEAN DEFAULT FALSE,
                    facebook_id TEXT,
                    line_id TEXT,
                    instagram_id TEXT,
                    twitter_id TEXT,
                    telegram_id TEXT,
                    phone_number TEXT,
                    referred_by INTEGER,
                    referral_code TEXT UNIQUE,
                    referrer_approved BOOLEAN DEFAULT FALSE,
                    referrer_approved_at TIMESTAMP,
                    is_approved BOOLEAN DEFAULT FALSE,
                    approved_at TIMESTAMP,
                    approved_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (referred_by) REFERENCES users(id),
                    FOREIGN KEY (approved_by) REFERENCES users(id)
                )
            ''')

            # Admin accounts table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admin_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_name TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    permissions TEXT DEFAULT 'full',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    login_attempts INTEGER DEFAULT 0,
                    locked_until TIMESTAMP,
                    session_token TEXT,
                    token_expires TIMESTAMP
                )
            ''')

            # Buds data table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS buds_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strain_name_th TEXT NOT NULL,
                    strain_name_en TEXT,
                    breeder TEXT,
                    strain_type TEXT CHECK(strain_type IN ('Indica', 'Sativa', 'Hybrid')),
                    thc_percentage REAL,
                    cbd_percentage REAL,
                    grade TEXT CHECK(grade IN ('A+', 'A', 'B+', 'B', 'C')),
                    aroma_flavor TEXT,
                    top_terpenes_1 TEXT,
                    top_terpenes_1_percentage REAL,
                    top_terpenes_2 TEXT,
                    top_terpenes_2_percentage REAL,
                    top_terpenes_3 TEXT,
                    top_terpenes_3_percentage REAL,
                    mental_effects_positive TEXT,
                    mental_effects_negative TEXT,
                    physical_effects_positive TEXT,
                    physical_effects_negative TEXT,
                    recommended_time TEXT CHECK(recommended_time IN ('day', 'night', 'all-day')),
                    grow_method TEXT,
                    harvest_date TEXT,
                    batch_number TEXT,
                    grower_id INTEGER NOT NULL,
                    grower_license_verified BOOLEAN DEFAULT FALSE,
                    fertilizer_type TEXT,
                    flowering_type TEXT CHECK(flowering_type IN ('photoperiod', 'autoflower')),
                    status TEXT DEFAULT 'available' CHECK(status IN ('available', 'sold_out', 'reserved')),
                    lab_test_name TEXT,
                    test_type TEXT,
                    image_1_url TEXT,
                    image_2_url TEXT,
                    image_3_url TEXT,
                    image_4_url TEXT,
                    certificate_image_1_url TEXT,
                    certificate_image_2_url TEXT,
                    certificate_image_3_url TEXT,
                    certificate_image_4_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by INTEGER,
                    FOREIGN KEY (grower_id) REFERENCES users(id),
                    FOREIGN KEY (created_by) REFERENCES users(id)
                )
            ''')

            # Reviews table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bud_reference_id INTEGER NOT NULL,
                    reviewer_id INTEGER NOT NULL,
                    overall_rating INTEGER CHECK(overall_rating BETWEEN 1 AND 5),
                    aroma_rating INTEGER CHECK(aroma_rating BETWEEN 1 AND 5),
                    short_summary TEXT,
                    full_review_content TEXT,
                    selected_effects TEXT,
                    aroma_flavors TEXT,
                    review_images TEXT,
                    video_review_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (bud_reference_id) REFERENCES buds_data(id),
                    FOREIGN KEY (reviewer_id) REFERENCES users(id)
                )
            ''')

            # Activities table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS activities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    start_registration_date TIMESTAMP,
                    end_registration_date TIMESTAMP,
                    judging_criteria TEXT,
                    max_participants INTEGER,
                    status TEXT DEFAULT 'draft' CHECK(status IN ('draft', 'open', 'closed', 'judging', 'completed')),
                    first_prize_description TEXT,
                    first_prize_value REAL,
                    first_prize_image TEXT,
                    second_prize_description TEXT,
                    second_prize_value REAL,
                    second_prize_image TEXT,
                    third_prize_description TEXT,
                    third_prize_value REAL,
                    third_prize_image TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by INTEGER,
                    FOREIGN KEY (created_by) REFERENCES users(id)
                )
            ''')

            # Activity participants table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS activity_participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    activity_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    bud_id INTEGER NOT NULL,
                    submission_images TEXT,
                    submission_description TEXT,
                    rank INTEGER,
                    prize_amount REAL,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(activity_id, user_id, bud_id),
                    FOREIGN KEY (activity_id) REFERENCES activities(id),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (bud_id) REFERENCES buds_data(id)
                )
            ''')

            # Friends table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS friends (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    friend_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'accepted')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, friend_id),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (friend_id) REFERENCES users(id)
                )
            ''')

            # Email verifications table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS email_verifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            # Password resets table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS password_resets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            # Strain names table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS strain_names (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Breeders table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS breeders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Admin settings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admin_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Referrals table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_user_id INTEGER NOT NULL,
                    referred_user_id INTEGER,
                    referral_code_used TEXT NOT NULL,
                    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'signed_up', 'verified', 'converted')),
                    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    signed_up_at TIMESTAMP,
                    verified_at TIMESTAMP,
                    converted_at TIMESTAMP,
                    utm_source TEXT,
                    utm_medium TEXT,
                    utm_campaign TEXT,
                    ip_hash TEXT,
                    user_agent_hash TEXT,
                    FOREIGN KEY (referrer_user_id) REFERENCES users(id),
                    FOREIGN KEY (referred_user_id) REFERENCES users(id)
                )
            ''')

            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_buds_grower ON buds_data(grower_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_buds_strain_name ON buds_data(strain_name_th, strain_name_en)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reviews_bud ON reviews(bud_reference_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reviews_reviewer ON reviews(reviewer_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_friends_user ON friends(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_friends_status ON friends(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_activities_status ON activities(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_activity_participants_activity ON activity_participants(activity_id)')

            try:
                print("✅ Database initialized successfully")
            except UnicodeEncodeError:
                print("[OK] Database initialized successfully")

    def migrate_add_referrer_approval(self):
        """Add referrer_approved and referrer_approved_at columns if they don't exist"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check if columns exist
            cursor.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in cursor.fetchall()]

            if 'referrer_approved' not in columns:
                cursor.execute('ALTER TABLE users ADD COLUMN referrer_approved BOOLEAN DEFAULT FALSE')
                print("✅ Added referrer_approved column")

            if 'referrer_approved_at' not in columns:
                cursor.execute('ALTER TABLE users ADD COLUMN referrer_approved_at TIMESTAMP')
                print("✅ Added referrer_approved_at column")

    def migrate_add_activity_criteria(self):
        """Add activity criteria columns if they don't exist"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check if columns exist
            cursor.execute("PRAGMA table_info(activities)")
            columns = [row[1] for row in cursor.fetchall()]

            # List of columns to add
            new_columns = {
                'allowed_strain_types': 'TEXT',
                'allowed_grow_methods': 'TEXT',
                'allowed_grades': 'TEXT',
                'allowed_fertilizer_types': 'TEXT',
                'allowed_recommended_times': 'TEXT',
                'allowed_flowering_types': 'TEXT',
                'preferred_terpenes': 'TEXT',
                'allowed_status': 'TEXT',
                'min_thc': 'REAL',
                'max_thc': 'REAL',
                'min_cbd': 'REAL',
                'max_cbd': 'REAL',
                'require_certificate': 'BOOLEAN DEFAULT FALSE',
                'require_min_images': 'BOOLEAN DEFAULT FALSE',
                'min_image_count': 'INTEGER',
                'require_min_reviews': 'BOOLEAN DEFAULT FALSE',
                'min_review_count': 'INTEGER',
                'preferred_aromas': 'TEXT',
                'preferred_effects': 'TEXT'
            }

            for column_name, column_type in new_columns.items():
                if column_name not in columns:
                    cursor.execute(f'ALTER TABLE activities ADD COLUMN {column_name} {column_type}')
                    print(f"✅ Added {column_name} column to activities")

    def migrate_fix_activity_status(self):
        """Fix activity status constraint by recreating table"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check if we need to migrate
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='activities'")
            result = cursor.fetchone()
            if result and "CHECK(status IN ('draft', 'open', 'closed', 'judging', 'completed'))" in result[0]:
                print("🔄 Migrating activities table to fix status constraint...")

                # Get existing column names
                cursor.execute("PRAGMA table_info(activities)")
                old_columns = [row[1] for row in cursor.fetchall()]
                columns_str = ', '.join(old_columns)

                # Rename old table
                cursor.execute('ALTER TABLE activities RENAME TO activities_old')

                # Create new table without CHECK constraint
                cursor.execute('''
                    CREATE TABLE activities (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        description TEXT,
                        start_registration_date TIMESTAMP,
                        end_registration_date TIMESTAMP,
                        judging_criteria TEXT,
                        max_participants INTEGER,
                        status TEXT DEFAULT 'upcoming',
                        first_prize_description TEXT,
                        first_prize_value REAL,
                        first_prize_image TEXT,
                        second_prize_description TEXT,
                        second_prize_value REAL,
                        second_prize_image TEXT,
                        third_prize_description TEXT,
                        third_prize_value REAL,
                        third_prize_image TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_by INTEGER,
                        allowed_strain_types TEXT,
                        allowed_grow_methods TEXT,
                        allowed_grades TEXT,
                        allowed_fertilizer_types TEXT,
                        allowed_recommended_times TEXT,
                        allowed_flowering_types TEXT,
                        preferred_terpenes TEXT,
                        allowed_status TEXT,
                        min_thc REAL,
                        max_thc REAL,
                        min_cbd REAL,
                        max_cbd REAL,
                        require_certificate BOOLEAN DEFAULT FALSE,
                        require_min_images BOOLEAN DEFAULT FALSE,
                        min_image_count INTEGER,
                        require_min_reviews BOOLEAN DEFAULT FALSE,
                        min_review_count INTEGER,
                        preferred_aromas TEXT,
                        preferred_effects TEXT,
                        FOREIGN KEY (created_by) REFERENCES users(id)
                    )
                ''')

                # Copy data from old table - only copy columns that exist
                cursor.execute(f'INSERT INTO activities ({columns_str}) SELECT {columns_str} FROM activities_old')

                # Drop old table
                cursor.execute('DROP TABLE activities_old')

                print("✅ Activities table migrated successfully")
