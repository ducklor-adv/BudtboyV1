from flask import Flask, render_template, request, jsonify, url_for, session, redirect
import psycopg2
from psycopg2 import pool, sql
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
import secrets
import bcrypt
import threading
import time
import json
import google_auth_oauthlib.flow
import google.oauth2.credentials
import requests
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'budtboy-secret-key-2024')

# Environment detection
def is_production():
    """Check if running in production deployment"""
    current_host = os.environ.get('REPL_SLUG', '')
    deployment_env = os.environ.get('REPLIT_DEPLOYMENT', '')
    request_host = os.environ.get('HTTP_HOST', '')

    # Check multiple indicators for production
    is_prod = (
        'budtboy.replit.app' in deployment_env or 
        deployment_env == 'production' or
        'budtboy.replit.app' in request_host or
        current_host == 'budtboy'
    )

    print(f"🔍 Production check - REPL_SLUG: {current_host}, REPLIT_DEPLOYMENT: {deployment_env}, HTTP_HOST: {request_host}")
    return is_prod

def is_preview():
    """Check if running in preview mode"""
    return not is_production() and ('REPLIT_DEV_DOMAIN' in os.environ or 'pike.replit.dev' in os.environ.get('HTTP_HOST', ''))

# Fallback authentication settings
FALLBACK_AUTH_ENABLED = is_preview()
FALLBACK_SECRET_KEY = os.environ.get('FALLBACK_AUTH_SECRET', 'fallback-dev-secret-2024')

print(f"🌍 Environment: {'Production' if is_production() else 'Preview' if is_preview() else 'Development'}")
print(f"🔐 Fallback Auth: {'Enabled' if FALLBACK_AUTH_ENABLED else 'Disabled'}")

# Google OAuth configuration - only in production
GOOGLE_OAUTH_CONFIG = {
    "web": {
        "client_id": os.environ.get('GOOGLE_CLIENT_ID') if is_production() else None,
        "client_secret": os.environ.get('GOOGLE_CLIENT_SECRET') if is_production() else None,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "redirect_uris": []  # Will be set dynamically
    }
}

# Initialize OAuth flow only in production
oauth_flow = None
if is_production():
    try:
        if GOOGLE_OAUTH_CONFIG["web"]["client_id"] and GOOGLE_OAUTH_CONFIG["web"]["client_secret"]:
            oauth_flow = google_auth_oauthlib.flow.Flow.from_client_config(
                GOOGLE_OAUTH_CONFIG,
                scopes=[
                    "https://www.googleapis.com/auth/userinfo.email",
                    "openid", 
                    "https://www.googleapis.com/auth/userinfo.profile"
                ]
            )
            print("✅ Google OAuth initialized successfully (Production)")
        else:
            print("⚠️ Warning: Google OAuth credentials not found in environment variables")
    except Exception as e:
        print(f"❌ Error initializing Google OAuth: {e}")
        oauth_flow = None
else:
    print("🔧 Google OAuth disabled in preview mode - using fallback authentication")

# Email configuration - using environment variables with fallback for testing
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'budtboy.app@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'demo_password')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME', 'budtboy.app@gmail.com')
app.config['MAIL_USE_SSL'] = False

# Check if we have real email credentials
DEMO_EMAIL_MODE = app.config['MAIL_PASSWORD'] == 'demo_password' or not app.config['MAIL_PASSWORD']

# File upload configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

mail = Mail(app)

# Create uploads directory if it doesn't exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Create attached_assets directory if it doesn't exist
if not os.path.exists('attached_assets'):
    os.makedirs('attached_assets')

# Connection pool
connection_pool = None
pool_lock = threading.Lock()

# Improved cache system with longer TTL
cache = {}
cache_lock = threading.Lock()
CACHE_TTL = 900  # 15 minutes for better balance
SHORT_CACHE_TTL = 180  # 3 minutes for frequently changing data
PROFILE_CACHE_TTL = 1800  # 30 minutes for profile data
ACTIVITY_CACHE_TTL = 600  # 10 minutes for activity data

def get_cache(key, ttl=CACHE_TTL):
    """Get cached data if not expired"""
    with cache_lock:
        if key in cache:
            data, timestamp, cache_ttl = cache[key]
            if time.time() - timestamp < cache_ttl:
                return data
            del cache[key]
    return None

def set_cache(key, data, ttl=CACHE_TTL):
    """Set cache with automatic cleanup"""
    with cache_lock:
        cache[key] = (data, time.time(), ttl)
        # Periodic cleanup
        if len(cache) > 1000:
            current_time = time.time()
            expired_keys = [k for k, (_, ts, cache_ttl) in cache.items() 
                          if current_time - ts > cache_ttl]
            for k in expired_keys[:100]:
                del cache[k]

def clear_cache_pattern(pattern):
    with cache_lock:
        keys_to_delete = [key for key in cache.keys() if pattern in key]
        for key in keys_to_delete:
            del cache[key]

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Database connection function
def get_db_connection():
    """Get database connection with improved error handling"""
    global connection_pool
    max_retries = 3

    for retry_count in range(max_retries):
        try:
            if connection_pool is None:
                init_connection_pool()

            if connection_pool:
                try:
                    conn = connection_pool.getconn()
                    if conn and not conn.closed:
                        # Test connection
                        with conn.cursor() as test_cur:
                            test_cur.execute("SELECT 1")
                        return conn
                except (psycopg2.OperationalError, psycopg2.InterfaceError):
                    if conn:
                        try:
                            connection_pool.putconn(conn, close=True)
                        except:
                            pass
                    connection_pool = None
                    continue

            # Fallback to direct connection
            if retry_count == max_retries - 1:
                database_url = os.environ.get('DATABASE_URL')
                if not database_url:
                    raise Exception("DATABASE_URL environment variable not set")

                return psycopg2.connect(
                    database_url,
                    sslmode='prefer',
                    connect_timeout=15,
                    application_name='cannabis_app'
                )

        except Exception as e:
            if retry_count == max_retries - 1:
                print(f"Database connection failed: {e}")
                return None
            time.sleep(0.1)

    return None

def init_connection_pool():
    """Initialize connection pool"""
    global connection_pool
    try:
        with pool_lock:
            if connection_pool is None:
                database_url = os.environ.get('DATABASE_URL')
                if database_url:
                    connection_pool = pool.ThreadedConnectionPool(
                        1, 20,  # min and max connections
                        database_url,
                        sslmode='prefer',
                        connect_timeout=15,
                        application_name='cannabis_app_pool'
                    )
                    print("Connection pool initialized successfully")
                else:
                    print("DATABASE_URL not found, connection pool not initialized")
    except Exception as e:
        print(f"Failed to initialize connection pool: {e}")
        connection_pool = None

def return_db_connection(conn):
    try:
        if connection_pool and conn:
            try:
                # Check if connection is still alive before returning to pool
                with conn.cursor() as test_cur:
                    test_cur.execute("SELECT 1")
                # Check if connection was obtained from pool before returning
                if hasattr(conn, '_from_pool') or connection_pool:
                    connection_pool.putconn(conn)
                else:
                    conn.close()
            except (psycopg2.OperationalError, psycopg2.InterfaceError):
                # Connection is dead, close it instead of returning to pool
                try:
                    conn.close()
                except:
                    pass
            except Exception as pool_error:
                # If putconn fails, just close the connection
                try:
                    conn.close()
                except:
                    pass
        elif conn:
            try:
                conn.close()
            except:
                pass
    except Exception as e:
        print(f"Error returning connection: {e}")
        # Ensure connection is closed
        try:
            if conn:
                conn.close()
        except:
            pass

