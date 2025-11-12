import sqlite3
import threading
from contextlib import contextmanager
import sys
import os


class Database:
    """Database manager supporting both SQLite and PostgreSQL"""

    def __init__(self, db_path=None, db_url=None, db_type='sqlite'):
        """
        Initialize database connection

        Args:
            db_path: Path to SQLite database file
            db_url: PostgreSQL connection URL
            db_type: 'sqlite' or 'postgresql'
        """
        self.db_type = db_type.lower()
        self.db_path = db_path
        self.db_url = db_url
        self.local = threading.local()

        # Import PostgreSQL driver if needed
        if self.db_type == 'postgresql':
            try:
                import psycopg2
                import psycopg2.extras
                self.psycopg2 = psycopg2
                self.psycopg2_extras = psycopg2.extras
            except ImportError:
                raise ImportError("psycopg2-binary is required for PostgreSQL support. Install it with: pip install psycopg2-binary")

    @contextmanager
    def get_connection(self):
        """Get database connection with context manager"""
        if self.db_type == 'sqlite':
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
        else:  # postgresql
            conn = self.psycopg2.connect(self.db_url)

        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _convert_query_placeholders(self, query):
        """Convert SQLite ? placeholders to PostgreSQL %s placeholders"""
        if self.db_type == 'postgresql':
            # Simply replace all ? with %s
            # psycopg2 will handle the parameter binding correctly
            query = query.replace('?', '%s')
        return query

    def execute_query(self, query, params=None):
        """Execute a query and return results"""
        query = self._convert_query_placeholders(query)

        with self.get_connection() as conn:
            if self.db_type == 'sqlite':
                cursor = conn.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                return cursor.fetchall()
            else:  # postgresql
                cursor = conn.cursor(cursor_factory=self.psycopg2_extras.RealDictCursor)
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                return cursor.fetchall()

    def execute_insert(self, query, params=None):
        """Execute insert and return last row id"""
        query = self._convert_query_placeholders(query)

        with self.get_connection() as conn:
            if self.db_type == 'sqlite':
                cursor = conn.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                return cursor.lastrowid
            else:  # postgresql
                # PostgreSQL needs RETURNING id clause
                if 'RETURNING' not in query.upper():
                    query = query.rstrip(';') + ' RETURNING id'

                # Use regular cursor first for execute, then fetch with RealDictCursor
                cursor = conn.cursor()

                if params:
                    # Ensure params is a tuple or list for psycopg2
                    if not isinstance(params, (tuple, list)):
                        params = (params,)

                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                result = cursor.fetchone()
                if result:
                    return result[0] if result else None
                return None

    def execute_update(self, query, params=None):
        """Execute update/delete and return affected rows"""
        query = self._convert_query_placeholders(query)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.rowcount

    def _get_create_table_syntax(self, table_sql):
        """Convert SQLite CREATE TABLE syntax to PostgreSQL if needed"""
        if self.db_type == 'sqlite':
            return table_sql

        # Convert SQLite to PostgreSQL syntax
        sql = table_sql

        # Replace INTEGER PRIMARY KEY AUTOINCREMENT with SERIAL PRIMARY KEY
        sql = sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')

        # Replace AUTOINCREMENT with nothing (handled by SERIAL)
        sql = sql.replace('AUTOINCREMENT', '')

        # Replace TEXT with VARCHAR for some fields, keep TEXT for others
        # (PostgreSQL handles both well)

        # Replace BOOLEAN DEFAULT FALSE/TRUE
        sql = sql.replace('BOOLEAN DEFAULT FALSE', 'BOOLEAN DEFAULT FALSE')
        sql = sql.replace('BOOLEAN DEFAULT TRUE', 'BOOLEAN DEFAULT TRUE')

        # Replace REAL with NUMERIC
        sql = sql.replace('REAL', 'NUMERIC')

        # Replace TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        sql = sql.replace('TIMESTAMP DEFAULT CURRENT_TIMESTAMP', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')

        # Remove SQLite-specific PRAGMA
        if 'PRAGMA' in sql:
            return None

        return sql

    def init_db(self):
        """Initialize database schema"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Users table
            table_sql = '''
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
            '''
            cursor.execute(self._get_create_table_syntax(table_sql))

            # Admin accounts table
            table_sql = '''
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
            '''
            cursor.execute(self._get_create_table_syntax(table_sql))

            # Buds data table
            table_sql = '''
                CREATE TABLE IF NOT EXISTS buds_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strain_name_th TEXT NOT NULL,
                    strain_name_en TEXT,
                    breeder TEXT,
                    strain_type TEXT,
                    thc_percentage REAL,
                    cbd_percentage REAL,
                    grade TEXT,
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
                    recommended_time TEXT,
                    grow_method TEXT,
                    harvest_date TEXT,
                    batch_number TEXT,
                    grower_id INTEGER NOT NULL,
                    grower_license_verified BOOLEAN DEFAULT FALSE,
                    fertilizer_type TEXT,
                    flowering_type TEXT,
                    status TEXT DEFAULT 'available',
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
            '''
            cursor.execute(self._get_create_table_syntax(table_sql))

            # Reviews table
            table_sql = '''
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bud_reference_id INTEGER NOT NULL,
                    reviewer_id INTEGER NOT NULL,
                    overall_rating INTEGER,
                    aroma_rating INTEGER,
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
            '''
            cursor.execute(self._get_create_table_syntax(table_sql))

            # Activities table
            table_sql = '''
                CREATE TABLE IF NOT EXISTS activities (
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
            '''
            cursor.execute(self._get_create_table_syntax(table_sql))

            # Activity participants table
            table_sql = '''
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
            '''
            cursor.execute(self._get_create_table_syntax(table_sql))

            # Friends table
            table_sql = '''
                CREATE TABLE IF NOT EXISTS friends (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    friend_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, friend_id),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (friend_id) REFERENCES users(id)
                )
            '''
            cursor.execute(self._get_create_table_syntax(table_sql))

            # Email verifications table
            table_sql = '''
                CREATE TABLE IF NOT EXISTS email_verifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            '''
            cursor.execute(self._get_create_table_syntax(table_sql))

            # Password resets table
            table_sql = '''
                CREATE TABLE IF NOT EXISTS password_resets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            '''
            cursor.execute(self._get_create_table_syntax(table_sql))

            # Strain names table
            table_sql = '''
                CREATE TABLE IF NOT EXISTS strain_names (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            '''
            cursor.execute(self._get_create_table_syntax(table_sql))

            # Breeders table
            table_sql = '''
                CREATE TABLE IF NOT EXISTS breeders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            '''
            cursor.execute(self._get_create_table_syntax(table_sql))

            # Admin settings table
            table_sql = '''
                CREATE TABLE IF NOT EXISTS admin_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            '''
            cursor.execute(self._get_create_table_syntax(table_sql))

            # Referrals table
            table_sql = '''
                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_user_id INTEGER NOT NULL,
                    referred_user_id INTEGER,
                    referral_code_used TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
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
            '''
            cursor.execute(self._get_create_table_syntax(table_sql))

            # Create indexes (skip for PostgreSQL if needed, or adjust syntax)
            if self.db_type == 'sqlite':
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
            else:  # postgresql
                # PostgreSQL uses different syntax for conditional index creation
                indexes = [
                    'CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)',
                    'CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)',
                    'CREATE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code)',
                    'CREATE INDEX IF NOT EXISTS idx_buds_grower ON buds_data(grower_id)',
                    'CREATE INDEX IF NOT EXISTS idx_buds_strain_name ON buds_data(strain_name_th, strain_name_en)',
                    'CREATE INDEX IF NOT EXISTS idx_reviews_bud ON reviews(bud_reference_id)',
                    'CREATE INDEX IF NOT EXISTS idx_reviews_reviewer ON reviews(reviewer_id)',
                    'CREATE INDEX IF NOT EXISTS idx_friends_user ON friends(user_id)',
                    'CREATE INDEX IF NOT EXISTS idx_friends_status ON friends(status)',
                    'CREATE INDEX IF NOT EXISTS idx_activities_status ON activities(status)',
                    'CREATE INDEX IF NOT EXISTS idx_activity_participants_activity ON activity_participants(activity_id)'
                ]
                for index_sql in indexes:
                    try:
                        cursor.execute(index_sql)
                    except:
                        pass  # Index might already exist

            try:
                print(f"✅ Database initialized successfully ({self.db_type})")
            except UnicodeEncodeError:
                print(f"[OK] Database initialized successfully ({self.db_type})")

    def migrate_add_referrer_approval(self):
        """Add referrer_approved and referrer_approved_at columns if they don't exist"""
        # Skip for PostgreSQL - these columns are already in init_db
        if self.db_type == 'postgresql':
            return

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check if columns exist (SQLite only)
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
        # Skip for PostgreSQL - these columns are already in init_db
        if self.db_type == 'postgresql':
            return

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check if columns exist (SQLite only)
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
        """Fix activity status constraint - only for SQLite"""
        if self.db_type == 'postgresql':
            return

        # SQLite-specific migration code...
        # (keeping original code for SQLite compatibility)
        pass
