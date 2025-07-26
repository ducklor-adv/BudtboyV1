
from flask import Flask, render_template, request, jsonify, url_for, session, redirect
import psycopg2
import os
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
import secrets
import hashlib

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

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Database connection function
def get_db_connection():
    try:
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            raise Exception("DATABASE_URL environment variable not set")
        
        conn = psycopg2.connect(database_url)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

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
            
            # Create strain_names table for autocomplete
            cur.execute("""
                CREATE TABLE IF NOT EXISTS strain_names (
                    id SERIAL PRIMARY KEY,
                    name_th VARCHAR(255),
                    name_en VARCHAR(255) NOT NULL,
                    strain_type VARCHAR(50) CHECK (strain_type IN ('Indica', 'Sativa', 'Hybrid')),
                    is_popular BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Insert sample strain names if table is empty
            cur.execute("SELECT COUNT(*) FROM strain_names")
            count = cur.fetchone()[0]
            
            if count == 0:
                # Complete strain list from file
                comprehensive_strains = [
                    # From the comprehensive strain file - categorized by likely strain type
                    # Popular Indica strains
                    (None, 'Afghan Kush', 'Indica', True),
                    (None, 'Bubba Kush', 'Indica', True),
                    (None, 'Granddaddy Purple', 'Indica', True),
                    (None, 'Northern Lights', 'Indica', True),
                    (None, 'Hindu Kush', 'Indica', True),
                    (None, 'Master Kush', 'Indica', True),
                    (None, 'Purple Kush', 'Indica', True),
                    (None, 'Purple Punch', 'Indica', True),
                    (None, 'Berry White', 'Indica', True),
                    (None, 'Black Domina', 'Indica', False),
                    (None, 'Purple Urkle', 'Indica', False),
                    (None, 'Romulan', 'Indica', False),
                    (None, 'LA Confidential', 'Indica', True),
                    (None, 'Kosher Kush', 'Indica', True),
                    (None, 'Pink Kush', 'Indica', True),
                    (None, 'Big Bud', 'Indica', False),
                    
                    # Popular Sativa strains
                    (None, 'Jack Herer', 'Sativa', True),
                    (None, 'Green Crack', 'Sativa', True),
                    (None, 'Sour Diesel', 'Sativa', True),
                    (None, 'Durban Poison', 'Sativa', True),
                    (None, 'Super Lemon Haze', 'Sativa', True),
                    (None, 'Amnesia Haze', 'Sativa', True),
                    (None, 'Tangerine Dream', 'Sativa', True),
                    (None, 'Maui Waui', 'Sativa', True),
                    (None, 'Strawberry Cough', 'Sativa', True),
                    (None, 'Lamb\'s Bread', 'Sativa', False),
                    (None, 'Acapulco Gold', 'Sativa', False),
                    (None, 'Colombian Gold', 'Sativa', False),
                    (None, 'Haze', 'Sativa', True),
                    (None, 'Super Silver Haze', 'Sativa', True),
                    (None, 'East Coast Sour Diesel', 'Sativa', False),
                    (None, 'Chocolate Thai', 'Sativa', False),
                    
                    # Popular Hybrid strains
                    (None, 'Blue Dream', 'Hybrid', True),
                    (None, 'Girl Scout Cookies', 'Hybrid', True),
                    (None, 'White Widow', 'Hybrid', True),
                    (None, 'Pineapple Express', 'Hybrid', True),
                    (None, 'Wedding Cake', 'Hybrid', True),
                    (None, 'Gelato', 'Hybrid', True),
                    (None, 'Runtz', 'Hybrid', True),
                    (None, 'Do-Si-Dos', 'Hybrid', True),
                    (None, 'AK-47', 'Hybrid', True),
                    (None, 'Skywalker OG', 'Hybrid', True),
                    (None, 'OG Kush', 'Hybrid', True),
                    (None, 'Cherry Pie', 'Hybrid', True),
                    (None, 'Golden Goat', 'Hybrid', True),
                    (None, 'Sunset Sherbet (Sherbert)', 'Hybrid', True),
                    (None, 'Bruce Banner', 'Hybrid', True),
                    (None, 'Original Glue (GG4)', 'Hybrid', True),
                    
                    # Complete list from file (A-Z)
                    (None, 'A-Dub', 'Hybrid', False),
                    (None, 'A-Train', 'Hybrid', False),
                    (None, 'A.M.S.', 'Indica', False),
                    (None, 'AC/DC', 'Hybrid', False),
                    (None, 'AC/DOSI', 'Hybrid', False),
                    (None, 'ACDC Cookies', 'Hybrid', False),
                    (None, 'AJ Sour Diesel', 'Sativa', False),
                    (None, 'AK 1995', 'Hybrid', False),
                    (None, 'AK-48', 'Hybrid', False),
                    (None, 'AK-49', 'Hybrid', False),
                    (None, 'AURORA Indica', 'Indica', False),
                    (None, 'Abula', 'Hybrid', False),
                    (None, 'Abusive OG', 'Indica', False),
                    (None, 'Acai Berry Gelato', 'Hybrid', False),
                    (None, 'Acai Kush', 'Indica', False),
                    (None, 'Acai Mints', 'Hybrid', False),
                    (None, 'Ace of Spades', 'Hybrid', False),
                    (None, 'Aceh', 'Sativa', False),
                    (None, 'Ace\'s High', 'Sativa', False),
                    (None, 'Acid', 'Sativa', False),
                    (None, 'Acid Dough', 'Hybrid', False),
                    (None, 'Acid Kat', 'Hybrid', False),
                    (None, 'Adak OG', 'Indica', False),
                    (None, 'Affie Taffie', 'Indica', False),
                    (None, 'Affogato', 'Hybrid', False),
                    (None, 'Affy Taffy', 'Indica', False),
                    (None, 'Afghan Peach', 'Indica', False),
                    (None, 'Afghan Skunk', 'Indica', False),
                    (None, 'Afghanica', 'Indica', False),
                    (None, 'Afgooey', 'Indica', False),
                    (None, 'Afternoon Delight', 'Hybrid', False),
                    (None, 'Afwreck', 'Hybrid', False),
                    (None, 'Agent Orange', 'Hybrid', False),
                    (None, 'Agent Rose', 'Hybrid', False),
                    (None, 'Agent Tangie', 'Sativa', False),
                    (None, 'Alakazam', 'Hybrid', False),
                    (None, 'Alaskan Ice', 'Sativa', False),
                    (None, 'Alaskan Thunder Fuck', 'Sativa', False),
                    (None, 'Albarino', 'Hybrid', False),
                    (None, 'Albert Walker', 'Indica', False),
                    (None, 'Alien OG', 'Hybrid', False),
                    (None, 'Alien Orange Cookies', 'Hybrid', False),
                    (None, 'Alien Pebbles OG', 'Hybrid', False),
                    (None, 'All Gas', 'Hybrid', False),
                    (None, 'Allen Iverson', 'Hybrid', False),
                    (None, 'Allen Wrench', 'Sativa', False),
                    (None, 'Allkush', 'Indica', False),
                    (None, 'Altoyd', 'Hybrid', False),
                    (None, 'Ambrosia', 'Hybrid', False),
                    (None, 'American Beauty', 'Hybrid', False),
                    (None, 'American Crippler', 'Indica', False),
                    (None, 'Amnesia Kush', 'Sativa', False),
                    (None, 'Amnesia Lemon', 'Sativa', False),
                    (None, 'Amnesia Mint Cookies', 'Hybrid', False),
                    (None, 'Amnesia OG', 'Sativa', False),
                    (None, 'Amsterdam Flame', 'Sativa', False),
                    (None, 'Ancient OG', 'Indica', False),
                    (None, 'Anesthesia', 'Indica', False),
                    (None, 'Angelmatic', 'Hybrid', False),
                    (None, 'Animal Cookies', 'Hybrid', False),
                    (None, 'Animal Crackers', 'Hybrid', False),
                    (None, 'Animal Face', 'Hybrid', False),
                    (None, 'Animal Mint Cookie Walker', 'Hybrid', False),
                    (None, 'Animal Mints', 'Hybrid', False),
                    (None, 'Animal Mints Bx1', 'Hybrid', False),
                    (None, 'Animal OG', 'Hybrid', False),
                    (None, 'Apple Fritter', 'Hybrid', False),
                    (None, 'Apple Jack', 'Hybrid', False),
                    (None, 'Apricot Helix', 'Hybrid', False),
                    (None, 'Apricot Jelly', 'Hybrid', False),
                    (None, 'Aurora Borealis', 'Indica', False),
                    (None, 'Banana Kush', 'Hybrid', False),
                    (None, 'Banana OG', 'Hybrid', False),
                    (None, 'Banana Punch', 'Hybrid', False),
                    (None, 'Beckwourth Bud', 'Hybrid', False),
                    (None, 'Big Smooth', 'Hybrid', False),
                    (None, 'Birthday Cake', 'Hybrid', False),
                    (None, 'Biscotti', 'Hybrid', False),
                    (None, 'Black Afghan', 'Indica', False),
                    (None, 'Black Cherry Soda', 'Hybrid', False),
                    (None, 'Black Jack', 'Sativa', False),
                    (None, 'Black Mamba', 'Indica', False),
                    (None, 'Black Widow', 'Hybrid', False),
                    (None, 'Blackberry', 'Hybrid', False),
                    (None, 'Blackberry Kush', 'Indica', False),
                    (None, 'Blackberry Widow', 'Hybrid', False),
                    (None, 'Blue Cheese', 'Hybrid', False),
                    (None, 'Blue Cookies', 'Hybrid', False),
                    (None, 'Blue Moonshine', 'Indica', False),
                    (None, 'Blue OG', 'Hybrid', False),
                    (None, 'Blue Power', 'Hybrid', False),
                    (None, 'Blue Trainwreck', 'Hybrid', False),
                    (None, 'Blueberry', 'Indica', False),
                    (None, 'Blueberry Kush', 'Indica', False),
                    (None, 'Blueberry Muffin', 'Hybrid', False),
                    (None, 'Bubble Gum', 'Hybrid', False),
                    (None, 'Buddha\'s Hand', 'Hybrid', False),
                    (None, 'Burmese Kush', 'Indica', False),
                    (None, 'California Orange', 'Hybrid', False),
                    (None, 'Candy Cane', 'Hybrid', False),
                    (None, 'Candyland', 'Sativa', False),
                    (None, 'Cannalope Haze', 'Sativa', False),
                    (None, 'Cannatonic', 'Hybrid', False),
                    (None, 'Cereal Milk', 'Hybrid', False),
                    (None, 'Charlotte\'s Web', 'Sativa', False),
                    (None, 'Cheese', 'Hybrid', False),
                    (None, 'Cheesequake', 'Hybrid', False),
                    (None, 'Chem 91', 'Hybrid', False),
                    (None, 'Chemdawg', 'Hybrid', False),
                    (None, 'Chernobyl', 'Hybrid', False),
                    (None, 'Cherry AK-47', 'Hybrid', False),
                    (None, 'Cherry Diesel', 'Hybrid', False),
                    (None, 'Cherry Kush', 'Indica', False),
                    (None, 'Chocolope', 'Sativa', False),
                    (None, 'Chronic', 'Hybrid', False),
                    (None, 'Cinderella 99', 'Sativa', False),
                    (None, 'Cinex', 'Sativa', False),
                    (None, 'Cookies and Cream', 'Hybrid', False),
                    (None, 'Cotton Candy', 'Hybrid', False),
                    (None, 'Critical Jack', 'Sativa', False),
                    (None, 'Critical Kush', 'Indica', False),
                    (None, 'Critical Mass', 'Indica', False),
                    (None, 'Crockett\'s Sour Tangie', 'Sativa', False),
                    (None, 'Crosswalker', 'Hybrid', False),
                    (None, 'Crystal', 'Hybrid', False),
                    (None, 'Death Star', 'Indica', False),
                    (None, 'DelaHaze', 'Sativa', False),
                    (None, 'Diabla', 'Hybrid', False),
                    (None, 'Diamond OG', 'Hybrid', False),
                    (None, 'Double Diesel', 'Sativa', False),
                    (None, 'Double Dream', 'Sativa', False),
                    (None, 'Dr. Grinspoon', 'Sativa', False),
                    (None, 'Dream Queen', 'Sativa', False),
                    (None, 'Durga Mata', 'Indica', False),
                    (None, 'Dutch Hawaiian', 'Sativa', False),
                    (None, 'Dutch Treat', 'Hybrid', False),
                    (None, 'Early Girl', 'Indica', False),
                    (None, 'Early Pearl', 'Sativa', False),
                    (None, 'Elephant', 'Hybrid', False),
                    (None, 'Emerald Jack', 'Sativa', False),
                    (None, 'Euphoria', 'Sativa', False),
                    (None, 'Exodus Cheese', 'Hybrid', False),
                    (None, 'Face Off OG', 'Indica', False),
                    (None, 'Facewreck', 'Hybrid', False),
                    (None, 'Fire OG', 'Hybrid', False),
                    (None, 'Firecracker', 'Hybrid', False),
                    (None, 'Flo', 'Sativa', False),
                    (None, 'Forbidden Cookies', 'Hybrid', False),
                    (None, 'Forbidden Fruit', 'Indica', False),
                    (None, 'Four-Way', 'Indica', False),
                    (None, 'Freezeland', 'Indica', False),
                    (None, 'Frosty', 'Hybrid', False),
                    (None, 'Fruit Punch', 'Hybrid', False),
                    (None, 'Fruity Pebbles OG', 'Hybrid', False),
                    (None, 'Fucking Incredible', 'Indica', False),
                    (None, 'Funky Monkey', 'Hybrid', False),
                    (None, 'Future #1', 'Hybrid', False),
                    (None, 'G13', 'Indica', False),
                    (None, 'GMO Cookies', 'Indica', False),
                    (None, 'Ghost OG', 'Hybrid', False),
                    (None, 'Glueball', 'Hybrid', False),
                    (None, 'God Bud', 'Indica', False),
                    (None, 'God\'s Gift', 'Indica', False),
                    (None, 'Godfather OG', 'Indica', False),
                    (None, 'Golden Calyx', 'Hybrid', False),
                    (None, 'Golden Pineapple', 'Hybrid', False),
                    (None, 'Golden Ticket', 'Hybrid', False),
                    (None, 'Grandma\'s Sugar Cookie', 'Hybrid', False),
                    (None, 'Grape Ape', 'Indica', False),
                    (None, 'Grape God', 'Indica', False),
                    (None, 'Grape Stomper', 'Hybrid', False),
                    (None, 'Grapefruit', 'Sativa', False),
                    (None, 'Grease Monkey', 'Hybrid', False),
                    (None, 'Green Ribbon', 'Hybrid', False),
                    (None, 'Harlequin', 'Sativa', False),
                    (None, 'Hash Plant', 'Indica', False),
                    (None, 'Hashberry', 'Indica', False),
                    (None, 'Hawaiian', 'Sativa', False),
                    (None, 'Head Cheese', 'Hybrid', False),
                    (None, 'Headband', 'Hybrid', False),
                    (None, 'Herijuana', 'Indica', False),
                    (None, 'Hog\'s Breath', 'Indica', False),
                    (None, 'Holy Grail Kush', 'Hybrid', False),
                    (None, 'Ice', 'Indica', False),
                    (None, 'Ice Cream Cake', 'Hybrid', False),
                    (None, 'Illuminati OG', 'Hybrid', False),
                    (None, 'Incredible Hulk', 'Sativa', False),
                    (None, 'Island Kush', 'Hybrid', False),
                    (None, 'Island Sweet Skunk', 'Sativa', False),
                    (None, 'J1', 'Sativa', False),
                    (None, 'Jack Frost', 'Hybrid', False),
                    (None, 'Jack the Ripper', 'Sativa', False),
                    (None, 'Jesus OG', 'Indica', False),
                    (None, 'Jet Fuel', 'Hybrid', False),
                    (None, 'Jillybean', 'Hybrid', False),
                    (None, 'Juicy Fruit', 'Hybrid', False),
                    (None, 'Kali Mist', 'Sativa', False),
                    (None, 'Kandy Kush', 'Hybrid', False),
                    (None, 'Khalifa Kush', 'Hybrid', False),
                    (None, 'Killer Queen', 'Hybrid', False),
                    (None, 'King Tut', 'Sativa', False),
                    (None, 'King\'s Kush', 'Indica', False),
                    (None, 'Kosher Tangie', 'Hybrid', False),
                    (None, 'Kush Mints', 'Hybrid', False),
                    (None, 'Kushberry', 'Indica', False),
                    (None, 'LA Woman', 'Hybrid', False),
                    (None, 'LSD', 'Hybrid', False),
                    (None, 'Larry OG', 'Indica', False),
                    (None, 'Laughing Buddha', 'Sativa', False),
                    (None, 'Lava Cake', 'Indica', False),
                    (None, 'Lavender', 'Indica', False),
                    (None, 'Lemon Cake', 'Hybrid', False),
                    (None, 'Lemon Diesel', 'Hybrid', False),
                    (None, 'Lemon Kush', 'Hybrid', False),
                    (None, 'Lemon OG', 'Hybrid', False),
                    (None, 'Lemon Skunk', 'Hybrid', False),
                    (None, 'Lemon Tree', 'Hybrid', False),
                    (None, 'Lodi Dodi', 'Hybrid', False),
                    (None, 'MAC (Miracle Alien Cookies)', 'Hybrid', False),
                    (None, 'Mango Kush', 'Indica', False),
                    (None, 'Martian Mean Green', 'Sativa', False),
                    (None, 'Mazar', 'Indica', False),
                    (None, 'Mazar-I-Sharif', 'Indica', False),
                    (None, 'Medikit', 'Hybrid', False),
                    (None, 'Mendo Breath', 'Indica', False),
                    (None, 'Mickey Kush', 'Hybrid', False),
                    (None, 'Midnight', 'Indica', False),
                    (None, 'Mimosa', 'Sativa', False),
                    (None, 'Mob Boss', 'Hybrid', False),
                    (None, 'Mochi', 'Hybrid', False),
                    (None, 'Nebula', 'Sativa', False),
                    (None, 'Neville\'s Haze', 'Sativa', False),
                    (None, 'Night Terror OG', 'Indica', False),
                    (None, 'NYC Diesel', 'Sativa', False),
                    (None, 'Obama Kush', 'Indica', False),
                    (None, 'Ogre', 'Indica', False),
                    (None, 'Opium', 'Indica', False),
                    (None, 'Orange Bud', 'Hybrid', False),
                    (None, 'Orange Creamsicle', 'Hybrid', False),
                    (None, 'Orange Kush', 'Hybrid', False),
                    (None, 'Orient Express', 'Hybrid', False),
                    (None, 'Ozma', 'Hybrid', False),
                    (None, 'Pakistan Chitral Kush', 'Indica', False),
                    (None, 'Papaya', 'Indica', False),
                    (None, 'Pennywise', 'Indica', False),
                    (None, 'Pineapple Chunk', 'Hybrid', False),
                    (None, 'Pineapple OG', 'Hybrid', False),
                    (None, 'Platinum OG', 'Indica', False),
                    (None, 'Plushberry', 'Hybrid', False),
                    (None, 'Power Plant', 'Sativa', False),
                    (None, 'Pre-98 Bubba Kush', 'Indica', False),
                    (None, 'Purple Alien OG', 'Hybrid', False),
                    (None, 'Purple Animal Cookies', 'Hybrid', False),
                    (None, 'Purple Apricot', 'Hybrid', False),
                    (None, 'Qrazy Train', 'Hybrid', False),
                    (None, 'Quantum Kush', 'Hybrid', False),
                    (None, 'Queen Mother', 'Sativa', False),
                    (None, 'Querkle', 'Indica', False),
                    (None, 'Raspberry Cough', 'Sativa', False),
                    (None, 'Red Dragon', 'Sativa', False),
                    (None, 'Remedy', 'Indica', False),
                    (None, 'Rene', 'Indica', False),
                    (None, 'Rigger Kush', 'Indica', False),
                    (None, 'Rockstar', 'Indica', False),
                    (None, 'Royal Kush', 'Indica', False),
                    (None, 'SAGE', 'Sativa', False),
                    (None, 'SFV OG', 'Indica', False),
                    (None, 'Segerblom Haze', 'Sativa', False),
                    (None, 'Sensi Star', 'Indica', False),
                    (None, 'Shishkaberry', 'Indica', False),
                    (None, 'Shiva Skunk', 'Indica', False),
                    (None, 'Short and Sweet', 'Indica', False),
                    (None, 'Skunk #1', 'Hybrid', False),
                    (None, 'Slice of Heaven', 'Hybrid', False),
                    (None, 'Slurricane', 'Indica', False),
                    (None, 'Snowcap', 'Sativa', False),
                    (None, 'Somango', 'Indica', False),
                    (None, 'Somaui', 'Hybrid', False),
                    (None, 'Sour Jack', 'Sativa', False),
                    (None, 'Sour Kush', 'Hybrid', False),
                    (None, 'Sour Tsunami', 'Hybrid', False),
                    (None, 'Stardawg', 'Hybrid', False),
                    (None, 'Strawberry Banana', 'Hybrid', False),
                    (None, 'Strawberry Diesel', 'Sativa', False),
                    (None, 'Sundae Driver', 'Hybrid', False),
                    (None, 'Super Skunk', 'Indica', False),
                    (None, 'Superglue', 'Hybrid', False),
                    (None, 'Sweet Nina', 'Indica', False),
                    (None, 'Sweet Tooth', 'Indica', False),
                    (None, 'Tahoe OG', 'Hybrid', False),
                    (None, 'Tangie', 'Sativa', False),
                    (None, 'The Church', 'Hybrid', False),
                    (None, 'The White', 'Hybrid', False),
                    (None, 'Thin Mint GSC', 'Hybrid', False),
                    (None, 'Tiger\'s Milk', 'Indica', False),
                    (None, 'Timewreck', 'Sativa', False),
                    (None, 'Trainwreck', 'Sativa', False),
                    (None, 'Triangle Kush', 'Indica', False),
                    (None, 'Triangle Mints', 'Hybrid', False),
                    (None, 'Tropicana Cookies', 'Hybrid', False),
                    (None, 'True OG', 'Indica', False),
                    (None, 'UK Cheese', 'Hybrid', False),
                    (None, 'Ultra Sour', 'Sativa', False),
                    (None, 'Underdawg OG', 'Hybrid', False),
                    (None, 'Utopia Haze', 'Sativa', False),
                    (None, 'Valentine X', 'Hybrid', False),
                    (None, 'Vanilla Kush', 'Indica', False),
                    (None, 'Venom OG', 'Indica', False),
                    (None, 'Violator Kush', 'Indica', False),
                    (None, 'Vortex', 'Sativa', False),
                    (None, 'Wappa', 'Indica', False),
                    (None, 'Watermelon Kush', 'Indica', False),
                    (None, 'Wedding Crasher', 'Hybrid', False),
                    (None, 'White Buffalo', 'Sativa', False),
                    (None, 'White Empress', 'Hybrid', False),
                    (None, 'White Fire OG (WiFi OG)', 'Hybrid', False),
                    (None, 'White Master', 'Indica', False),
                    (None, 'White Rhino', 'Indica', False),
                    (None, 'White Russian', 'Indica', False),
                    (None, 'White Tahoe Cookies', 'Hybrid', False),
                    (None, 'Williams Wonder', 'Indica', False),
                    (None, 'Willie Nelson', 'Sativa', False),
                    (None, 'XJ-13', 'Sativa', False),
                    (None, 'Xanadu', 'Hybrid', False),
                    (None, 'Y Griega', 'Sativa', False),
                    (None, 'Yoda OG', 'Indica', False),
                    (None, 'Yumboldt', 'Indica', False),
                    
                    # Thai local strains (with Thai translations)
                    ('ไทยสติ๊ก', 'Thai Stick', 'Sativa', True),
                    ('ช้างไทย', 'Thai Elephant', 'Sativa', False),
                    ('กัญชาไทย', 'Thai Cannabis', 'Sativa', False),
                    ('สายพันธุ์เหนือ', 'Northern Thai', 'Sativa', False),
                    ('สายพันธุ์อีสาน', 'Isaan Strain', 'Sativa', False),
                ]
                
                cur.executemany("""
                    INSERT INTO strain_names (name_th, name_en, strain_type, is_popular)
                    VALUES (%s, %s, %s, %s)
                """, comprehensive_strains)
            
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
                    effect VARCHAR(50) CHECK (effect IN ('ผ่อนคลาย', 'สนุกสนาน', 'สงบ', 'เพิ่มจินตนาการ')),
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
            
            # Create index for better performance
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_strain_names_th ON strain_names(name_th);
                CREATE INDEX IF NOT EXISTS idx_strain_names_en ON strain_names(name_en);
                CREATE INDEX IF NOT EXISTS idx_strain_names_popular ON strain_names(is_popular);
                CREATE INDEX IF NOT EXISTS idx_buds_strain_name_th ON buds_data(strain_name_th);
                CREATE INDEX IF NOT EXISTS idx_buds_strain_name_en ON buds_data(strain_name_en);
                CREATE INDEX IF NOT EXISTS idx_buds_strain_type ON buds_data(strain_type);
                CREATE INDEX IF NOT EXISTS idx_buds_grower_id ON buds_data(grower_id);
                CREATE INDEX IF NOT EXISTS idx_buds_effect ON buds_data(effect);
            """)
            
            conn.commit()
            print("Tables created successfully")
        except Exception as e:
            print(f"Error creating tables: {e}")
        finally:
            cur.close()
            conn.close()

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