# Create tables on startup
def create_tables():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Create users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(80) UNIQUE NOT NULL,
                    email VARCHAR(120) UNIQUE NOT NULL,
                    password_hash VARCHAR(128) NOT NULL,
                    is_grower BOOLEAN DEFAULT FALSE,
                    grow_license_file_url VARCHAR(255) NULL,
                    is_budtender BOOLEAN DEFAULT FALSE,
                    is_consumer BOOLEAN DEFAULT TRUE,
                    birth_year INTEGER NULL,
                    profile_image_url VARCHAR(255) NULL,
                    is_verified BOOLEAN DEFAULT FALSE,
                    contact_facebook VARCHAR(500) NULL,
                    contact_line VARCHAR(500) NULL,
                    contact_instagram VARCHAR(500) NULL,
                    contact_twitter VARCHAR(500) NULL,
                    contact_telegram VARCHAR(500) NULL,
                    contact_phone VARCHAR(20) NULL,
                    contact_other VARCHAR(500) NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    referred_by INTEGER REFERENCES users(id),
                    referral_code VARCHAR(50) UNIQUE,
                    is_approved BOOLEAN DEFAULT TRUE,
                    approved_at TIMESTAMP,
                    approved_by INTEGER REFERENCES users(id)
                );
            """)

            # Add contact fields if they don't exist (for existing databases)
            try:
                cur.execute("""
                    ALTER TABLE users 
                    ADD COLUMN IF NOT EXISTS contact_facebook VARCHAR(500),
                    ADD COLUMN IF NOT EXISTS contact_line VARCHAR(500),
                    ADD COLUMN IF NOT EXISTS contact_instagram VARCHAR(500),
                    ADD COLUMN IF NOT EXISTS contact_twitter VARCHAR(500),
                    ADD COLUMN IF NOT EXISTS contact_telegram VARCHAR(500),
                    ADD COLUMN IF NOT EXISTS contact_phone VARCHAR(20),
                    ADD COLUMN IF NOT EXISTS contact_other VARCHAR(500);
                """)
            except Exception as e:
                print(f"Note: Contact columns may already exist: {e}")

            # Create email verification table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS email_verifications (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    token VARCHAR(128) UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    is_used BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Create password reset table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS password_resets (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE UNIQUE,
                    token VARCHAR(128) UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    is_used BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Create strain_names table for autocomplete (removed strain_type)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS strain_names (
                    id SERIAL PRIMARY KEY,
                    name_th VARCHAR(255),
                    name_en VARCHAR(255) NOT NULL,
                    is_popular BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Create breeders table for autocomplete
            cur.execute("""
                CREATE TABLE IF NOT EXISTS breeders (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) UNIQUE NOT NULL,
                    is_popular BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Insert all 456 strain names if table is empty
            cur.execute("SELECT COUNT(*) FROM strain_names")
            count = cur.fetchone()[0]

            if count == 0:
                # Complete strain list from attached file (all 456 strains)
                all_strains = [
                    # Popular strains first
                    (None, 'Blue Dream', True),
                    (None, 'Girl Scout Cookies', True),
                    (None, 'White Widow', True),
                    (None, 'OG Kush', True),
                    (None, 'Jack Herer', True),
                    (None, 'Green Crack', True),
                    (None, 'Sour Diesel', True),
                    (None, 'Afghan Kush', True),
                    (None, 'Granddaddy Purple', True),
                    (None, 'Pineapple Express', True),
                    (None, 'Godfather OG', True),

                    # All 456 strains from the file
                    (None, 'A-Dub', False),
                    (None, 'A-Train', False),
                    (None, 'A.M.S.', False),
                    (None, 'AC/DC', False),
                    (None, 'AC/DOSI', False),
                    (None, 'ACDC Cookies', False),
                    (None, 'AJ Sour Diesel', False),
                    (None, 'AK 1995', False),
                    (None, 'AK-47', False),
                    (None, 'AK-48', False),
                    (None, 'AK-49', False),
                    (None, 'AURORA Indica', False),
                    (None, 'Abula', False),
                    (None, 'Abusive OG', False),
                    (None, 'Acai Berry Gelato', False),
                    (None, 'Acai Kush', False),
                    (None, 'Acai Mints', False),
                    (None, 'Acapulco Gold', False),
                    (None, 'Ace of Spades', False),
                    (None, 'Aceh', False),
                    (None, 'Ace\'s High', False),
                    (None, 'Acid', False),
                    (None, 'Acid Dough', False),
                    (None, 'Acid Kat', False),
                    (None, 'Adak OG', False),
                    (None, 'Affie Taffie', False),
                    (None, 'Affogato', False),
                    (None, 'Affy Taffy', False),
                    (None, 'Afghan Peach', False),
                    (None, 'Afghan Skunk', False),
                    (None, 'Afghanica', False),
                    (None, 'Afgooey', False),
                    (None, 'Afternoon Delight', False),
                    (None, 'Afwreck', False),
                    (None, 'Agent Orange', False),
                    (None, 'Agent Rose', False),
                    (None, 'Agent Tangie', False),
                    (None, 'Alakazam', False),
                    (None, 'Alaskan Ice', False),
                    (None, 'Alaskan Thunder Fuck', False),
                    (None, 'Albarino', False),
                    (None, 'Albert Walker', False),
                    (None, 'Alien OG', False),
                    (None, 'Alien Orange Cookies', False),
                    (None, 'Alien Pebbles OG', False),
                    (None, 'All Gas', False),
                    (None, 'Allen Iverson', False),
                    (None, 'Allen Wrench', False),
                    (None, 'Allkush', False),
                    (None, 'Altoyd', False),
                    (None, 'Ambrosia', False),
                    (None, 'American Beauty', False),
                    (None, 'American Crippler', False),
                    (None, 'Amnesia Haze', False),
                    (None, 'Amnesia Kush', False),
                    (None, 'Amnesia Lemon', False),
                    (None, 'Amnesia Mint Cookies', False),
                    (None, 'Amnesia OG', False),
                    (None, 'Amsterdam Flame', False),
                    (None, 'Ancient OG', False),
                    (None, 'Anesthesia', False),
                    (None, 'Angelmatic', False),
                    (None, 'Animal Cookies', False),
                    (None, 'Animal Crackers', False),
                    (None, 'Animal Face', False),
                    (None, 'Animal Mint Cookie Walker', False),
                    (None, 'Animal Mints', False),
                    (None, 'Animal Mints Bx1', False),
                    (None, 'Animal OG', False),
                    (None, 'Apple Fritter', False),
                    (None, 'Apple Jack', False),
                    (None, 'Apricot Helix', False),
                    (None, 'Apricot Jelly', False),
                    (None, 'Aurora Borealis', False),
                    (None, 'Banana Kush', False),
                    (None, 'Banana OG', False),
                    (None, 'Banana Punch', False),
                    (None, 'Beckwourth Bud', False),
                    (None, 'Berry White', False),
                    (None, 'Big Bud', False),
                    (None, 'Big Smooth', False),
                    (None, 'Birthday Cake', False),
                    (None, 'Biscotti', False),
                    (None, 'Black Afghan', False),
                    (None, 'Black Cherry Soda', False),
                    (None, 'Black Domina', False),
                    (None, 'Black Jack', False),
                    (None, 'Black Mamba', False),
                    (None, 'Black Widow', False),
                    (None, 'Blackberry', False),
                    (None, 'Blackberry Kush', False),
                    (None, 'Blackberry Widow', False),
                    (None, 'Blue Cheese', False),
                    (None, 'Blue Cookies', False),
                    (None, 'Blue Moonshine', False),
                    (None, 'Blue OG', False),
                    (None, 'Blue Power', False),
                    (None, 'Blue Trainwreck', False),
                    (None, 'Blueberry', False),
                    (None, 'Blueberry Kush', False),
                    (None, 'Blueberry Muffin', False),
                    (None, 'Bruce Banner', False),
                    (None, 'Bubba Kush', False),
                    (None, 'Bubble Gum', False),
                    (None, 'Buddha\'s Hand', False),
                    (None, 'Burmese Kush', False),
                    (None, 'California Orange', False),
                    (None, 'Candy Cane', False),
                    (None, 'Candyland', False),
                    (None, 'Cannalope Haze', False),
                    (None, 'Cannatonic', False),
                    (None, 'Cereal Milk', False),
                    (None, 'Charlotte\'s Web', False),
                    (None, 'Cheese', False),
                    (None, 'Cheesequake', False),
                    (None, 'Chem 91', False),
                    (None, 'Chemdawg', False),
                    (None, 'Chernobyl', False),
                    (None, 'Cherry AK-47', False),
                    (None, 'Cherry Diesel', False),
                    (None, 'Cherry Kush', False),
                    (None, 'Cherry Pie', False),
                    (None, 'Chocolate Thai', False),
                    (None, 'Chocolope', False),
                    (None, 'Chronic', False),
                    (None, 'Cinderella 99', False),
                    (None, 'Cinex', False),
                    (None, 'Colombian Gold', False),
                    (None, 'Cookies and Cream', False),
                    (None, 'Cotton Candy', False),
                    (None, 'Critical Jack', False),
                    (None, 'Critical Kush', False),
                    (None, 'Critical Mass', False),
                    (None, 'Crockett\'s Sour Tangie', False),
                    (None, 'Crosswalker', False),
                    (None, 'Crystal', False),
                    (None, 'Death Star', False),
                    (None, 'DelaHaze', False),
                    (None, 'Diabla', False),
                    (None, 'Diamond OG', False),
                    (None, 'Do-Si-Dos', False),
                    (None, 'Double Diesel', False),
                    (None, 'Double Dream', False),
                    (None, 'Dr. Grinspoon', False),
                    (None, 'Dream Queen', False),
                    (None, 'Durban Poison', False),
                    (None, 'Durga Mata', False),
                    (None, 'Dutch Hawaiian', False),
                    (None, 'Dutch Treat', False),
                    (None, 'Early Girl', False),
                    (None, 'Early Pearl', False),
                    (None, 'East Coast Sour Diesel', False),
                    (None, 'Elephant', False),
                    (None, 'Emerald Jack', False),
                    (None, 'Euphoria', False),
                    (None, 'Exodus Cheese', False),
                    (None, 'Face Off OG', False),
                    (None, 'Facewreck', False),
                    (None, 'Fire OG', False),
                    (None, 'Firecracker', False),
                    (None, 'Flo', False),
                    (None, 'Forbidden Cookies', False),
                    (None, 'Forbidden Fruit', False),
                    (None, 'Four-Way', False),
                    (None, 'Freezeland', False),
                    (None, 'Frosty', False),
                    (None, 'Fruit Punch', False),
                    (None, 'Fruity Pebbles OG', False),
                    (None, 'Fucking Incredible', False),
                    (None, 'Funky Monkey', False),
                    (None, 'Future #1', False),
                    (None, 'G13', False),
                    (None, 'GMO Cookies', False),
                    (None, 'Gelato', False),
                    (None, 'Ghost OG', False),
                    (None, 'Glueball', False),
                    (None, 'God Bud', False),
                    (None, 'God\'s Gift', False),
                    (None, 'Golden Calyx', False),
                    (None, 'Golden Goat', False),
                    (None, 'Golden Pineapple', False),
                    (None, 'Golden Ticket', False),
                    (None, 'Grandma\'s Sugar Cookie', False),
                    (None, 'Grape Ape', False),
                    (None, 'Grape God', False),
                    (None, 'Grape Stomper', False),
                    (None, 'Grapefruit', False),
                    (None, 'Grease Monkey', False),
                    (None, 'Green Ribbon', False),
                    (None, 'Harlequin', False),
                    (None, 'Hash Plant', False),
                    (None, 'Hashberry', False),
                    (None, 'Hawaiian', False),
                    (None, 'Haze', False),
                    (None, 'Head Cheese', False),
                    (None, 'Headband', False),
                    (None, 'Herijuana', False),
                    (None, 'Hindu Kush', False),
                    (None, 'Hog\'s Breath', False),
                    (None, 'Holy Grail Kush', False),
                    (None, 'Ice', False),
                    (None, 'Ice Cream Cake', False),
                    (None, 'Illuminati OG', False),
                    (None, 'Incredible Hulk', False),
                    (None, 'Island Kush', False),
                    (None, 'Island Sweet Skunk', False),
                    (None, 'J1', False),
                    (None, 'Jack Frost', False),
                    (None, 'Jack the Ripper', False),
                    (None, 'Jesus OG', False),
                    (None, 'Jet Fuel', False),
                    (None, 'Jillybean', False),
                    (None, 'Juicy Fruit', False),
                    (None, 'Kali Mist', False),
                    (None, 'Kandy Kush', False),
                    (None, 'Khalifa Kush', False),
                    (None, 'Killer Queen', False),
                    (None, 'King Tut', False),
                    (None, 'King\'s Kush', False),
                    (None, 'Kosher Kush', False),
                    (None, 'Kosher Tangie', False),
                    (None, 'Kush Mints', False),
                    (None, 'Kushberry', False),
                    (None, 'LA Confidential', False),
                    (None, 'LA Woman', False),
                    (None, 'LSD', False),
                    (None, 'Lamb\'s Bread', False),
                    (None, 'Larry OG', False),
                    (None, 'Laughing Buddha', False),
                    (None, 'Lava Cake', False),
                    (None, 'Lavender', False),
                    (None, 'Lemon Cake', False),
                    (None, 'Lemon Diesel', False),
                    (None, 'Lemon Kush', False),
                    (None, 'Lemon OG', False),
                    (None, 'Lemon Skunk', False),
                    (None, 'Lemon Tree', False),
                    (None, 'Lodi Dodi', False),
                    (None, 'MAC (Miracle Alien Cookies)', False),
                    (None, 'Mango Kush', False),
                    (None, 'Martian Mean Green', False),
                    (None, 'Master Kush', False),
                    (None, 'Maui Waui', False),
                    (None, 'Mazar', False),
                    (None, 'Mazar-I-Sharif', False),
                    (None, 'Medikit', False),
                    (None, 'Mendo Breath', False),
                    (None, 'Mickey Kush', False),
                    (None, 'Midnight', False),
                    (None, 'Mimosa', False),
                    (None, 'Mob Boss', False),
                    (None, 'Mochi', False),
                    (None, 'Nebula', False),
                    (None, 'Neville\'s Haze', False),
                    (None, 'Night Terror OG', False),
                    (None, 'Northern Lights', False),
                    (None, 'NYC Diesel', False),
                    (None, 'Obama Kush', False),
                    (None, 'Ogre', False),
                    (None, 'Opium', False),
                    (None, 'Orange Bud', False),
                    (None, 'Orange Creamsicle', False),
                    (None, 'Orange Kush', False),
                    (None, 'Orient Express', False),
                    (None, 'Original Glue (GG4)', False),
                    (None, 'Ozma', False),
                    (None, 'Pakistan Chitral Kush', False),
                    (None, 'Papaya', False),
                    (None, 'Pennywise', False),
                    (None, 'Pineapple Chunk', False),
                    (None, 'Pineapple OG', False),
                    (None, 'Pink Kush', False),
                    (None, 'Platinum OG', False),
                    (None, 'Plushberry', False),
                    (None, 'Power Plant', False),
                    (None, 'Pre-98 Bubba Kush', False),
                    (None, 'Purple Alien OG', False),
                    (None, 'Purple Animal Cookies', False),
                    (None, 'Purple Apricot', False),
                    (None, 'Purple Kush', False),
                    (None, 'Purple Punch', False),
                    (None, 'Purple Urkle', False),
                    (None, 'Qrazy Train', False),
                    (None, 'Quantum Kush', False),
                    (None, 'Queen Mother', False),
                    (None, 'Querkle', False),
                    (None, 'Raspberry Cough', False),
                    (None, 'Red Dragon', False),
                    (None, 'Remedy', False),
                    (None, 'Rene', False),
                    (None, 'Rigger Kush', False),
                    (None, 'Rockstar', False),
                    (None, 'Romulan', False),
                    (None, 'Royal Kush', False),
                    (None, 'Runtz', False),
                    (None, 'SAGE', False),
                    (None, 'SFV OG', False),
                    (None, 'Segerblom Haze', False),
                    (None, 'Sensi Star', False),
                    (None, 'Shishkaberry', False),
                    (None, 'Shiva Skunk', False),
                    (None, 'Short and Sweet', False),
                    (None, 'Skunk #1', False),
                    (None, 'Skywalker OG', False),
                    (None, 'Slice of Heaven', False),
                    (None, 'Slurricane', False),
                    (None, 'Snowcap', False),
                    (None, 'Somango', False),
                    (None, 'Somaui', False),
                    (None, 'Sour Jack', False),
                    (None, 'Sour Kush', False),
                    (None, 'Sour Tsunami', False),
                    (None, 'Stardawg', False),
                    (None, 'Strawberry Banana', False),
                    (None, 'Strawberry Cough', False),
                    (None, 'Strawberry Diesel', False),
                    (None, 'Sundae Driver', False),
                    (None, 'Sunset Sherbet (Sherbert)', False),
                    (None, 'Super Lemon Haze', False),
                    (None, 'Super Silver Haze', False),
                    (None, 'Super Skunk', False),
                    (None, 'Superglue', False),
                    (None, 'Sweet Nina', False),
                    (None, 'Sweet Tooth', False),
                    (None, 'Tahoe OG', False),
                    (None, 'Tangerine Dream', False),
                    (None, 'Tangie', False),
                    (None, 'The Church', False),
                    (None, 'The White', False),
                    (None, 'Thin Mint GSC', False),
                    (None, 'Tiger\'s Milk', False),
                    (None, 'Timewreck', False),
                    (None, 'Trainwreck', False),
                    (None, 'Triangle Kush', False),
                    (None, 'Triangle Mints', False),
                    (None, 'Tropicana Cookies', False),
                    (None, 'True OG', False),
                    (None, 'UK Cheese', False),
                    (None, 'Ultra Sour', False),
                    (None, 'Underdawg OG', False),
                    (None, 'Utopia Haze', False),
                    (None, 'Valentine X', False),
                    (None, 'Vanilla Kush', False),
                    (None, 'Venom OG', False),
                    (None, 'Violator Kush', False),
                    (None, 'Vortex', False),
                    (None, 'Wappa', False),
                    (None, 'Watermelon Kush', False),
                    (None, 'Wedding Cake', False),
                    (None, 'Wedding Crasher', False),
                    (None, 'White Buffalo', False),
                    (None, 'White Empress', False),
                    (None, 'White Fire OG (WiFi OG)', False),
                    (None, 'White Master', False),
                    (None, 'White Rhino', False),
                    (None, 'White Russian', False),
                    (None, 'White Tahoe Cookies', False),
                    (None, 'Williams Wonder', False),
                    (None, 'Willie Nelson', False),
                    (None, 'XJ-13', False),
                    (None, 'Xanadu', False),
                    (None, 'Y Griega', False),
                    (None, 'Yoda OG', False),
                    (None, 'Yumboldt', False),
                    (None, 'Z Face', False),
                    (None, 'Z Lato', False),
                    (None, 'Zeta Sage', False),
                    (None, 'Zeus OG', False),
                    (None, 'Zev', False),
                    (None, 'Zheetos', False),
                    (None, 'Zhirley Temple', False),
                    (None, 'Zhits Fire', False),
                    (None, 'Zion\'s Amethyst', False),
                    (None, 'Zkippy', False),
                    (None, 'Zkittle Head', False),
                    (None, 'Zkittlez', False),
                    (None, 'Zkittlez Cake', False),
                    (None, 'Zkittlez Glue', False),
                    (None, 'Zkittlez Kush Mints', False),
                    (None, 'Zkittlez Pie', False),
                    (None, 'Zkittlez Punch', False),
                    (None, 'Zkittlez Runtz', False),
                    (None, 'Zlato', False),
                    (None, 'Zoap', False),
                    (None, 'Zombie Kush', False),
                    (None, 'Zombie OG', False),
                    (None, 'Zookies', False),
                    (None, '1 Stunna', False),
                    (None, '100 OG', False),
                    (None, '10k Jack', False),
                    (None, '10th Planet', False),
                    (None, '11 Roses', False),
                    (None, '12 Year OG', False),
                    (None, '120K', False),
                    (None, '13 Dawgs', False),
                    (None, '14er', False),
                    (None, '2 Face', False),
                    (None, '2 Fast 2 Vast', False),
                    (None, '2 Scoops', False),
                    (None, '2090 Shit', False),
                    (None, '22 Jack', False),
                    (None, '22 OG', False),
                    (None, '22 Red', False),
                    (None, '24K Blue Dream', False),
                    (None, '24K Gold', False),
                    (None, '2Pak', False),
                    (None, '3 Bear OG', False),
                    (None, '3 Bears', False),
                    (None, '3 Blue Kings', False),
                    (None, '3 Chems', False),
                    (None, '3 Gorillas', False),
                    (None, '3 In The Pink', False),
                    (None, '3 Kings', False),
                    (None, '303 OG Kush', False),
                    (None, '309 OG', False),
                    (None, '33 Bananas', False),
                    (None, '33 Mints', False),
                    (None, '33 Splitter', False),
                    (None, '38 Special', False),
                    (None, '3D', False),
                    (None, '3D CBD', False),
                    (None, '3X Crazy', False),
                    (None, '3rd Coast Panama Chunk', False),
                    (None, '40 Elephants', False),
                    (None, '405 Cookies', False),
                    (None, '5th Dimension', False),
                    (None, '5th Element', False),
                    (None, '60 Day Lemon', False),
                    (None, '60 Day Wonder', False),
                    (None, '66 Cookies', False),
                    (None, '6Ixth Sense', False),
                    (None, '7 Ghost', False),
                    (None, '7 Of 9', False),
                    (None, '7 Steps To Heaven', False),
                    (None, '702 Headband', False),
                    (None, '707 Headband', False),
                    (None, '707 Kush', False),
                    (None, '707 Truthband', False),
                    (None, '8 Ball Kush', False),
                    (None, '8 Inch Bagel', False),
                    (None, '805 Glue', False),
                    (None, '805 Sour', False),
                    (None, '814 Fireworks', False),
                    (None, '818 OG', False),
                    (None, '88G', False),

                    # Thai local strains (with Thai translations)
                    ('ไทยสติ๊ก', 'Thai Stick', True),
                    ('ช้างไทย', 'Thai Elephant', False),
                    ('กัญชาไทย', 'Thai Cannabis', False),
                    ('สายพันธุ์เหนือ', 'Northern Thai', False),
                    ('สายพันธุ์อีสาน', 'Isaan Strain', False),
                ]

                cur.executemany("""
                    INSERT INTO strain_names (name_th, name_en, is_popular)
                    VALUES (%s, %s, %s)
                """, all_strains)

            # Insert breeder names if table is empty
            cur.execute("SELECT COUNT(*) FROM breeders")
            breeder_count = cur.fetchone()[0]

            if breeder_count == 0:
                # All breeders from the file
                all_breeders = [
                    ('303 Seeds', False),
                    ('707 Seed Bank', False),
                    ('710 Genetics', False),
                    ('Ace Seeds', False),
                    ('Aficionado Seeds', False),
                    ('Alpine Seeds', False),
                    ('Anesia Seeds', False),
                    ('Apex Seeds', False),
                    ('Archive Seed Bank', False),
                    ('Atlas Seeds', False),
                    ('Attitude Seedbank', False),
                    ('Authentic Genetics', False),
                    ('Auto Seeds', False),
                    ('BC Bud Depot', False),
                    ('BOG Seeds', False),
                    ('Barney\'s Farm', True),
                    ('BeLeaf Cannabis Genetics', False),
                    ('Big Buddha Seeds', False),
                    ('Blimburn Seeds', False),
                    ('Bodhi Seeds', False),
                    ('Brothers Grimm Seeds', False),
                    ('Buddha Seeds', False),
                    ('CBD Crew', False),
                    ('Cali Connection', False),
                    ('Cannabiogen', False),
                    ('Cannarado Genetics', False),
                    ('Capulator', False),
                    ('Clearwater Genetics', False),
                    ('Compound Genetics', False),
                    ('Connoisseur Genetics', False),
                    ('Cookies Fam Genetics', True),
                    ('Cookies Seed Bank', False),
                    ('Crockett Family Farms', False),
                    ('Crop King Seeds', False),
                    ('DJ Short / Old World Genetics', False),
                    ('DNA Genetics', True),
                    ('Delicious Seeds', False),
                    ('Dinafem Seeds', True),
                    ('Dirty Bird Genetics', False),
                    ('Dominion Seed Company', False),
                    ('Dr Underground', False),
                    ('Dr. Blaze', False),
                    ('Duke Diamond\'s Vault', False),
                    ('Dutch Passion', True),
                    ('Dynasty Genetics', False),
                    ('Elev8 Seeds', False),
                    ('Emerald Triangle Seeds', False),
                    ('Envy Genetics', False),
                    ('Ethos Genetics', False),
                    ('Ethos Seeds', False),
                    ('Exotic Genetix', False),
                    ('Fast Buds', True),
                    ('Fast Buds 420', False),
                    ('Fast Flowers', False),
                    ('Feminized Seeds Co', False),
                    ('Flash Seeds', False),
                    ('FreeWorld Genetics', False),
                    ('Freeborn Selections', False),
                    ('Fresh Coast Genetics', False),
                    ('G13 Labs', False),
                    ('GTR (Grow the Revolution)', False),
                    ('Gage Green Group', False),
                    ('Gorilla Glue Genetics', False),
                    ('Green Bodhi', False),
                    ('Green House Seed Company', True),
                    ('Greenthumb Seeds', False),
                    ('Growers Choice Seeds', False),
                    ('Heavyweight Seeds', False),
                    ('Homegrown Cannabis Co', False),
                    ('House of Dankness', False),
                    ('Humboldt Seed Company', False),
                    ('Humboldt Seed Organization', False),
                    ('ILGM (I Love Growing Marijuana)', False),
                    ('In House Genetics', False),
                    ('Jordan of the Islands', False),
                    ('Jungle Boys Genetics', True),
                    ('Kalashnikov Seeds', False),
                    ('Kannabia Seeds', False),
                    ('Karma Genetics', False),
                    ('Kera Seeds', False),
                    ('Khalifa Genetics', False),
                    ('LIT Farms', False),
                    ('Liontree Genetics', False),
                    ('Lovin In Her Eyes', False),
                    ('MSNL (Marijuana Seeds NL)', False),
                    ('Magus Genetics', False),
                    ('Mandala Seeds', False),
                    ('Medical Seeds', False),
                    ('Mephisto Genetics', True),
                    ('Ministry of Cannabis', False),
                    ('Mosca Seeds', False),
                    ('Mr. Nice Seedbank', True),
                    ('Next Generation Seeds', False),
                    ('Night Owl Seeds', False),
                    ('Nirvana Seeds', True),
                    ('OG Raskal Genetics', False),
                    ('Ocean Grown Seeds',False),
                    ('Oni Seed Co', False),
                    ('Paradise Seeds', True),
                    ('Philosopher Seeds', False),
                    ('Positronics Seeds', False),
                    ('Premium Cultivars', False),
                    ('Purple City Genetics', False),
                    ('Pyramid Seeds', False),
                    ('Rare Dankness', False),
                    ('Raw Genetics', False),
                    ('Resin Seeds', False),
                    ('Ripper Seeds', False),
                    ('Royal Queen Seeds', True),
                    ('Seed Junky Genetics', False),
                    ('Seed Stockers', False),
                    ('Seed Supreme', False),
                    ('Seedsman', True),
                    ('Sensi Seeds', True),
                    ('Serious Seeds', False),
                    ('Sherbinski\'s Genetics', False),
                    ('Sin City Seeds', False),
                    ('Snow High Seeds', False),
                    ('Solfire Gardens', False),
                    ('Spliff Seeds', False),
                    ('Square One Genetics', False),
                    ('Sub Rosa Seed', False),
                    ('Subcool Seeds (TGA)', False),
                    ('Super Sativa Seed Club', False),
                    ('Sweet Seeds', True),
                    ('Symbiotic Genetics', False),
                    ('T.H. Seeds', False),
                    ('Tangled Roots Genetics', False),
                    ('Terphogz (Zkittlez)', False),
                    ('Tiki Madman', False),
                    ('Top Dawg Genetics', False),
                    ('Top Shelf Elite Seeds', False),
                    ('Tropical Seeds Company', False),
                    ('Twenty20 Mendocino', False),
                    ('Urban Legends Genetics', False),
                    ('Vision Seeds', False),
                    ('Wolfpack Selections', False),
                    ('Yieldmonger Genetics', False),
                    ('Zamnesia', False),
                    ('Zmoothiez', False)
                ]

                cur.executemany("""
                    INSERT INTO breeders (name, is_popular)
                    VALUES (%s, %s)
                """, all_breeders)

            # Create buds_data table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS buds_data (
                    id SERIAL PRIMARY KEY,
                    strain_name_th VARCHAR(255),
                    strain_name_en VARCHAR(255) NOT NULL,
                    breeder VARCHAR(255),
                    strain_type VARCHAR(50) CHECK (strain_type IN ('Indica', 'Sativa', 'Hybrid')),
                    thc_percentage DECIMAL(5,2) CHECK (thc_percentage >= 0 AND thc_percentage <= 100),
                    cbd_percentage DECIMAL(5,2) CHECK (cbd_percentage >= 0 AND cbd_percentage <= 100),
                    grade VARCHAR(10) CHECK (grade IN ('A+', 'A', 'B+', 'B', 'C')),
                    aroma_flavor TEXT,
                    top_terpenes_1 VARCHAR(100),
                    top_terpenes_2 VARCHAR(100),
                    top_terpenes_3 VARCHAR(100),
                    mental_effects_positive TEXT,
                    mental_effects_negative TEXT,
                    physical_effects_positive TEXT,
                    physical_effects_negative TEXT,
                    recommended_time VARCHAR(20) CHECK (recommended_time IN ('กลางวัน', 'กลางคืน', 'ตลอดวัน')),
                    grow_method VARCHAR(30) CHECK (grow_method IN ('Indoor', 'Outdoor', 'Greenhouse', 'Hydroponic')),
                    harvest_date DATE,
                    batch_number VARCHAR(100),
                    grower_id INTEGER REFERENCES users(id),
                    grower_license_verified BOOLEAN DEFAULT FALSE,
                    fertilizer_type VARCHAR(20) CHECK (fertilizer_type IN ('Organic', 'Chemical', 'Mixed')),
                    flowering_type VARCHAR(20) CHECK (flowering_type IN ('Photoperiod', 'Autoflower')),
                    status VARCHAR(20) CHECK (status IN ('available', 'sold_out')) DEFAULT 'available',
                    lab_test_name VARCHAR(255),
                    test_type VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by INTEGER REFERENCES users(id),
                    image_1_url VARCHAR(500),
                    image_2_url VARCHAR(500),
                    image_3_url VARCHAR(500),
                    image_4_url VARCHAR(500)
                );
            """)

            # Add image columns if they don't exist (for existing databases)
            for i in range(1, 5):
                try:
                    cur.execute(f"ALTER TABLE buds_data ADD COLUMN IF NOT EXISTS image_{i}_url VARCHAR(500)")
                    print(f"Added image_{i}_url column")
                except psycopg2.errors.DuplicateColumn:
                    pass  # Column already exists

            # Add certificate columns if they don't exist
            try:
                cur.execute("ALTER TABLE buds_data ADD COLUMN IF NOT EXISTS lab_test_name VARCHAR(255)")
                print("Added lab_test_name column")
            except psycopg2.errors.DuplicateColumn:
                pass  # Column already exists
            except Exception as e:
                print(f"Note: lab_test_name column may already exist: {e}")

            try:
                cur.execute("ALTER TABLE buds_data ADD COLUMN IF NOT EXISTS test_type VARCHAR(255)")
                print("Added test_type column")
            except psycopg2.errors.DuplicateColumn:
                pass  # Column already exists
            except Exception as e:
                print(f"Note: test_type column may already exist: {e}")

            # Add certificate image columns if they don't exist
            for i in range(1, 5):
                try:
                    cur.execute(f"ALTER TABLE buds_data ADD COLUMN IF NOT EXISTS certificate_image_{i}_url VARCHAR(500)")
                    print(f"Added certificate_image_{i}_url column")
                except psycopg2.errors.DuplicateColumn:
                    pass  # Column already exists
                except Exception as e:
                    print(f"Note: certificate_image_{i}_url column may already exist: {e}")

            # Add status column if it doesn't exist (for existing databases)
            try:
                cur.execute("""
                    ALTER TABLE buds_data 
                    ADD COLUMN IF NOT EXISTS status VARCHAR(20) CHECK (status IN ('available', 'sold_out')) DEFAULT 'available';
                """)
                # Set default status for existing records
                cur.execute("UPDATE buds_data SET status = 'available' WHERE status IS NULL;")
            except Exception as e:
                print(f"Note: Status column may already exist: {e}")

            # Create reviews table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id SERIAL PRIMARY KEY,
                    bud_reference_id INTEGER REFERENCES buds_data(id) ON DELETE CASCADE,
                    reviewer_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    overall_rating SMALLINT CHECK (overall_rating >= 1 AND overall_rating <= 5),
                    aroma_flavors TEXT[] DEFAULT '{}',
                    aroma_rating SMALLINT CHECK (aroma_rating >= 1 AND aroma_rating <= 5),
                    selected_effects TEXT[] DEFAULT '{}',
                    short_summary VARCHAR(200),
                    full_review_content TEXT,
                    review_images TEXT[] DEFAULT '{}',
                    video_review_url VARCHAR(500),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Add selected_effects column if it doesn't exist (for existing databases)
            cur.execute("""
                ALTER TABLE reviews 
                ADD COLUMN IF NOT EXISTS selected_effects TEXT[] DEFAULT '{}';
            """)

            # Add video_review_url column if it doesn't exist (for existing databases)
            cur.execute("""
                ALTER TABLE reviews 
                ADD COLUMN IF NOT EXISTS video_review_url VARCHAR(500);
            """)

            # Add referral system and approval columns
            cur.execute("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS referred_by INTEGER REFERENCES users(id),
                ADD COLUMN IF NOT EXISTS referral_code VARCHAR(50) UNIQUE,
                ADD COLUMN IF NOT EXISTS is_approved BOOLEAN DEFAULT TRUE,
                ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS approved_by INTEGER REFERENCES users(id);
            """)

            # Set existing users as approved
            cur.execute("UPDATE users SET is_approved = TRUE WHERE is_approved IS NULL")

            # Generate referral codes for existing users
            cur.execute("SELECT id FROM users WHERE referral_code IS NULL")
            users_without_codes = cur.fetchall()

            for user_row in users_without_codes:
                import secrets
                referral_code = secrets.token_urlsafe(8)
                cur.execute("UPDATE users SET referral_code = %s WHERE id = %s", (referral_code, user_row[0]))

            # Create admin_settings table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_settings (
                    id SERIAL PRIMARY KEY,
                    setting_key VARCHAR(255) UNIQUE NOT NULL,
                    setting_value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_by INTEGER REFERENCES users(id)
                );
            """)

            # Create admin_accounts table for secure admin management
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_accounts (
                    id SERIAL PRIMARY KEY,
                    admin_name VARCHAR(100) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    last_login TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by INTEGER REFERENCES users(id),
                    login_attempts INTEGER DEFAULT 0,
                    locked_until TIMESTAMP,
                    session_token VARCHAR(255),
                    token_expires TIMESTAMP
                );
            """)

            # Create admin_activity_logs table for security tracking
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_activity_logs (
                    id SERIAL PRIMARY KEY,
                    admin_name VARCHAR(100),
                    action VARCHAR(255) NOT NULL,
                    ip_address VARCHAR(45),
                    user_agent TEXT,
                    success BOOLEAN DEFAULT TRUE,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Create user_activity_logs table for user actions tracking
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_activity_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    username VARCHAR(100),
                    action VARCHAR(255) NOT NULL,
                    resource_type VARCHAR(50),
                    resource_id INTEGER,
                    ip_address VARCHAR(45),
                    user_agent TEXT,
                    old_data JSONB,
                    new_data JSONB,
                    success BOOLEAN DEFAULT TRUE,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Insert default admin settings if table is empty
            cur.execute("SELECT COUNT(*) FROM admin_settings")
            settings_count = cur.fetchone()[0]

            if settings_count == 0:
                default_settings = [
                    ('autoApproval', 'false'),
                    ('publicRegistration', 'true'),
                    ('emailVerification', 'true'),
                    ('autoApproveReviews', 'false'),
                    ('maxImagesPerReview', '4'),
                    ('maxImageSize', '5'),
                    ('multipleLogin', 'true'),
                    ('sessionTimeout', '60'),
                    ('loginLogging', 'true'),
                    ('siteName', 'Cannabis App'),
                    ('siteDescription', 'แพลตฟอร์มสำหรับแชร์ข้อมูลและรีวิวกัญชา'),
                    ('adminEmail', 'admin@budtboy.app'),
                    ('defaultLanguage', 'th'),
                    ('displayMode', 'auto'),
                    ('itemsPerPage', '20'),
                    ('enableNotifications', 'true'),
                    ('maintenanceMode', 'false'),
                    ('registrationMode', 'public')
                ]

                cur.executemany("""
                    INSERT INTO admin_settings (setting_key, setting_value)
                    VALUES (%s, %s)
                """, default_settings)

            # Create activities table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS activities (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    start_registration_date TIMESTAMP NOT NULL,
                    end_registration_date TIMESTAMP NOT NULL,
                    judging_criteria TEXT,
                    max_participants INTEGER DEFAULT 0,
                    first_prize_description TEXT,
                    first_prize_value DECIMAL(10,2) DEFAULT 0,
                    first_prize_image VARCHAR(500),
                    second_prize_description TEXT,
                    second_prize_value DECIMAL(10,2) DEFAULT 0,
                    second_prize_image VARCHAR(500),
                    third_prize_description TEXT,
                    third_prize_value DECIMAL(10,2) DEFAULT 0,
                    third_prize_image VARCHAR(500),
                    status VARCHAR(20) CHECK (status IN ('upcoming', 'registration_open', 'registration_closed', 'judging', 'completed')) DEFAULT 'upcoming',
                    created_by INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Add new prize columns if they don't exist (for existing databases)
            try:
                # First, add the new description columns
                cur.execute("""
                    ALTER TABLE activities 
                    ADD COLUMN IF NOT EXISTS first_prize_description TEXT,
                    ADD COLUMN IF NOT EXISTS second_prize_description TEXT,
                    ADD COLUMN IF NOT EXISTS third_prize_description TEXT;
                """)

                # Keep existing columns for backward compatibility but rename them internally
                cur.execute("""
                    ALTER TABLE activities 
                    ADD COLUMN IF NOT EXISTS first_prize_image VARCHAR(500),
                    ADD COLUMN IF NOT EXISTS second_prize_image VARCHAR(500),
                    ADD COLUMN IF NOT EXISTS third_prize_image VARCHAR(500),
                    ADD COLUMN IF NOT EXISTS first_prize_value DECIMAL(10,2) DEFAULT 0,
                    ADD COLUMN IF NOT EXISTS second_prize_value DECIMAL(10,2) DEFAULT 0,
                    ADD COLUMN IF NOT EXISTS third_prize_value DECIMAL(10,2) DEFAULT 0;
                """)

                # Migrate data from old columns to new format if needed
                cur.execute("""
                    UPDATE activities 
                    SET first_prize_description = COALESCE(first_prize_name, first_prize_amount::TEXT),
                        second_prize_description = COALESCE(second_prize_name, second_prize_amount::TEXT),
                        third_prize_description = COALESCE(third_prize_name, third_prize_amount::TEXT)
                    WHERE first_prize_description IS NULL;
                """)

                # Copy old prize values if new ones are not set
                cur.execute("""
                    UPDATE activities 
                    SET first_prize_value = COALESCE(first_prize_value, first_prize_amount),
                        second_prize_value = COALESCE(second_prize_value, second_prize_amount),
                        third_prize_value = COALESCE(third_prize_value, third_prize_amount)
                    WHERE first_prize_value = 0 AND first_prize_amount > 0;
                """)

            except Exception as e:
                print(f"Note: Prize columns may already exist: {e}")

            # Create activity participants table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS activity_participants (
                    id SERIAL PRIMARY KEY,
                    activity_id INTEGER REFERENCES activities(id) ON DELETE CASCADE,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    bud_id INTEGER REFERENCES buds_data(id) ON DELETE CASCADE,
                    submission_images TEXT[] DEFAULT '{}',
                    submission_description TEXT,
                    rank INTEGER,
                    prize_amount DECIMAL(10,2),
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(activity_id, user_id, bud_id)
                );
            """)

            # Create index for better performance
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_strain_names_th ON strain_names(name_th);
                CREATE INDEX IF NOT EXISTS idx_strain_names_en ON strain_names(name_en);
                CREATE INDEX IF NOT EXISTS idx_strain_names_popular ON strain_names(is_popular);
                CREATE INDEX IF NOT EXISTS idx_breeders_name ON breeders(name);
                CREATE INDEX IF NOT EXISTS idx_breeders_popular ON breeders(is_popular);
                CREATE INDEX IF NOT EXISTS idx_buds_strain_name_th ON buds_data(strain_name_th);
                CREATE INDEX IF NOT EXISTS idx_buds_strain_name_en ON buds_data(strain_name_en);
                CREATE INDEX IF NOT EXISTS idx_buds_strain_type ON buds_data(strain_type);
                CREATE INDEX IF NOT EXISTS idx_buds_grower_id ON buds_data(grower_id);
                CREATE INDEX IF NOT EXISTS idx_buds_created_by ON buds_data(created_by);
                CREATE INDEX IF NOT EXISTS idx_buds_created_at ON buds_data(created_at);
                CREATE INDEX IF NOT EXISTS idx_reviews_bud_id ON reviews(bud_reference_id);
                CREATE INDEX IF NOT EXISTS idx_reviews_reviewer_id ON reviews(reviewer_id);
                CREATE INDEX IF NOT EXISTS idx_reviews_rating ON reviews(overall_rating);
                CREATE INDEX IF NOT EXISTS idx_reviews_created_at ON reviews(created_at);
                CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
                CREATE INDEX IF NOT EXISTS idx_admin_settings_key ON admin_settings(setting_key);
                CREATE INDEX IF NOT EXISTS idx_activities_status ON activities(status);
                CREATE INDEX IF NOT EXISTS idx_activities_dates ON activities(start_registration_date, end_registration_date);
                CREATE INDEX IF NOT EXISTS idx_activity_participants_activity ON activity_participants(activity_id);
                CREATE INDEX IF NOT EXISTS idx_activity_participants_user ON activity_participants(user_id);
            """)

            conn.commit()

            # Insert sample bud data for existing users
            try:
                # Check if there are any users in the system
                cur.execute("SELECT id FROM users LIMIT 5")
                user_ids = [row[0] for row in cur.fetchall()]

                # Check for environment variable to force create sample data
                force_create_sample = os.environ.get('FORCE_CREATE_SAMPLE_DATA', 'false').lower() == 'true'

                if user_ids:
                    # Check if bud data already exists
                    cur.execute("SELECT COUNT(*) FROM buds_data")
                    bud_count = cur.fetchone()[0]

                    if bud_count == 0 or force_create_sample:
                        print("Adding sample bud data...")

                        # Sample bud data for each user
                        sample_buds = []
                        for i, user_id in enumerate(user_ids):
                            sample_buds.extend([
                                # User's first bud
                                (
                                    f'บลูดรีม{i+1}', 'Blue Dream', 'Barney\'s Farm', 'Hybrid',
                                    18.5, 1.2, 'A+', 'หวาน, เบอร์รี่, ซิตรัส',
                                    'Myrcene', 'Limonene', 'Pinene',
                                    'ผ่อนคลาย, สร้างสรรค์, สุขใจ', '',
                                    'บรรเทาปวด, คลายกล้าม', 'ปากแห้ง',
                                    'ตลอดวัน', 'Indoor', '2024-12-01',
                                    f'BD2024-{i+1:03d}', user_id, True,
                                    'Organic', 'Photoperiod', None, None, user_id, 'available'
                                ),
                                # User's second bud
                                (
                                    f'โอจี คัช{i+1}', 'OG Kush', 'DNA Genetics', 'Indica',
                                    22.3, 0.8, 'A', 'ดิน, สน, เผ็ด',
                                    'Myrcene', 'Caryophyllene', 'Limonene',
                                    'ผ่อนคลาย, หลับง่าย', 'ง่วงหนัก',
                                    'บรรเทาปวด, หลับง่าย', 'ตาแดง, ปากแห้ง',
                                    'กลางคืน', 'Indoor', '2024-11-15',
                                    f'OG2024-{i+1:03d}', user_id, True,
                                    'Chemical', 'Photoperiod', None, None, user_id, 'active'
                                ),
                                # User's third bud  
                                (
                                    f'ไวท์ วิโดว์{i+1}', 'White Widow', 'Green House Seed Company', 'Hybrid',
                                    20.1, 1.5, 'A+', 'หวาน, ดอกไม้, มินต์',
                                    'Pinene', 'Myrcene', 'Limonene',
                                    'ตื่นตัว, โฟกัส, เบิกบาน', '',
                                    'ต้านอักเสบ, สดชื่น', 'ตาแห้ง',
                                    'กลางวัน', 'Greenhouse', '2024-10-20',
                                    f'WW2024-{i+1:03d}', user_id, True,
                                    'Organic', 'Photoperiod', None, None, user_id, 'available'
                                )
                            ])

                        # Insert sample buds
                        cur.executemany("""
                            INSERT INTO buds_data (
                                strain_name_th, strain_name_en, breeder, strain_type,
                                thc_percentage, cbd_percentage, grade, aroma_flavor,
                                top_terpenes_1, top_terpenes_2, top_terpenes_3,
                                mental_effects_positive, mental_effects_negative,
                                physical_effects_positive, physical_effects_negative,
                                recommended_time, grow_method, harvest_date,
                                batch_number, grower_id, grower_license_verified,
                                fertilizer_type, flowering_type, lab_test_name, test_type,
                                created_by, status
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                            )
                        """, sample_buds)

                        conn.commit()
                        print(f"Added {len(sample_buds)} sample bud records for {len(user_ids)} users")
                    else:
                        print(f"Bud data already exists ({bud_count} records)")
                else:
                    print("No users found - skipping sample bud data")

            except Exception as e:
                print(f"Error adding sample bud data: {e}")

            # Create default admin account if not exists
            create_default_admin_if_not_exists(cur, conn)

            print("Tables created successfully")
        except Exception as e:
            print(f"Error creating tables: {e}")
        finally:
            cur.close()
            return_db_connection(conn)

def create_default_admin_if_not_exists(cur, conn):
    """Create default admin account if it doesn't exist"""
    try:
        # Check if default admin exists
        cur.execute("SELECT id FROM admin_accounts WHERE admin_name = %s", ('admin999',))
        if cur.fetchone():
            print("Default admin 'admin999' already exists")
            return

        # Create default admin
        default_admin_name = 'admin999'
        default_admin_password = 'Admin123!@#'
        password_hash = hash_password(default_admin_password)

        cur.execute("""
            INSERT INTO admin_accounts (admin_name, password_hash, is_active, created_at)
            VALUES (%s, %s, TRUE, NOW())
        """, (default_admin_name, password_hash))

        conn.commit()
        print(f"✅ Created default admin account: {default_admin_name}")
        print(f"🔑 Default admin password: {default_admin_password}")
        print("⚠️  Please change the password after first login in production!")

        # Log admin creation
        log_admin_activity(default_admin_name, 'ADMIN_CREATED_DEFAULT', True, 
                         details='Default admin account created automatically')

    except Exception as e:
        print(f"Error creating default admin: {e}")
        conn.rollback()

def generate_verification_token():
    return secrets.token_urlsafe(32)

def hash_password(password):
    """Hash password using bcrypt with salt"""
    # Convert password to bytes if it's a string
    if isinstance(password, str):
        password = password.encode('utf-8')

    # Generate salt and hash the password
    salt = bcrypt.gensalt(rounds=12)  # 12 rounds is good balance of security and performance
    hashed = bcrypt.hashpw(password, salt)

    # Return as string for database storage
    return hashed.decode('utf-8')

def verify_password(password, hashed_password):
    """Verify password against bcrypt hash with error handling"""
    try:
        if isinstance(password, str):
            password = password.encode('utf-8')
        if isinstance(hashed_password, str):
            hashed_password = hashed_password.encode('utf-8')

        return bcrypt.checkpw(password, hashed_password)
    except ValueError as e:
        print(f"Password verification error: {e}")
        # Handle legacy passwords or invalid hashes
        return False
    except Exception as e:
        print(f"Unexpected error in password verification: {e}")
        return False

def validate_password_strength(password):
    """Validate password meets security requirements"""
    if not password or len(password) < 8:
        return False, "รหัสผ่านต้องมีอย่างน้อย 8 ตัวอักษร"

    if len(password) > 128:
        return False, "รหัสผ่านยาวเกินไป (สูงสุด 128 ตัวอักษร)"

    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)

    if not (has_upper and has_lower and has_digit):
        return False, "รหัสผ่านต้องมีตัวอักษรพิมพ์ใหญ่ พิมพ์เล็ก และตัวเลข"

    return True, "รหัสผ่านปลอดภัย"

