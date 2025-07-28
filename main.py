from flask import Flask, render_template, request, jsonify, url_for, session, redirect
import psycopg2
from psycopg2 import pool
import os
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
import secrets
import hashlib
import threading
import time

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'budtboy-secret-key-2024')

# Email configuration - using environment variables with fallback for testing
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'budtboy.app@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'demo_password')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME', 'budtboy.app@gmail.com')
app.config['MAIL_USE_SSL'] = False

# File upload configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

mail = Mail(app)

# Create uploads directory if it doesn't exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Connection pool
connection_pool = None
pool_lock = threading.Lock()

# Simple cache system
cache = {}
cache_lock = threading.Lock()
CACHE_TTL = 300  # 5 minutes

def init_connection_pool():
    global connection_pool
    with pool_lock:
        if connection_pool is None:
                try:
                    database_url = os.environ.get('DATABASE_URL')
                    if database_url:
                        connection_pool = psycopg2.pool.ThreadedConnectionPool(
                            1, 8,  # Reduced connection count for stability
                            database_url,
                            # Add connection optimization with keepalive
                            sslmode='prefer',
                            connect_timeout=15,
                            application_name='cannabis_app',
                            keepalives=1,
                            keepalives_idle=30,
                            keepalives_interval=10,
                            keepalives_count=5
                        )
                        print("Connection pool initialized successfully")
                    else:
                        print("DATABASE_URL not found")
                except Exception as e:
                    print(f"Error initializing connection pool: {e}")
                    connection_pool = None

def get_cache(key):
    with cache_lock:
        if key in cache:
            data, timestamp = cache[key]
            if time.time() - timestamp < CACHE_TTL:
                return data
            else:
                del cache[key]
    return None

def set_cache(key, data):
    with cache_lock:
        cache[key] = (data, time.time())

def clear_cache_pattern(pattern):
    with cache_lock:
        keys_to_delete = [key for key in cache.keys() if pattern in key]
        for key in keys_to_delete:
            del cache[key]

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Database connection function
def get_db_connection():
    global connection_pool
    try:
        if connection_pool is None:
            init_connection_pool()

        if connection_pool:
            try:
                conn = connection_pool.getconn()
                if conn:
                    # Test connection
                    with conn.cursor() as test_cur:
                        test_cur.execute("SELECT 1")
                    return conn
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                print(f"Connection pool error: {e}, trying to reinitialize...")
                # Reset connection pool and try again
                connection_pool = None
                init_connection_pool()
                if connection_pool:
                    try:
                        conn = connection_pool.getconn()
                        if conn:
                            with conn.cursor() as test_cur:
                                test_cur.execute("SELECT 1")
                            return conn
                    except Exception:
                        pass

        # Fallback to direct connection
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            raise Exception("DATABASE_URL environment variable not set")

        conn = psycopg2.connect(
            database_url,
            sslmode='prefer',
            connect_timeout=10,
            application_name='cannabis_app_direct'
        )
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

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

# Create tables if they don't exist
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

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
                    strain_name_th VARCHAR(255) NOT NULL,
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
                    image_1_url VARCHAR(500),
                    image_2_url VARCHAR(500),
                    image_3_url VARCHAR(500),
                    image_4_url VARCHAR(500),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by INTEGER REFERENCES users(id)
                );
            """)

            # Add image columns if they don't exist (for existing databases)
            try:
                cur.execute("""
                    ALTER TABLE buds_data 
                    ADD COLUMN IF NOT EXISTS image_1_url VARCHAR(500),
                    ADD COLUMN IF NOT EXISTS image_2_url VARCHAR(500),
                    ADD COLUMN IF NOT EXISTS image_3_url VARCHAR(500),
                    ADD COLUMN IF NOT EXISTS image_4_url VARCHAR(500);
                """)
            except Exception as e:
                print(f"Note: Image columns may already exist: {e}")

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
            """)

            conn.commit()

            # Insert sample bud data for existing users
            try:
                # Check if there are any users in the system
                cur.execute("SELECT id FROM users LIMIT 5")
                user_ids = [row[0] for row in cur.fetchall()]

                if user_ids:
                    # Check if bud data already exists
                    cur.execute("SELECT COUNT(*) FROM buds_data")
                    bud_count = cur.fetchone()[0]

                    if bud_count == 0:
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
                                    'Organic', 'Photoperiod', user_id
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
                                    'Chemical', 'Photoperiod', user_id
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
                                    'Organic', 'Photoperiod', user_id
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
                                fertilizer_type, flowering_type, created_by
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
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

            print("Tables created successfully")
        except Exception as e:
            print(f"Error creating tables: {e}")
        finally:
            cur.close()
            return_db_connection(conn)

