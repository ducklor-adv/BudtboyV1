from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime, timedelta
from app.utils import hash_password, verify_password, admin_required
from config import config
import os

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def get_db():
    """Get database instance"""
    from flask import current_app
    return current_app.db


@admin_bp.route('/login', methods=['GET', 'POST'])
def login_page():
    """Admin login page and handler"""
    if request.method == 'GET':
        return render_template('admin_login.html')

    # POST - handle login
    data = request.get_json()
    admin_name = data.get('admin_name', '').strip()
    password = data.get('password', '')

    if not admin_name or not password:
        return jsonify({'error': 'กรุณากรอกชื่อผู้ใช้และรหัสผ่าน'}), 400

    # Check master admin
    master_password = os.environ.get('ADMIN_MASTER_PASSWORD')
    if not master_password:
        return jsonify({'error': 'ระบบไม่พร้อมใช้งาน กรุณาตั้งค่า ADMIN_MASTER_PASSWORD'}), 500

    if admin_name == "admin999" and password == master_password:
        session.permanent = True
        session['admin_logged_in'] = True
        session['admin_name'] = admin_name
        session['admin_id'] = 0  # Master admin
        return jsonify({'success': True, 'message': 'เข้าสู่ระบบสำเร็จ'})

    # Check database admins
    db = get_db()
    try:
        admins = db.execute_query(
            'SELECT * FROM admin_accounts WHERE admin_name = ? AND is_active = 1',
            (admin_name,)
        )

        if not admins:
            return jsonify({'error': 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'}), 401

        admin = dict(admins[0])

        # Check if locked
        if admin.get('locked_until'):
            locked_until = datetime.fromisoformat(admin['locked_until'])
            if datetime.now() < locked_until:
                return jsonify({'error': 'บัญชีถูกล็อก กรุณาลองใหม่ภายหลัง'}), 403

        # Verify password
        if not verify_password(password, admin['password_hash']):
            # Increment login attempts
            attempts = admin.get('login_attempts', 0) + 1
            db.execute_update(
                'UPDATE admin_accounts SET login_attempts = ? WHERE id = ?',
                (attempts, admin['id'])
            )

            # Lock after 5 failed attempts
            if attempts >= 5:
                locked_until = datetime.now() + timedelta(minutes=30)
                db.execute_update(
                    'UPDATE admin_accounts SET locked_until = ? WHERE id = ?',
                    (locked_until, admin['id'])
                )
                return jsonify({'error': 'บัญชีถูกล็อกเนื่องจากพยายามเข้าสู่ระบบหลายครั้ง'}), 403

            return jsonify({'error': 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'}), 401

        # Reset login attempts
        db.execute_update(
            'UPDATE admin_accounts SET login_attempts = 0, last_login = ? WHERE id = ?',
            (datetime.now(), admin['id'])
        )

        # Set session
        session.permanent = True
        session['admin_logged_in'] = True
        session['admin_name'] = admin['admin_name']
        session['admin_id'] = admin['id']

        return jsonify({'success': True, 'message': 'เข้าสู่ระบบสำเร็จ'})

    except Exception as e:
        print(f"Admin login error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาดในการเข้าสู่ระบบ'}), 500


@admin_bp.route('/logout')
def logout():
    """Admin logout"""
    session.clear()
    return redirect(url_for('admin.login_page'))


@admin_bp.route('/')
@admin_required
def dashboard():
    """Admin dashboard"""
    return render_template('admin.html')


@admin_bp.route('/users')
@admin_required
def users():
    """User management page"""
    return render_template('admin_users.html')


@admin_bp.route('/user/<int:user_id>')
@admin_required
def user_detail(user_id):
    """User detail page"""
    return render_template('admin_users.html')


@admin_bp.route('/buds')
@admin_required
def buds():
    """Bud management page"""
    return render_template('admin_buds.html')


@admin_bp.route('/reviews')
@admin_required
def reviews():
    """Review management page"""
    return render_template('admin_reviews.html')


@admin_bp.route('/activities')
@admin_required
def activities():
    """Activity management page"""
    return render_template('admin_activities.html')


@admin_bp.route('/settings')
@admin_required
def settings():
    """Settings page"""
    return render_template('admin_settings.html')


@admin_bp.route('/settings/general')
@admin_required
def settings_general():
    """General settings page"""
    return render_template('admin_settings_general.html')


@admin_bp.route('/settings/security')
@admin_required
def settings_security():
    """Security settings page"""
    return render_template('admin_settings_security.html')


@admin_bp.route('/settings/content')
@admin_required
def settings_content():
    """Content settings page"""
    return render_template('admin_settings_content.html')


@admin_bp.route('/settings/maintenance')
@admin_required
def settings_maintenance():
    """Maintenance settings page"""
    return render_template('admin_settings_maintenance.html')


@admin_bp.route('/settings/users')
@admin_required
def settings_users():
    """User settings page"""
    return render_template('admin_settings_users.html')


@admin_bp.route('/settings/auth-images')
@admin_required
def settings_auth_images():
    """Auth images settings page"""
    return render_template('admin_settings_auth_images.html')