def send_verification_email(email, username, token):
    try:
        # For demo/testing - simulate email sending if no real email config
        if app.config['MAIL_PASSWORD'] == 'demo_password':
            verification_url = url_for('verify_email', token=token, _external=True)
            print(f"""
            🔶 จำลองการส่งอีเมล (Demo Mode) 🔶
            ถึง: {email}
            หัวข้อ: ยืนยันการลงทะเบียน - Cannabis App

            สวัสดี {username}!
            ขอบคุณที่ลงทะเบียนกับ Cannabis App

            ลิงก์ยืนยัน: {verification_url}

            📌 สำหรับการทดสอบ: คุณสามารถคัดลอกลิงก์ข้างต้นไปวางในเบราว์เซอร์เพื่อยืนยันได้เลย
            """)
            return True

        verification_url = url_for('verify_email', token=token, _external=True)
        msg = Message(
            subject='ยืนยันการลงทะเบียน - Cannabis App',
            recipients=[email],
            sender=app.config['MAIL_DEFAULT_SENDER'],
            html=f"""
            <h2>สวัสดี {username}!</h2>
            <p>ขอบคุณที่ลงทะเบียนกับ Cannabis App</p>
            <p>กรุณาคลิกลิงก์ด้านล่างเพื่อยืนยันอีเมลของคุณ:</p>
            <a href="{verification_url}" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">
                ยืนยันอีเมล
            </a>
            <p>หากคุณไม่ได้ลงทะเบียน กรุณาเพิกเฉยต่ออีเมลนี้</p>
            <p>ลิงก์นี้จะหมดอายุใน 24 ชั่วโมง</p>
            """
        )
        mail.send(msg)
        print(f"Verification email sent successfully to {email}")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def send_password_reset_email(email, username, token):
    """Send password reset email"""
    try:
        reset_url = url_for('reset_password_page', token=token, _external=True)

        # For demo/testing - simulate email sending if no real email config
        if DEMO_EMAIL_MODE:
            print(f"""
            🔶 จำลองการส่งอีเมลรีเซ็ตรหัสผ่าน (Demo Mode) 🔶
            ถึง: {email}
            หัวข้อ: รีเซ็ตรหัสผ่าน - Cannabis App

            สวัสดี {username}!
            เราได้รับคำขอรีเซ็ตรหัสผ่านสำหรับบัญชีของคุณ

            ลิงก์รีเซ็ตรหัสผ่าน: {reset_url}

            📌 สำหรับการทดสอบ: คุณสามารถคัดลอกลิงก์ข้างต้นไปวางในเบราว์เซอร์เพื่อรีเซ็ตรหัสผ่านได้เลย

            หากคุณไม่ได้ขอรีเซ็ตรหัสผ่าน กรุณาเพิกเฉยต่ออีเมลนี้
            ลิงก์นี้จะหมดอายุใน 1 ชั่วโมง
            """)
            return True

        # Try to send real email
        msg = Message(
            subject='รีเซ็ตรหัสผ่าน - Cannabis App',
            recipients=[email],
            sender=app.config['MAIL_DEFAULT_SENDER'],
            html=f"""
            <h2>สวัสดี {username}!</h2>
            <p>เราได้รับคำขอรีเซ็ตรหัสผ่านสำหรับบัญชีของคุณ</p>
            <p>กรุณาคลิกลิงก์ด้านล่างเพื่อรีเซ็ตรหัสผ่าน:</p>
            <a href="{reset_url}" style="background-color: #f44336; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">
                รีเซ็ตรหัสผ่าน
            </a>
            <p>หากคุณไม่ได้ขอรีเซ็ตรหัสผ่าน กรุณาเพิกเฉยต่ออีเมลนี้</p>
            <p>ลิงก์นี้จะหมดอายุใน 1 ชั่วโมง</p>
            <p>เพื่อความปลอดภัย กรุณาเปลี่ยนรหัสผ่านหลังจากเข้าสู่ระบบ</p>
            """
        )
        mail.send(msg)
        print(f"Password reset email sent successfully to {email}")
        return True
    except Exception as e:
        print(f"Error sending password reset email: {e}")
        # Fall back to demo mode if email fails
        print(f"""
        🔶 อีเมลส่งไม่ได้ - แสดงลิงก์รีเซ็ตในคอนโซลแทน 🔶
        ถึง: {email} ({username})
        ลิงก์รีเซ็ต: {reset_url}
        """)
        return True  # Return True so the user still gets success message

@app.route('/')
def index():
    # Check if user is logged in, if not redirect to auth page
    if 'user_id' not in session:
        return redirect('/auth')
    return redirect('/profile')

def is_authenticated():
    return 'user_id' in session

def is_approved():
    if not is_authenticated():
        return False

    user_id = session.get('user_id')
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT is_approved FROM users WHERE id = %s", (user_id,))
            result = cur.fetchone()
            cur.close()
            return_db_connection(conn)
            return result and result[0]
        except:
            if conn:
                return_db_connection(conn)
            return False
    return False

@app.route('/profile')
def profile():
    if not is_authenticated():
        return redirect('/auth')
    return render_template('profile.html')

@app.route('/activity')
def activity():
    if not is_authenticated():
        return redirect('/auth')
    if not is_approved():
        return redirect('/profile?not_approved=1')
    return render_template('activity.html')

@app.route('/api/user_buds')
def get_user_buds():
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session.get('user_id')
    cache_key = f"user_buds_{user_id}"

    # Check cache first with activity-specific TTL
    cached_data = get_cache(cache_key, ACTIVITY_CACHE_TTL)
    if cached_data:
        return jsonify({'buds': cached_data})

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        if not conn:
            print("Failed to get database connection")
            return jsonify({'error': 'Database connection failed', 'buds': []}), 500

        cur = conn.cursor()

        # Optimized query with better performance - separate review stats
        # Check if certificate columns exist first
        cur.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='buds_data' AND column_name IN ('lab_test_name', 'test_type')
        """)
        existing_columns = [row[0] for row in cur.fetchall()]
        has_lab_test = 'lab_test_name' in existing_columns
        has_test_type = 'test_type' in existing_columns

        if has_lab_test and has_test_type:
            cur.execute("""
                SELECT b.id, b.strain_name_en, b.strain_name_th, b.breeder, b.thc_percentage, 
                       b.cbd_percentage, b.strain_type, b.created_at, b.image_1_url, b.status,
                       b.lab_test_name, b.test_type
                FROM buds_data b
                WHERE b.created_by = %s 
                ORDER BY b.created_at DESC
                LIMIT 50
            """, (user_id,))
        else:
            cur.execute("""
                SELECT b.id, b.strain_name_en, b.strain_name_th, b.breeder, b.thc_percentage, 
                       b.cbd_percentage, b.strain_type, b.created_at, b.image_1_url, b.status,
                       NULL as lab_test_name, NULL as test_type
                FROM buds_data b
                WHERE b.created_by = %s 
                ORDER BY b.created_at DESC
                LIMIT 50
            """, (user_id,))

        bud_rows = cur.fetchall()

        # Get review stats in separate query for better performance
        bud_ids = [row[0] for row in bud_rows]
        review_stats = {}

        if bud_ids:
            cur.execute("""
                SELECT bud_reference_id, 
                       COALESCE(AVG(overall_rating), 0) as avg_rating,
                       COUNT(id) as review_count
                FROM reviews 
                WHERE bud_reference_id = ANY(%s)
                GROUP BY bud_reference_id
            """, (bud_ids,))

        for stats_row in cur.fetchall():
                review_stats[stats_row[0]] = {
                    'avg_rating': float(stats_row[1]),
                    'review_count': stats_row[2]
                }

        buds = []
        for row in bud_rows:
            bud_id = row[0]
            stats = review_stats.get(bud_id, {'avg_rating': 0, 'review_count': 0})

            buds.append({
                'id': bud_id,
                'strain_name_en': row[1],
                'strain_name_th': row[2],
                'breeder': row[3],
                'thc_percentage': float(row[4]) if row[4] else None,
                'cbd_percentage': float(row[5]) if row[5] else None,
                'strain_type': row[6],
                'created_at': row[7].strftime('%Y-%m-%d %H:%M:%S') if row[7] else None,
                'image_1_url': f'/uploads/{row[8].split("/")[-1]}' if row[8] else None,
                'status': row[9] or 'available',
                'avg_rating': stats['avg_rating'],
                'review_count': stats['review_count'],
                'lab_test_name': row[10],
                'test_type': row[11]
            })

        # Cache for activity-specific time
        set_cache(cache_key, buds, ACTIVITY_CACHE_TTL)

        return jsonify({'buds': buds})

    except psycopg2.OperationalError as e:
        print(f"Database operational error in get_user_buds: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาดในการเชื่อมต่อฐานข้อมูล', 'buds': []}), 500
    except Exception as e:
        print(f"Error in get_user_buds: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาดภายในระบบ', 'buds': []}), 500
    finally:
        if cur:
            try:
                cur.close()
            except:
                pass
        if conn:
            return_db_connection(conn)

@app.route('/api/user_reviews')
def get_user_reviews():
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session.get('user_id')
    cache_key = f"user_reviews_{user_id}"

    # Check cache first
    cached_data = get_cache(cache_key)
    if cached_data:
        return jsonify({'reviews': cached_data})

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        if not conn:
            print("Failed to get database connection")
            return jsonify({'error': 'Database connection failed', 'reviews': []}), 500

        cur = conn.cursor()

        # Optimized query with limit
        cur.execute("""
            SELECT r.id, r.overall_rating, r.short_summary, r.full_review_content, 
                   r.aroma_rating, r.selected_effects, r.aroma_flavors, r.review_images,
                   r.created_at, r.updated_at, r.video_review_url,
                   b.strain_name_en, b.strain_name_th, b.breeder,
                   u.username as reviewer_name, u.profile_image_url as reviewer_profile_image,
                   r.bud_reference_id
            FROM reviews r
            JOIN buds_data b ON r.bud_reference_id = b.id
            JOIN users u ON r.reviewer_id = u.id
            WHERE r.reviewer_id = %s 
            ORDER BY r.created_at DESC
            LIMIT 50
        """, (user_id,))

        print(f"Debug: Query executed for user_id {user_id}")

        reviews = []
        for row in cur.fetchall():
            # Format profile image URL correctly
            reviewer_profile_image = None
            if row[15]:  # reviewer_profile_image
                if row[15].startswith('/uploads/'):
                    reviewer_profile_image = row[15]
                elif row[15].startswith('uploads/'):
                    reviewer_profile_image = f'/{row[15]}'
                else:
                    reviewer_profile_image = f'/uploads/{row[15].split("/")[-1]}'

            review_data = {
                'id': row[0],
                'overall_rating': row[1],
                'short_summary': row[2],
                'full_review_content': row[3],
                'aroma_rating': row[4],
                'selected_effects': row[5] if row[5] else [],
                'aroma_flavors': row[6] if row[6] else [],
                'review_images': row[7] if row[7] else [],
                'created_at': row[8].strftime('%Y-%m-%d %H:%M:%S') if row[8] else None,
                'updated_at': row[9].strftime('%Y-%m-%d %H:%M:%S') if row[9] else None,
                'video_review_url': row[10],
                'strain_name_en': row[11],
                'strain_name_th': row[12],
                'breeder': row[13],
                'reviewer_name': row[14],
                'reviewer_profile_image': reviewer_profile_image,
                'bud_reference_id': row[16]  # Add bud reference ID from reviews table
            }

            reviews.append(review_data)

        # Cache for 2 minutes
        set_cache(cache_key, reviews)

        return jsonify({'reviews': reviews})

    except psycopg2.OperationalError as e:
        print(f"Database operational error in get_user_reviews: {e}")
        return jsonify({'error': 'Database connection lost', 'reviews': []}), 500
    except Exception as e:
        print(f"Error in get_user_reviews: {e}")
        return jsonify({'error': 'Internal server error', 'reviews': []}), 500
    finally:
        if cur:
            try:
                cur.close()
            except:
                pass
        if conn:
            return_db_connection(conn)

@app.route('/register')
def register_page():
    # Check if user is logged in, if not redirect to auth page
    if 'user_id' not in session:
        return redirect('/auth')
    return render_template('index.html')

@app.route('/auth')
def auth():
    # Get video settings from database
    video_url = None  # default
    video_title = "ทำความรู้จัก Budt.Boy"  # default
    show_video = False  # default เป็น false

    def convert_youtube_url_to_embed(url):
        """Convert various YouTube URL formats to embeddable format"""
        if not url or ('youtube.com' not in url and 'youtu.be' not in url):
            return url

        # Handle YouTube Shorts
        if '/shorts/' in url:
            video_id = url.split('/shorts/')[-1].split('?')[0]
            return f"https://www.youtube.com/embed/{video_id}"

        # Handle regular YouTube URLs
        if 'watch?v=' in url:
            video_id = url.split('watch?v=')[-1].split('&')[0]
            return f"https://www.youtube.com/embed/{video_id}"

        # Handle youtu.be URLs
        if 'youtu.be/' in url:
            video_id = url.split('youtu.be/')[-1].split('?')[0]
            return f"https://www.youtube.com/embed/{video_id}"

        return url

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            # Get video settings
            cur.execute("""
                SELECT setting_key, setting_value 
                FROM admin_settings 
                WHERE setting_key IN ('authVideoUrl', 'authVideoTitle', 'showAuthVideo')
            """)
            settings = cur.fetchall()

            for setting in settings:
                if setting[0] == 'authVideoUrl' and setting[1] and setting[1].strip():
                    video_url = convert_youtube_url_to_embed(setting[1].strip())
                    print(f"Auth video URL set to: {video_url}")
                elif setting[0] == 'authVideoTitle' and setting[1] and setting[1].strip():
                    video_title = setting[1].strip()
                elif setting[0] == 'showAuthVideo':
                    show_video = setting[1].lower() == 'true'
                    print(f"Show auth video: {show_video}")

            cur.close()
        except Exception as e:
            print(f"Error loading video settings: {e}")
        finally:
            return_db_connection(conn)

    print(f"Final auth settings - URL: {video_url}, Title: {video_title}, Show: {show_video}")
    return render_template('auth.html', 
                         video_url=video_url, 
                         video_title=video_title, 
                         show_video=show_video)

@app.route('/add-buds')
def add_buds_page():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')
    if not is_approved():
        return redirect('/profile?not_approved=1')
    return render_template('add_buds.html')

@app.route('/edit-bud')
def edit_bud_page():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')
    return render_template('edit_bud.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'success': False, 'error': 'กรุณากรอกอีเมลและรหัสผ่าน'}), 400

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        if not conn:
            print("Failed to get database connection for login")
            return jsonify({'success': False, 'error': 'เชื่อมต่อฐานข้อมูลไม่ได้ กรุณาลองใหม่อีกครั้ง'}), 500

        cur = conn.cursor()
        cur.execute("""
            SELECT id, username, email, is_verified, password_hash
            FROM users 
            WHERE email = %s
        """, (email,))

        user = cur.fetchone()
        if user:
            try:
                password_valid = verify_password(password, user[4])
                if password_valid:
                    user_id, username, email, is_verified = user[:4]

                    # Create session (no email verification required)
                    session['user_id'] = user_id
                    session['username'] = username
                    session['email'] = email

                    print(f"Login successful for user: {username} (ID: {user_id})")

                    return jsonify({
                        'success': True,
                        'message': f'เข้าสู่ระบบสำเร็จ ยินดีต้อนรับ {username}!',
                        'redirect': '/profile'
                    })
                else:
                    print(f"Login failed - invalid password for email: {email}")
                    return jsonify({
                        'success': False,
                        'error': 'อีเมลหรือรหัสผ่านไม่ถูกต้อง'
                    }), 400
            except Exception as pwd_error:
                print(f"Password verification error for email {email}: {pwd_error}")
                return jsonify({
                    'success': False,
                    'error': 'เกิดข้อผิดพลาดในการตรวจสอบรหัสผ่าน กรุณาติดต่อผู้ดูแลระบบ'
                }), 400
        else:
            print(f"Login failed - user not found for email: {email}")
            return jsonify({
                'success': False,
                'error': 'อีเมลหรือรหัสผ่านไม่ถูกต้อง'
            }), 400

    except psycopg2.OperationalError as e:
        print(f"Database operational error in login: {e}")
        return jsonify({'success': False, 'error': 'เกิดข้อผิดพลาดในการเชื่อมต่อฐานข้อมูล กรุณาลองใหม่อีกครั้ง'}), 500
    except Exception as e:
        print(f"General error in login: {e}")
        return jsonify({'success': False, 'error': 'เกิดข้อผิดพลาดในระบบ กรุณาลองใหม่อีกครั้ง'}), 500
    finally:
        if cur:
            try:
                cur.close()
            except:
                pass
        if conn:
            return_db_connection(conn)

@app.route('/quick_signup', methods=['POST'])
def quick_signup():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    referral_code = data.get('referral_code')  # Get referral code from form

    if not username or not email or not password:
        return jsonify({'success': False, 'error': 'กรุณากรอกข้อมูลให้ครบถ้วน'}), 400

    # Validate password strength
    is_valid, message = validate_password_strength(password)
    if not is_valid:
        return jsonify({'success': False, 'error': message}), 400

    # Check registration mode from admin settings
    registration_mode = get_registration_mode()

    # Hash password securely
    password_hash = hash_password(password)

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if user exists
            cur.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
            if cur.fetchone():
                return jsonify({
                    'success': False,
                    'error': 'ชื่อผู้ใช้หรืออีเมลนี้ถูกใช้แล้ว'
                }), 400

            # Check referral code if provided
            referred_by_id = None
            if referral_code:
                cur.execute("SELECT id FROM users WHERE referral_code = %s", (referral_code,))
                referrer = cur.fetchone()
                if referrer:
                    referred_by_id = referrer[0]

            # Generate referral code for new user
            import secrets
            new_referral_code = secrets.token_urlsafe(8)

            # Check registration mode requirements
            if registration_mode == 'referral_only':
                # Referral mode: must have valid referral code
                if not referred_by_id:
                    return jsonify({
                        'success': False,
                        'error': 'การสมัครสมาชิกต้องผ่าน Referral Link เท่านั้น กรุณาใช้ลิงก์ที่เพื่อนแชร์ให้'
                    }), 400
                # User needs approval from referrer
                is_approved = False
            else:
                # Public mode: can signup without referral code
                # Auto-approve if no referral, or needs approval if has referral
                is_approved = True if not referred_by_id else False

            # Create user
            cur.execute("""
                INSERT INTO users (username, email, password_hash, is_consumer, is_verified, referred_by, referral_code, is_approved)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (username, email, password_hash, True, True, referred_by_id, new_referral_code, is_approved))

            user_id = cur.fetchone()[0]
            conn.commit()

            # Auto login
            session['user_id'] = user_id
            session['username'] = username
            session['email'] = email

            if is_approved:
                message = f'สมัครสมาชิกสำเร็จ! ยินดีต้อนรับ {username}'
            else:
                message = f'สมัครสมาชิกสำเร็จ! รอการอนุมัติจากผู้แนะนำ ยินดีต้อนรับ {username}'

            return jsonify({
                'success': True,
                'message': message,
                'redirect': '/profile'
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'success': False, 'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/auth')

@app.route('/forgot-password')
def forgot_password_page():
    """Forgot password page"""
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>')
def reset_password_page(token):
    """Reset password page with token"""
    return render_template('reset_password.html', token=token)

@app.route('/api/forgot_password', methods=['POST'])
def forgot_password():
    """Send password reset email"""
    data = request.get_json()
    email = data.get('email')

    if not email:
        return jsonify({'success': False, 'error': 'กรุณากรอกอีเมล'}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if user exists
            cur.execute("SELECT id, username FROM users WHERE email = %s", (email,))
            user = cur.fetchone()

            if not user:
                # Don't reveal if email exists or not for security
                return jsonify({
                    'success': True,
                    'message': 'หากอีเมลนี้มีในระบบ เราจะส่งลิงก์รีเซ็ตรหัสผ่านให้คุณ'
                })

            user_id, username = user

            # Generate reset token
            reset_token = generate_verification_token()
            expires_at = datetime.now() + timedelta(hours=1)  # 1 hour expiry

            # Store reset token
            cur.execute("""
                INSERT INTO password_resets (user_id, token, expires_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) 
                DO UPDATE SET token = EXCLUDED.token, expires_at = EXCLUDED.expires_at
            """, (user_id, reset_token, expires_at))

            conn.commit()

            # Send reset email
            email_sent = send_password_reset_email(email, username, reset_token)

            if DEMO_EMAIL_MODE:
                return jsonify({
                    'success': True,
                    'message': 'ลิงก์รีเซ็ตรหัสผ่านแสดงในคอนโซลแล้ว (Demo Mode)',
                    'demo_mode': True,
                    'reset_url': url_for('reset_password_page', token=reset_token, _external=True)
                })
            elif email_sent:
                return jsonify({
                    'success': True,
                    'message': 'หากอีเมลนี้มีในระบบ เราจะส่งลิงก์รีเซ็ตรหัสผ่านให้คุณ'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'ไม่สามารถส่งอีเมลได้ กรุณาลองใหม่อีกครั้ง'
                }), 500

        except Exception as e:
            conn.rollback()
            print(f"Error in forgot_password: {e}")
            return jsonify({'success': False, 'error': 'เกิดข้อผิดพลาดในระบบ'}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'success': False, 'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/reset_password', methods=['POST'])
def reset_password():
    """Reset password with token"""
    data = request.get_json()
    token = data.get('token')
    new_password = data.get('password')

    if not token or not new_password:
        return jsonify({'success': False, 'error': 'กรุณากรอกข้อมูลให้ครบถ้วน'}), 400

    # Validate password strength
    is_valid, message = validate_password_strength(new_password)
    if not is_valid:
        return jsonify({'success': False, 'error': message}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if token is valid and not expired
            cur.execute("""
                SELECT pr.user_id, u.username, u.email
                FROM password_resets pr
                JOIN users u ON pr.user_id = u.id
                WHERE pr.token = %s AND pr.expires_at > NOW() AND pr.is_used = FALSE
            """, (token,))

            result = cur.fetchone()
            if not result:
                return jsonify({
                    'success': False,
                    'error': 'ลิงก์รีเซ็ตรหัสผ่านไม่ถูกต้องหรือหมดอายุแล้ว'
                }), 400

            user_id, username, email = result

            # Hash new password
            password_hash = hash_password(new_password)

            # Update password
            cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id))

            # Mark token as used
            cur.execute("UPDATE password_resets SET is_used = TRUE WHERE token = %s", (token,))

            conn.commit()

            return jsonify({
                'success': True,
                'message': 'รีเซ็ตรหัสผ่านสำเร็จ กรุณาเข้าสู่ระบบด้วยรหัสผ่านใหม่'
            })

        except Exception as e:
            conn.rollback()
            print(f"Error in reset_password: {e}")
            return jsonify({'success': False, 'error': 'เกิดข้อผิดพลาดในระบบ'}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'success': False, 'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/signin')
def signin():
    """Initialize Google OAuth signin"""
    # Block OAuth in preview mode only
    if FALLBACK_AUTH_ENABLED and is_preview():
        return redirect('/auth?error=oauth_disabled_preview')

    if not oauth_flow:
        return redirect('/auth?error=oauth_not_configured')

    # Check if CAPTCHA and age verification are completed
    captcha_verified = session.get('captcha_verified', False)
    age_verified = session.get('age_verified', False)

    if not captcha_verified:
        return redirect('/auth?error=captcha_required')

    if not age_verified:
        return redirect('/auth?error=age_required')

    try:
        # Check if we have valid credentials
        if not GOOGLE_OAUTH_CONFIG["web"]["client_id"]:
            return redirect('/auth?error=missing_client_id')

        if not GOOGLE_OAUTH_CONFIG["web"]["client_secret"]:
            return redirect('/auth?error=missing_client_secret')

        # Always use production URL for OAuth callback to avoid redirect issues
        redirect_uri = 'https://budtboy.replit.app/oauth2callback'
        oauth_flow.redirect_uri = redirect_uri

        print(f"🔧 OAuth redirect URI set to: {redirect_uri}")
        print(f"🌐 Current request host: {request.host}")
        print(f"🔑 Environment: {'Production' if is_production() else 'Preview'}")

        # Generate authorization URL with proper parameters
        authorization_url, state = oauth_flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='select_account'  # Force account selection
        )

        session['state'] = state
        print(f"✅ Generated authorization URL: {authorization_url}")

        return redirect(authorization_url)

    except Exception as e:
        print(f"❌ Error in signin: {e}")
        return redirect(f'/auth?error=oauth_error&message={str(e)}')

@app.route('/oauth2callback')
def oauth2callback():
    """Handle Google OAuth callback"""
    if not oauth_flow:
        return redirect('/auth?error=oauth_not_configured')

    try:
        # Verify state parameter
        if 'state' not in session or request.args.get('state') != session['state']:
            print(f"❌ State mismatch - Session: {session.get('state')}, Request: {request.args.get('state')}")
            return redirect('/auth?error=invalid_state')

        # Always use production URL for OAuth callback
        redirect_uri = 'https://budtboy.replit.app/oauth2callback'
        oauth_flow.redirect_uri = redirect_uri

        # Construct callback URL properly - ensure HTTPS
        callback_url = request.url
        if callback_url.startswith('http://'):
            callback_url = callback_url.replace('http://', 'https://')

        # Handle reverse proxy headers
        if request.headers.get('X-Forwarded-Proto') == 'https':
            callback_url = callback_url.replace('http://', 'https://')

        # Ensure callback URL uses production domain
        if 'pike.replit.dev' in callback_url:
            callback_url = callback_url.replace(request.host, 'budtboy.replit.app')

        print(f"🔧 OAuth callback URL: {callback_url}")
        print(f"🔧 OAuth redirect URI: {redirect_uri}")
        print(f"🌐 Request host: {request.host}")
        print(f"🔑 Environment: {'Production' if is_production() else 'Preview'}")

        # Exchange authorization code for access token
        oauth_flow.fetch_token(authorization_response=callback_url)

        # Get user info from Google
        user_info_response = requests.get(
            'https://www.googleapis.com/oauth2/v1/userinfo',
            headers={'Authorization': f'Bearer {oauth_flow.credentials.token}'}
        )

        if user_info_response.status_code != 200:
            print(f"❌ Failed to get user info: {user_info_response.status_code}")
            return redirect('/auth?error=failed_to_get_user_info')

        user_info = user_info_response.json()
        email = user_info.get('email')
        name = user_info.get('name')
        google_id = user_info.get('id')

        print(f"✅ Got user info: {email}, {name}")

        if not email:
            return redirect('/auth?error=no_email_from_google')

        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()

                # Check if user exists
                cur.execute("SELECT id, username FROM users WHERE email = %s", (email,))
                existing_user = cur.fetchone()

                if existing_user:
                    # User exists, log them in
                    user_id, username = existing_user
                    session['user_id'] = user_id
                    session['username'] = username
                    session['email'] = email

                    # Clear verification session data
                    session.pop('captcha_verified', None)
                    session.pop('age_verified', None)
                    session.pop('state', None)

                    print(f"✅ Existing user logged in: {username}")
                    cur.close()
                    return_db_connection(conn)

                    return redirect('/profile')
                else:
                    # Create new user
                    username = name or email.split('@')[0]

                    # Make sure username is unique
                    base_username = username
                    counter = 1
                    while True:
                        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
                        if not cur.fetchone():
                            break
                        username = f"{base_username}_{counter}"
                        counter += 1

                    # Generate referral code
                    referral_code = secrets.token_urlsafe(8)

                    # Create user account
                    cur.execute("""
                        INSERT INTO users (username, email, password_hash, is_consumer, is_verified, 
                                         referral_code, is_approved, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                        RETURNING id
                    """, (username, email, '', True, True, referral_code, True))

                    user_id = cur.fetchone()[0]
                    conn.commit()

                    # Log them in
                    session['user_id'] = user_id
                    session['username'] = username
                    session['email'] = email

                    # Clear verification session data
                    session.pop('captcha_verified', None)
                    session.pop('age_verified', None)
                    session.pop('state', None)

                    print(f"✅ New user created and logged in: {username}")
                    cur.close()
                    return_db_connection(conn)

                    return redirect('/profile')

            except Exception as e:
                if conn:
                    conn.rollback()
                print(f"❌ Database error in oauth2callback: {e}")
                return redirect('/auth?error=database_error')
            finally:
                if cur:
                    cur.close()
                if conn:
                    return_db_connection(conn)

        return redirect('/auth?error=database_connection_failed')

    except Exception as e:
        print(f"❌ OAuth callback error: {e}")
        import traceback
        traceback.print_exc()
        return redirect('/auth?error=oauth_callback_failed')

@app.route('/verify_email/<token>')
def verify_email(token):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if token is valid and not expired
            cur.execute("""
                SELECT ev.user_id, u.username, u.email 
                FROM email_verifications ev
                JOIN users u ON ev.user_id = u.id
                WHERE ev.token = %s AND ev.expires_at > NOW() AND ev.is_used = FALSE
            """, (token,))

            result = cur.fetchone()
            if result:
                user_id, username, email = result

                # Mark token as used and user as verified
                cur.execute("UPDATE email_verifications SET is_used = TRUE WHERE token = %s", (token,))
                cur.execute("UPDATE users SET is_verified = TRUE WHERE id = %s", (user_id,))
                conn.commit()

                return f"""
                <html>
                <head><meta charset="UTF-8"></head>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h2 style="color: #4CAF50;">✅ ยืนยันอีเมลสำเร็จ!</h2>
                    <p>สวัสดี {username}</p>
                    <p>อีเมล {email} ได้รับการยืนยันเรียบร้อยแล้ว</p>
                    <a href="/" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">
                        กลับสู่หน้าหลัก
                    </a>
                </body>
                </html>
                """
            else:
                return """
                <html>
                <head><meta charset="UTF-8"></head>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h2 style="color: #f44336;">❌ ลิงก์ไม่ถูกต้องหรือหมดอายุ</h2>
                    <p>ลิงก์ยืนยันอีเมลนี้ไม่ถูกต้องหรือหมดอายุแล้ว</p>
                    <a href="/" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">
                        กลับสู่หน้าหลัก
                    </a>
                </body>
                </html>
                """
        except Exception as e:
            return f"เกิดข้อผิดพลาด: {str(e)}"
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return "ไม่สามารถเชื่อมต่อฐานข้อมูลได้"