def generate_verification_token():
    return secrets.token_urlsafe(32)

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

@app.route('/')
def index():
    # Check if user is logged in, if not redirect to auth page
    if 'user_id' not in session:
        return redirect('/auth')
    return redirect('/profile')

def is_authenticated():
    return 'user_id' in session

@app.route('/profile')
def profile():
    if not is_authenticated():
        return redirect('/auth')
    return render_template('profile.html')

@app.route('/activity')
def activity():
    if not is_authenticated():
        return redirect('/auth')
    return render_template('activity.html')

@app.route('/api/user_buds')
def get_user_buds():
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session.get('user_id')
    cache_key = f"user_buds_{user_id}"

    # Check cache first
    cached_data = get_cache(cache_key)
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

        # Optimized query with better performance
        cur.execute("""
            SELECT b.id, b.strain_name_en, b.strain_name_th, b.breeder, b.thc_percentage, 
                   b.cbd_percentage, b.strain_type, b.created_at, b.image_1_url,
                   COALESCE(AVG(r.overall_rating), 0) as avg_rating,
                   COUNT(r.id) as review_count
            FROM buds_data b
            LEFT JOIN reviews r ON b.id = r.bud_reference_id
            WHERE b.created_by = %s 
            GROUP BY b.id, b.strain_name_en, b.strain_name_th, b.breeder, 
                     b.thc_percentage, b.cbd_percentage, b.strain_type, b.created_at, b.image_1_url
            ORDER BY b.created_at DESC
            LIMIT 50
        """, (user_id,))

        buds = []
        for row in cur.fetchall():
            buds.append({
                'id': row[0],
                'strain_name_en': row[1],
                'strain_name_th': row[2],
                'breeder': row[3],
                'thc_percentage': float(row[4]) if row[4] else None,
                'cbd_percentage': float(row[5]) if row[5] else None,
                'strain_type': row[6],
                'created_at': row[7].strftime('%Y-%m-%d %H:%M:%S') if row[7] else None,
                'image_1_url': f'/uploads/{row[8].split("/")[-1]}' if row[8] else None,
                'avg_rating': float(row[9]) if row[9] else 0,
                'review_count': row[10]
            })

        # Cache for 2 minutes
        set_cache(cache_key, buds)

        return jsonify({'buds': buds})

    except psycopg2.OperationalError as e:
        print(f"Database operational error in get_user_buds: {e}")
        return jsonify({'error': 'Database connection lost', 'buds': []}), 500
    except Exception as e:
        print(f"Error in get_user_buds: {e}")
        return jsonify({'error': 'Internal server error', 'buds': []}), 500
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
def auth_page():
    return render_template('auth.html')

