
from flask import Flask, render_template, request, jsonify
import psycopg2
import os
from datetime import datetime

app = Flask(__name__)

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

# Create users table if it doesn't exist
def create_users_table():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
            print("Users table created successfully")
        except Exception as e:
            print(f"Error creating table: {e}")
        finally:
            cur.close()
            conn.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/users')
def list_users():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, username, email, is_grower, is_budtender, is_consumer, birth_year, created_at FROM users")
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
                    'created_at': user[7].strftime('%Y-%m-%d %H:%M:%S') if user[7] else None
                })
            
            return jsonify(users_list)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            conn.close()
    else:
        return jsonify({'error': 'Database connection failed'}), 500

@app.route('/add_user', methods=['POST'])
def add_user():
    data = request.get_json()
    
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO users (username, email, password_hash, is_grower, grow_license_file_url, 
                                 is_budtender, is_consumer, birth_year)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                data.get('username'),
                data.get('email'),
                data.get('password_hash'),
                data.get('is_grower', False),
                data.get('grow_license_file_url'),
                data.get('is_budtender', False),
                data.get('is_consumer', True),
                data.get('birth_year')
            ))
            
            user_id = cur.fetchone()[0]
            conn.commit()
            
            return jsonify({'message': 'User created successfully', 'user_id': user_id}), 201
        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            conn.close()
    else:
        return jsonify({'error': 'Database connection failed'}), 500

if __name__ == '__main__':
    # Create table on startup
    create_users_table()
    app.run(host='0.0.0.0', port=5000, debug=True)