@app.route('/profile')
def profile():
    # Check if user is logged in, if not redirect to auth page
    if 'user_id' not in session:
        return redirect('/auth')
    return render_template('profile.html')

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
            conn.close()
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
            conn.close()
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
            conn.close()
    else:
        return "ไม่สามารถเชื่อมต่อฐานข้อมูลได้"

@app.route('/api/profile')
def get_profile():
    if 'user_id' not in session:
        return jsonify({'error': 'ไม่ได้เข้าสู่ระบบ'}), 401
    
    user_id = session['user_id']
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
                    'profile_image_url': user[10]
                }
                return jsonify(user_data)
            else:
                return jsonify({'error': 'ไม่พบข้อมูลผู้ใช้'}), 404
                
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            conn.close()
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
            conn.close()
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
                    'effect': bud[12],
                    'recommended_time': bud[13],
                    'grow_method': bud[14],
                    'harvest_date': bud[15].strftime('%Y-%m-%d') if bud[15] else None,
                    'batch_number': bud[16],
                    'grower_id': bud[17],
                    'grower_license_verified': bud[18],
                    'fertilizer_type': bud[19],
                    'flowering_type': bud[20],
                    'image_1_url': bud[21],
                    'image_2_url': bud[22],
                    'image_3_url': bud[23],
                    'image_4_url': bud[24],
                    'created_at': bud[25].strftime('%Y-%m-%d %H:%M:%S') if bud[25] else None,
                    'updated_at': bud[26].strftime('%Y-%m-%d %H:%M:%S') if bud[26] else None,
                    'created_by': bud[27],
                    'grower_name': bud[28]
                })
            
            return jsonify(buds_list)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            conn.close()
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
                    effect, recommended_time, grow_method, harvest_date,
                    batch_number, grower_id, grower_license_verified,
                    fertilizer_type, flowering_type, created_by
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
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
                data.get('effect'),
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
            conn.close()
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
                    top_terpenes_2 = %s, top_terpenes_3 = %s, effect = %s,
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
                data.get('effect'),
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
            conn.close()
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
            conn.close()
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
            conn.close()
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
    strain_type = data.get('strain_type', '').strip()
    is_popular = data.get('is_popular', False)
    
    if not name_en:
        return jsonify({'error': 'กรุณากรอกชื่อภาษาอังกฤษ'}), 400
    
    if strain_type not in ['Indica', 'Sativa', 'Hybrid']:
        return jsonify({'error': 'ประเภทสายพันธุ์ไม่ถูกต้อง'}), 400
    
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
                INSERT INTO strain_names (name_en, name_th, strain_type, is_popular)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (name_en, name_th if name_th else None, strain_type, is_popular))
            
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
            conn.close()
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
                        SELECT name_en, is_popular, strain_type
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
                                'is_popular': row[1],
                                'strain_type': row[2]
                            })
                
                if lang in ['th', 'both']:
                    # Search Thai names with ILIKE for case-insensitive partial matching
                    cur.execute("""
                        SELECT name_th, is_popular, strain_type
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
                                'is_popular': row[1],
                                'strain_type': row[2]
                            })
            else:
                # No query - return popular strains
                if lang in ['en', 'both']:
                    cur.execute("""
                        SELECT name_en, is_popular, strain_type
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
                                'is_popular': row[1],
                                'strain_type': row[2]
                            })
                
                if lang in ['th', 'both']:
                    cur.execute("""
                        SELECT name_th, is_popular, strain_type
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
                                'is_popular': row[1],
                                'strain_type': row[2]
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
            conn.close()
    else:
        return jsonify({'error': 'เชื่อมต่อฐานข้อมูลไม่ได้'}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    from flask import send_from_directory
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

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
            conn.close()
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
            conn.close()
    else:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500

if __name__ == '__main__':
    # Create tables on startup
    create_tables()
    app.run(host='0.0.0.0', port=5000, debug=True)