@app.route('/add-buds')
def add_buds_page():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')
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

    password_hash = hashlib.sha256(password.encode()).hexdigest()

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, username, email, is_verified
                FROM users 
                WHERE email = %s AND password_hash = %s
            """, (email, password_hash))

            user = cur.fetchone()
            if user:
                user_id, username, email, is_verified = user

                # Create session (no email verification required)
                session['user_id'] = user_id
                session['username'] = username
                session['email'] = email

                return jsonify({
                    'success': True,
                    'message': f'เข้าสู่ระบบสำเร็จ ยินดีต้อนรับ {username}!',
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
    else:
        return jsonify({'success': False, 'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/quick_signup', methods=['POST'])
def quick_signup():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not username or not email or not password:
        return jsonify({'success': False, 'error': 'กรุณากรอกข้อมูลให้ครบถ้วน'}), 400

    password_hash = hashlib.sha256(password.encode()).hexdigest()

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

            # Create user (quick signup - auto verified)
            cur.execute("""
                INSERT INTO users (username, email, password_hash, is_consumer, is_verified)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (username, email, password_hash, True, True))

            user_id = cur.fetchone()[0]
            conn.commit()

            # Auto login
            session['user_id'] = user_id
            session['username'] = username
            session['email'] = email

            return jsonify({
                'success': True,
                'message': f'สมัครสมาชิกสำเร็จ! ยินดีต้อนรับ {username}',
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

    # Check cache first
    cached_data = get_cache(cache_key)
    if cached_data:
        return jsonify(cached_data)

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, username, email, is_grower, is_budtender, is_consumer, 
                       birth_year, created_at, is_verified, grow_license_file_url, profile_image_url 
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
                    'profile_image_url': profile_image_url
                }

                # Cache the result
                set_cache(cache_key, user_data)

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
                    is_consumer = %s, is_grower = %s, is_budtender = %s
                WHERE id = %s
            """, (
                username, email, 
                int(birth_year) if birth_year else None,
                is_consumer, is_grower, is_budtender, user_id
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

            cur.execute("""
                INSERT INTO buds_data (
                    strain_name_th, strain_name_en, breeder, strain_type,
                    thc_percentage, cbd_percentage, grade, aroma_flavor,
                    top_terpenes_1, top_terpenes_2, top_terpenes_3,
                    mental_effects_positive, mental_effects_negative,
                    physical_effects_positive, physical_effects_negative,
                    recommended_time, grow_method, harvest_date,
                    batch_number, grower_id, grower_license_verified,
                    fertilizer_type, flowering_type, created_by
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) RETURNING id
            """, (
                data.get('strain_name_th'),
                data.get('strain_name_en'),
                data.get('breeder'),
                data.get('strain_type'),
                data.get('thc_percentage'),
                data.get('cbd_percentage'),
                data.get('grade'),
                data.get('aroma_flavor'),
                data.get('top_terpenes_1'),
                data.get('top_terpenes_2'),
                data.get('top_terpenes_3'),
                data.get('mental_effects_positive'),
                data.get('mental_effects_negative'),
                data.get('physical_effects_positive'),
                data.get('physical_effects_negative'),
                data.get('recommended_time'),
                data.get('grow_method'),
                data.get('harvest_date'),
                data.get('batch_number'),
                data.get('grower_id'),
                data.get('grower_license_verified', False),
                data.get('fertilizer_type'),
                data.get('flowering_type'),
                user_id
            ))

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

    conn = get_db_connection()
    if conn:
        try:
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

            cur.execute("""
                UPDATE buds_data SET
                    strain_name_th = %s, strain_name_en = %s, breeder = %s,
                    strain_type = %s, thc_percentage = %s, cbd_percentage = %s,
                    grade = %s, aroma_flavor = %s, top_terpenes_1 = %s,
                    top_terpenes_2 = %s, top_terpenes_3 = %s, 
                    mental_effects_positive = %s, mental_effects_negative = %s,
                    physical_effects_positive = %s, physical_effects_negative = %s,
                    recommended_time = %s, grow_method = %s, harvest_date = %s,
                    batch_number = %s, grower_id = %s, grower_license_verified = %s,
                    fertilizer_type = %s, flowering_type = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (
                data.get('strain_name_th'),
                data.get('strain_name_en'),
                data.get('breeder'),
                data.get('strain_type'),
                data.get('thc_percentage'),
                data.get('cbd_percentage'),
                data.get('grade'),
                data.get('aroma_flavor'),
                data.get('top_terpenes_1'),
                data.get('top_terpenes_2'),
                data.get('top_terpenes_3'),
                data.get('mental_effects_positive'),
                data.get('mental_effects_negative'),
                data.get('physical_effects_positive'),
                data.get('physical_effects_negative'),
                data.get('recommended_time'),
                data.get('grow_method'),
                data.get('harvest_date'),
                data.get('batch_number'),
                data.get('grower_id'),
                data.get('grower_license_verified', False),
                data.get('fertilizer_type'),
                data.get('flowering_type'),
                bud_id
            ))

            conn.commit()

            return jsonify({
                'success': True,
                'message': 'อัพเดทข้อมูล Bud สำเร็จ'
            })

        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

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

            # Update database with image URLs
            if image_urls:
                update_fields = []
                update_values = []
                for field, url in image_urls.items():
                    update_fields.append(f"{field} = %s")
                    update_values.append(url)

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