@app.route('/api/profile')
def get_profile():
    if 'user_id' not in session:
        return jsonify({'error': 'ไม่ได้เข้าสู่ระบบ'}), 401

    user_id = session['user_id']
    cache_key = f"profile_{user_id}"

    # Check cache first with longer TTL for profile data
    cached_data = get_cache(cache_key, PROFILE_CACHE_TTL)
    if cached_data:
        return jsonify(cached_data)

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, username, email, is_grower, is_budtender, is_consumer, 
                       birth_year, created_at, is_verified, grow_license_file_url, profile_image_url,
                       contact_facebook, contact_line, contact_instagram, contact_twitter, 
                       contact_telegram, contact_phone, contact_other, is_approved, referred_by
                FROM users WHERE id = %s
            """, (user_id,))
            user = cur.fetchone()

            if user:
                # Format profile image URL correctly
                profile_image_url = None
                if user[10]:
                    if user[10].startswith('/uploads/'):
                        profile_image_url = user[10]
                    elif user[10].startswith('uploads/'):
                        profile_image_url = f'/{user[10]}'
                    else:
                        profile_image_url = f'/uploads/{user[10].split("/")[-1]}'

                user_data = {
                    'id': user[0],
                    'username': user[1],
                    'email': user[2],
                    'is_grower': user[3],
                    'is_budtender': user[4],
                    'is_consumer': user[5],
                    'birth_year': user[6],
                    'created_at': user[7].strftime('%Y-%m-%d %H:%M:%S') if user[7] else None,
                    'is_verified': user[8],
                    'grow_license_file_url': user[9],
                    'profile_image_url': profile_image_url,
                    'contact_facebook': user[11],
                    'contact_line': user[12],
                    'contact_instagram': user[13],
                    'contact_twitter': user[14],
                    'contact_telegram': user[15],
                    'contact_phone': user[16],
                    'contact_other': user[17],
                    'is_approved': user[18],
                    'referred_by': user[19]
                }

                # Cache the result for longer time
                set_cache(cache_key, user_data, PROFILE_CACHE_TTL)

                return jsonify(user_data)
            else:
                return jsonify({'error': 'ไม่พบข้อมูลผู้ใช้'}), 404

        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/update_profile', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return jsonify({'error': 'ไม่ได้เข้าสู่ระบบ'}), 401

    user_id = session['user_id']
    data = request.get_json()

    username = data.get('username')
    email = data.get('email')
    birth_year = data.get('birth_year')
    is_consumer = data.get('is_consumer', False)
    is_grower = data.get('is_grower', False)
    is_budtender = data.get('is_budtender', False)

    # Contact fields
    contact_facebook = data.get('contact_facebook', '')
    contact_line = data.get('contact_line', '')
    contact_instagram = data.get('contact_instagram', '')
    contact_twitter = data.get('contact_twitter', '')
    contact_telegram = data.get('contact_telegram', '')
    contact_phone = data.get('contact_phone', '')
    contact_other = data.get('contact_other', '')

    if not username or not email:
        return jsonify({'error': 'กรุณากรอกชื่อผู้ใช้และอีเมล'}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if username or email already exists (excluding current user)
            cur.execute("""
                SELECT id FROM users 
                WHERE (username = %s OR email = %s) AND id != %s
            """, (username, email, user_id))

            existing_user = cur.fetchone()

            if existing_user:
                return jsonify({
                    'error': 'ชื่อผู้ใช้หรืออีเมลนี้ถูกใช้โดยผู้ใช้อื่นแล้ว'
                }), 400

            # Update user profile
            cur.execute("""
                UPDATE users 
                SET username = %s, email = %s, birth_year = %s, 
                    is_consumer = %s, is_grower = %s, is_budtender = %s,
                    contact_facebook = %s, contact_line = %s, contact_instagram = %s,
                    contact_twitter = %s, contact_telegram = %s, contact_phone = %s,
                    contact_other = %s
                WHERE id = %s
            """, (
                username, email, 
                int(birth_year) if birth_year else None,
                is_consumer, is_grower, is_budtender,
                contact_facebook if contact_facebook else None,
                contact_line if contact_line else None,
                contact_instagram if contact_instagram else None,
                contact_twitter if contact_twitter else None,
                contact_telegram if contact_telegram else None,
                contact_phone if contact_phone else None,
                contact_other if contact_other else None,
                user_id
            ))

            conn.commit()

            # Clear cache for this user
            clear_cache_pattern(f"profile_{user_id}")

            # Update session data
            session['username'] = username
            session['email'] = email

            return jsonify({
                'success': True,
                'message': 'อัพเดทโปรไฟล์สำเร็จ'
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/buds', methods=['GET'])
def get_buds():
    """Get all buds data with optional filtering"""
    strain_type = request.args.get('strain_type')
    effect = request.args.get('effect')
    grower_id = request.args.get('grower_id')

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Build query with filters
            query = """
                SELECT b.*, u.username as grower_name 
                FROM buds_data b
                LEFT JOIN users u ON b.grower_id = u.id
                WHERE 1=1
            """
            params = []

            if strain_type:
                query += " AND b.strain_type = %s"
                params.append(strain_type)
            if effect:
                query += " AND b.effect = %s"
                params.append(effect)
            if grower_id:
                query += " AND b.grower_id = %s"
                params.append(grower_id)

            query += " ORDER BY b.created_at DESC"

            cur.execute(query, params)
            buds = cur.fetchall()

            buds_list = []
            for bud in buds:
                buds_list.append({
                    'id': bud[0],
                    'strain_name_th': bud[1],
                    'strain_name_en': bud[2],
                    'breeder': bud[3],
                    'strain_type': bud[4],
                    'thc_percentage': float(bud[5]) if bud[5] else None,
                    'cbd_percentage': float(bud[6]) if bud[6] else None,
                    'grade': bud[7],
                    'aroma_flavor': bud[8],
                    'top_terpenes_1': bud[9],
                    'top_terpenes_2': bud[10],
                    'top_terpenes_3': bud[11],
                    'mental_effects_positive': bud[12],
                    'mental_effects_negative': bud[13],
                    'physical_effects_positive': bud[14],
                    'physical_effects_negative': bud[15],
                    'recommended_time': bud[16],
                    'grow_method': bud[17],
                    'harvest_date': bud[18].strftime('%Y-%m-%d') if bud[18] else None,
                    'batch_number': bud[19],
                    'grower_id': bud[20],
                    'grower_license_verified': bud[21],
                    'fertilizer_type': bud[22],
                    'flowering_type': bud[23],
                    'image_1_url': bud[24],
                    'image_2_url': bud[25],
                    'image_3_url': bud[26],
                    'image_4_url': bud[27],
                    'created_at': bud[28].strftime('%Y-%m-%d %H:%M:%S') if bud[28] else None,
                    'updated_at': bud[29].strftime('%Y-%m-%d %H:%M:%S') if bud[29] else None,
                    'created_by': bud[30],
                    'grower_name': bud[31]
                })

            return jsonify(buds_list)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/buds', methods=['POST'])
def add_bud():
    """Add new bud data"""
    if 'user_id' not in session:
        return jsonify({'error': 'ไม่ได้เข้าสู่ระบบ'}), 401

    data = request.get_json()
    user_id = session['user_id']

    # Required fields validation
    required_fields = ['strain_name_th', 'strain_name_en', 'strain_type']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': f'กรุณากรอก {field}'}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Process potential constraint fields
            strain_type = data.get('strain_type')
            if strain_type:
                strain_type = strain_type.strip()
                if strain_type not in ['Indica', 'Sativa', 'Hybrid']:
                    strain_type = None
            else:
                strain_type = None

            thc_percentage = data.get('thc_percentage')
            if thc_percentage and str(thc_percentage).strip():
                try:
                    thc_percentage = float(thc_percentage)
                except (ValueError, TypeError):
                    thc_percentage = None
            else:
                thc_percentage = None

            cbd_percentage = data.get('cbd_percentage')
            if cbd_percentage and str(cbd_percentage).strip():
                try:
                    cbd_percentage = float(cbd_percentage)
                except (ValueError, TypeError):
                    cbd_percentage = None
            else:
                cbd_percentage = None

            grade = data.get('grade')
            if grade:
                grade = grade.strip()
                if grade not in ['A+', 'A', 'B+', 'B', 'C']:
                    grade = None
            else:
                grade = None

            recommended_time = data.get('recommended_time')
            if recommended_time:
                recommended_time = recommended_time.strip()
                if recommended_time not in ['กลางวัน', 'กลางคืน', 'ตลอดวัน']:
                    recommended_time = None
            else:
                recommended_time = None

            grow_method = data.get('grow_method')
            if grow_method:
                grow_method = grow_method.strip()
                if grow_method not in ['Indoor', 'Outdoor', 'Greenhouse', 'Hydroponic']:
                    grow_method = None
            else:
                grow_method = None

            fertilizer_type = data.get('fertilizer_type')
            if fertilizer_type:
                fertilizer_type = fertilizer_type.strip()
                if fertilizer_type not in ['Organic', 'Chemical', 'Mixed']:
                    fertilizer_type = None
            else:
                fertilizer_type = None

            flowering_type = data.get('flowering_type')
            if flowering_type:
                flowering_type = flowering_type.strip()
                if flowering_type not in ['Photoperiod', 'Autoflower']:
                    flowering_type = None
            else:
                flowering_type = None

            # Certificate fields
            lab_test_name = data.get('lab_test_name')
            test_type = data.get('test_type')


            # Construct the INSERT query dynamically
            query_fields = [
                'strain_name_th', 'strain_name_en', 'breeder', 'strain_type',
                'thc_percentage', 'cbd_percentage', 'grade', 'aroma_flavor',
                'top_terpenes_1', 'top_terpenes_2', 'top_terpenes_3',
                'mental_effects_positive', 'mental_effects_negative',
                'physical_effects_positive', 'physical_effects_negative',
                'recommended_time', 'grow_method', 'harvest_date', 'batch_number',
                'grower_id', 'grower_license_verified', 'fertilizer_type', 'flowering_type',
                'lab_test_name', 'test_type',
                'created_by', 'status'
            ]

            values = [
                data.get('strain_name_th'), data.get('strain_name_en'), 
                data.get('breeder'), strain_type,
                thc_percentage, cbd_percentage, grade, data.get('aroma_flavor'),
                data.get('top_terpenes_1'), data.get('top_terpenes_2'), data.get('top_terpenes_3'),
                data.get('mental_effects_positive'), data.get('mental_effects_negative'),
                data.get('physical_effects_positive'), data.get('physical_effects_negative'),
                data.get('recommended_time'), grow_method, data.get('harvest_date'), data.get('batch_number'),
                data.get('grower_id'),
                data.get('grower_license_verified', False),
                fertilizer_type, flowering_type,
                lab_test_name, test_type,
                user_id, 'active'
            ]

            # Build the SQL query
            query = sql.SQL("INSERT INTO buds_data ({}) VALUES ({}) RETURNING id").format(
                sql.SQL(', ').join(map(sql.Identifier, query_fields)),
                sql.SQL(', ').join(sql.Placeholder() * len(query_fields))
            )

            cur.execute(query, values)

            bud_id = cur.fetchone()[0]
            conn.commit()

            return jsonify({
                'success': True,
                'message': 'เพิ่มข้อมูล Bud สำเร็จ',
                'bud_id': bud_id
            }), 201

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/buds/<int:bud_id>', methods=['PUT'])
def update_bud(bud_id):
    """Update existing bud data"""
    if 'user_id' not in session:
        return jsonify({'error': 'ไม่ได้เข้าสู่ระบบ'}), 401

    data = request.get_json()
    user_id = session['user_id']

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

        cur = conn.cursor()

        # Check if user has permission to update (owner or admin)
        cur.execute("""
            SELECT created_by FROM buds_data WHERE id = %s
        """, (bud_id,))
        result = cur.fetchone()

        if not result:
            return jsonify({'error': 'ไม่พบข้อมูล Bud'}), 404

        if result[0] != user_id:
            return jsonify({'error': 'ไม่มีสิทธิ์แก้ไขข้อมูลนี้'}), 403

        # Handle deleted images - check for images marked for deletion
        image_updates = {}
        for i in range(1, 5):
            deleted_key = f'deleted_image_{i}'
            if data.get(deleted_key) == 'true':
                image_updates[f'image_{i}_url'] = None

        # Build update query with image deletions and constraint validation
        update_fields = [
            sql.SQL("strain_name_th = %s"), sql.SQL("strain_name_en = %s"), sql.SQL("breeder = %s"),
            sql.SQL("strain_type = %s"), sql.SQL("thc_percentage = %s"), sql.SQL("cbd_percentage = %s"),
            sql.SQL("grade = %s"), sql.SQL("aroma_flavor = %s"), sql.SQL("top_terpenes_1 = %s"),
            sql.SQL("top_terpenes_2 = %s"), sql.SQL("top_terpenes_3 = %s"), 
            sql.SQL("mental_effects_positive = %s"), sql.SQL("mental_effects_negative = %s"),
            sql.SQL("physical_effects_positive = %s"), sql.SQL("physical_effects_negative = %s"),
            sql.SQL("recommended_time = %s"), sql.SQL("grow_method = %s"), sql.SQL("harvest_date = %s"),
            sql.SQL("batch_number = %s"), sql.SQL("grower_id = %s"), sql.SQL("grower_license_verified = %s"),
            sql.SQL("fertilizer_type = %s"), sql.SQL("flowering_type = %s"),
            sql.SQL("lab_test_name = %s"), sql.SQL("test_type = %s"),
            sql.SQL("updated_at = CURRENT_TIMESTAMP")
        ]

        # Validate and clean constraint fields with better handling
        grow_method = data.get('grow_method')
        if grow_method:
            grow_method = grow_method.strip()
            if grow_method not in ['Indoor', 'Outdoor', 'Greenhouse', 'Hydroponic']:
                grow_method = None
        else:
            grow_method = None

        strain_type = data.get('strain_type')
        if strain_type:
            strain_type = strain_type.strip()
            if strain_type not in ['Indica', 'Sativa', 'Hybrid']:
                strain_type = None
        else:
            strain_type = None

        grade = data.get('grade')
        if grade:
            grade = grade.strip()
            if grade not in ['A+', 'A', 'B+', 'B', 'C']:
                grade = None
        else:
            grade = None

        recommended_time = data.get('recommended_time')
        if recommended_time:
            recommended_time = recommended_time.strip()
            if recommended_time not in ['กลางวัน', 'กลางคืน', 'ตลอดวัน']:
                recommended_time = None
        else:
            recommended_time = None

        fertilizer_type = data.get('fertilizer_type')
        if fertilizer_type:
            fertilizer_type = fertilizer_type.strip()
            if fertilizer_type not in ['Organic', 'Chemical', 'Mixed']:
                fertilizer_type = None
        else:
            fertilizer_type = None

        flowering_type = data.get('flowering_type')
        if flowering_type:
            flowering_type = flowering_type.strip()
            if flowering_type not in ['Photoperiod', 'Autoflower']:
                flowering_type = None
        else:
            flowering_type = None

        # Convert numeric fields - handle empty strings and None values properly
        thc_percentage = data.get('thc_percentage')
        if thc_percentage and str(thc_percentage).strip():
            try:
                thc_percentage = float(thc_percentage)
            except (ValueError, TypeError):
                thc_percentage = None
        else:
            thc_percentage = None

        cbd_percentage = data.get('cbd_percentage')
        if cbd_percentage and str(cbd_percentage).strip():
            try:
                cbd_percentage = float(cbd_percentage)
            except (ValueError, TypeError):
                cbd_percentage = None
        else:
            cbd_percentage = None

        update_values = [
            data.get('strain_name_th'),
            data.get('strain_name_en'),
            data.get('breeder'),
            strain_type,
            thc_percentage,
            cbd_percentage,
            grade,
            data.get('aroma_flavor'),
            data.get('top_terpenes_1'),
            data.get('top_terpenes_2'),
            data.get('top_terpenes_3'),
            data.get('mental_effects_positive'),
            data.get('mental_effects_negative'),
            data.get('physical_effects_positive'),
            data.get('physical_effects_negative'),
            recommended_time,
            grow_method,
            data.get('harvest_date'),
            data.get('batch_number'),
            data.get('grower_id'),
            data.get('grower_license_verified', False),
            fertilizer_type,
            flowering_type,
            data.get('lab_test_name'),
            data.get('test_type')
        ]

        # Add image deletion updates with whitelist validation
        allowed_image_columns = {'image_1_url', 'image_2_url', 'image_3_url', 'image_4_url'}
        for field, value in image_updates.items():
            if field in allowed_image_columns:  # Whitelist validation
                update_fields.append(sql.SQL("{} = %s").format(sql.Identifier(field)))
                update_values.append(value)

        # Add bud_id for WHERE clause
        update_values.append(bud_id)

        # Construct query safely using psycopg2.sql to prevent SQL injection
        query = sql.SQL("UPDATE buds_data SET {} WHERE id = %s").format(
            sql.SQL(', ').join(update_fields)
        )

        print(f"Executing update query for bud {bud_id}")
        cur.execute(query, update_values)

        if cur.rowcount == 0:
            return jsonify({'error': 'ไม่สามารถอัพเดทข้อมูลได้'}), 400

        conn.commit()
        print(f"Successfully updated bud {bud_id}")

        # Clear all related cache
        clear_cache_pattern(f"bud_detail_{bud_id}")
        clear_cache_pattern(f"bud_info_{bud_id}")
        clear_cache_pattern(f"user_buds_{user_id}")
        clear_cache_pattern("all_buds_report")

        return jsonify({
            'success': True,
            'message': 'อัพเดทข้อมูล Bud สำเร็จ'
        })

    except psycopg2.Error as e:
        print(f"Database error in update_bud: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': f'เกิดข้อผิดพลาดในฐานข้อมูล: {str(e)}'}), 500
    except Exception as e:
        print(f"General error in update_bud: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500
    finally:
        if cur:
            try:
                cur.close()
            except:
                pass
        if conn:
            return_db_connection(conn)

@app.route('/api/buds/<int:bud_id>/upload-images', methods=['POST'])
def upload_bud_images(bud_id):
    """Upload images for a specific bud"""
    if 'user_id' not in session:
        return jsonify({'error': 'ไม่ได้เข้าสู่ระบบ'}), 401

    user_id = session['user_id']

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if user has permission to upload images (owner of the bud)
            cur.execute("""
                SELECT created_by FROM buds_data WHERE id = %s
            """, (bud_id,))
            result = cur.fetchone()

            if not result:
                return jsonify({'error': 'ไม่พบข้อมูล Bud'}), 404

            if result[0] != user_id:
                return jsonify({'error': 'ไม่มีสิทธิ์อัพโหลดรูปภาพสำหรับ Bud นี้'}), 403

            # Handle image uploads
            image_urls = {}

            # Handle bud images
            for i in range(1, 5):  # image_1 to image_4
                file_key = f'image_{i}'
                if file_key in request.files:
                    file = request.files[file_key]
                    if file and file.filename != '' and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                        filename = f"{timestamp}bud_{bud_id}_{file_key}_{filename}"
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(file_path)
                        image_urls[f'image_{i}_url'] = file_path

            # Handle certificate images
            for i in range(1, 5):  # certificate_image_1 to certificate_image_4
                file_key = f'certificate_image_{i}'
                if file_key in request.files:
                    file = request.files[file_key]
                    if file and file.filename != '' and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                        filename = f"{timestamp}cert_{bud_id}_{file_key}_{filename}"
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(file_path)
                        image_urls[f'certificate_image_{i}_url'] = file_path

            # Update database with image URLs
            if image_urls:
                # Define allowed field names to prevent SQL injection
                allowed_fields = {
                    'image_1_url', 'image_2_url', 'image_3_url', 'image_4_url',
                    'certificate_image_1_url', 'certificate_image_2_url', 
                    'certificate_image_3_url', 'certificate_image_4_url'
                }
                update_fields = []
                update_values = []
                for field, url in image_urls.items():
                    # Validate field name against whitelist
                    if field not in allowed_fields:
                        continue  # Skip invalid field names
                    update_fields.append(f"{field} = %s")
                    update_values.append(url)

                if update_fields:  # Only proceed if we have valid fields to update
                    update_values.append(bud_id)
                    update_query = f"""
                        UPDATE buds_data SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """

                    cur.execute(update_query, update_values)
                    conn.commit()

                return jsonify({
                    'success': True,
                    'message': f'อัพโหลดรูปภาพสำเร็จ ({len(image_urls)} รูป)',
                    'uploaded_images': list(image_urls.keys())
                })
            else:
                return jsonify({'error': 'ไม่พบไฟล์รูปภาพที่ถูกต้อง'}), 400

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/buds/<int:bud_id>/detail', methods=['GET'])
def get_bud_detail(bud_id):
    """Get individual bud data for editing"""
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    cache_key = f"bud_detail_{bud_id}_{user_id}"

    # Check cache first
    cached_data = get_cache(cache_key)
    if cached_data:
        print(f"Returning cached data for bud {bud_id}")
        return jsonify(cached_data)

    conn = None
    cur = None
    try:
        print(f"Loading bud detail for ID: {bud_id}, User: {user_id}")
        conn = get_db_connection()
        if not conn:
            print("Failed to get database connection")
            return jsonify({'error': 'Database connection failed'}), 500

        cur = conn.cursor()

        # Query to get bud data for the current user
        cur.execute("""
            SELECT id, strain_name_th, strain_name_en, breeder, strain_type,
                   thc_percentage, cbd_percentage, grade, aroma_flavor,
                   top_terpenes_1, top_terpenes_2, top_terpenes_3,
                   mental_effects_positive, mental_effects_negative,
                   physical_effects_positive, physical_effects_negative,
                   recommended_time, grow_method, harvest_date, batch_number,
                   grower_id, grower_license_verified, fertilizer_type, 
                   flowering_type, image_1_url, image_2_url, image_3_url, image_4_url,
                   created_at, updated_at, created_by,
                   lab_test_name, test_type
            FROM buds_data
            WHERE id = %s AND created_by = %s
        """, (bud_id, user_id))

        result = cur.fetchone()
        print(f"Query result: {result is not None}")

        if not result:
            print(f"No bud found with ID {bud_id} for user {user_id}")
            return jsonify({'error': 'ไม่พบข้อมูลดอกหรือไม่มีสิทธิ์เข้าถึง'}), 404

        bud_data = {
            'id': result[0],
            'strain_name_th': result[1] or '',
            'strain_name_en': result[2] or '',
            'breeder': result[3] or '',
            'strain_type': result[4] or '',
            'thc_percentage': float(result[5]) if result[5] else None,
            'cbd_percentage': float(result[6]) if result[6] else None,
            'grade': result[7] or '',
            'aroma_flavor': result[8] or '',
            'top_terpenes_1': result[9] or '',
            'top_terpenes_2': result[10] or '',
            'top_terpenes_3': result[11] or '',
            'mental_effects_positive': result[12] or '',
            'mental_effects_negative': result[13] or '',
            'physical_effects_positive': result[14] or '',
            'physical_effects_negative': result[15] or '',
            'recommended_time': result[16] or '',
            'grow_method': result[17] or '',
            'harvest_date': result[18].strftime('%Y-%m-%d') if result[18] else '',
            'batch_number': result[19] or '',
            'grower_id': result[20],
            'grower_license_verified': result[21] or False,
            'fertilizer_type': result[22] or '',
            'flowering_type': result[23] or '',
            'image_1_url': result[24] or '',
            'image_2_url': result[25] or '',
            'image_3_url': result[26] or '',
            'image_4_url': result[27] or '',
            'created_at': result[28].strftime('%Y-%m-%d %H:%M:%S') if result[28] else '',
            'updated_at': result[29].strftime('%Y-%m-%d %H:%M:%S') if result[29] else '',
            'created_by': result[30],
            'lab_test_name': result[31] or '',
            'test_type': result[32] or ''
        }

        print(f"Successfully loaded bud data: {bud_data['strain_name_en']}")

        # Cache for 2 minutes
        set_cache(cache_key, bud_data)

        return jsonify(bud_data)

    except psycopg2.OperationalError as e:
        print(f"Database operational error in get_bud_detail: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาดในการเชื่อมต่อฐานข้อมูล กรุณาลองใหม่อีกครั้ง'}), 500
    except Exception as e:
        print(f"Error in get_bud_detail for bud {bud_id}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'เกิดข้อผิดพลาดในการโหลดข้อมูล: {str(e)}'}), 500
    finally:
        if cur:
            try:
                cur.close()
            except:
                pass
        if conn:
            return_db_connection(conn)

@app.route('/add-review')
def add_review_page():
    """Add review page"""
    if 'user_id' not in session:
        return redirect('/auth')
    return render_template('add_review.html')

@app.route('/edit-review')
def edit_review_page():
    """Edit review page"""
    if 'user_id' not in session:
        return redirect('/auth')
    return render_template('edit_review.html')

@app.route('/bud-reviews')
def bud_reviews_page():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')
    return render_template('bud_reviews.html')

@app.route('/report')
def report_page():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')
    return render_template('report.html')

@app.route('/bud-report/')
@app.route('/bud-report/<int:bud_id>')
@app.route('/bud-report')
@app.route('/bud-report/<int:bud_id>')
def bud_report_page(bud_id=None):
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')

    # Handle query parameter for id
    if bud_id is None:
        bud_id = request.args.get('id')
        if bud_id:
            try:
                bud_id = int(bud_id)
            except (ValueError, TypeError):
                bud_id = None

    return render_template('bud_report.html', bud_id=bud_id)

@app.route('/search-tool')
def search_tool_page():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')
    if not is_approved():
        return redirect('/profile?not_approved=1')
    return render_template('search_tool.html')

@app.route('/friends')
def friends_page():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')
    if not is_approved():
        return redirect('/profile?not_approved=1')
    return render_template('friends.html')

@app.route('/my-reviews')
def my_reviews_page():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')
    if not is_approved():
        return redirect('/profile?not_approved=1')
    return render_template('my_reviews.html')

@app.route('/friends-reviews')
def friends_reviews_page():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')
    if not is_approved():
        return redirect('/profile?not_approved=1')
    return render_template('friends_reviews.html')

@app.route('/activities')
def activities_page():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')
    if not is_approved():
        return redirect('/profile?not_approved=1')
    return render_template('activities.html')

@app.route('/api/activities', methods=['GET'])
def get_activities():
    """Get all activities"""
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT a.id, a.name, a.description, a.start_registration_date, a.end_registration_date,
                       a.judging_criteria, a.max_participants, 
                       a.first_prize_description, a.first_prize_value, a.first_prize_image,
                       a.second_prize_description, a.second_prize_value, a.second_prize_image,
                       a.third_prize_description, a.third_prize_value, a.third_prize_image,
                       a.status, a.created_at,
                       COUNT(ap.id) as participant_count
                FROM activities a
                LEFT JOIN activity_participants ap ON a.id = ap.activity_id
                GROUP BY a.id, a.name, a.description, a.start_registration_date, a.end_registration_date,
                         a.judging_criteria, a.max_participants,
                         a.first_prize_description, a.first_prize_value, a.first_prize_image,
                         a.second_prize_description, a.second_prize_value, a.second_prize_image,
                         a.third_prize_description, a.third_prize_value, a.third_prize_image,
                         a.status, a.created_at
                ORDER BY a.created_at DESC
            """)

            activities = []
            for row in cur.fetchall():
                activities.append({
                    'id': row[0],
                    'name': row[1],
                    'description': row[2],
                    'start_registration_date': row[3].strftime('%Y-%m-%d %H:%M:%S') if row[3] else None,
                    'end_registration_date': row[4].strftime('%Y-%m-%d %H:%M:%S') if row[4] else None,
                    'judging_criteria': row[5],
                    'max_participants': row[6],
                    'first_prize_description': row[7],
                    'first_prize_value': float(row[8]) if row[8] else 0,
                    'first_prize_image': row[9],
                    'second_prize_description': row[10],
                    'second_prize_value': float(row[11]) if row[11] else 0,
                    'second_prize_image': row[12],
                    'third_prize_description': row[13],
                    'third_prize_value': float(row[14]) if row[14] else 0,
                    'third_prize_image': row[15],
                    'status': row[16],
                    'created_at': row[17].strftime('%Y-%m-%d %H:%M:%S') if row[17] else None,
                    'participant_count': row[18]
                })

            return jsonify({'activities': activities})

        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/activities/<int:activity_id>/participants', methods=['GET'])
