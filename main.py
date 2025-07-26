
from flask import Flask, render_template, request, jsonify, url_for
import psycopg2
import os
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
import secrets
import hashlib

app = Flask(__name__)

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
    return render_template('index.html')

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