@app.route('/api/buds/<int:bud_id>', methods=['GET'])
def get_bud(bud_id):
    """Get individual bud data for editing"""
    if 'user_id' not in session:
        return jsonify({'error': 'ไม่ได้เข้าสู่ระบบ'}), 401

    user_id = session['user_id']

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            cur.execute("""
                SELECT id, strain_name_th, strain_name_en, breeder, strain_type,
                       thc_percentage, cbd_percentage, grade, aroma_flavor,
                       top_terpenes_1, top_terpenes_2, top_terpenes_3,
                       mental_effects_positive, mental_effects_negative,
                       physical_effects_positive, physical_effects_negative,
                       recommended_time, grow_method, harvest_date, batch_number,
                       grower_id, grower_license_verified, fertilizer_type, 
                       flowering_type, image_1_url, image_2_url, image_3_url, image_4_url,
                       created_at, updated_at, created_by
                FROM buds_data WHERE id = %s AND created_by = %s
            """, (bud_id, user_id))

            result = cur.fetchone()
            if not result:
                return jsonify({'error': 'ไม่พบข้อมูลดอกหรือไม่มีสิทธิ์เข้าถึง'}), 404

            bud_data = {
                'id': result[0],
                'strain_name_th': result[1],
                'strain_name_en': result[2],
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
                'image_1_url': result[24],
                'image_2_url': result[25],
                'image_3_url': result[26],
                'image_4_url': result[27],
                'created_at': result[28].strftime('%Y-%m-%d %H:%M:%S') if result[28] else None,
                'updated_at': result[29].strftime('%Y-%m-%d %H:%M:%S') if result[29] else None,
                'created_by': result[30]
            }

            cur.close()
            return_db_connection(conn)
            return jsonify(bud_data)

        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if cur:
                cur.close()
            if conn:
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
                INSERT INTO strain_names (name_en, name_th, is_popular)
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
                'bud_reference_id': result[10],
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

        cur.execute("""
            SELECT b.id, b.strain_name_en, b.strain_name_th, b.breeder, b.strain_type,
                   b.thc_percentage, b.cbd_percentage, b.grade, b.aroma_flavor,
                   b.top_terpenes_1, b.top_terpenes_2, b.top_terpenes_3,
                   b.mental_effects_positive, b.mental_effects_negative,
                   b.physical_effects_positive, b.physical_effects_negative,
                   b.recommended_time, b.grow_method, b.harvest_date, b.batch_number,
                   b.grower_id, b.grower_license_verified, b.fertilizer_type, 
                   b.flowering_type, b.created_at, b.updated_at,
                   u.username as grower_name, u.is_grower,
                   COALESCE(AVG(r.overall_rating), 0) as avg_rating,
                   COUNT(r.id) as review_count
            FROM buds_data b
            LEFT JOIN users u ON b.grower_id = u.id
            LEFT JOIN reviews r ON b.id = r.bud_reference_id
            GROUP BY b.id, b.strain_name_en, b.strain_name_th, b.breeder, b.strain_type,
                     b.thc_percentage, b.cbd_percentage, b.grade, b.aroma_flavor,
                     b.top_terpenes_1, b.top_terpenes_2, b.top_terpenes_3,
                     b.mental_effects_positive, b.mental_effects_negative,
                     b.physical_effects_positive, b.physical_effects_negative,
                     b.recommended_time, b.grow_method, b.harvest_date, b.batch_number,
                     b.grower_id, b.grower_license_verified, b.fertilizer_type, 
                     b.flowering_type, b.created_at, b.updated_at,
                     u.username, u.is_grower
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
                'created_at': row[24].strftime('%Y-%m-%d %H:%M:%S') if row[24] else None,
                'updated_at': row[25].strftime('%Y-%m-%d %H:%M:%S') if row[25] else None,
                'grower_name': row[26],
                'is_grower': row[27],
                'avg_rating': float(row[28]) if row[28] else 0,
                'review_count': row[29]
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
                       thc_percentage, cbd_percentage, created_at
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
                    'created_at': row[7].strftime('%Y-%m-%d') if row[7] else None
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

@app.route('/api/buds/<int:bud_id>/info')
def get_bud_info(bud_id):
    """Get detailed bud information including grower info"""
    if not is_authenticated():
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT b.id, b.strain_name_en, b.strain_name_th, b.breeder, 
                       b.strain_type, b.thc_percentage, b.cbd_percentage, 
                       b.grade, b.aroma_flavor, b.recommended_time, b.grow_method,
                       b.harvest_date, b.batch_number, b.grower_license_verified,
                       b.fertilizer_type, b.flowering_type, 
                       b.created_at, b.grower_id,
                       u.username as grower_name, u.is_grower
                FROM buds_data b
                LEFT JOIN users u ON b.grower_id = u.id
                WHERE b.id = %s
            """, (bud_id,))

            result = cur.fetchone()
            if not result:
                return jsonify({
                    'success': False,
                    'error': f'ไม่พบข้อมูลดอก ID: {bud_id}'
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
                'recommended_time': result[9],
                'grow_method': result[10],
                'harvest_date': result[11].strftime('%Y-%m-%d') if result[11] else None,
                'batch_number': result[12],
                'grower_license_verified': result[13],
                'fertilizer_type': result[14],
                'flowering_type': result[15],
                'created_at': result[16].strftime('%Y-%m-%d %H:%M:%S') if result[16] else None,
                'grower_id': result[17],
                'grower_name': result[18],
                'is_grower': result[19]
            }

            cur.close()
            return_db_connection(conn)

            return jsonify({
                'success': True,
                'bud': bud_info
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'เกิดข้อผิดพลาดในการตรวจสอบ: {str(e)}'
            }), 500
        finally:
            if cur:
                cur.close()
            if conn:
                return_db_connection(conn)
    else:
        return jsonify({
            'success': False,
            'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'
        }), 500

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

@app.route('/bud-report')
def bud_report_page():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')
    return render_template('bud_report.html')

@app.route('/bud_report/<int:bud_id>')
def bud_report_detail(bud_id):
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect('/auth')
    return render_template('bud_report.html', bud_id=bud_id)

@app.route('/api/buds/<int:bud_id>', methods=['GET'])
def get_bud_detail(bud_id):
    """Get individual bud data for editing"""
    if 'user_id' not in session:
        return jsonify({'error': 'ไม่ได้เข้าสู่ระบบ'}), 401

    user_id = session['user_id']
    cache_key = f"bud_detail_{bud_id}_{user_id}"

    # Check cache first
    cached_data = get_cache(cache_key)
    if cached_data:
        return jsonify(cached_data)

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

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
                   created_at, updated_at, created_by
            FROM buds_data
            WHERE id = %s AND created_by = %s
        """, (bud_id, user_id))

        result = cur.fetchone()
        if not result:
            return jsonify({'error': 'ไม่พบข้อมูลดอกหรือไม่มีสิทธิ์เข้าถึง'}), 404

        bud_data = {
            'id': result[0],
            'strain_name_th': result[1],
            'strain_name_en': result[2],
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
            'image_1_url': result[24],
            'image_2_url': result[25],
            'image_3_url': result[26],
            'image_4_url': result[27],
            'created_at': result[28].strftime('%Y-%m-%d %H:%M:%S') if result[28] else None,
            'updated_at': result[29].strftime('%Y-%m-%d %H:%M:%S') if result[29] else None,
            'created_by': result[30]
        }

        # Cache for 5 minutes
        set_cache(cache_key, bud_data)

        return jsonify(bud_data)

    except psycopg2.OperationalError as e:
        print(f"Database operational error in get_bud_detail: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาดในการเชื่อมต่อฐานข้อมูล'}), 500
    except Exception as e:
        print(f"Error in get_bud_detail: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาดในการโหลดข้อมูล'}), 500
    finally:
        if cur:
            try:
                cur.close()
            except:
                pass
        if conn:
            return_db_connection(conn)

@app.route('/api/upload-images', methods=['POST'])
def upload_images():
    """Upload multiple images for reviews"""
    if 'user_id' not in session:
        return jsonify({'error': 'ไม่ได้เข้าสู่ระบบ'}), 401

    try:
        uploaded_urls = []

        # Process up to 4 images
        for i in range(4):
            file_key = f'image_{i}'
            if file_key in request.files:
                file = request.files[file_key]
                if file and file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                    filename = f"{timestamp}review_{session['user_id']}_{filename}"
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    uploaded_urls.append(f'/uploads/{filename}')

        return jsonify({
            'success': True,
            'message': f'อัปโหลดรูปภาพสำเร็จ ({len(uploaded_urls)} รูป)',
            'image_urls': uploaded_urls
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload_profile_image', methods=['POST'])
def upload_profile_image():
    """Upload profile image"""
    if 'user_id' not in session:
        return jsonify({'error': 'ไม่ได้เข้าสู่ระบบ'}), 401

    user_id = session['user_id']

    if 'profile_image' not in request.files:
        return jsonify({'error': 'ไม่พบไฟล์รูปภาพ'}), 400

    file = request.files['profile_image']

    if file.filename == '':
        return jsonify({'error': 'ไม่ได้เลือกไฟล์'}), 400

    if file and allowed_file(file.filename):
        try:
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            filename = f"{timestamp}profile_{user_id}_{filename}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            # Update database with new profile image URL
            conn = get_db_connection()
            if conn:
                cur = conn.cursor()
                profile_image_url = f'/uploads/{filename}'

                cur.execute("""
                    UPDATE users SET profile_image_url = %s WHERE id = %s
                """, (profile_image_url, user_id))

                conn.commit()

                # Clear cache for this user
                clear_cache_pattern(f"profile_{user_id}")

                cur.close()
                return_db_connection(conn)

                return jsonify({
                    'success': True,
                    'message': 'อัปโหลดรูปโปรไฟล์สำเร็จ',
                    'profile_image_url': profile_image_url
                })
            else:
                return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:
        return jsonify({'error': 'ประเภทไฟล์ไม่ถูกต้อง กรุณาเลือกไฟล์ภาพ'}), 400

@app.route('/users')
def list_users():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, username, email, is_grower, is_budtender, is_consumer, 
                       birth_year, created_at, is_verified, grow_license_file_url, profile_image_url 
                FROM users ORDER BY created_at DESC
            """)
            users = cur.fetchall()

            users_list = []
            for user in users:
                users_list.append({
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
                    'profile_image_url': user[10]
                })

            return jsonify(users_list)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'error': 'Database connection failed'}), 500