def get_activity_participants(activity_id):
    """Get participants for specific activity"""
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT ap.id, ap.submission_description, ap.submission_images, ap.rank, ap.prize_amount,
                       ap.registered_at, u.username, u.profile_image_url,
                       b.strain_name_en, b.strain_name_th, b.image_1_url, b.image_2_url, b.image_3_url, b.image_4_url
                FROM activity_participants ap
                JOIN users u ON ap.user_id = u.id
                JOIN buds_data b ON ap.bud_id = b.id
                WHERE ap.activity_id = %s
                ORDER BY ap.rank ASC NULLS LAST, ap.registered_at ASC
            """, (activity_id,))

            participants = []
            for row in cur.fetchall():
                participants.append({
                    'id': row[0],
                    'submission_description': row[1],
                    'submission_images': row[2] if row[2] else [],
                    'rank': row[3],
                    'prize_amount': float(row[4]) if row[4] else 0,
                    'registered_at': row[5].strftime('%Y-%m-%d %H:%M:%S') if row[5] else None,
                    'username': row[6],
                    'profile_image_url': row[7],
                    'strain_name_en': row[8],
                    'strain_name_th': row[9],
                    'bud_images': [row[10], row[11], row[12], row[13]]
                })

            return jsonify({'participants': participants})

        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/admin/activities', methods=['POST'])
def admin_create_activity():
    """Admin create new activity"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()

    if not data.get('name'):
        return jsonify({'error': 'กรุณากรอกชื่อกิจกรรม'}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO activities (
                    name, description, start_registration_date, end_registration_date,
                    judging_criteria, max_participants, status,
                    first_prize_description, first_prize_value, first_prize_image,
                    second_prize_description, second_prize_value, second_prize_image,
                    third_prize_description, third_prize_value, third_prize_image
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) RETURNING id
            """, (
                data.get('name'),
                data.get('description'),
                data.get('start_registration_date'),
                data.get('end_registration_date'),
                data.get('judging_criteria'),
                data.get('max_participants', 0),
                data.get('status', 'upcoming'),
                data.get('first_prize_description'),
                data.get('first_prize_value', 0),
                data.get('first_prize_image'),
                data.get('second_prize_description'),
                data.get('second_prize_value', 0),
                data.get('second_prize_image'),
                data.get('third_prize_description'),
                data.get('third_prize_value', 0),
                data.get('third_prize_image')
            ))

            activity_id = cur.fetchone()[0]
            conn.commit()

            return jsonify({
                'success': True,
                'message': 'สร้างกิจกรรมสำเร็จ',
                'activity_id': activity_id
            }), 201

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/activities/<int:activity_id>/join', methods=['POST'])
def join_activity(activity_id):
    """Join an activity with a bud"""
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    data = request.get_json()
    bud_id = data.get('bud_id')
    submission_description = data.get('submission_description', '')

    if not bud_id:
        return jsonify({'error': 'กรุณาเลือกดอกที่ต้องการส่งเข้าประกวด'}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if activity exists and is open for registration
            cur.execute("""
                SELECT id, name, status, max_participants, end_registration_date
                FROM activities 
                WHERE id = %s
            """, (activity_id,))

            activity = cur.fetchone()
            if not activity:
                return jsonify({'error': 'ไม่พบกิจกรรมนี้'}), 404

            if activity[2] != 'registration_open':
                return jsonify({'error': 'กิจกรรมนี้ไม่เปิดรับสมัครแล้ว'}), 400

            if activity[4] and activity[4] < datetime.now():
                return jsonify({'error': 'หมดเวลาการสมัครแล้ว'}), 400

            # Check if user owns the bud
            cur.execute("SELECT id FROM buds_data WHERE id = %s AND created_by = %s", (bud_id, user_id))
            if not cur.fetchone():
                return jsonify({'error': 'ไม่พบดอกนี้หรือคุณไม่ใช่เจ้าของ'}), 403

            # Check if already joined with this bud
            cur.execute("""
                SELECT id FROM activity_participants 
                WHERE activity_id = %s AND user_id = %s AND bud_id = %s
            """, (activity_id, user_id, bud_id))

            if cur.fetchone():
                return jsonify({'error': 'คุณได้ส่งดอกนี้เข้าร่วมกิจกรรมแล้ว'}), 400

            # Check participant limit
            if activity[3] > 0:  # max_participants
                cur.execute("SELECT COUNT(*) FROM activity_participants WHERE activity_id = %s", (activity_id,))
                current_count = cur.fetchone()[0]
                if current_count >= activity[3]:
                    return jsonify({'error': 'กิจกรรมนี้เต็มแล้ว'}), 400

            # Join activity
            cur.execute("""
                INSERT INTO activity_participants (activity_id, user_id, bud_id, submission_description)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (activity_id, user_id, bud_id, submission_description))

            participant_id = cur.fetchone()[0]
            conn.commit()

            return jsonify({
                'success': True,
                'message': f'เข้าร่วมกิจกรรม "{activity[1]}" สำเร็จ',
                'participant_id': participant_id
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500



@app.route('/api/admin/activities/<int:activity_id>', methods=['PUT'])
def admin_update_activity(activity_id):
    """Admin update activity"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if activity exists
            cur.execute("SELECT id FROM activities WHERE id = %s", (activity_id,))
            if not cur.fetchone():
                return jsonify({'error': 'ไม่พบกิจกรรมนี้'}), 404

            cur.execute("""
                UPDATE activities SET
                    name = %s, description = %s, start_registration_date = %s,
                    end_registration_date = %s, judging_criteria = %s,
                    max_participants = %s, status = %s,
                    first_prize_description = %s, first_prize_value = %s, first_prize_image = %s,
                    second_prize_description = %s, second_prize_value = %s, second_prize_image = %s,
                    third_prize_description = %s, third_prize_value = %s, third_prize_image = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (
                data.get('name'),
                data.get('description'),
                data.get('start_registration_date'),
                data.get('end_registration_date'),
                data.get('judging_criteria'),
                data.get('max_participants', 0),
                data.get('status'),
                data.get('first_prize_description'),
                data.get('first_prize_value', 0),
                data.get('first_prize_image'),
                data.get('second_prize_description'),
                data.get('second_prize_value', 0),
                data.get('second_prize_image'),
                data.get('third_prize_description'),
                data.get('third_prize_value', 0),
                data.get('third_prize_image'),
                activity_id
            ))

            conn.commit()

            return jsonify({
                'success': True,
                'message': 'อัพเดทกิจกรรมสำเร็จ'
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/admin/activities/<int:activity_id>', methods=['DELETE'])
def admin_delete_activity(activity_id):
    """Admin delete activity"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if activity exists
            cur.execute("SELECT name FROM activities WHERE id = %s", (activity_id,))
            activity = cur.fetchone()
            if not activity:
                return jsonify({'error': 'ไม่พบกิจกรรมนี้'}), 404

            # Delete activity (CASCADE will handle participants)
            cur.execute("DELETE FROM activities WHERE id = %s", (activity_id,))
            conn.commit()

            return jsonify({
                'success': True,
                'message': f'ลบกิจกรรม "{activity[0]}" สำเร็จ'
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/activities/<int:activity_id>/participants')
def activity_participants_page(activity_id):
    """Activity participants page"""
    if 'user_id' not in session:
        return redirect('/auth')
    if not is_approved():
        return redirect('/profile?not_approved=1')
    return render_template('activity_participants.html', activity_id=activity_id)

@app.route('/activities/<int:activity_id>/join')
def activity_join_page(activity_id):
    """Activity join page"""
    if 'user_id' not in session:
        return redirect('/auth')
    if not is_approved():
        return redirect('/profile?not_approved=1')
    return render_template('activity_join.html', activity_id=activity_id)



def get_registration_mode():
    """Get current registration mode from admin settings"""
    conn = get_db_connection()
    if conn:
        try:
            cur = get_db_connection().cursor() # Corrected to use get_db_connection()
            cur.execute("""
                SELECT setting_value FROM admin_settings 
                WHERE setting_key = 'registrationMode'
            """)
            result = cur.fetchone()
            cur.close()
            return_db_connection(conn)

            if result:
                return result[0]
            else:
                # Default to public registration
                return 'public'
        except:
            if conn:
                return_db_connection(conn)
            return 'public'
    return 'public'

def is_admin():
    """Check if current user is admin"""
    # Check if user has admin session
    admin_logged_in = session.get('admin_logged_in', False)
    admin_token = session.get('admin_token')
    admin_name = session.get('admin_name')

    print(f"Admin check - logged_in: {admin_logged_in}, has_token: {bool(admin_token)}, admin_name: {admin_name}")

    if not admin_logged_in or not admin_token:
        return False

    # For default admin, check if admin_name is admin999 OR if no admin_name but valid token
    if admin_name == 'admin999' or (not admin_name and admin_logged_in and admin_token):
        return True

    # For database admins, verify token
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT admin_name FROM admin_accounts 
                WHERE session_token = %s AND token_expires > NOW() AND is_active = TRUE
            """, (admin_token,))
            result = cur.fetchone()
            cur.close()
            return_db_connection(conn)
            return result is not None
        except:
            if conn:
                return_db_connection(conn)
            return False
    return False

def create_admin_account(admin_name, password, created_by_user_id=None):
    """Create new admin account securely"""
    # Validate password strength
    is_valid, message = validate_password_strength(password)
    if not is_valid:
        return False, message

    # Hash password securely
    password_hash = hash_password(password)

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if admin already exists
            cur.execute("SELECT id FROM admin_accounts WHERE admin_name = %s", (admin_name,))
            if cur.fetchone():
                return False, "ชื่อ Admin นี้มีอยู่แล้ว"

            # Insert new admin
            cur.execute("""
                INSERT INTO admin_accounts (admin_name, password_hash, created_by)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (admin_name, password_hash, created_by_user_id))

            admin_id = cur.fetchone()[0]
            conn.commit()

            # Log the creation
            log_admin_activity(admin_name, 'ADMIN_CREATED', True, 
                             details='New admin account created: {admin_name}')

            cur.close()
            return_db_connection(conn)
            return True, f"สร้าง Admin account '{admin_name}' สำเร็จ"

        except Exception as e:
            conn.rollback()
            cur.close()
            return_db_connection(conn)
            return False, f"เกิดข้อผิดพลาด: {str(e)}"
    return False, "เชื่อมต่อฐานข้อมูลไม่ได้"

def verify_admin_login(admin_name, password, ip_address=None, user_agent=None):
    """Verify admin login with security measures"""
    import secrets
    import time
    from datetime import datetime, timedelta

    # Check for default admin first
    master_password = os.environ.get('ADMIN_MASTER_PASSWORD', 'Admin123!@#')
    if admin_name == "admin999" and password == master_password:
        # Generate session token for default admin
        session_token = secrets.token_urlsafe(32)

        # Log successful login
        log_admin_activity(admin_name, 'LOGIN_SUCCESS', True, ip_address, user_agent, 'Default admin login')
        print(f"Default admin login successful: {admin_name}")

        return True, "เข้าสู่ระบบ Admin สำเร็จ", session_token

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if admin exists in database
            cur.execute("""
                SELECT admin_name, password_hash, login_attempts, locked_until FROM admin_accounts 
                WHERE admin_name = %s
            """, (admin_name,))

            admin_record = cur.fetchone()

            if admin_record:
                stored_admin_name, stored_password_hash, attempts, locked_until = admin_record

                # Check if account is locked
                if locked_until and locked_until > datetime.now():
                    log_admin_activity(admin_name, 'LOGIN_BLOCKED', False, ip_address, user_agent,
                                     'Account locked due to multiple failed attempts')
                    return False, "บัญชี Admin ถูกล็อค เนื่องจากใส่รหัสผ่านผิดหลายครั้ง", None

                # Verify password
                if verify_password(password, stored_password_hash):
                    # Generate session token
                    session_token = secrets.token_urlsafe(32)
                    token_expires = datetime.now() + timedelta(hours=2)  # 2 hour session

                    # Update admin record
                    cur.execute("""
                        UPDATE admin_accounts SET 
                            session_token = %s,
                            token_expires = %s,
                            last_login = NOW(),
                            login_attempts = 0,
                            locked_until = NULL
                        WHERE admin_name = %s
                    """, (session_token, token_expires, admin_name))

                    conn.commit()

                    # Log successful login
                    log_admin_activity(admin_name, 'LOGIN_SUCCESS', True, ip_address, user_agent)

                    cur.close()
                    return_db_connection(conn)
                    return True, f"เข้าสู่ระบบ Admin สำเร็จ", session_token
                else:
                    # Increment failed attempts
                    cur.execute("""
                        UPDATE admin_accounts SET 
                            login_attempts = login_attempts + 1,
                            locked_until = CASE 
                                WHEN login_attempts + 1 >= 5 THEN NOW() + INTERVAL '30 minutes'
                                ELSE NULL 
                            END
                        WHERE admin_name = %s
                    """, (admin_name,))

                    conn.commit()

                    # Log failed login
                    log_admin_activity(admin_name, 'LOGIN_FAILED', False, ip_address, user_agent,
                                     'Invalid password')

                    cur.close()
                    return_db_connection(conn)
                    return False, "รหัสผ่าน Admin ไม่ถูกต้อง", None
            else:
                # Admin not found
                log_admin_activity(admin_name, 'LOGIN_FAILED', False, ip_address, user_agent,
                                 'Admin account not found')

                cur.close()
                return_db_connection(conn)
                return False, "ไม่พบบัญชี Admin นี้", None

        except Exception as e:
            conn.rollback()
            cur.close()
            return_db_connection(conn)
            return False, f"เกิดข้อผิดพลาด: {str(e)}", None

    return False, "เชื่อมต่อฐานข้อมูลไม่ได้", None

def log_admin_activity(admin_name, action, success=True, ip_address=None, user_agent=None, details=None):
    """Log admin activity for security tracking"""
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO admin_activity_logs (admin_name, action, ip_address, user_agent, success, details)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (admin_name, action, ip_address, user_agent, success, details))
            conn.commit()
            cur.close()
            return_db_connection(conn)
        except:
            if conn:
                return_db_connection(conn)

@app.route('/api/verify_captcha', methods=['POST'])
def verify_captcha():
    """Verify reCAPTCHA token"""
    data = request.get_json()
    captcha_token = data.get('token')

    if not captcha_token:
        return jsonify({'success': False, 'error': 'ไม่พบ CAPTCHA token'}), 400

    # For production, you would verify with Google reCAPTCHA API:
    # secret_key = os.environ.get('RECAPTCHA_SECRET_KEY')
    # verify_url = 'https://www.google.com/recaptcha/api/siteverify'
    # response = requests.post(verify_url, data={
    #     'secret': secret_key,
    #     'response': captcha_token,
    #     'remoteip': request.environ.get('REMOTE_ADDR')
    # })
    # result = response.json()

    # For demo purposes, we'll accept any non-empty token
    if captcha_token:
        session['captcha_verified'] = True
        return jsonify({
            'success': True,
            'message': 'CAPTCHA verified successfully'
        })
    else:
        return jsonify({
            'success': False,
            'error': 'CAPTCHA verification failed'
        }), 400

@app.route('/fallback_login', methods=['POST'])
def fallback_login():
    """Fallback login for preview mode"""
    if not FALLBACK_AUTH_ENABLED:
        return jsonify({'success': False, 'error': 'Fallback authentication is disabled'}), 403

    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'success': False, 'error': 'กรุณากรอกอีเมลและรหัสผ่าน'}), 400

    # Special fallback accounts for development
    fallback_accounts = {
        'dev@budtboy.com': 'dev1123',
        'test@budtboy.com': 'test123',
        'admin@budtboy.com': 'admin123'
    }

    if email in fallback_accounts and password == fallback_accounts[email]:
        # Create temporary session for fallback user
        session['user_id'] = 999  # Special fallback user ID
        session['username'] = email.split('@')[0].title()
        session['email'] = email
        session['fallback_mode'] = True

        return jsonify({
            'success': True,
            'message': f'เข้าสู่ระบบสำเร็จ (Preview Mode)',
            'redirect': '/profile'
        })
    else:
        # Try regular database authentication
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("""
                    SELECT id, username, email, password_hash
                    FROM users 
                    WHERE email = %s
                """, (email,))

                user = cur.fetchone()
                if user and verify_password(password, user[3]):
                    session['user_id'] = user[0]
                    session['username'] = user[1]
                    session['email'] = user[2]
                    session['fallback_mode'] = True

                    return jsonify({
                        'success': True,
                        'message': f'เข้าสู่ระบบสำเร็จ ยินดีต้อนรับ {user[1]}!',
                        'redirect': '/profile'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': 'อีเมลหรือรหัสผ่านไม่ถูกต้อง'
                    }), 400

            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
            finally:
                cur.close()
                return_db_connection(conn)

        return jsonify({'success': False, 'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/fallback_signup', methods=['POST'])
def fallback_signup():
    """Fallback signup for preview mode"""
    if not FALLBACK_AUTH_ENABLED:
        return jsonify({'success': False, 'error': 'Fallback authentication is disabled'}), 403

    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not username or not email or not password:
        return jsonify({'success': False, 'error': 'กรุณากรอกข้อมูลให้ครบถ้วน'}), 400

    # Validate password strength
    is_valid, message = validate_password_strength(password)
    if not is_valid:
        return jsonify({'success': False, 'error': message}), 400

    # Hash password securely
    password_hash = hash_password(password)

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if user exists
            cur.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
            if cur.fetchone():
                return jsonify({
                    'success': False,
                    'error': 'ชื่อผู้ใช้หรืออีเมลนี้ถูกใช้แล้ว'
                }), 400

            # Generate referral code
            import secrets
            new_referral_code = secrets.token_urlsafe(8)

            # Create user
            cur.execute("""
                INSERT INTO users (username, email, password_hash, is_consumer, is_verified, referral_code, is_approved)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (username, email, password_hash, True, True, new_referral_code, True))

            user_id = cur.fetchone()[0]
            conn.commit()

            # Auto login
            session['user_id'] = user_id
            session['username'] = username
            session['email'] = email
            session['fallback_mode'] = True

            return jsonify({
                'success': True,
                'message': f'สมัครสมาชิกสำเร็จ! ยินดีต้อนรับ {username} (Preview Mode)',
                'redirect': '/profile'
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'success': False, 'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

def log_user_activity(user_id, username, action, resource_type=None, resource_id=None, 
                     old_data=None, new_data=None, success=True, details=None, request_obj=None):
    """Log user activity for tracking data changes"""
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Get IP and User Agent from request if provided
            ip_address = None
            user_agent = None
            if request_obj:
                ip_address = request_obj.environ.get('HTTP_X_FORWARDED_FOR', request_obj.environ.get('REMOTE_ADDR'))
                user_agent = request_obj.headers.get('User-Agent')

            # Convert data to JSON if provided
            import json
            old_data_json = json.dumps(old_data) if old_data else None
            new_data_json = json.dumps(new_data) if new_data else None

            cur.execute("""
                INSERT INTO user_activity_logs (user_id, username, action, resource_type, resource_id,
                                               ip_address, user_agent, old_data, new_data, success, details)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (user_id, username, action, resource_type, resource_id, 
                  ip_address, user_agent, old_data_json, new_data_json, success, details))
            conn.commit()
            cur.close()
            return_db_connection(conn)
        except Exception as e:
            print(f"Error logging user activity: {e}")
            if conn:
                return_db_connection(conn)

# Decorator for admin routes
def admin_required(func):
    from functools import wraps
    @wraps(func)
    def decorated_view(**kwargs):
        if not is_admin():
            # Optionally redirect to a forbidden page or return an error
            return redirect('/profile?no_admin=1')
        return func(**kwargs)
    return decorated_view

@app.route('/admin_login')
def admin_login_page():
    """Admin login page"""
    return render_template('admin_login.html')

@app.route('/admin_login', methods=['POST'])
def admin_login():
    """Handle admin login"""
    data = request.get_json()
    admin_name = data.get('admin_name', 'admin999')  # Default to admin999
    password = data.get('password')

    if not admin_name or not password:
        return jsonify({'success': False, 'error': 'กรุณากรอกชื่อ Admin และรหัสผ่าน'}), 400

    # Get client info for security logging
    ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR'))
    user_agent = request.headers.get('User-Agent')

    success, message, session_token = verify_admin_login(admin_name, password, ip_address, user_agent)

    if success:
        # Set admin session
        session['admin_token'] = session_token
        session['admin_logged_in'] = True
        session['admin_name'] = admin_name  # Always set admin name to session

        print(f"Admin login successful: {admin_name}, token: {session_token[:10]}...")

        return jsonify({
            'success': True,
            'message': message,
            'redirect': '/admin'
        })
    else:
        print(f"Admin login failed: {message}")
        return jsonify({
            'success': False,
            'error': message
        }), 400

@app.route('/admin_logout')
def admin_logout():
    """Admin logout"""
    admin_token = session.get('admin_token')
    if admin_token:
        # Clear token from database
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE admin_accounts 
                    SET session_token = NULL, token_expires = NULL 
                    WHERE session_token = %s
                """, (admin_token,))
                conn.commit()
                cur.close()
                return_db_connection(conn)
            except:
                if conn:
                    return_db_connection(conn)

        # Log logout
        log_admin_activity("admin", 'LOGOUT', True, 
                         request.environ.get('REMOTE_ADDR'),
                         request.headers.get('User-Agent'))

    # Clear admin session
    session.pop('admin_token', None)
    session.pop('admin_logged_in', None)

    return redirect('/admin_login')

@app.route('/admin')
def admin_dashboard():
    """Admin dashboard page"""
    if not is_admin():
        return redirect('/admin_login')

    # Log admin access
    log_admin_activity("admin", 'DASHBOARD_ACCESS', True,
                     request.environ.get('REMOTE_ADDR'),
                     request.headers.get('User-Agent'))

    return render_template('admin.html')

@app.route('/admin/users')
def admin_users():
    """Admin users management page"""
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_users.html')

# Admin settings routes
@app.route('/admin/settings')
def admin_settings():
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_settings.html')

@app.route('/admin/settings/general')
def admin_settings_general():
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_settings_general.html')

@app.route('/admin/settings/auth-images')
def admin_settings_auth_images():
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_settings_auth_images.html')

@app.route('/admin/settings/users')
def admin_settings_users():
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_settings_users.html')

@app.route('/admin/settings/content')
def admin_settings_content():
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_settings_content.html')

@app.route('/admin/settings/security')
def admin_settings_security():
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_settings_security.html')

@app.route('/admin/settings/maintenance')
def admin_settings_maintenance():
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_settings_maintenance.html')

@app.route('/admin/buds')
def admin_buds():
    """Admin buds management page"""
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_buds.html')

@app.route('/admin/reviews')
def admin_reviews():
    """Admin reviews management page"""
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_reviews.html')

@app.route('/api/admin/stats')
def get_admin_stats():
    """Get admin dashboard statistics"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Get total users
            cur.execute("SELECT COUNT(*) FROM users")
            total_users = cur.fetchone()[0]

            # Get pending users
            cur.execute("SELECT COUNT(*) FROM users WHERE is_approved = FALSE")
            pending_users = cur.fetchone()[0]

            # Get total buds
            cur.execute("SELECT COUNT(*) FROM buds_data")
            total_buds = cur.fetchone()[0]

            # Get total reviews
            cur.execute("SELECT COUNT(*) FROM reviews")
            total_reviews = cur.fetchone()[0]

            # Get total activities
            cur.execute("SELECT COUNT(*) FROM activities")
            total_activities = cur.fetchone()[0]

            # Get active activities
            cur.execute("SELECT COUNT(*) FROM activities WHERE status IN ('registration_open', 'judging')")
            active_activities = cur.fetchone()[0]

            cur.close()
            return_db_connection(conn)

            return jsonify({
                'total_users': total_users,
                'pending_users': pending_users,
                'total_buds': total_buds,
                'total_reviews': total_reviews,
                'total_activities': total_activities,
                'active_activities': active_activities
            })

        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if cur:
                cur.close()
            if conn:
                return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/admin/pending_users')
# @admin_required # Commented out to allow access for testing purposes - uncomment for production
def get_pending_users():
    """Get list of users pending approval"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            # Using RealDictCursor to get results as dictionaries
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # Get pending users with referrer information
            cur.execute("""
                SELECT u.id, u.username, u.email, u.profile_image_url, u.created_at,
                       u.referred_by, r.username as referred_by_username, u.is_approved
                FROM users u
                LEFT JOIN users r ON u.referred_by = r.id
                WHERE u.is_approved = FALSE
                ORDER BY u.created_at DESC
            """)

            pending_users = cur.fetchall()

            # Format datetime and profile image URL
            users_list = []
            for user in pending_users:
                user_dict = dict(user)
                if user_dict['created_at']:
                    user_dict['created_at'] = user_dict['created_at'].isoformat()
                if user_dict['approved_at']:
                    user_dict['approved_at'] = user_dict['approved_at'].isoformat()

                # Format profile image URL correctly
                profile_image_url = None
                if user_dict.get('profile_image_url'):
                    if user_dict['profile_image_url'].startswith('/uploads/'):
                        profile_image_url = user_dict['profile_image_url']
                    elif user_dict['profile_image_url'].startswith('uploads/'):
                        profile_image_url = f'/{user_dict["profile_image_url"]}'
                    else:
                        profile_image_url = f'/uploads/{user_dict["profile_image_url"].split("/")[-1]}'
                user_dict['profile_image_url'] = profile_image_url

                users_list.append(user_dict)

            return jsonify({'users': users_list})

        except Exception as e:
            print(f"Error getting pending users: {e}")
            return jsonify({'error': str(e)}), 500
        finally:
            if cur:
                cur.close()
            if conn:
                return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/admin/approve_user', methods=['POST'])
# @admin_required # Commented out for testing
def admin_approve_user():
    """Admin approve a pending user"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    user_id_to_approve = data.get('user_id')

    if not user_id_to_approve:
        return jsonify({'error': 'ไม่พบ user_id ที่จะอนุมัติ'}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if user exists and is pending
            cur.execute("""
                SELECT id, username, is_approved 
                FROM users 
                WHERE id = %s
            """, (user_id_to_approve,))

            user_to_approve = cur.fetchone()
            if not user_to_approve:
                return jsonify({'error': 'ไม่พบผู้ใช้ที่ต้องอนุมัติ'}), 404

            if user_to_approve[2]:  # is_approved
                return jsonify({'error': 'ผู้ใช้นี้ได้รับการอนุมัติแล้ว'}), 400

            # Approve the user
            admin_id = session.get('user_id') # Get current logged-in user ID
            if not admin_id: # If admin logged in without user_id (e.g. default admin)
                admin_id = None # Or handle as appropriate, e.g., use a placeholder admin ID

            cur.execute("""
                UPDATE users 
                SET is_approved = TRUE, approved_at = CURRENT_TIMESTAMP, approved_by = %s
                WHERE id = %s
            """, (admin_id, user_id_to_approve))

            conn.commit()
            cur.close()
            return_db_connection(conn)

            return jsonify({
                'success': True,
                'message': f'อนุมัติผู้ใช้ {user_to_approve[1]} เรียบร้อยแล้ว'
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            if cur:
                cur.close()
            if conn:
                return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/admin/reject_user', methods=['POST'])
# @admin_required # Commented out for testing
def admin_reject_user():
    """Admin reject a pending user (delete from system)"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    user_id_to_reject = data.get('user_id')

    if not user_id_to_reject:
        return jsonify({'error': 'ไม่พบ user_id ที่จะปฏิเสธ'}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if user exists and is pending
            cur.execute("""
                SELECT id, username, is_approved 
                FROM users 
                WHERE id = %s
            """, (user_id_to_reject,))

            user_to_reject = cur.fetchone()
            if not user_to_reject:
                return jsonify({'error': 'ไม่พบผู้ใช้ที่ต้องปฏิเสธ'}), 404

            if user_to_reject[2]:  # is_approved
                return jsonify({'error': 'ไม่สามารถปฏิเสธผู้ใช้ที่อนุมัติแล้วได้'}), 400

            # Delete the user (CASCADE will handle related records)
            cur.execute("DELETE FROM users WHERE id = %s", (user_id_to_reject,))

            conn.commit()
            cur.close()
            return_db_connection(conn)

            return jsonify({
                'success': True,
                'message': f'ปฏิเสธและลบผู้ใช้ {user_to_reject[1]} เรียบร้อยแล้ว'
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            if cur:
                cur.close()
            if conn:
                return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/admin/users')
# @admin_required # Commented out for testing
def get_admin_users():
    """Get all users for admin management"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            cur.execute("""
                SELECT id, username, email, is_grower, is_budtender, is_consumer,
                       birth_year, profile_image_url, is_verified, is_approved,
                       created_at, approved_at, referred_by,
                       ref.username as referred_by_username
                FROM users u
                LEFT JOIN users ref ON u.referred_by = ref.id
                ORDER BY u.is_approved ASC, u.created_at DESC
            """)

            users = []
            for row in cur.fetchall():
                user_data = {
                    'id': row[0],
                    'username': row[1],
                    'email': row[2],
                    'is_grower': row[3],
                    'is_budtender': row[4],
                    'is_consumer': row[5],
                    'birth_year': row[6],
                    'profile_image_url': row[7],
                    'is_verified': row[8],
                    'is_approved': row[9],
                    'created_at': row[10].strftime('%Y-%m-%d %H:%M:%S') if row[10] else None,
                    'approved_at': row[11].strftime('%Y-%m-%d %H:%M:%S') if row[11] else None,
                    'referred_by': row[12],
                    'referred_by_username': row[13]
                }
                users.append(user_data)

            cur.close()
            return_db_connection(conn)

            return jsonify({'users': users})

        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if cur:
                cur.close()
            if conn:
                return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/search-buds', methods=['POST'])
def search_buds():
    """Search buds based on criteria"""
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Build dynamic query with safe SQL composition
            conditions = []
            params = {}

            base_query = """
                SELECT b.id, b.strain_name_en, b.strain_name_th, b.breeder, b.strain_type,
                       b.thc_percentage, b.cbd_percentage, b.grade, b.aroma_flavor,
                       b.recommended_time, b.grow_method, b.created_at,
                       COALESCE(AVG(r.overall_rating), 0) as avg_rating,
                       COUNT(r.id) as review_count,
                       b.lab_test_name, b.test_type
                FROM buds_data b
                LEFT JOIN reviews r ON b.id = r.bud_reference_id
                WHERE 1=1
            """

            # Add search conditions
            if data.get('strain_name_en'):
                conditions.append("AND b.strain_name_en ILIKE %(strain_name_en)s")
                params['strain_name_en'] = f"%{data['strain_name_en']}%"

            if data.get('strain_name_th'):
                conditions.append("AND b.strain_name_th ILIKE %(strain_name_th)s")
                params['strain_name_th'] = f"%{data['strain_name_th']}%"

            if data.get('breeder'):
                conditions.append("AND b.breeder ILIKE %(breeder)s")
                params['breeder'] = f"%{data['breeder']}%"

            if data.get('strain_type'):
                conditions.append("AND b.strain_type = %(strain_type)s")
                params['strain_type'] = data['strain_type']

            if data.get('grade'):
                conditions.append("AND b.grade = %(grade)s")
                params['grade'] = data['grade']

            if data.get('recommended_time'):
                conditions.append("AND b.recommended_time = %(recommended_time)s")
                params['recommended_time'] = data['recommended_time']

            if data.get('grow_method'):
                conditions.append("AND b.grow_method = %(grow_method)s")
                params['grow_method'] = data['grow_method']

            # THC range
            if data.get('thc_min'):
                conditions.append("AND b.thc_percentage >= %(thc_min)s")
                params['thc_min'] = float(data['thc_min'])

            if data.get('thc_max'):
                conditions.append("AND b.thc_percentage <= %(thc_max)s")
                params['thc_max'] = float(data['thc_max'])

            # CBD range
            if data.get('cbd_min'):
                conditions.append("AND b.cbd_percentage >= %(cbd_min)s")
                params['cbd_min'] = float(data['cbd_min'])

            if data.get('cbd_max'):
                conditions.append("AND b.cbd_percentage <= %(cbd_max)s")
                params['cbd_max'] = float(data['cbd_max'])

            # Aroma/flavor search
            if data.get('aroma_flavor'):
                flavors = [f.strip() for f in data['aroma_flavor'].split(',')]
                flavor_conditions = []
                for i, flavor in enumerate(flavors):
                    if flavor:
                        param_name = f'flavor_{i}'
                        flavor_conditions.append(f"b.aroma_flavor ILIKE %({param_name})s")
                        params[param_name] = f"%{flavor}%"
                if flavor_conditions:
                    or_clause = "AND (" + " OR ".join(flavor_conditions) + ")"
                    conditions.append(or_clause)

            # Complete query with explicit structure
            query_parts = [base_query]
            query_parts.extend(conditions)
            query_parts.append("""
                GROUP BY b.id, b.strain_name_en, b.strain_name_th, b.breeder, b.strain_type,
                         b.thc_percentage, b.cbd_percentage, b.grade, b.aroma_flavor,
                         b.recommended_time, b.grow_method, b.created_at,
                         b.lab_test_name, b.test_type
                ORDER BY avg_rating DESC, b.created_at DESC
                LIMIT 50
            """)
            full_query = ' '.join(query_parts)

            cur.execute(full_query, params)
            results = cur.fetchall()

            buds = []
            for row in results:
                buds.append({
                    'id': row[0],
                    'strain_name_en': row[1],
                    'strain_name_th': row[2],
                    'breeder': row[3],
                    'strain_type': row[4],
                    'thc_percentage': float(row[5]) if row[5] else None,
                    'cbd_percentage': float(row[6]) if row[6] else None,
                    'grade': row[7],
                    'aroma_flavor': row[8],
                    'recommended_time': row[9],
                    'grow_method': row[10],
                    'created_at': row[11].strftime('%Y-%m-%d') if row[11] else None,
                    'avg_rating': float(row[12]) if row[12] else 0,
                    'review_count': row[13],
                    'lab_test_name': row[14],
                    'test_type': row[15]
                })

            cur.close()
            return_db_connection(conn)

            return jsonify({'success': True, 'buds': buds})

        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if cur:
                cur.close()
            if conn:
                return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/buds/<int:bud_id>/detail', methods=['GET'])
def get_bud_detail(bud_id):
    """Get individual bud data for editing"""
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    cache_key = f"bud_detail_{bud_id}_{user_id}"

    # Check cache first
    cached_data = get_cache(cache_key)
    if cached_data:
        print(f"Returning cached data for bud {bud_id}")
        return jsonify(cached_data)

    conn = None
    cur = None
    try:
        print(f"Loading bud detail for ID: {bud_id}, User: {user_id}")
        conn = get_db_connection()
        if not conn:
            print("Failed to get database connection")
            return jsonify({'error': 'Database connection failed'}), 500

        cur = conn.cursor()

        # Query to get bud data for the current user
        cur.execute("""
            SELECT id, strain_name_th, strain_name_en, breeder, strain_type,
                   thc_percentage, cbd_percentage, grade, aroma_flavor,
                   top_terpenes_1, top_terpenes_2, top_terpenes_3,
                   mental_effects_positive, mental_effects_negative,
                   physical_effects_positive, physical_effects_negative,
                   recommended_time, grow_method, harvest_date, batch_number,
                   grower_id, grower_license_verified, fertilizer_type, 
                   flowering_type, image_1_url, image_2_url, image_3_url, image_4_url,
                   created_at, updated_at, created_by,
                   lab_test_name, test_type
            FROM buds_data
            WHERE id = %s AND created_by = %s
        """, (bud_id, user_id))

        result = cur.fetchone()
        print(f"Query result: {result is not None}")

        if not result:
            print(f"No bud found with ID {bud_id} for user {user_id}")
            return jsonify({'error': 'ไม่พบข้อมูลดอกหรือไม่มีสิทธิ์เข้าถึง'}), 404

        bud_data = {
            'id': result[0],
            'strain_name_th': result[1] or '',
            'strain_name_en': result[2] or '',
            'breeder': result[3] or '',
            'strain_type': result[4] or '',
            'thc_percentage': float(result[5]) if result[5] else None,
            'cbd_percentage': float(result[6]) if result[6] else None,
            'grade': result[7] or '',
            'aroma_flavor': result[8] or '',
            'top_terpenes_1': result[9] or '',
            'top_terpenes_2': result[10] or '',
            'top_terpenes_3': result[11] or '',
            'mental_effects_positive': result[12] or '',
            'mental_effects_negative': result[13] or '',
            'physical_effects_positive': result[14] or '',
            'physical_effects_negative': result[15] or '',
            'recommended_time': result[16] or '',
            'grow_method': result[17] or '',
            'harvest_date': result[18].strftime('%Y-%m-%d') if result[18] else '',
            'batch_number': result[19] or '',
            'grower_id': result[20],
            'grower_license_verified': result[21] or False,
            'fertilizer_type': result[22] or '',
            'flowering_type': result[23] or '',
            'image_1_url': result[24] or '',
            'image_2_url': result[25] or '',
            'image_3_url': result[26] or '',
            'image_4_url': result[27] or '',
            'created_at': result[28].strftime('%Y-%m-%d %H:%M:%S') if result[28] else '',
            'updated_at': result[29].strftime('%Y-%m-%d %H:%M:%S') if result[29] else '',
            'created_by': result[30],
            'lab_test_name': result[31] or '',
            'test_type': result[32] or ''
        }

        print(f"Successfully loaded bud data: {bud_data['strain_name_en']}")

        # Cache for 2 minutes
        set_cache(cache_key, bud_data)

        return jsonify(bud_data)

    except psycopg2.OperationalError as e:
        print(f"Database operational error in get_bud_detail: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาดในการเชื่อมต่อฐานข้อมูล กรุณาลองใหม่อีกครั้ง'}), 500
    except Exception as e:
        print(f"Error in get_bud_detail for bud {bud_id}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'เกิดข้อผิดพลาดในการโหลดข้อมูล: {str(e)}'}), 500
    finally:
        if cur:
            try:
                cur.close()
            except:
                pass
        if conn:
            return_db_connection(conn)

@app.route('/api/buds/<int:bud_id>/status', methods=['PUT'])
def update_bud_status(bud_id):
    """Update bud status (available/sold_out)"""
    if 'user_id' not in session:
        return jsonify({'error': 'ไม่ได้เข้าสู่ระบบ'}), 401

    data = request.get_json()
    user_id = session['user_id']
    new_status = data.get('status')

    if new_status not in ['available', 'sold_out']:
        return jsonify({'error': 'สถานะไม่ถูกต้อง'}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if user has permission to update (owner of the bud)
            cur.execute("""
                SELECT created_by FROM buds_data WHERE id = %s
            """, (bud_id,))
            result = cur.fetchone()

            if not result:
                return jsonify({'error': 'ไม่พบข้อมูล Bud'}), 404

            if result[0] != user_id:
                return jsonify({'error': 'ไม่มีสิทธิ์เปลี่ยนสถานะของ Bud นี้'}), 403

            # Update status
            cur.execute("""
                UPDATE buds_data 
                SET status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (new_status, bud_id))

            conn.commit()

            # Clear cache
            clear_cache_pattern(f"user_buds_{user_id}")
            clear_cache_pattern("all_buds_report")

            status_text = 'ยังเหลือ' if new_status == 'available' else 'หมดแล้ว'
            return jsonify({
                'success': True,
                'message': f'เปลี่ยนสถานะเป็น "{status_text}" สำเร็จ',
                'new_status': new_status
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/buds/<int:bud_id>', methods=['DELETE'])
def delete_bud(bud_id):
    """Delete bud data"""
    if 'user_id' not in session:
        return jsonify({'error': 'ไม่ได้เข้าสู่ระบบ'}), 401

    user_id = session['user_id']

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if user has permission to delete
            cur.execute("""
                SELECT created_by FROM buds_data WHERE id = %s
            """, (bud_id,))
            result = cur.fetchone()

            if not result:
                return jsonify({'error': 'ไม่พบข้อมูล Bud'}), 404

            if result[0] != user_id:
                return jsonify({'error': 'ไม่มีสิทธิ์ลบข้อมูลนี้'}), 403

            cur.execute("DELETE FROM buds_data WHERE id = %s", (bud_id,))
            conn.commit()

            return jsonify({
                'success': True,
                'message': 'ลบข้อมูล Bud สำเร็จ'
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/strains', methods=['POST'])
def add_strain():
    """Add new strain name to database"""
    if 'user_id' not in session:
        return jsonify({'error': 'ไม่ได้เข้าสู่ระบบ'}), 401

    data = request.get_json()
    name_en = data.get('name_en', '').strip()
    name_th = data.get('name_th', '').strip()
    is_popular = data.get('is_popular', False)

    if not name_en:
        return jsonify({'error': 'กรุณากรอกชื่อภาษาอังกฤษ'}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if strain already exists
            cur.execute("""
                SELECT id FROM strain_names 
                WHERE name_en ILIKE %s OR (name_th IS NOT NULL AND name_th ILIKE %s)
            """, (name_en, name_th if name_th else None))

            if cur.fetchone():
                return jsonify({'error': 'สายพันธุ์นี้มีในระบบแล้ว'}), 400

            # Insert new strain
            cur.execute("""
                INSERT INTO strain_names (name_en, name_name_th, is_popular)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (name_en, name_th if name_th else None, is_popular))

            strain_id = cur.fetchone()[0]
            conn.commit()

            return jsonify({
                'success': True,
                'message': f'เพิ่มสายพันธุ์ "{name_en}" สำเร็จ',
                'strain_id': strain_id
            }), 201

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/breeders/search', methods=['GET'])
def search_breeders():
    """Search breeder names with autocomplete suggestions"""
    query = request.args.get('q', '').strip()
    limit = int(request.args.get('limit', 15))

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            suggestions = []

            if query:
                # Search with query - case-insensitive partial matching
                cur.execute("""
                    SELECT name, is_popular
                    FROM breeders 
                    WHERE name ILIKE %s
                    ORDER BY is_popular DESC, 
                             CASE WHEN name ILIKE %s THEN 0 ELSE 1 END,
                             name
                    LIMIT %s
                """, (f'%{query}%', f'{query}%', limit))

                for row in cur.fetchall():
                    suggestions.append({
                        'name': row[0],
                        'is_popular': row[1]
                    })
            else:
                # No query - return popular breeders first
                cur.execute("""
                    SELECT name, is_popular
                    FROM breeders 
                    ORDER BY is_popular DESC, name
                    LIMIT %s
                """, (limit,))

                for row in cur.fetchall():
                    suggestions.append({
                        'name': row[0],
                        'is_popular': row[1]
                    })

            return jsonify(suggestions)

        except Exception as e:
            print(f"Error in search_breeders: {e}")
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/strains/search', methods=['GET'])
def search_strains():
    """Search strain names with autocomplete suggestions"""
    query = request.args.get('q', '').strip()
    lang = request.args.get('lang', 'both')  # 'th', 'en', or 'both'
    limit = int(request.args.get('limit', 10))

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            suggestions = []

            if query:
                # Search with query
                if lang in ['en', 'both']:
                    # Search English names with ILIKE for case-insensitive partial matching
                    cur.execute("""
                        SELECT name_en, is_popular
                        FROM strain_names 
                        WHERE name_en IS NOT NULL 
                        AND name_en ILIKE %s
                        ORDER BY is_popular DESC, 
                                 CASE WHEN name_en ILIKE %s THEN 0 ELSE 1 END,
                                 name_en
                        LIMIT %s
                    """, (f'%{query}%', f'{query}%', limit))

                    for row in cur.fetchall():
                        if row[0]:
                            suggestions.append({
                                'name': row[0],
                                'language': 'en',
                                'is_popular': row[1]
                            })

                if lang in ['th', 'both']:
                    # Search Thai names with ILIKE for case-insensitive partial matching
                    cur.execute("""
                        SELECT name_th, is_popular
                        FROM strain_names 
                        WHERE name_th IS NOT NULL 
                        AND name_th ILIKE %s
                        ORDER BY is_popular DESC,
                                 CASE WHEN name_th ILIKE %s THEN 0 ELSE 1 END,
                                 name_th
                        LIMIT %s
                    """, (f'%{query}%', f'{query}%', limit))

                    for row in cur.fetchall():
                        if row[0]:
                            suggestions.append({
                                'name': row[0],
                                'language': 'th',
                                'is_popular': row[1]
                            })
            else:
                # No query - return popular strains
                if lang in ['en', 'both']:
                    cur.execute("""
                        SELECT name_en, is_popular
                        FROM strain_names 
                        WHERE name_en IS NOT NULL AND is_popular = TRUE
                        ORDER BY name_en
                        LIMIT %s
                    """, (limit,))

                    for row in cur.fetchall():
                        if row[0]:
                            suggestions.append({
                                'name': row[0],
                                'language': 'en',
                                'is_popular': row[1]
                            })

                if lang in ['th', 'both']:
                    cur.execute("""
                        SELECT name_th, is_popular
                        FROM strain_names 
                        WHERE name_th IS NOT NULL AND is_popular = TRUE
                        ORDER BY name_th
                        LIMIT %s
                    """, (limit,))

                    for row in cur.fetchall():
                        if row[0]:
                            suggestions.append({
                                'name': row[0],
                                'language': 'th',
                                'is_popular': row[1]
                            })

            # Remove duplicates and sort by popularity then alphabetically
            unique_suggestions = []
            seen_names = set()

            for suggestion in suggestions:
                if suggestion['name'] not in seen_names:
                    unique_suggestions.append(suggestion)
                    seen_names.add(suggestion['name'])

            # Sort: popular first, then alphabetically
            unique_suggestions.sort(key=lambda x: (not x['is_popular'], x['name']))

            return jsonify(unique_suggestions[:limit])

        except Exception as e:
            print(f"Error in search_strains: {e}")
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    from flask import send_from_directory
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/attached_assets/<filename>')
def attached_assets_file(filename):
    """Serve attached assets files"""
    from flask import send_from_directory
    return send_from_directory('attached_assets', filename)

@app.route('/api/reviews', methods=['GET'])
def get_reviews():
    """Get all reviews with optional filtering"""
    bud_id = request.args.get('bud_id')
    reviewer_id = request.args.get('reviewer_id')
    min_rating = request.args.get('min_rating')

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Build query with filters
            query = """
                SELECT r.id, r.overall_rating, r.short_summary, r.full_review_content,
                       r.aroma_rating, r.selected_effects, r.aroma_flavors, r.review_images,
                       r.created_at, r.updated_at, r.video_review_url,
                       b.strain_name_en, b.strain_name_th, b.breeder,
                       u.username as reviewer_name, u.profile_image_url as reviewer_profile_image
                FROM reviews r
                JOIN buds_data b ON r.bud_reference_id = b.id
                JOIN users u ON r.reviewer_id = u.id
                WHERE 1=1
            """
            params = []

            if bud_id:
                query += " AND r.bud_reference_id = %s"
                params.append(bud_id)
            if reviewer_id:
                query += " AND r.reviewer_id = %s"
                params.append(reviewer_id)
            if min_rating:
                query += " AND r.overall_rating >= %s"
                params.append(min_rating)

            query += " ORDER BY r.created_at DESC"

            cur.execute(query, params)
            reviews = cur.fetchall()

            reviews_list = []
            for review in reviews:
                # Format profile image URL correctly
                reviewer_profile_image = None
                if review[15]:  # reviewer_profile_image
                    if review[15].startswith('/uploads/'):
                        reviewer_profile_image = review[15]
                    elif review[15].startswith('uploads/'):
                        reviewer_profile_image = f'/{review[15]}'
                    else:
                        reviewer_profile_image = f'/uploads/{review[15].split("/")[-1]}'

                reviews_list.append({
                    'id': review[0],
                    'overall_rating': review[1],
                    'short_summary': review[2],
                    'full_review_content': review[3],
                    'aroma_rating': review[4],
                    'selected_effects': review[5] if review[5] else [],
                    'aroma_flavors': review[6] if review[6] else [],
                    'review_images': review[7] if review[7] else [],
                    'created_at': review[8].strftime('%Y-%m-%d %H:%M:%S') if review[8] else None,
                    'updated_at': review[9].strftime('%Y-%m-%d %H:%M:%S') if review[9] else None,
                    'video_review_url': review[10],
                    'strain_name_en': review[11],
                    'strain_name_th': review[12],
                    'breeder': review[13],
                    'reviewer_name': review[14],
                    'reviewer_profile_image': reviewer_profile_image
                })

            return jsonify(reviews_list)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/reviews', methods=['POST'])
def add_review():
    """Add new review"""
    if 'user_id' not in session:
        return jsonify({'error': 'ไม่ได้เข้าสู่ระบบ'}), 401

    data = request.get_json()
    user_id = session['user_id']

    # Required fields validation
    required_fields = ['bud_reference_id', 'overall_rating', 'short_summary']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': f'กรุณากรอก {field}'}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if bud exists
            cur.execute("SELECT id FROM buds_data WHERE id = %s", (data.get('bud_reference_id'),))
            if not cur.fetchone():
                return jsonify({'error': 'ไม่พบข้อมูลดอกที่อ้างอิง'}), 400

            # Check if user already reviewed this bud
            cur.execute("""
                SELECT id FROM reviews 
                WHERE bud_reference_id = %s AND reviewer_id = %s
            """, (data.get('bud_reference_id'), user_id))

            if cur.fetchone():
                return jsonify({'error': 'คุณได้รีวิวดอกนี้แล้ว'}), 400

            cur.execute("""
                INSERT INTO reviews (
                    bud_reference_id, reviewer_id, overall_rating, aroma_flavors,
                    aroma_rating, selected_effects, short_summary, full_review_content,
                    review_images
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) RETURNING id
            """, (
                data.get('bud_reference_id'),
                user_id,
                data.get('overall_rating'),
                data.get('aroma_flavors', []),
                data.get('aroma_rating'),
                data.get('selected_effects', []),
                data.get('short_summary'),
                data.get('full_review_content'),
                data.get('review_images', [])
            ))

            review_id = cur.fetchone()[0]
            conn.commit()

            return jsonify({
                'success': True,
                'message': 'เพิ่มรีวิวสำเร็จ',
                'review_id': review_id
            }), 201

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/reviews/<int:review_id>', methods=['GET'])
def get_review(review_id):
    """Get individual review data"""
    if 'user_id' not in session:
        return jsonify({'error': 'ไม่ได้เข้าสู่ระบบ'}), 401

    user_id = session['user_id']

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Get review with bud info - only allow user to access their own reviews
            cur.execute("""
                SELECT r.id, r.overall_rating, r.short_summary, r.full_review_content,
                       r.aroma_rating, r.selected_effects, r.aroma_flavors, r.review_images,
                       r.created_at, r.updated_at, r.bud_reference_id,
                       b.strain_name_en, b.strain_name_th, b.breeder
                FROM reviews r
                JOIN buds_data b ON r.bud_reference_id = b.id
                WHERE r.id = %s AND r.reviewer_id = %s
            """, (review_id, user_id))

            result = cur.fetchone()
            if not result:
                return jsonify({'error': 'ไม่พบรีวิวหรือไม่มีสิทธิ์เข้าถึง'}), 404

            review_data = {
                'id': result[0],
                'overall_rating': result[1],
                'short_summary': result[2],
                'full_review_content': result[3],
                'aroma_rating': result[4],
                'selected_effects': result[5] if result[5] else [],
                'aroma_flavors': result[6] if result[6] else [],
                'review_images': result[7] if result[7] else [],
                'created_at': result[8].strftime('%Y-%m-%d %H:%M:%S') if result[8] else None,
                'updated_at': result[9].strftime('%Y-%m-%d %H:%M:%S') if result[9] else None,
                'video_review_url': result[10],
                'strain_name_en': result[11],
                'strain_name_th': result[12],
                'breeder': result[13]
            }

            cur.close()
            return_db_connection(conn)
            return jsonify(review_data)

        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if cur:
                cur.close()
            if conn:
                return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/reviews/<int:review_id>', methods=['PUT'])
def update_review(review_id):
    """Update existing review"""
    if 'user_id' not in session:
        return jsonify({'error': 'ไม่ได้เข้าสู่ระบบ'}), 401

    data = request.get_json()
    user_id = session['user_id']

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if user has permission to update
            cur.execute("SELECT reviewer_id FROM reviews WHERE id = %s", (review_id,))
            result = cur.fetchone()

            if not result:
                return jsonify({'error': 'ไม่พบรีวิว'}), 404

            if result[0] != user_id:
                return jsonify({'error': 'ไม่มีสิทธิ์แก้ไขรีวิวนี้'}), 403

            cur.execute("""
                UPDATE reviews SET
                    overall_rating = %s, aroma_flavors = %s, aroma_rating = %s,
                    selected_effects = %s, short_summary = %s, full_review_content = %s,
                    review_images = %s, video_review_url = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (
                data.get('overall_rating'),
                data.get('aroma_flavors', []),
                data.get('aroma_rating'),
                data.get('selected_effects', []),
                data.get('short_summary'),
                data.get('full_review_content'),
                data.get('review_images', []),
                data.get('video_review_url'),
                review_id
            ))

            conn.commit()

            return jsonify({
                'success': True,
                'message': 'อัพเดทรีวิวสำเร็จ'
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/reviews/<int:review_id>', methods=['DELETE'])
def delete_review(review_id):
    """Delete review"""
    if 'user_id' not in session:
        return jsonify({'error': 'ไม่ได้เข้าสู่ระบบ'}), 401

    user_id = session['user_id']

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if user has permission to delete
            cur.execute("SELECT reviewer_id FROM reviews WHERE id = %s", (review_id,))
            result = cur.fetchone()

            if not result:
                return jsonify({'error': 'ไม่พบรีวิว'}), 404

            if result[0] != user_id:
                return jsonify({'error': 'ไม่มีสิทธิ์ลบรีวิวนี้'}), 403

            cur.execute("DELETE FROM reviews WHERE id = %s", (review_id,))
            conn.commit()

            return jsonify({
                'success': True,
                'message': 'ลบรีวิวสำเร็จ'
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/all-buds-report')
def get_all_buds_report():
    """Get comprehensive report of all buds with ratings and review counts"""
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Check if certificate columns exist first
        cur.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='buds_data' AND column_name IN ('lab_test_name', 'test_type')
        """)
        existing_columns = [row[0] for row in cur.fetchall()]
        has_lab_test = 'lab_test_name' in existing_columns
        has_test_type = 'test_type' in existing_columns

        if has_lab_test and has_test_type:
            lab_test_select = "b.lab_test_name, b.test_type"
        else:
            lab_test_select = "NULL as lab_test_name, NULL as test_type"

        cur.execute(f"""
            SELECT b.id, b.strain_name_en, b.strain_name_th, b.breeder, b.strain_type,
                   b.thc_percentage, b.cbd_percentage, b.grade, b.aroma_flavor,
                   b.top_terpenes_1, b.top_terpenes_2, b.top_terpenes_3,
                   b.mental_effects_positive, b.mental_effects_negative,
                   b.physical_effects_positive, b.physical_effects_negative,
                   b.recommended_time, b.grow_method, b.harvest_date, b.batch_number,
                   b.grower_id, b.grower_license_verified, b.fertilizer_type, 
                   b.flowering_type, b.status, b.created_at, b.updated_at, b.created_by,
                   COALESCE(u_grower.username, u_creator.username, 'บัดท์บอย') as grower_name, 
                   COALESCE(u_grower.is_grower, u_creator.is_grower, false) as is_grower,
                   COALESCE(AVG(r.overall_rating), 0) as avg_rating,
                   COUNT(r.id) as review_count,
                   {lab_test_select}
            FROM buds_data b
            LEFT JOIN users u_grower ON b.grower_id = u_grower.id
            LEFT JOIN users u_creator ON b.created_by = u_creator.id
            LEFT JOIN reviews r ON b.id = r.bud_reference_id
            GROUP BY b.id, b.strain_name_en, b.strain_name_th, b.breeder, b.strain_type,
                     b.thc_percentage, b.cbd_percentage, b.grade, b.aroma_flavor,
                     b.top_terpenes_1, b.top_terpenes_2, b.top_terpenes_3,
                     b.mental_effects_positive, b.mental_effects_negative,
                     b.physical_effects_positive, b.physical_effects_negative,
                     b.recommended_time, b.grow_method, b.harvest_date, b.batch_number,
                     b.grower_id, b.grower_license_verified, b.fertilizer_type, 
                     b.flowering_type, b.status, b.created_at, b.updated_at, b.created_by,
                     u_grower.username, u_grower.is_grower, u_creator.username, u_creator.is_grower,
                     b.lab_test_name, b.test_type
            ORDER BY b.created_at DESC
        """)

        buds = []
        for row in cur.fetchall():
            buds.append({
                'id': row[0],
                'strain_name_en': row[1],
                'strain_name_th': row[2],
                'breeder': row[3],
                'strain_type': row[4],
                'thc_percentage': float(row[5]) if row[5] else None,
                'cbd_percentage': float(row[6]) if row[6] else None,
                'grade': row[7],
                'aroma_flavor': row[8],
                'top_terpenes_1': row[9],
                'top_terpenes_2': row[10],
                'top_terpenes_3': row[11],
                'mental_effects_positive': row[12],
                'mental_effects_negative': row[13],
                'physical_effects_positive': row[14],
                'physical_effects_negative': row[15],
                'recommended_time': row[16],
                'grow_method': row[17],
                'harvest_date': row[18].strftime('%Y-%m-%d') if row[18] else None,
                'batch_number': row[19],
                'grower_id': row[20],
                'grower_license_verified': row[21],
                'fertilizer_type': row[22],
                'flowering_type': row[23],
                'status': row[24] or 'available',
                'created_at': row[25].strftime('%Y-%m-%d %H:%M:%S') if row[25] else None,
                'updated_at': row[26].strftime('%Y-%m-%d %H:%M:%S') if row[26] else None,
                'created_by': row[27],
                'grower_name': row[28],
                'is_grower': row[29],
                'avg_rating': float(row[30]) if row[30] else 0,
                'review_count': row[31],
                'lab_test_name': row[32],
                'test_type': row[33]
            })

        return jsonify({'buds': buds})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        return_db_connection(conn)

@app.route('/api/buds/for-review')
def get_buds_for_review():
    """Get all buds available for review"""
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, strain_name_en, strain_name_th, breeder, strain_type,
                       thc_percentage, cbd_percentage, created_at, lab_test_name, test_type
                FROM buds_data 
                ORDER BY created_at DESC
            """)

            buds = []
            for row in cur.fetchall():
                buds.append({
                    'id': row[0],
                    'strain_name_en': row[1],
                    'strain_name_th': row[2],
                    'breeder': row[3],
                    'strain_type': row[4],
                    'thc_percentage': float(row[5]) if row[5] else None,
                    'cbd_percentage': float(row[6]) if row[6] else None,
                    'created_at': row[7].strftime('%Y-%m-%d') if row[7] else None,
                    'lab_test_name': row[8],
                    'test_type': row[9]
                })

            cur.close()
            return_db_connection(conn)
            return jsonify({'buds': buds})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if cur:
                cur.close()
            if conn:
                return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/buds/<int:bud_id>/info', methods=['GET'])
def get_bud_info(bud_id):
    """Get detailed bud information with grower details"""
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session.get('user_id')
    cache_key = f"bud_info_{bud_id}_{user_id}"

    # Check cache first
    cached_data = get_cache(cache_key)
    if cached_data:
        print(f"Returning cached data for bud {bud_id}")
        return jsonify(cached_data)

    conn = None
    cur = None
    try:
        print(f"Loading bud detail for ID: {bud_id}, User: {session.get('user_id', 'N/A')}")

        conn = get_db_connection()
        if not conn:
            print("Failed to get database connection")
            return jsonify({'error': 'Database connection failed'}), 500

        cur = conn.cursor()

        # Check if certificate columns exist first
        cur.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='buds_data' AND column_name IN ('lab_test_name', 'test_type')
        """)
        existing_columns = [row[0] for row in cur.fetchall()]
        has_lab_test = 'lab_test_name' in existing_columns
        has_test_type = 'test_type' in existing_columns

        # Build query based on available columns
        if has_lab_test and has_test_type:
            lab_test_select = "b.lab_test_name, b.test_type"
        else:
            lab_test_select = "NULL as lab_test_name, NULL as test_type"

        # Get detailed bud info with grower contact information
        cur.execute(f"""
            SELECT b.id, b.strain_name_en, b.strain_name_th, b.breeder, b.strain_type,
                   b.thc_percentage, b.cbd_percentage, b.grade, b.aroma_flavor,
                   b.top_terpenes_1, b.top_terpenes_2, b.top_terpenes_3,
                   b.mental_effects_positive, b.mental_effects_negative,
                   b.physical_effects_positive, b.physical_effects_negative,
                   b.recommended_time, b.grow_method, b.harvest_date, b.batch_number,
                   b.grower_id, b.grower_license_verified, b.fertilizer_type, 
                   b.flowering_type, b.status, b.created_at, b.updated_at, b.created_by,
                   b.image_1_url, b.image_2_url, b.image_3_url, b.image_4_url,
                   {lab_test_select},
                   COALESCE(u_grower.username, u_creator.username, 'บัดท์บอย') as grower_name,
                   u_grower.profile_image_url as grower_profile_image,
                   u_grower.contact_facebook as grower_contact_facebook,
                   u_grower.contact_line as grower_contact_line,
                   u_grower.contact_instagram as grower_contact_instagram,
                   u_grower.contact_twitter as grower_contact_twitter,
                   u_grower.contact_telegram as grower_contact_telegram,
                   u_grower.contact_phone as grower_contact_phone,
                   u_grower.contact_other as grower_contact_other
            FROM buds_data b
            LEFT JOIN users u_grower ON b.grower_id = u_grower.id
            LEFT JOIN users u_creator ON b.created_by = u_creator.id
            WHERE b.id = %s
        """, (bud_id,))

        result = cur.fetchone()
        print(f"Query result: {result is not None}")

        if not result:
            print(f"No bud found with ID {bud_id}")
            return jsonify({
                'success': False,
                'error': f'ไม่พบข้อมูล Bud ID: {bud_id}'
            }), 404

        bud_info = {
            'id': result[0],
            'strain_name_en': result[1],
            'strain_name_th': result[2],
            'breeder': result[3],
            'strain_type': result[4],
            'thc_percentage': float(result[5]) if result[5] else None,
            'cbd_percentage': float(result[6]) if result[6] else None,
            'grade': result[7],
            'aroma_flavor': result[8],
            'top_terpenes_1': result[9],
            'top_terpenes_2': result[10],
            'top_terpenes_3': result[11],
            'mental_effects_positive': result[12],
            'mental_effects_negative': result[13],
            'physical_effects_positive': result[14],
            'physical_effects_negative': result[15],
            'recommended_time': result[16],
            'grow_method': result[17],
            'harvest_date': result[18].strftime('%Y-%m-%d') if result[18] else None,
            'batch_number': result[19],
            'grower_id': result[20],
            'grower_license_verified': result[21],
            'fertilizer_type': result[22],
            'flowering_type': result[23],
            'status': result[24] or 'available',
            'created_at': result[25].strftime('%Y-%m-%d %H:%M:%S') if result[25] else None,
            'updated_at': result[26].strftime('%Y-%m-%d %H:%M:%S') if result[26] else None,
            'created_by': result[27],
            'image_1_url': result[28],
            'image_2_url': result[29],
            'image_3_url': result[30],
            'image_4_url': result[31],
            'lab_test_name': result[32],
            'test_type': result[33],
            'grower_name': result[34],
            'grower_profile_image': result[35],
            'grower_contact_facebook': result[36],
            'grower_contact_line': result[37],
            'grower_contact_instagram': result[38],
            'grower_contact_twitter': result[39],
            'grower_contact_telegram': result[40],
            'grower_contact_phone': result[41],
            'grower_contact_other': result[42]
        }

        print(f"Successfully loaded bud data: {bud_info['strain_name_en']}")

        # Cache for 5 minutes
        response_data = {'success': True, 'bud': bud_info}
        set_cache(cache_key, response_data)

        return jsonify(response_data)

    except psycopg2.OperationalError as e:
        print(f"Database operational error in get_bud_info: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาดในการเชื่อมต่อฐานข้อมูล กรุณาลองใหม่อีกครั้ง'}), 500
    except Exception as e:
        print(f"Error in get_bud_info for bud {bud_id}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'เกิดข้อผิดพลาดในการโหลดข้อมูล: {str(e)}'}), 500
    finally:
        if cur:
            try:
                cur.close()
            except:
                pass
        if conn:
            return_db_connection(conn)

@app.route('/add-review')
def add_review_page():
    """Add review page"""
    if 'user_id' not in session:
        return redirect('/auth')
    return render_template('add_review.html')

@app.route('/edit-review')
def edit_review_page():
    """Edit review page"""
    if 'user_id' not in session:
        return redirect('/auth')
    return render_template('edit_review.html')

@app.route('/bud-reviews')
def bud_reviews_page():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')
    return render_template('bud_reviews.html')

@app.route('/report')
def report_page():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')
    return render_template('report.html')

@app.route('/bud-report/')
@app.route('/bud-report/<int:bud_id>')
@app.route('/bud-report')
@app.route('/bud-report/<int:bud_id>')
def bud_report_page(bud_id=None):
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')

    # Handle query parameter for id
    if bud_id is None:
        bud_id = request.args.get('id')
        if bud_id:
            try:
                bud_id = int(bud_id)
            except (ValueError, TypeError):
                bud_id = None

    return render_template('bud_report.html', bud_id=bud_id)

@app.route('/search-tool')
def search_tool_page():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')
    if not is_approved():
        return redirect('/profile?not_approved=1')
    return render_template('search_tool.html')

@app.route('/friends')
def friends_page():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')
    if not is_approved():
        return redirect('/profile?not_approved=1')
    return render_template('friends.html')

@app.route('/my-reviews')
def my_reviews_page():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')
    if not is_approved():
        return redirect('/profile?not_approved=1')
    return render_template('my_reviews.html')

@app.route('/friends-reviews')
def friends_reviews_page():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')
    if not is_approved():
        return redirect('/profile?not_approved=1')
    return render_template('friends_reviews.html')

@app.route('/activities')
def activities_page():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')
    if not is_approved():
        return redirect('/profile?not_approved=1')
    return render_template('activities.html')

@app.route('/api/activities', methods=['GET'])
def get_activities():
    """Get all activities"""
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT a.id, a.name, a.description, a.start_registration_date, a.end_registration_date,
                       a.judging_criteria, a.max_participants, 
                       a.first_prize_description, a.first_prize_value, a.first_prize_image,
                       a.second_prize_description, a.second_prize_value, a.second_prize_image,
                       a.third_prize_description, a.third_prize_value, a.third_prize_image,
                       a.status, a.created_at,
                       COUNT(ap.id) as participant_count
                FROM activities a
                LEFT JOIN activity_participants ap ON a.id = ap.activity_id
                GROUP BY a.id, a.name, a.description, a.start_registration_date, a.end_registration_date,
                         a.judging_criteria, a.max_participants,
                         a.first_prize_description, a.first_prize_value, a.first_prize_image,
                         a.second_prize_description, a.second_prize_value, a.second_prize_image,
                         a.third_prize_description, a.third_prize_value, a.third_prize_image,
                         a.status, a.created_at
                ORDER BY a.created_at DESC
            """)

            activities = []
            for row in cur.fetchall():
                activities.append({
                    'id': row[0],
                    'name': row[1],
                    'description': row[2],
                    'start_registration_date': row[3].strftime('%Y-%m-%d %H:%M:%S') if row[3] else None,
                    'end_registration_date': row[4].strftime('%Y-%m-%d %H:%M:%S') if row[4] else None,
                    'judging_criteria': row[5],
                    'max_participants': row[6],
                    'first_prize_description': row[7],
                    'first_prize_value': float(row[8]) if row[8] else 0,
                    'first_prize_image': row[9],
                    'second_prize_description': row[10],
                    'second_prize_value': float(row[11]) if row[11] else 0,
                    'second_prize_image': row[12],
                    'third_prize_description': row[13],
                    'third_prize_value': float(row[14]) if row[14] else 0,
                    'third_prize_image': row[15],
                    'status': row[16],
                    'created_at': row[17].strftime('%Y-%m-%d %H:%M:%S') if row[17] else None,
                    'participant_count': row[18]
                })

            return jsonify({'activities': activities})

        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/activities/<int:activity_id>/participants', methods=['GET'])
def get_activity_participants(activity_id):
    """Get participants for specific activity"""
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT ap.id, ap.submission_description, ap.submission_images, ap.rank, ap.prize_amount,
                       ap.registered_at, u.username, u.profile_image_url,
                       b.strain_name_en, b.strain_name_th, b.image_1_url, b.image_2_url, b.image_3_url, b.image_4_url
                FROM activity_participants ap
                JOIN users u ON ap.user_id = u.id
                JOIN buds_data b ON ap.bud_id = b.id
                WHERE ap.activity_id = %s
                ORDER BY ap.rank ASC NULLS LAST, ap.registered_at ASC
            """, (activity_id,))

            participants = []
            for row in cur.fetchall():
                participants.append({
                    'id': row[0],
                    'submission_description': row[1],
                    'submission_images': row[2] if row[2] else [],
                    'rank': row[3],
                    'prize_amount': float(row[4]) if row[4] else 0,
                    'registered_at': row[5].strftime('%Y-%m-%d %H:%M:%S') if row[5] else None,
                    'username': row[6],
                    'profile_image_url': row[7],
                    'strain_name_en': row[8],
                    'strain_name_th': row[9],
                    'bud_images': [row[10], row[11], row[12], row[13]]
                })

            return jsonify({'participants': participants})

        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/admin/activities', methods=['POST'])
def admin_create_activity():
    """Admin create new activity"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()

    if not data.get('name'):
        return jsonify({'error': 'กรุณากรอกชื่อกิจกรรม'}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO activities (
                    name, description, start_registration_date, end_registration_date,
                    judging_criteria, max_participants, status,
                    first_prize_description, first_prize_value, first_prize_image,
                    second_prize_description, second_prize_value, second_prize_image,
                    third_prize_description, third_prize_value, third_prize_image
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) RETURNING id
            """, (
                data.get('name'),
                data.get('description'),
                data.get('start_registration_date'),
                data.get('end_registration_date'),
                data.get('judging_criteria'),
                data.get('max_participants', 0),
                data.get('status', 'upcoming'),
                data.get('first_prize_description'),
                data.get('first_prize_value', 0),
                data.get('first_prize_image'),
                data.get('second_prize_description'),
                data.get('second_prize_value', 0),
                data.get('second_prize_image'),
                data.get('third_prize_description'),
                data.get('third_prize_value', 0),
                data.get('third_prize_image')
            ))

            activity_id = cur.fetchone()[0]
            conn.commit()

            return jsonify({
                'success': True,
                'message': 'สร้างกิจกรรมสำเร็จ',
                'activity_id': activity_id
            }), 201

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/activities/<int:activity_id>/join', methods=['POST'])
def join_activity(activity_id):
    """Join an activity with a bud"""
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    data = request.get_json()
    bud_id = data.get('bud_id')
    submission_description = data.get('submission_description', '')

    if not bud_id:
        return jsonify({'error': 'กรุณาเลือกดอกที่ต้องการส่งเข้าประกวด'}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if activity exists and is open for registration
            cur.execute("""
                SELECT id, name, status, max_participants, end_registration_date
                FROM activities 
                WHERE id = %s
            """, (activity_id,))

            activity = cur.fetchone()
            if not activity:
                return jsonify({'error': 'ไม่พบกิจกรรมนี้'}), 404

            if activity[2] != 'registration_open':
                return jsonify({'error': 'กิจกรรมนี้ไม่เปิดรับสมัครแล้ว'}), 400

            if activity[4] and activity[4] < datetime.now():
                return jsonify({'error': 'หมดเวลาการสมัครแล้ว'}), 400

            # Check if user owns the bud
            cur.execute("SELECT id FROM buds_data WHERE id = %s AND created_by = %s", (bud_id, user_id))
            if not cur.fetchone():
                return jsonify({'error': 'ไม่พบดอกนี้หรือคุณไม่ใช่เจ้าของ'}), 403

            # Check if already joined with this bud
            cur.execute("""
                SELECT id FROM activity_participants 
                WHERE activity_id = %s AND user_id = %s AND bud_id = %s
            """, (activity_id, user_id, bud_id))

            if cur.fetchone():
                return jsonify({'error': 'คุณได้ส่งดอกนี้เข้าร่วมกิจกรรมแล้ว'}), 400

            # Check participant limit
            if activity[3] > 0:  # max_participants
                cur.execute("SELECT COUNT(*) FROM activity_participants WHERE activity_id = %s", (activity_id,))
                current_count = cur.fetchone()[0]
                if current_count >= activity[3]:
                    return jsonify({'error': 'กิจกรรมนี้เต็มแล้ว'}), 400

            # Join activity
            cur.execute("""
                INSERT INTO activity_participants (activity_id, user_id, bud_id, submission_description)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (activity_id, user_id, bud_id, submission_description))

            participant_id = cur.fetchone()[0]
            conn.commit()

            return jsonify({
                'success': True,
                'message': f'เข้าร่วมกิจกรรม "{activity[1]}" สำเร็จ',
                'participant_id': participant_id
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500



@app.route('/api/admin/activities/<int:activity_id>', methods=['PUT'])
def admin_update_activity(activity_id):
    """Admin update activity"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if activity exists
            cur.execute("SELECT id FROM activities WHERE id = %s", (activity_id,))
            if not cur.fetchone():
                return jsonify({'error': 'ไม่พบกิจกรรมนี้'}), 404

            cur.execute("""
                UPDATE activities SET
                    name = %s, description = %s, start_registration_date = %s,
                    end_registration_date = %s, judging_criteria = %s,
                    max_participants = %s, status = %s,
                    first_prize_description = %s, first_prize_value = %s, first_prize_image = %s,
                    second_prize_description = %s, second_prize_value = %s, second_prize_image = %s,
                    third_prize_description = %s, third_prize_value = %s, third_prize_image = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (
                data.get('name'),
                data.get('description'),
                data.get('start_registration_date'),
                data.get('end_registration_date'),
                data.get('judging_criteria'),
                data.get('max_participants', 0),
                data.get('status'),
                data.get('first_prize_description'),
                data.get('first_prize_value', 0),
                data.get('first_prize_image'),
                data.get('second_prize_description'),
                data.get('second_prize_value', 0),
                data.get('second_prize_image'),
                data.get('third_prize_description'),
                data.get('third_prize_value', 0),
                data.get('third_prize_image'),
                activity_id
            ))

            conn.commit()

            return jsonify({
                'success': True,
                'message': 'อัพเดทกิจกรรมสำเร็จ'
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/admin/activities/<int:activity_id>', methods=['DELETE'])
def admin_delete_activity(activity_id):
    """Admin delete activity"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if activity exists
            cur.execute("SELECT name FROM activities WHERE id = %s", (activity_id,))
            activity = cur.fetchone()
            if not activity:
                return jsonify({'error': 'ไม่พบกิจกรรมนี้'}), 404

            # Delete activity (CASCADE will handle participants)
            cur.execute("DELETE FROM activities WHERE id = %s", (activity_id,))
            conn.commit()

            return jsonify({
                'success': True,
                'message': f'ลบกิจกรรม "{activity[0]}" สำเร็จ'
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/activities/<int:activity_id>/participants')
def activity_participants_page(activity_id):
    """Activity participants page"""
    if 'user_id' not in session:
        return redirect('/auth')
    if not is_approved():
        return redirect('/profile?not_approved=1')
    return render_template('activity_participants.html', activity_id=activity_id)

@app.route('/activities/<int:activity_id>/join')
def activity_join_page(activity_id):
    """Activity join page"""
    if 'user_id' not in session:
        return redirect('/auth')
    if not is_approved():
        return redirect('/profile?not_approved=1')
    return render_template('activity_join.html', activity_id=activity_id)



def get_registration_mode():
    """Get current registration mode from admin settings"""
    conn = get_db_connection()
    if conn:
        try:
            cur = get_db_connection().cursor() # Corrected to use get_db_connection()
            cur.execute("""
                SELECT setting_value FROM admin_settings 
                WHERE setting_key = 'registrationMode'
            """)
            result = cur.fetchone()
            cur.close()
            return_db_connection(conn)

            if result:
                return result[0]
            else:
                # Default to public registration
                return 'public'
        except:
            if conn:
                return_db_connection(conn)
            return 'public'
    return 'public'

def is_admin():
    """Check if current user is admin"""
    # Check if user has admin session
    admin_logged_in = session.get('admin_logged_in', False)
    admin_token = session.get('admin_token')
    admin_name = session.get('admin_name')

    print(f"Admin check - logged_in: {admin_logged_in}, has_token: {bool(admin_token)}, admin_name: {admin_name}")

    if not admin_logged_in or not admin_token:
        return False

    # For default admin, check if admin_name is admin999 OR if no admin_name but valid token
    if admin_name == 'admin999' or (not admin_name and admin_logged_in and admin_token):
        return True

    # For database admins, verify token
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT admin_name FROM admin_accounts 
                WHERE session_token = %s AND token_expires > NOW() AND is_active = TRUE
            """, (admin_token,))
            result = cur.fetchone()
            cur.close()
            return_db_connection(conn)
            return result is not None
        except:
            if conn:
                return_db_connection(conn)
            return False
    return False

def create_admin_account(admin_name, password, created_by_user_id=None):
    """Create new admin account securely"""
    # Validate password strength
    is_valid, message = validate_password_strength(password)
    if not is_valid:
        return False, message

    # Hash password securely
    password_hash = hash_password(password)

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if admin already exists
            cur.execute("SELECT id FROM admin_accounts WHERE admin_name = %s", (admin_name,))
            if cur.fetchone():
                return False, "ชื่อ Admin นี้มีอยู่แล้ว"

            # Insert new admin
            cur.execute("""
                INSERT INTO admin_accounts (admin_name, password_hash, created_by)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (admin_name, password_hash, created_by_user_id))

            admin_id = cur.fetchone()[0]
            conn.commit()

            # Log the creation
            log_admin_activity(admin_name, 'ADMIN_CREATED', True, 
                             details='New admin account created: {admin_name}')

            cur.close()
            return_db_connection(conn)
            return True, f"สร้าง Admin account '{admin_name}' สำเร็จ"

        except Exception as e:
            conn.rollback()
            cur.close()
            return_db_connection(conn)
            return False, f"เกิดข้อผิดพลาด: {str(e)}"
    return False, "เชื่อมต่อฐานข้อมูลไม่ได้"

def verify_admin_login(admin_name, password, ip_address=None, user_agent=None):
    """Verify admin login with security measures"""
    import secrets
    import time
    from datetime import datetime, timedelta

    # Check for default admin first
    master_password = os.environ.get('ADMIN_MASTER_PASSWORD', 'Admin123!@#')
    if admin_name == "admin999" and password == master_password:
        # Generate session token for default admin
        session_token = secrets.token_urlsafe(32)

        # Log successful login
        log_admin_activity(admin_name, 'LOGIN_SUCCESS', True, ip_address, user_agent, 'Default admin login')
        print(f"Default admin login successful: {admin_name}")

        return True, "เข้าสู่ระบบ Admin สำเร็จ", session_token

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if admin exists in database
            cur.execute("""
                SELECT admin_name, password_hash, login_attempts, locked_until FROM admin_accounts 
                WHERE admin_name = %s
            """, (admin_name,))

            admin_record = cur.fetchone()

            if admin_record:
                stored_admin_name, stored_password_hash, attempts, locked_until = admin_record

                # Check if account is locked
                if locked_until and locked_until > datetime.now():
                    log_admin_activity(admin_name, 'LOGIN_BLOCKED', False, ip_address, user_agent,
                                     'Account locked due to multiple failed attempts')
                    return False, "บัญชี Admin ถูกล็อค เนื่องจากใส่รหัสผ่านผิดหลายครั้ง", None

                # Verify password
                if verify_password(password, stored_password_hash):
                    # Generate session token
                    session_token = secrets.token_urlsafe(32)
                    token_expires = datetime.now() + timedelta(hours=2)  # 2 hour session

                    # Update admin record
                    cur.execute("""
                        UPDATE admin_accounts SET 
                            session_token = %s,
                            token_expires = %s,
                            last_login = NOW(),
                            login_attempts = 0,
                            locked_until = NULL
                        WHERE admin_name = %s
                    """, (session_token, token_expires, admin_name))

                    conn.commit()

                    # Log successful login
                    log_admin_activity(admin_name, 'LOGIN_SUCCESS', True, ip_address, user_agent)

                    cur.close()
                    return_db_connection(conn)
                    return True, f"เข้าสู่ระบบ Admin สำเร็จ", session_token
                else:
                    # Increment failed attempts
                    cur.execute("""
                        UPDATE admin_accounts SET 
                            login_attempts = login_attempts + 1,
                            locked_until = CASE 
                                WHEN login_attempts + 1 >= 5 THEN NOW() + INTERVAL '30 minutes'
                                ELSE NULL 
                            END
                        WHERE admin_name = %s
                    """, (admin_name,))

                    conn.commit()

                    # Log failed login
                    log_admin_activity(admin_name, 'LOGIN_FAILED', False, ip_address, user_agent,
                                     'Invalid password')

                    cur.close()
                    return_db_connection(conn)
                    return False, "รหัสผ่าน Admin ไม่ถูกต้อง", None
            else:
                # Admin not found
                log_admin_activity(admin_name, 'LOGIN_FAILED', False, ip_address, user_agent,
                                 'Admin account not found')

                cur.close()
                return_db_connection(conn)
                return False, "ไม่พบบัญชี Admin นี้", None

        except Exception as e:
            conn.rollback()
            cur.close()
            return_db_connection(conn)
            return False, f"เกิดข้อผิดพลาด: {str(e)}", None

    return False, "เชื่อมต่อฐานข้อมูลไม่ได้", None

def log_admin_activity(admin_name, action, success=True, ip_address=None, user_agent=None, details=None):
    """Log admin activity for security tracking"""
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO admin_activity_logs (admin_name, action, ip_address, user_agent, success, details)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (admin_name, action, ip_address, user_agent, success, details))
            conn.commit()
            cur.close()
            return_db_connection(conn)
        except:
            if conn:
                return_db_connection(conn)

@app.route('/api/verify_captcha', methods=['POST'])
def verify_captcha():
    """Verify reCAPTCHA token"""
    data = request.get_json()
    captcha_token = data.get('token')

    if not captcha_token:
        return jsonify({'success': False, 'error': 'ไม่พบ CAPTCHA token'}), 400

    # For production, you would verify with Google reCAPTCHA API:
    # secret_key = os.environ.get('RECAPTCHA_SECRET_KEY')
    # verify_url = 'https://www.google.com/recaptcha/api/siteverify'
    # response = requests.post(verify_url, data={
    #     'secret': secret_key,
    #     'response': captcha_token,
    #     'remoteip': request.environ.get('REMOTE_ADDR')
    # })
    # result = response.json()

    # For demo purposes, we'll accept any non-empty token
    if captcha_token:
        session['captcha_verified'] = True
        return jsonify({
            'success': True,
            'message': 'CAPTCHA verified successfully'
        })
    else:
        return jsonify({
            'success': False,
            'error': 'CAPTCHA verification failed'
        }), 400

@app.route('/fallback_login', methods=['POST'])
def fallback_login():
    """Fallback login for preview mode"""
    if not FALLBACK_AUTH_ENABLED:
        return jsonify({'success': False, 'error': 'Fallback authentication is disabled'}), 403

    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'success': False, 'error': 'กรุณากรอกอีเมลและรหัสผ่าน'}), 400

    # Special fallback accounts for development
    fallback_accounts = {
        'dev@budtboy.com': 'dev1123',
        'test@budtboy.com': 'test123',
        'admin@budtboy.com': 'admin123'
    }

    if email in fallback_accounts and password == fallback_accounts[email]:
        # Create temporary session for fallback user
        session['user_id'] = 999  # Special fallback user ID
        session['username'] = email.split('@')[0].title()
        session['email'] = email
        session['fallback_mode'] = True

        return jsonify({
            'success': True,
            'message': f'เข้าสู่ระบบสำเร็จ (Preview Mode)',
            'redirect': '/profile'
        })
    else:
        # Try regular database authentication
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("""
                    SELECT id, username, email, password_hash
                    FROM users 
                    WHERE email = %s
                """, (email,))

                user = cur.fetchone()
                if user and verify_password(password, user[3]):
                    session['user_id'] = user[0]
                    session['username'] = user[1]
                    session['email'] = user[2]
                    session['fallback_mode'] = True

                    return jsonify({
                        'success': True,
                        'message': f'เข้าสู่ระบบสำเร็จ ยินดีต้อนรับ {user[1]}!',
                        'redirect': '/profile'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': 'อีเมลหรือรหัสผ่านไม่ถูกต้อง'
                    }), 400

            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
            finally:
                cur.close()
                return_db_connection(conn)

        return jsonify({'success': False, 'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/fallback_signup', methods=['POST'])
def fallback_signup():
    """Fallback signup for preview mode"""
    if not FALLBACK_AUTH_ENABLED:
        return jsonify({'success': False, 'error': 'Fallback authentication is disabled'}), 403

    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not username or not email or not password:
        return jsonify({'success': False, 'error': 'กรุณากรอกข้อมูลให้ครบถ้วน'}), 400

    # Validate password strength
    is_valid, message = validate_password_strength(password)
    if not is_valid:
        return jsonify({'success': False, 'error': message}), 400

    # Hash password securely
    password_hash = hash_password(password)

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if user exists
            cur.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
            if cur.fetchone():
                return jsonify({
                    'success': False,
                    'error': 'ชื่อผู้ใช้หรืออีเมลนี้ถูกใช้แล้ว'
                }), 400

            # Generate referral code
            import secrets
            new_referral_code = secrets.token_urlsafe(8)

            # Create user
            cur.execute("""
                INSERT INTO users (username, email, password_hash, is_consumer, is_verified, referral_code, is_approved)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (username, email, password_hash, True, True, new_referral_code, True))

            user_id = cur.fetchone()[0]
            conn.commit()

            # Auto login
            session['user_id'] = user_id
            session['username'] = username
            session['email'] = email
            session['fallback_mode'] = True

            return jsonify({
                'success': True,
                'message': f'สมัครสมาชิกสำเร็จ! ยินดีต้อนรับ {username} (Preview Mode)',
                'redirect': '/profile'
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'success': False, 'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

def log_user_activity(user_id, username, action, resource_type=None, resource_id=None, 
                     old_data=None, new_data=None, success=True, details=None, request_obj=None):
    """Log user activity for tracking data changes"""
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Get IP and User Agent from request if provided
            ip_address = None
            user_agent = None
            if request_obj:
                ip_address = request_obj.environ.get('HTTP_X_FORWARDED_FOR', request_obj.environ.get('REMOTE_ADDR'))
                user_agent = request_obj.headers.get('User-Agent')

            # Convert data to JSON if provided
            import json
            old_data_json = json.dumps(old_data) if old_data else None
            new_data_json = json.dumps(new_data) if new_data else None

            cur.execute("""
                INSERT INTO user_activity_logs (user_id, username, action, resource_type, resource_id,
                                               ip_address, user_agent, old_data, new_data, success, details)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (user_id, username, action, resource_type, resource_id, 
                  ip_address, user_agent, old_data_json, new_data_json, success, details))
            conn.commit()
            cur.close()
            return_db_connection(conn)
        except Exception as e:
            print(f"Error logging user activity: {e}")
            if conn:
                return_db_connection(conn)

# Decorator for admin routes
def admin_required(func):
    from functools import wraps
    @wraps(func)
    def decorated_view(**kwargs):
        if not is_admin():
            # Optionally redirect to a forbidden page or return an error
            return redirect('/profile?no_admin=1')
        return func(**kwargs)
    return decorated_view

@app.route('/admin_login')
def admin_login_page():
    """Admin login page"""
    return render_template('admin_login.html')

@app.route('/admin_login', methods=['POST'])
def admin_login():
    """Handle admin login"""
    data = request.get_json()
    admin_name = data.get('admin_name', 'admin999')  # Default to admin999
    password = data.get('password')

    if not admin_name or not password:
        return jsonify({'success': False, 'error': 'กรุณากรอกชื่อ Admin และรหัสผ่าน'}), 400

    # Get client info for security logging
    ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR'))
    user_agent = request.headers.get('User-Agent')

    success, message, session_token = verify_admin_login(admin_name, password, ip_address, user_agent)

    if success:
        # Set admin session
        session['admin_token'] = session_token
        session['admin_logged_in'] = True
        session['admin_name'] = admin_name  # Always set admin name to session

        print(f"Admin login successful: {admin_name}, token: {session_token[:10]}...")

        return jsonify({
            'success': True,
            'message': message,
            'redirect': '/admin'
        })
    else:
        print(f"Admin login failed: {message}")
        return jsonify({
            'success': False,
            'error': message
        }), 400

@app.route('/admin_logout')
def admin_logout():
    """Admin logout"""
    admin_token = session.get('admin_token')
    if admin_token:
        # Clear token from database
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE admin_accounts 
                    SET session_token = NULL, token_expires = NULL 
                    WHERE session_token = %s
                """, (admin_token,))
                conn.commit()
                cur.close()
                return_db_connection(conn)
            except:
                if conn:
                    return_db_connection(conn)

        # Log logout
        log_admin_activity("admin", 'LOGOUT', True, 
                         request.environ.get('REMOTE_ADDR'),
                         request.headers.get('User-Agent'))

    # Clear admin session
    session.pop('admin_token', None)
    session.pop('admin_logged_in', None)

    return redirect('/admin_login')

@app.route('/admin')
def admin_dashboard():
    """Admin dashboard page"""
    if not is_admin():
        return redirect('/admin_login')

    # Log admin access
    log_admin_activity("admin", 'DASHBOARD_ACCESS', True,
                     request.environ.get('REMOTE_ADDR'),
                     request.headers.get('User-Agent'))

    return render_template('admin.html')

@app.route('/admin/users')
def admin_users():
    """Admin users management page"""
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_users.html')

# Admin settings routes
@app.route('/admin/settings')
def admin_settings():
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_settings.html')

@app.route('/admin/settings/general')
def admin_settings_general():
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_settings_general.html')

@app.route('/admin/settings/auth-images')
def admin_settings_auth_images():
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_settings_auth_images.html')

@app.route('/admin/settings/users')
def admin_settings_users():
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_settings_users.html')

@app.route('/admin/settings/content')
def admin_settings_content():
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_settings_content.html')

@app.route('/admin/settings/security')
def admin_settings_security():
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_settings_security.html')

@app.route('/admin/settings/maintenance')
def admin_settings_maintenance():
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_settings_maintenance.html')

@app.route('/admin/buds')
def admin_buds():
    """Admin buds management page"""
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_buds.html')

@app.route('/admin/reviews')
def admin_reviews():
    """Admin reviews management page"""
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_reviews.html')

@app.route('/api/admin/stats')
def get_admin_stats():
    """Get admin dashboard statistics"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Get total users
            cur.execute("SELECT COUNT(*) FROM users")
            total_users = cur.fetchone()[0]

            # Get pending users
            cur.execute("SELECT COUNT(*) FROM users WHERE is_approved = FALSE")
            pending_users = cur.fetchone()[0]

            # Get total buds
            cur.execute("SELECT COUNT(*) FROM buds_data")
            total_buds = cur.fetchone()[0]

            # Get total reviews
            cur.execute("SELECT COUNT(*) FROM reviews")
            total_reviews = cur.fetchone()[0]

            # Get total activities
            cur.execute("SELECT COUNT(*) FROM activities")
            total_activities = cur.fetchone()[0]

            # Get active activities
            cur.execute("SELECT COUNT(*) FROM activities WHERE status IN ('registration_open', 'judging')")
            active_activities = cur.fetchone()[0]

            cur.close()
            return_db_connection(conn)

            return jsonify({
                'total_users': total_users,
                'pending_users': pending_users,
                'total_buds': total_buds,
                'total_reviews': total_reviews,
                'total_activities': total_activities,
                'active_activities': active_activities
            })

        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if cur:
                cur.close()
            if conn:
                return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/admin/pending_users')
# @admin_required # Commented out to allow access for testing purposes - uncomment for production
def get_pending_users():
    """Get list of users pending approval"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            # Using RealDictCursor to get results as dictionaries
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # Get pending users with referrer information
            cur.execute("""
                SELECT u.id, u.username, u.email, u.profile_image_url, u.created_at,
                       u.referred_by, r.username as referred_by_username, u.is_approved
                FROM users u
                LEFT JOIN users r ON u.referred_by = r.id
                WHERE u.is_approved = FALSE
                ORDER BY u.created_at DESC
            """)

            pending_users = cur.fetchall()

            # Format datetime and profile image URL
            users_list = []
            for user in pending_users:
                user_dict = dict(user)
                if user_dict['created_at']:
                    user_dict['created_at'] = user_dict['created_at'].isoformat()
                if user_dict['approved_at']:
                    user_dict['approved_at'] = user_dict['approved_at'].isoformat()

                # Format profile image URL correctly
                profile_image_url = None
                if user_dict.get('profile_image_url'):
                    if user_dict['profile_image_url'].startswith('/uploads/'):
                        profile_image_url = user_dict['profile_image_url']
                    elif user_dict['profile_image_url'].startswith('uploads/'):
                        profile_image_url = f'/{user_dict["profile_image_url"]}'
                    else:
                        profile_image_url = f'/uploads/{user_dict["profile_image_url"].split("/")[-1]}'
                user_dict['profile_image_url'] = profile_image_url

                users_list.append(user_dict)

            return jsonify({'users': users_list})

        except Exception as e:
            print(f"Error getting pending users: {e}")
            return jsonify({'error': str(e)}), 500
        finally:
            if cur:
                cur.close()
            if conn:
                return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/admin/approve_user', methods=['POST'])
# @admin_required # Commented out for testing
def admin_approve_user():
    """Admin approve a pending user"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    user_id_to_approve = data.get('user_id')

    if not user_id_to_approve:
        return jsonify({'error': 'ไม่พบ user_id ที่จะอนุมัติ'}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if user exists and is pending
            cur.execute("""
                SELECT id, username, is_approved 
                FROM users 
                WHERE id = %s
            """, (user_id_to_approve,))

            user_to_approve = cur.fetchone()
            if not user_to_approve:
                return jsonify({'error': 'ไม่พบผู้ใช้ที่ต้องอนุมัติ'}), 404

            if user_to_approve[2]:  # is_approved
                return jsonify({'error': 'ผู้ใช้นี้ได้รับการอนุมัติแล้ว'}), 400

            # Approve the user
            admin_id = session.get('user_id') # Get current logged-in user ID
            if not admin_id: # If admin logged in without user_id (e.g. default admin)
                admin_id = None # Or handle as appropriate, e.g., use a placeholder admin ID

            cur.execute("""
                UPDATE users 
                SET is_approved = TRUE, approved_at = CURRENT_TIMESTAMP, approved_by = %s
                WHERE id = %s
            """, (admin_id, user_id_to_approve))

            conn.commit()
            cur.close()
            return_db_connection(conn)

            return jsonify({
                'success': True,
                'message': f'อนุมัติผู้ใช้ {user_to_approve[1]} เรียบร้อยแล้ว'
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            if cur:
                cur.close()
            if conn:
                return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/admin/reject_user', methods=['POST'])
# @admin_required # Commented out for testing
def admin_reject_user():
    """Admin reject a pending user (delete from system)"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    user_id_to_reject = data.get('user_id')

    if not user_id_to_reject:
        return jsonify({'error': 'ไม่พบ user_id ที่จะปฏิเสธ'}), 400

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if user exists and is pending
            cur.execute("""
                SELECT id, username, is_approved 
                FROM users 
                WHERE id = %s
            """, (user_id_to_reject,))

            user_to_reject = cur.fetchone()
            if not user_to_reject:
                return jsonify({'error': 'ไม่พบผู้ใช้ที่ต้องปฏิเสธ'}), 404

            if user_to_reject[2]:  # is_approved
                return jsonify({'error': 'ไม่สามารถปฏิเสธผู้ใช้ที่อนุมัติแล้วได้'}), 400

            # Delete the user (CASCADE will handle related records)
            cur.execute("DELETE FROM users WHERE id = %s", (user_id_to_reject,))

            conn.commit()
            cur.close()
            return_db_connection(conn)

            return jsonify({
                'success': True,
                'message': f'ปฏิเสธและลบผู้ใช้ {user_to_reject[1]} เรียบร้อยแล้ว'
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            if cur:
                cur.close()
            if conn:
                return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/admin/users')
# @admin_required # Commented out for testing
def get_admin_users():
    """Get all users for admin management"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            cur.execute("""
                SELECT id, username, email, is_grower, is_budtender, is_consumer,
                       birth_year, profile_image_url, is_verified, is_approved,
                       created_at, approved_at, referred_by,
                       ref.username as referred_by_username
                FROM users u
                LEFT JOIN users ref ON u.referred_by = ref.id
                ORDER BY u.is_approved ASC, u.created_at DESC
            """)

            users = []
            for row in cur.fetchall():
                user_data = {
                    'id': row[0],
                    'username': row[1],
                    'email': row[2],
                    'is_grower': row[3],
                    'is_budtender': row[4],
                    'is_consumer': row[5],
                    'birth_year': row[6],
                    'profile_image_url': row[7],
                    'is_verified': row[8],
                    'is_approved': row[9],
                    'created_at': row[10].strftime('%Y-%m-%d %H:%M:%S') if row[10] else None,
                    'approved_at': row[11].strftime('%Y-%m-%d %H:%M:%S') if row[11] else None,
                    'referred_by': row[12],
                    'referred_by_username': row[13]
                }
                users.append(user_data)

            cur.close()
            return_db_connection(conn)

            return jsonify({'users': users})

        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if cur:
                cur.close()
            if conn:
                return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/admin/settings', methods=['POST'])
def save_admin_settings():
    """Save admin general settings"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400

            cur = conn.cursor()

            # ตรวจสอบว่าตาราง admin_settings มีอยู่หรือไม่
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'admin_settings'
                )
            """)
            table_exists = cur.fetchone()[0]

            if not table_exists:
                # สร้างตารางถ้ายังไม่มี
                cur.execute("""
                    CREATE TABLE admin_settings (
                        id SERIAL PRIMARY KEY,
                        setting_key VARCHAR(255) UNIQUE NOT NULL,
                        setting_value TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_by INTEGER REFERENCES users(id)
                    );
                """)
                print("Created admin_settings table")

            # Get admin ID - for admin sessions, user_id might not exist
            admin_id = session.get('user_id')
            if not admin_id:
                # For admin-only sessions, use a default admin user ID or None
                admin_id = None

            saved_count = 0

            # บันทึกการตั้งค่าแต่ละรายการ
            for key, value in data.items():
                if value is not None:
                    try:
                        cur.execute("""
                            INSERT INTO admin_settings (setting_key, setting_value, updated_by)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (setting_key)
                            DO UPDATE SET 
                                setting_value = EXCLUDED.setting_value,
                                updated_at = CURRENT_TIMESTAMP,
                                updated_by = EXCLUDED.updated_by
                        """, (key, str(value), admin_id))
                        saved_count += 1
                        print(f"Saved setting: {key} = {value}")
                    except Exception as e:
                        print(f"Error saving setting {key}: {e}")
                        continue

            conn.commit()
            print(f"Total settings saved: {saved_count}")

            cur.close()
            return_db_connection(conn)

            return jsonify({
                'success': True,
                'message': f'บันทึกการตั้งค่าระบบทั่วไปสำเร็จ ({saved_count} รายการ)',
                'saved_count': saved_count
            })

        except Exception as e:
            print(f"Error saving admin settings: {e}")
            if conn:
                conn.rollback()
            return jsonify({'error': f'เกิดข้อผิดพลาดในการบันทึก: {str(e)}'}), 500
        finally:
            if cur:
                try:
                    cur.close()
                except:
                    pass
            if conn:
                return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/admin/settings/general', methods=['POST'])
def save_general_settings():
    """Save admin general settings (specific endpoint)"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400

            cur = conn.cursor()

            # ตรวจสอบว่าตาราง admin_settings มีอยู่หรือไม่
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'admin_settings'
                )
            """)
            table_exists = cur.fetchone()[0]

            if not table_exists:
                # สร้างตารางถ้ายังไม่มี
                cur.execute("""
                    CREATE TABLE admin_settings (
                        id SERIAL PRIMARY KEY,
                        setting_key VARCHAR(255) UNIQUE NOT NULL,
                        setting_value TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_by INTEGER REFERENCES users(id)
                    );
                """)
                print("Created admin_settings table")

            # Get admin ID - for admin sessions, user_id might not exist
            admin_id = session.get('user_id')
            if not admin_id:
                # For admin-only sessions, use a default admin user ID or None
                admin_id = None

            saved_count = 0

            # บันทึกการตั้งค่าแต่ละรายการ
            for key, value in data.items():
                if value is not None:
                    try:
                        cur.execute("""
                            INSERT INTO admin_settings (setting_key, setting_value, updated_by)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (setting_key)
                            DO UPDATE SET 
                                setting_value = EXCLUDED.setting_value,
                                updated_at = CURRENT_TIMESTAMP,
                                updated_by = EXCLUDED.updated_by
                        """, (key, str(value), admin_id))
                        saved_count += 1
                        print(f"Saved general setting: {key} = {value}")
                    except Exception as e:
                        print(f"Error saving general setting {key}: {e}")
                        continue

            conn.commit()
            print(f"Total general settings saved: {saved_count}")

            cur.close()
            return_db_connection(conn)

            return jsonify({
                'success': True,
                'message': f'บันทึกการตั้งค่าระบบทั่วไปสำเร็จ ({saved_count} รายการ)',
                'saved_count': saved_count
            })

        except Exception as e:
            print(f"Error saving general settings: {e}")
            if conn:
                conn.rollback()
            return jsonify({'error': f'เกิดข้อผิดพลาดในการบันทึก: {str(e)}'}), 500
        finally:
            if cur:
                try:
                    cur.close()
                except:
                    pass
            if conn:
                return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/admin/get_settings', methods=['GET'])
def get_admin_settings():
    """Get current admin settings"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # ตรวจสอบว่าตาราง admin_settings มีอยู่หรือไม่
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'admin_settings'
                )
            """)
            table_exists = cur.fetchone()[0]

            if not table_exists:
                # สร้างตารางถ้ายังไม่มี
                cur.execute("""
                    CREATE TABLE admin_settings (
                        id SERIAL PRIMARY KEY,
                        setting_key VARCHAR(255) UNIQUE NOT NULL,
                        setting_value TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_by INTEGER REFERENCES users(id)
                    );
                """)

                # เพิ่มการตั้งค่าเริ่มต้น
                default_settings = [
                    ('autoApproval', 'false'),
                    ('publicRegistration', 'true'),
                    ('emailVerification', 'true'),
                    ('autoApproveReviews', 'false'),
                    ('maxImagesPerReview', '4'),
                    ('maxImageSize', '5'),
                    ('multipleLogin', 'true'),
                    ('sessionTimeout', '60'),
                    ('loginLogging', 'true')
                ]

                cur.executemany("""
                    INSERT INTO admin_settings (setting_key, setting_value)
                    VALUES (%s, %s)
                """, default_settings)

                conn.commit()

            # ดึงการตั้งค่าปัจจุบัน
            cur.execute("""
                SELECT setting_key, setting_value FROM admin_settings
            """)

            settings = {}
            for row in cur.fetchall():
                key, value = row
                # แปลงค่าตามประเภท
                if value and value.lower() in ['true', 'false']:
                    settings[key] = value.lower() == 'true'
                elif value and value.isdigit():
                    settings[key] = int(value)
                else:
                    settings[key] = value

            cur.close()
            return_db_connection(conn)

            return jsonify({
                'success': True,
                'settings': settings
            })

        except Exception as e:
            print(f"Error getting admin settings: {e}")
            if conn:
                conn.rollback()
            return jsonify({'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500
        finally:
            if cur:
                cur.close()
            if conn:
                return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/admin/create_admin', methods=['POST'])
def create_new_admin():
    """Create new admin account (requires existing admin)"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    admin_name = data.get('admin_name')
    password = data.get('password')

    if not admin_name or not password:
        return jsonify({'error': 'กรุณากรอกชื่อ Admin และรหัสผ่าน'}), 400

    # Get current user ID (if any)
    current_user_id = session.get('user_id')

    success, message = create_admin_account(admin_name, password, current_user_id)

    if success:
        # Log admin creation
        log_admin_activity(admin_name, 'ADMIN_ACCOUNT_CREATED', True,
                         request.environ.get('REMOTE_ADDR'),
                         request.headers.get('User-Agent'),
                         f'Created admin: {admin_name}')

        return jsonify({
            'success': True,
            'message': message
        })
    else:
        return jsonify({
            'success': False,
            'error': message
        }), 400

@app.route('/admin/activities')
def admin_activities():
    """Admin activities management page"""
    if not is_admin():
        return redirect('/admin_login')
    return render_template('admin_activities.html')

@app.route('/api/admin/activities', methods=['GET'])
def admin_get_activities():
    """Admin get all activities"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT a.id, a.name, a.description, a.start_registration_date, a.end_registration_date,
                       a.judging_criteria, a.max_participants, a.first_prize_amount, a.second_prize_amount,
                       a.third_prize_amount, a.status, a.created_at, a.created_by,
                       COUNT(ap.id) as participant_count,
                       u.username as created_by_username
                FROM activities a
                LEFT JOIN activity_participants ap ON a.id = ap.activity_id
                LEFT JOIN users u ON a.created_by = u.id
                GROUP BY a.id, a.name, a.description, a.start_registration_date, a.end_registration_date,
                         a.judging_criteria, a.max_participants, a.first_prize_amount, a.second_prize_amount,
                         a.third_prize_amount, a.status, a.created_at, a.created_by, u.username
                ORDER BY a.created_at DESC
            """)

            activities = []
            for row in cur.fetchall():
                activities.append({
                    'id': row[0],
                    'name': row[1],
                    'description': row[2],
                    'start_registration_date': row[3].strftime('%Y-%m-%d %H:%M:%S') if row[3] else None,
                    'end_registration_date': row[4].strftime('%Y-%m-%d %H:%M:%S') if row[4] else None,
                    'judging_criteria': row[5],
                    'max_participants': row[6],
                    'first_prize_amount': float(row[7]) if row[7] else 0,
                    'second_prize_amount': float(row[8]) if row[8] else 0,
                    'third_prize_amount': float(row[9]) if row[9] else 0,
                    'status': row[10],
                    'created_at': row[11].strftime('%Y-%m-%d %H:%M:%S') if row[11] else None,
                    'created_by': row[12],
                    'participant_count': row[13],
                    'created_by_username': row[14]
                })

            return jsonify({'activities': activities})

        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/admin/create_sample_data', methods=['POST'])
def admin_create_sample_data():
    """Admin endpoint to create sample data"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if sample user exists
            cur.execute("SELECT id FROM users WHERE username = 'Budt.Boy'")
            sample_user = cur.fetchone()

            if not sample_user:
                # Create sample user
                password_hash = hash_password('BudtBoy123!')
                import secrets
                referral_code = secrets.token_urlsafe(8)

                cur.execute("""
                    INSERT INTO users (username, email, password_hash, is_grower, is_consumer, 
                                     is_verified, is_approved, referral_code, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    RETURNING id
                """, ('Budt.Boy', 'budtboy@example.com', password_hash, True, True, True, True, referral_code))

                sample_user_id = cur.fetchone()[0]
            else:
                sample_user_id = sample_user[0]

            # Create sample buds
            sample_buds = [
                ('บลูดรีม', 'Blue Dream', 'Barney\'s Farm', 'Hybrid', 18.5, 1.2, 'A+', 'หวาน, เบอร์รี่, ซิตรัส',
                 'Myrcene', 'Limonene', 'Pinene', 'ผ่อนคลาย, สร้างสรรค์, สุขใจ', '', 'บรรเทาปวด, คลายกล้าม', 'ปากแห้ง',
                 'ตลอดวัน', 'Indoor', '2024-12-01', 'BD2024-001', sample_user_id, True, 'Organic', 'Photoperiod', None, None, sample_user_id, 'available'),
                ('โอจี คัช', 'OG Kush', 'DNA Genetics', 'Indica', 22.3, 0.8, 'A', 'ดิน, สน, เผ็ด',
                 'Myrcene', 'Caryophyllene', 'Limonene', 'ผ่อนคลาย, หลับง่าย', 'ง่วงหนัก', 'บรรเทาปวด, หลับง่าย', 'ตาแดง, ปากแห้ง',
                 'กลางคืน', 'Indoor', '2024-11-15', 'OG2024-001', sample_user_id, True, 'Chemical', 'Photoperiod', None, None, sample_user_id, 'active'),
                ('ไวท์ วิโดว์', 'White Widow', 'Green House Seed Company', 'Hybrid', 20.1, 1.5, 'A+', 'หวาน, ดอกไม้, มินต์',
                 'Pinene', 'Myrcene', 'Limonene', 'ตื่นตัว, โฟกัส, เบิกบาน', '', 'ต้านอักเสบ, สดชื่น', 'ตาแห้ง',
                 'กลางวัน', 'Greenhouse', '2024-10-20', 'WW2024-001', sample_user_id, True, 'Organic', 'Photoperiod', None, None, sample_user_id, 'available'),
                ('บลูดรีม 2', 'Blue Dream', 'DNA Genetics', 'Hybrid', 19.2, 2.0, 'B+', 'กาแฟ, สตรอว์เบอร์รี่, บัตเตอร์',
                 'Myrcene', 'Limonene', 'Caryophyllene', 'ผ่อนคลาย, สร้างสรรค์', '', 'บรรเทาปวด, คลายกล้าม', 'ปากแห้ง',
                 'ตลอดวัน', 'Indoor', '2025-07-16', '', sample_user_id, True, 'Organic', 'Photoperiod', None, None, sample_user_id, 'active')
            ]

            cur.executemany("""
                INSERT INTO buds_data (
                    strain_name_th, strain_name_en, breeder, strain_type,
                    thc_percentage, cbd_percentage, grade, aroma_flavor,
                    top_terpenes_1, top_terpenes_2, top_terpenes_3,
                    mental_effects_positive, mental_effects_negative,
                    physical_effects_positive, physical_effects_negative,
                    recommended_time, grow_method, harvest_date,
                    batch_number, grower_id, grower_license_verified,
                    fertilizer_type, flowering_type, lab_test_name, test_type,
                    created_by, status
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, sample_buds)

            conn.commit()

            return jsonify({
                'success': True,
                'message': f'สร้างข้อมูลตัวอย่างสำเร็จ ({len(sample_buds)} buds)'
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/admin/activity_logs')
def get_admin_activity_logs():
    """Get admin activity logs"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT admin_name, action, ip_address, success, details, created_at
                FROM admin_activity_logs
                ORDER BY created_at DESC
                LIMIT 100
            """)

            logs = []
            for row in cur.fetchall():
                logs.append({
                    'admin_name': row[0],
                    'action': row[1],
                    'ip_address': row[2],
                    'success': row[3],
                    'details': row[4],
                    'created_at': row[5].strftime('%Y-%m-%d %H:%M:%S') if row[5] else None
                })

            cur.close()
            return_db_connection(conn)
            return jsonify({'logs': logs})

        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if cur:
                cur.close()
            if conn:
                return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/api/admin/get_auth_images', methods=['GET'])
def get_current_auth_images():
    """Get current auth page images"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        import os
        images = {
            'logo': None,
            'background': None
        }

        # ค้นหารูป logo ปัจจุบัน
        if os.path.exists('attached_assets'):
            files = os.listdir('attached_assets')

            # หา logo file ใหม่ล่าสุด
            logo_files = [f for f in files if f.startswith('budtboy_logo_')]
            if logo_files:
                # เรียงตามวันที่และเวลา (จากชื่อไฟล์)
                logo_files.sort(reverse=True)
                images['logo'] = f'/attached_assets/{logo_files[0]}'
            else:
                # ใช้ logo เดิม
                for f in files:
                    if 'budtboy' in f.lower() and any(ext in f.lower() for ext in ['.png', '.jpg', '.jpeg']):
                        images['logo'] = f'/attached_assets/{f}'
                        break

            # หา background files
            bg_files = [f for f in files if f.startswith('auth_background_')]
            if bg_files:
                bg_files.sort(reverse=True)
                images['background'] = f'/attached_assets/{bg_files[0]}'

        return jsonify({
            'success': True,
            'images': images
        })

    except Exception as e:
        print(f"Error getting auth images: {e}")
        return jsonify({'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500

@app.route('/api/admin/upload_auth_image', methods=['POST'])
# @admin_required # Commented out for testing
def upload_auth_image():
    """Upload and update auth page images"""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        # Check if file was uploaded
        if 'authImage' not in request.files:
            return jsonify({'error': 'ไม่พบไฟล์รูปภาพ'}), 400

        file = request.files['authImage']
        image_type = request.form.get('imageType', '')

        if file.filename == '':
            return jsonify({'error': 'ไม่ได้เลือกไฟล์'}), 400

        if not image_type:
            return jsonify({'error': 'กรุณาเลือกประเภทรูป'}), 400

        # Check file type
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        if not ('.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_extensions):
            return jsonify({'error': 'ประเภทไฟล์ไม่ถูกต้อง (รองรับ: PNG, JPG, JPEG, GIF, WEBP)'}), 400

        # Create filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_extension = file.filename.rsplit('.', 1)[1].lower()

        if image_type == 'logo':
            filename = f'budtboy_logo_{timestamp}.{file_extension}'
        elif image_type == 'background':
            filename = f'auth_background_{timestamp}.{file_extension}'
        else:
            filename = f'auth_{image_type}_{timestamp}.{file_extension}'

        # Save file
        file_path = os.path.join('attached_assets', filename)
        file.save(file_path)

        # Update the auth template with new image path if it's the logo
        if image_type == 'logo':
            update_auth_logo(filename)

        return jsonify({
            'success': True,
            'message': 'อัปโหลดรูปภาพสำเร็จ',
            'filename': filename,
            'file_path': f'/attached_assets/{filename}'
        })

    except Exception as e:
        print(f"Error uploading auth image: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาดในการอัปโหลด'}), 500

def update_auth_logo(new_filename):
    """Update the logo filename in auth.html template"""
    try:
        auth_template_path = 'templates/auth.html'

        # Read the current template
        with open(auth_template_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find and replace the logo src using regex
        import re
        pattern = r'<img src="(/attached_assets/[^"]*)" alt="Budt\.Boy Logo" class="logo">'
        replacement = f'<img src="/attached_assets/{new_filename}" alt="Budt.Boy Logo" class="logo">'

        updated_content, num_replacements = re.subn(pattern, replacement, content)

        if num_replacements > 0:
            # Write back to file only if a replacement was made
            with open(auth_template_path, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            print(f"Updated auth.html logo to: {new_filename}")
        else:
            print(f"Logo image tag not found in auth.html for replacement with {new_filename}")

    except FileNotFoundError:
        print(f"Error: auth.html not found at {auth_template_path}")
    except Exception as e:
        print(f"Error updating auth template: {e}")
        # Raise the exception to indicate failure if needed
        # raise

if __name__ == '__main__':
    # Initialize connection pool
    init_connection_pool()

    # Create tables on startup
    create_tables()

    # Production configuration
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)