from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime
from app.utils import (
    hash_password, verify_password, validate_password_strength,
    generate_token, generate_referral_code, validate_email, validate_username
)
from config import config
import os

auth_bp = Blueprint('auth', __name__)


def get_db():
    """Get database instance"""
    from flask import current_app
    return current_app.db


@auth_bp.route('/auth')
def login_page():
    """Login/signup page"""
    if 'user_id' in session:
        return redirect(url_for('main.profile'))
    return render_template('auth.html')


@auth_bp.route('/login', methods=['POST'])
def login():
    """Handle user login"""
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'กรุณากรอกอีเมลและรหัสผ่าน'}), 400

    db = get_db()

    try:
        # Get user by email
        users = db.execute_query(
            'SELECT * FROM users WHERE email = ?',
            (email,)
        )

        if not users:
            return jsonify({'error': 'อีเมลหรือรหัสผ่านไม่ถูกต้อง'}), 401

        user = dict(users[0])

        # Verify password
        if not user['password_hash'] or not verify_password(password, user['password_hash']):
            return jsonify({'error': 'อีเมลหรือรหัสผ่านไม่ถูกต้อง'}), 401

        # Check if user is approved
        if not user.get('is_approved', False):
            return jsonify({'error': 'บัญชีของคุณยังไม่ได้รับการอนุมัติ'}), 403

        # Set session
        session.permanent = True
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['email'] = user['email']

        return jsonify({
            'success': True,
            'message': 'เข้าสู่ระบบสำเร็จ',
            'user': {
                'id': user['id'],
                'username': user['username'],
                'email': user['email']
            }
        })

    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาดในการเข้าสู่ระบบ'}), 500


@auth_bp.route('/signup', methods=['POST'])
def signup():
    """Handle user registration"""
    data = request.get_json()

    username = data.get('username', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    referral_code = data.get('referral_code', '').strip()

    # Validate inputs
    is_valid, error = validate_username(username)
    if not is_valid:
        return jsonify({'error': error}), 400

    is_valid, error = validate_email(email)
    if not is_valid:
        return jsonify({'error': 'อีเมลไม่ถูกต้อง'}), 400

    is_valid, error = validate_password_strength(password)
    if not is_valid:
        return jsonify({'error': error}), 400

    db = get_db()

    try:
        # Check if username exists
        existing = db.execute_query(
            'SELECT id FROM users WHERE username = ?',
            (username,)
        )
        if existing:
            return jsonify({'error': 'ชื่อผู้ใช้นี้ถูกใช้แล้ว'}), 400

        # Check if email exists
        existing = db.execute_query(
            'SELECT id FROM users WHERE email = ?',
            (email,)
        )
        if existing:
            return jsonify({'error': 'อีเมลนี้ถูกใช้แล้ว'}), 400

        # Hash password
        password_hash = hash_password(password).decode('utf-8')

        # Insert new user - Default: not approved, not verified
        user_id = db.execute_insert('''
            INSERT INTO users (username, email, password_hash, is_approved, is_verified, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (username, email, password_hash, False, False, datetime.now()))

        # Generate referral code
        ref_code = generate_referral_code(user_id)
        db.execute_update(
            'UPDATE users SET referral_code = ? WHERE id = ?',
            (ref_code, user_id)
        )

        # Handle referral if provided
        if referral_code:
            referrer = db.execute_query(
                'SELECT id FROM users WHERE referral_code = ?',
                (referral_code,)
            )
            if referrer:
                referrer_id = referrer[0]['id']
                db.execute_update(
                    'UPDATE users SET referred_by = ? WHERE id = ?',
                    (referrer_id, user_id)
                )

        # Set session
        session.permanent = True
        session['user_id'] = user_id
        session['username'] = username
        session['email'] = email

        return jsonify({
            'success': True,
            'message': 'ลงทะเบียนสำเร็จ',
            'user': {
                'id': user_id,
                'username': username,
                'email': email
            }
        })

    except Exception as e:
        print(f"Signup error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาดในการลงทะเบียน'}), 500


@auth_bp.route('/fallback_login', methods=['POST'])
def fallback_login():
    """Handle fallback login (alias for /login)"""
    return login()


@auth_bp.route('/fallback_signup', methods=['POST'])
def fallback_signup():
    """Handle fallback signup (alias for /signup)"""
    return signup()


@auth_bp.route('/logout')
def logout():
    """Handle user logout"""
    session.clear()
    return redirect(url_for('auth.login_page'))


@auth_bp.route('/forgot-password')
def forgot_password_page():
    """Forgot password page"""
    return render_template('forgot_password.html')


@auth_bp.route('/reset-password/<token>')
def reset_password_page(token):
    """Reset password page"""
    return render_template('reset_password.html', token=token)