@app.route('/register_user', methods=['POST'])
def register_user():
    # Handle license file upload
    license_file_url = None
    if 'grow_license_file' in request.files:
        file = request.files['grow_license_file']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Add timestamp to filename to avoid conflicts
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            filename = timestamp + filename
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            license_file_url = file_path

    # Handle profile image upload
    profile_image_url = None
    if 'profile_image' in request.files:
        file = request.files['profile_image']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Add timestamp to filename to avoid conflicts
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            filename = timestamp + 'profile_' + filename
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            profile_image_url = file_path

    # Get form data
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    birth_year = request.form.get('birth_year')
    is_grower = 'is_grower' in request.form
    is_budtender = 'is_budtender' in request.form
    is_consumer = 'is_consumer' in request.form

    # Simple password hashing (use proper hashing in production)
    password_hash = hashlib.sha256(password.encode()).hexdigest()

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check if username or email already exists
            cur.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
            existing_user = cur.fetchone()

            if existing_user:
                return jsonify({
                    'success': False, 
                    'error': 'ชื่อผู้ใช้หรืออีเมลนี้ถูกใช้ไปแล้ว'
                }), 400

            # Insert user
            cur.execute("""
                INSERT INTO users (username, email, password_hash, is_grower, grow_license_file_url, 
                                 is_budtender, is_consumer, birth_year, profile_image_url, is_verified)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                username, email, password_hash, is_grower, license_file_url,
                is_budtender, is_consumer,
                int(birth_year) if birth_year else None,
                profile_image_url,
                False  # Not verified initially
            ))

            user_id = cur.fetchone()[0]

            # Generate verification token
            token = generate_verification_token()
            expires_at = datetime.now() + timedelta(hours=24)

            cur.execute("""
                INSERT INTO email_verifications (user_id, token, expires_at)
                VALUES (%s, %s, %s)
            """, (user_id, token, expires_at))

            conn.commit()

            # Send verification email
            if send_verification_email(email, username, token):
                return jsonify({
                    'success': True,
                    'message': 'ลงทะเบียนสำเร็จ! กรุณาตรวจสอบอีเมลเพื่อยืนยันการลงทะเบียน',
                    'user_id': user_id
                }), 201
            else:
                return jsonify({
                    'success': True,
                    'message': 'ลงทะเบียนสำเร็จ แต่ไม่สามารถส่งอีเมลยืนยันได้',
                    'user_id': user_id
                }), 201

        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
        finally:
            cur.close()
            return_db_connection(conn)
    else:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500

if __name__ == '__main__':
    # Initialize connection pool
    init_connection_pool()

    # Create tables on startup
    create_tables()
    app.run(host='0.0.0.0', port=3000, debug=True)