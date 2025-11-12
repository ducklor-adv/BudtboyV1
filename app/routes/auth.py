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

    db = get_db()

    # Get logo from settings
    site_logo = '/attached_assets/budtboy_logo_20250907_064050.jpg'  # Default
    signup_method = 'both'  # Default: both email and Google

    try:
        settings = db.execute_query(
            "SELECT key, value FROM admin_settings WHERE key IN (%s, %s)",
            ('siteLogo', 'signupMethod')
        )
        if settings:
            for setting in settings:
                if setting['key'] == 'siteLogo':
                    site_logo = setting['value']
                elif setting['key'] == 'signupMethod':
                    signup_method = setting['value']
    except Exception as e:
        print(f"Error loading settings: {e}")

    return render_template('auth.html', site_logo=site_logo, signup_method=signup_method)


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
        # created_at has DEFAULT CURRENT_TIMESTAMP, so we don't need to pass it
        user_id = db.execute_insert('''
            INSERT INTO users (username, email, password_hash, is_approved, is_verified)
            VALUES (?, ?, ?, ?, ?)
        ''', (username, email, password_hash, False, False))

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


@auth_bp.route('/signin')
def google_signin():
    """Initiate Google OAuth sign-in"""
    from google_auth_oauthlib.flow import Flow
    from flask import current_app

    # Allow OAuth over HTTP for development
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

    # Check for referral code in query parameters
    referral_code = request.args.get('ref')

    # Check if Google OAuth is enabled
    db = get_db()
    try:
        signup_method_result = db.execute_query(
            "SELECT value FROM admin_settings WHERE key = %s",
            ('signupMethod',)
        )
        signup_method = signup_method_result[0]['value'] if signup_method_result else 'both'

        # If email_only mode, don't allow Google OAuth
        if signup_method == 'email_only':
            return jsonify({'error': 'Google OAuth ถูกปิดใช้งาน'}), 403
    except Exception as e:
        print(f"Error checking signup method: {e}")

    # Get Google OAuth credentials from config
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')

    if not client_id or not client_secret:
        return jsonify({'error': 'Google OAuth ยังไม่ได้ตั้งค่า'}), 500

    # Create Flow instance
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [url_for('auth.google_callback', _external=True)]
            }
        },
        scopes=['openid', 'https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/userinfo.profile']
    )

    flow.redirect_uri = url_for('auth.google_callback', _external=True)

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )

    # Store state and referral code in session for CSRF protection
    session['oauth_state'] = state
    if referral_code:
        session['oauth_referral_code'] = referral_code

    print("="*50)
    print("🟢 Google OAuth Sign-in Initiated")
    print(f"Redirect URI: {flow.redirect_uri}")
    print(f"Authorization URL: {authorization_url}")
    print(f"State: {state}")
    print(f"Referral Code: {referral_code}")
    print(f"Session keys: {list(session.keys())}")
    print("="*50)

    return redirect(authorization_url)


@auth_bp.route('/callback')
def google_callback():
    """Handle Google OAuth callback"""
    from google_auth_oauthlib.flow import Flow
    from google.auth.transport import requests as google_requests
    import google.auth.transport.requests

    print("="*50)
    print("🔵 Google OAuth Callback Received")
    print(f"Request URL: {request.url}")
    print(f"Session keys: {list(session.keys())}")
    print("="*50)

    # Allow OAuth over HTTP for development
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

    # Verify state for CSRF protection
    state = session.get('oauth_state')
    print(f"🔍 State from session: {state}")

    if not state:
        print("❌ No state found in session - redirecting to login")
        return redirect(url_for('auth.login_page'))

    # Get Google OAuth credentials from config
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')

    if not client_id or not client_secret:
        return redirect(url_for('auth.login_page'))

    # Create Flow instance
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [url_for('auth.google_callback', _external=True)]
            }
        },
        scopes=['openid', 'https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/userinfo.profile'],
        state=state
    )

    flow.redirect_uri = url_for('auth.google_callback', _external=True)

    try:
        # Fetch token
        flow.fetch_token(authorization_response=request.url)

        # Get credentials
        credentials = flow.credentials

        # Get user info
        import requests as http_requests
        userinfo_response = http_requests.get(
            'https://www.googleapis.com/oauth2/v1/userinfo',
            headers={'Authorization': f'Bearer {credentials.token}'}
        )
        userinfo = userinfo_response.json()

        # Extract user data
        google_id = userinfo.get('id')
        email = userinfo.get('email', '').lower()
        name = userinfo.get('name', '')
        picture = userinfo.get('picture', '')

        if not email or not google_id:
            return redirect(url_for('auth.login_page'))

        db = get_db()

        # Check if user exists with this email
        existing_user = db.execute_query(
            'SELECT * FROM users WHERE email = %s',
            (email,)
        )

        if existing_user:
            # User exists, log them in
            user = dict(existing_user[0])

            # Update google_id if not set
            if not user.get('google_id'):
                db.execute_update(
                    'UPDATE users SET google_id = %s WHERE id = %s',
                    (google_id, user['id'])
                )

            # Set session
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['email'] = user['email']

            return redirect(url_for('main.profile'))
        else:
            # Create new user
            # Generate username from email or name
            username = name.replace(' ', '_').lower() if name else email.split('@')[0]

            # Make sure username is unique
            base_username = username
            counter = 1
            while True:
                check = db.execute_query(
                    'SELECT id FROM users WHERE username = %s',
                    (username,)
                )
                if not check:
                    break
                username = f"{base_username}{counter}"
                counter += 1

            # Check if referral is required for new signups
            signup_method_result = db.execute_query(
                "SELECT value FROM admin_settings WHERE key = %s",
                ('signupMethod',)
            )
            signup_method = signup_method_result[0]['value'] if signup_method_result else 'both'

            # Get referral code from session
            referral_code = session.get('oauth_referral_code')
            referrer_id = None

            # If there's a referral code, validate it
            if referral_code:
                referrer = db.execute_query(
                    'SELECT id FROM users WHERE referral_code = %s',
                    (referral_code,)
                )
                if referrer:
                    referrer_id = referrer[0]['id']
                    print(f"✅ Valid referrer found: {referrer_id}")

            # Insert new user - No password hash for Google OAuth users
            user_id = db.execute_insert('''
                INSERT INTO users (username, email, google_id, is_approved, is_verified, profile_image_url, referred_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (username, email, google_id, False, True, picture, referrer_id))

            # Generate referral code
            ref_code = generate_referral_code(user_id)
            db.execute_update(
                'UPDATE users SET referral_code = %s WHERE id = %s',
                (ref_code, user_id)
            )

            # Clear referral code from session
            if 'oauth_referral_code' in session:
                del session['oauth_referral_code']

            # Set session
            session.permanent = True
            session['user_id'] = user_id
            session['username'] = username
            session['email'] = email

            return redirect(url_for('main.profile'))

    except Exception as e:
        print(f"Google OAuth callback error: {e}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('auth.login_page'))
