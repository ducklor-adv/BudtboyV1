import bcrypt
import secrets
import re
from functools import wraps
from flask import session, redirect, url_for, jsonify


def hash_password(password):
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12))


def verify_password(password, hashed):
    """Verify a password against a hash"""
    if isinstance(hashed, str):
        hashed = hashed.encode('utf-8')
    return bcrypt.checkpw(password.encode('utf-8'), hashed)


def validate_password_strength(password):
    """
    Validate password meets security requirements
    Returns (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "รหัสผ่านต้องมีอย่างน้อย 8 ตัวอักษร"

    if len(password) > 128:
        return False, "รหัสผ่านยาวเกินไป"

    if not re.search(r'[A-Z]', password):
        return False, "รหัสผ่านต้องมีตัวอักษรพิมพ์ใหญ่อย่างน้อย 1 ตัว"

    if not re.search(r'[a-z]', password):
        return False, "รหัสผ่านต้องมีตัวอักษรพิมพ์เล็กอย่างน้อย 1 ตัว"

    if not re.search(r'\d', password):
        return False, "รหัสผ่านต้องมีตัวเลขอย่างน้อย 1 ตัว"

    return True, None


def generate_token(length=32):
    """Generate a secure random token"""
    return secrets.token_urlsafe(length)


def generate_referral_code(user_id):
    """Generate a unique referral code for a user"""
    random_part = secrets.token_urlsafe(6)
    return f"REF{user_id}{random_part}"


def login_required(f):
    """Decorator to require user login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login_page'))
        return f(*args, **kwargs)
    return decorated_function


def api_login_required(f):
    """Decorator to require login for API endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require admin login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('admin.login_page'))
        return f(*args, **kwargs)
    return decorated_function


def api_admin_required(f):
    """Decorator to require admin for API endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return jsonify({'error': 'Admin authentication required'}), 403
        return f(*args, **kwargs)
    return decorated_function
