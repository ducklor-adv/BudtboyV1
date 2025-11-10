"""
API Routes Blueprint
This file contains API endpoints for the application
"""
from flask import Blueprint, request, jsonify, session, send_from_directory, current_app
from werkzeug.utils import secure_filename
from datetime import datetime
from app.utils import (
    api_login_required, api_admin_required,
    allowed_file, generate_unique_filename,
    dict_from_row, dicts_from_rows
)
import os

api_bp = Blueprint('api', __name__, url_prefix='/api')


def get_db():
    """Get database instance"""
    return current_app.db


def get_cache():
    """Get cache manager instance"""
    return current_app.cache


# ==================== Profile API ====================

@api_bp.route('/profile', methods=['GET'])
@api_login_required
def get_profile():
    """Get user profile"""
    user_id = session.get('user_id')
    db = get_db()

    try:
        users = db.execute_query(
            'SELECT * FROM users WHERE id = ?',
            (user_id,)
        )

        if not users:
            return jsonify({'error': 'ไม่พบผู้ใช้'}), 404

        user = dict(users[0])
        # Remove sensitive data
        user.pop('password_hash', None)

        return jsonify({'success': True, 'user': user})

    except Exception as e:
        print(f"Get profile error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500


@api_bp.route('/profile', methods=['PUT'])
@api_login_required
def update_profile():
    """Update user profile"""
    user_id = session.get('user_id')
    data = request.get_json()

    db = get_db()
    cache = get_cache()

    try:
        # Build update query dynamically based on provided fields
        allowed_fields = [
            'username', 'birth_year', 'is_grower', 'is_budtender', 'is_consumer',
            'facebook_id', 'line_id', 'instagram_id', 'twitter_id', 'telegram_id', 'phone_number'
        ]

        update_fields = []
        update_values = []

        for field in allowed_fields:
            if field in data:
                update_fields.append(f"{field} = ?")
                update_values.append(data[field])

        if not update_fields:
            return jsonify({'error': 'ไม่มีข้อมูลที่ต้องอัพเดท'}), 400

        # Add user_id to values
        update_values.append(user_id)

        query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = ?"
        db.execute_update(query, tuple(update_values))

        # Clear cache
        cache.clear_pattern(f'profile_{user_id}')

        return jsonify({'success': True, 'message': 'อัพเดทโปรไฟล์สำเร็จ'})

    except Exception as e:
        print(f"Update profile error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาดในการอัพเดท'}), 500


@api_bp.route('/profile/image', methods=['POST'])
@api_login_required
def upload_profile_image():
    """Upload profile image"""
    user_id = session.get('user_id')

    if 'image' not in request.files:
        return jsonify({'error': 'ไม่พบไฟล์รูปภาพ'}), 400

    file = request.files['image']

    if file.filename == '':
        return jsonify({'error': 'ไม่ได้เลือกไฟล์'}), 400

    if not allowed_file(file.filename, current_app.config['ALLOWED_EXTENSIONS']):
        return jsonify({'error': 'ประเภทไฟล์ไม่ถูกต้อง'}), 400

    # Validate file size
    from app.utils.validators import validate_file_size
    is_valid, error_msg = validate_file_size(file, max_size_mb=16)
    if not is_valid:
        return jsonify({'error': error_msg}), 400

    try:
        # Generate unique filename
        filename = generate_unique_filename(file.filename)
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)

        # Save file
        file.save(filepath)

        # Update database with full path
        db = get_db()
        profile_image_url = f'/uploads/{filename}'
        db.execute_update(
            'UPDATE users SET profile_image_url = ? WHERE id = ?',
            (profile_image_url, user_id)
        )

        # Clear cache
        cache = get_cache()
        cache.clear_pattern(f'profile_{user_id}')

        return jsonify({
            'success': True,
            'message': 'อัพโหลดรูปภาพสำเร็จ',
            'profile_image_url': f'/uploads/{filename}'
        })

    except Exception as e:
        print(f"Upload image error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาดในการอัพโหลด'}), 500


# ==================== Buds API ====================

@api_bp.route('/buds', methods=['GET'])
@api_login_required
def get_buds():
    """Get list of buds with optional filters"""
    user_id = session.get('user_id')
    grower_id = request.args.get('grower_id')
    status = request.args.get('status')

    db = get_db()

    try:
        query = 'SELECT * FROM buds_data WHERE 1=1'
        params = []

        if grower_id:
            query += ' AND grower_id = ?'
            params.append(grower_id)
        else:
            # Default: show user's own buds
            query += ' AND grower_id = ?'
            params.append(user_id)

        if status:
            query += ' AND status = ?'
            params.append(status)

        query += ' ORDER BY created_at DESC'

        buds = db.execute_query(query, tuple(params) if params else None)
        buds_list = dicts_from_rows(buds)

        return jsonify({'success': True, 'buds': buds_list})

    except Exception as e:
        print(f"Get buds error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500


@api_bp.route('/buds/<int:bud_id>', methods=['GET', 'PUT'])
@api_login_required
def handle_bud_detail(bud_id):
    """Get or update bud details"""
    db = get_db()

    if request.method == 'GET':
        try:
            buds = db.execute_query(
                'SELECT * FROM buds_data WHERE id = ?',
                (bud_id,)
            )

            if not buds:
                return jsonify({'error': 'ไม่พบข้อมูล'}), 404

            bud = dict(buds[0])
            # Return bud data directly for edit form compatibility
            return jsonify(bud)

        except Exception as e:
            print(f"Get bud detail error: {e}")
            return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500

    elif request.method == 'PUT':
        # Update bud
        user_id = session.get('user_id')

        try:
            # Check if bud exists and belongs to user
            buds = db.execute_query(
                'SELECT grower_id FROM buds_data WHERE id = ?',
                (bud_id,)
            )

            if not buds:
                return jsonify({'error': 'ไม่พบข้อมูลดอก'}), 404

            if buds[0]['grower_id'] != user_id:
                return jsonify({'error': 'คุณไม่มีสิทธิ์แก้ไขดอกนี้'}), 403

            data = request.get_json()

            # Build update query dynamically based on provided fields
            update_fields = []
            params = []

            # List of allowed fields to update
            allowed_fields = [
                'strain_name_en', 'strain_name_th', 'breeder', 'strain_type',
                'thc_percentage', 'cbd_percentage', 'grade', 'harvest_date',
                'flowering_time', 'plant_height', 'yield_amount', 'grow_difficulty',
                'climate_type',
                # Terpenes
                'top_terpenes_1', 'top_terpenes_1_percentage',
                'top_terpenes_2', 'top_terpenes_2_percentage',
                'top_terpenes_3', 'top_terpenes_3_percentage',
                # Aroma and effects
                'aroma_flavor',
                'mental_effects_positive', 'mental_effects_negative',
                'physical_effects_positive', 'physical_effects_negative',
                'recommended_time',
                # Growing information
                'grow_method', 'batch_number', 'fertilizer_type', 'flowering_type',
                'effect', 'medical_use', 'grow_location',
                'light_type', 'nutrients', 'training_method', 'description',
                'youtube_url', 'status',
                # Lab test information
                'lab_test_name', 'test_type',
                # Image URLs
                'image_1_url', 'image_2_url', 'image_3_url', 'image_4_url',
                # Certificate image URLs
                'certificate_image_1_url', 'certificate_image_2_url',
                'certificate_image_3_url', 'certificate_image_4_url'
            ]

            for field in allowed_fields:
                if field in data:
                    value = data[field]
                    # Skip empty strings and None values for fields with CHECK constraints
                    if value == '' or value is None:
                        continue
                    update_fields.append(f"{field} = ?")
                    params.append(value)

            if not update_fields:
                return jsonify({'error': 'ไม่มีข้อมูลที่ต้องอัปเดต'}), 400

            # Add bud_id to params
            params.append(bud_id)

            # Execute update
            query = f"UPDATE buds_data SET {', '.join(update_fields)} WHERE id = ?"
            db.execute_update(query, tuple(params))

            return jsonify({
                'success': True,
                'message': 'อัปเดตข้อมูลสำเร็จ'
            })

        except Exception as e:
            import traceback
            print(f"Update bud error: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            return jsonify({'error': f'เกิดข้อผิดพลาดในการอัปเดต: {str(e)}'}), 500


@api_bp.route('/buds/<int:bud_id>/upload-images', methods=['POST'])
@api_login_required
def upload_bud_images(bud_id):
    """Upload bud images (including certificate images)"""
    user_id = session.get('user_id')
    db = get_db()

    try:
        # Check if bud exists and belongs to user
        buds = db.execute_query('SELECT grower_id FROM buds_data WHERE id = ?', (bud_id,))
        if not buds:
            return jsonify({'error': 'ไม่พบข้อมูลดอก'}), 404
        if buds[0]['grower_id'] != user_id:
            return jsonify({'error': 'คุณไม่มีสิทธิ์แก้ไขดอกนี้'}), 403

        uploaded_images = {}
        update_fields = []
        params = []

        # Process bud images (image_1 to image_4)
        from app.utils.validators import validate_file_size
        for i in range(1, 5):
            field_name = f'image_{i}'
            if field_name in request.files:
                file = request.files[field_name]
                if file and file.filename != '':
                    if not allowed_file(file.filename, current_app.config['ALLOWED_EXTENSIONS']):
                        return jsonify({'error': f'ประเภทไฟล์รูปที่ {i} ไม่ถูกต้อง'}), 400

                    # Validate file size
                    is_valid, error_msg = validate_file_size(file, max_size_mb=16)
                    if not is_valid:
                        return jsonify({'error': f'รูปที่ {i}: {error_msg}'}), 400

                    # Generate unique filename and save
                    filename = generate_unique_filename(file.filename)
                    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)

                    # Store URL for update
                    image_url = f'/uploads/{filename}'
                    uploaded_images[f'image_{i}_url'] = image_url
                    update_fields.append(f'image_{i}_url = ?')
                    params.append(image_url)

        # Process certificate images (certificate_image_1 to certificate_image_4)
        for i in range(1, 5):
            field_name = f'certificate_image_{i}'
            if field_name in request.files:
                file = request.files[field_name]
                if file and file.filename != '':
                    if not allowed_file(file.filename, current_app.config['ALLOWED_EXTENSIONS']):
                        return jsonify({'error': f'ประเภทไฟล์ใบรับรองที่ {i} ไม่ถูกต้อง'}), 400

                    # Validate file size
                    is_valid, error_msg = validate_file_size(file, max_size_mb=16)
                    if not is_valid:
                        return jsonify({'error': f'ใบรับรองที่ {i}: {error_msg}'}), 400

                    # Generate unique filename and save
                    filename = generate_unique_filename(file.filename)
                    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)

                    # Store URL for update
                    image_url = f'/uploads/{filename}'
                    uploaded_images[f'certificate_image_{i}_url'] = image_url
                    update_fields.append(f'certificate_image_{i}_url = ?')
                    params.append(image_url)

        # Update database if any images were uploaded
        if update_fields:
            params.append(bud_id)
            query = f"UPDATE buds_data SET {', '.join(update_fields)} WHERE id = ?"
            db.execute_update(query, tuple(params))

            return jsonify({
                'success': True,
                'message': f'อัพโหลดรูปภาพสำเร็จ ({len(uploaded_images)} รูป)',
                'uploaded_images': uploaded_images
            })
        else:
            return jsonify({
                'success': True,
                'message': 'ไม่มีรูปภาพใหม่ที่ต้องอัพโหลด'
            })

    except Exception as e:
        import traceback
        print(f"Upload bud images error: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': f'เกิดข้อผิดพลาดในการอัพโหลดรูปภาพ: {str(e)}'}), 500


@api_bp.route('/buds/<int:bud_id>/info', methods=['GET'])
@api_login_required
def get_bud_info(bud_id):
    """Get bud full information including reviews and ratings"""
    db = get_db()

    try:
        # Get bud details with creator info
        buds = db.execute_query('''
            SELECT
                b.*,
                u.username as grower_name,
                u.profile_image_url as grower_profile_image
            FROM buds_data b
            LEFT JOIN users u ON b.created_by = u.id
            WHERE b.id = ?
        ''', (bud_id,))

        if not buds:
            return jsonify({'error': 'ไม่พบข้อมูล'}), 404

        bud = dict(buds[0])

        # Get reviews for this bud
        reviews = db.execute_query('''
            SELECT r.*, u.username as reviewer_name, u.profile_image_url as reviewer_image
            FROM reviews r
            LEFT JOIN users u ON r.reviewer_id = u.id
            WHERE r.bud_reference_id = ?
            ORDER BY r.created_at DESC
        ''', (bud_id,))

        reviews_list = dicts_from_rows(reviews) if reviews else []

        # Calculate average rating
        if reviews_list:
            # Filter reviews that have overall_rating
            rated_reviews = [r for r in reviews_list if r.get('overall_rating') is not None]
            if rated_reviews:
                total_rating = sum(r['overall_rating'] for r in rated_reviews)
                avg_rating = total_rating / len(rated_reviews)
            else:
                avg_rating = 0
        else:
            avg_rating = 0

        return jsonify({
            'success': True,
            'bud': bud,
            'reviews': reviews_list,
            'avg_rating': avg_rating,
            'review_count': len(reviews_list)
        })

    except Exception as e:
        print(f"Get bud info error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500


@api_bp.route('/buds', methods=['POST'])
@api_login_required
def create_bud():
    """Create new bud"""
    user_id = session.get('user_id')
    data = request.get_json()

    db = get_db()

    try:
        # Insert bud
        bud_id = db.execute_insert('''
            INSERT INTO buds_data (
                strain_name_th, strain_name_en, breeder, strain_type,
                thc_percentage, cbd_percentage, grade, aroma_flavor,
                grower_id, status, created_at, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('strain_name_th'),
            data.get('strain_name_en'),
            data.get('breeder'),
            data.get('strain_type'),
            data.get('thc_percentage'),
            data.get('cbd_percentage'),
            data.get('grade'),
            data.get('aroma_flavor'),
            user_id,
            'available',
            datetime.now(),
            user_id
        ))

        return jsonify({
            'success': True,
            'message': 'เพิ่มข้อมูลสำเร็จ',
            'bud_id': bud_id
        })

    except Exception as e:
        print(f"Create bud error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500


@api_bp.route('/buds/<int:bud_id>', methods=['DELETE'])
@api_login_required
def delete_bud(bud_id):
    """Delete bud"""
    user_id = session.get('user_id')
    db = get_db()

    try:
        # Check ownership
        buds = db.execute_query(
            'SELECT grower_id FROM buds_data WHERE id = ?',
            (bud_id,)
        )

        if not buds:
            return jsonify({'error': 'ไม่พบข้อมูล'}), 404

        bud = dict(buds[0])
        if bud['grower_id'] != user_id:
            return jsonify({'error': 'คุณไม่มีสิทธิ์ลบข้อมูลนี้'}), 403

        # Delete
        db.execute_update('DELETE FROM buds_data WHERE id = ?', (bud_id,))

        return jsonify({'success': True, 'message': 'ลบข้อมูลสำเร็จ'})

    except Exception as e:
        print(f"Delete bud error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500


@api_bp.route('/buds/<int:bud_id>/status', methods=['PUT'])
@api_login_required
def update_bud_status(bud_id):
    """Update bud status (available/sold_out)"""
    user_id = session.get('user_id')
    db = get_db()

    try:
        data = request.get_json()
        new_status = data.get('status')

        # Validate status
        if new_status not in ['available', 'sold_out']:
            return jsonify({'error': 'สถานะไม่ถูกต้อง'}), 400

        # Check if bud exists and belongs to user
        bud = db.execute_query(
            'SELECT id, grower_id, status FROM buds_data WHERE id = ?',
            (bud_id,)
        )

        if not bud:
            return jsonify({'error': 'ไม่พบข้อมูลดอก'}), 404

        if bud[0]['grower_id'] != user_id:
            return jsonify({'error': 'คุณไม่มีสิทธิ์แก้ไขดอกนี้'}), 403

        # Update status
        db.execute_update(
            'UPDATE buds_data SET status = ? WHERE id = ?',
            (new_status, bud_id)
        )

        status_text = 'ยังเหลือ' if new_status == 'available' else 'หมดแล้ว'

        return jsonify({
            'success': True,
            'message': f'เปลี่ยนสถานะเป็น "{status_text}" เรียบร้อยแล้ว',
            'status': new_status
        })

    except Exception as e:
        print(f"Update bud status error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาดในการอัปเดตสถานะ'}), 500


@api_bp.route('/user_buds', methods=['GET'])
@api_login_required
def get_user_buds():
    """Get current user's buds with review stats"""
    user_id = session.get('user_id')
    db = get_db()

    try:
        # Try with grower_id first
        try:
            buds = db.execute_query('''
                SELECT
                    b.*,
                    COALESCE(AVG(r.overall_rating), 0) as avg_rating,
                    COUNT(r.id) as review_count
                FROM buds_data b
                LEFT JOIN reviews r ON b.id = r.bud_reference_id
                WHERE b.grower_id = ?
                GROUP BY b.id
                ORDER BY b.created_at DESC
            ''', (user_id,))
        except:
            # Fallback to user_id if grower_id doesn't exist
            buds = db.execute_query('''
                SELECT
                    b.*,
                    COALESCE(AVG(r.overall_rating), 0) as avg_rating,
                    COUNT(r.id) as review_count
                FROM buds_data b
                LEFT JOIN reviews r ON b.id = r.bud_reference_id
                WHERE b.user_id = ?
                GROUP BY b.id
                ORDER BY b.created_at DESC
            ''', (user_id,))

        buds_list = dicts_from_rows(buds) if buds else []
        return jsonify({'buds': buds_list})

    except Exception as e:
        print(f"Get user buds error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'เกิดข้อผิดพลาด', 'buds': []}), 500


# ==================== Reviews API ====================

@api_bp.route('/reviews', methods=['GET'])
@api_login_required
def get_reviews():
    """Get reviews"""
    bud_id = request.args.get('bud_id')
    reviewer_id = request.args.get('reviewer_id', session.get('user_id'))

    db = get_db()

    try:
        query = '''
            SELECT r.*, u.username as reviewer_name, u.profile_image_url as reviewer_image
            FROM reviews r
            LEFT JOIN users u ON r.reviewer_id = u.id
            WHERE 1=1
        '''
        params = []

        if bud_id:
            query += ' AND r.bud_reference_id = ?'
            params.append(bud_id)

        if reviewer_id:
            query += ' AND r.reviewer_id = ?'
            params.append(reviewer_id)

        query += ' ORDER BY r.created_at DESC'

        reviews = db.execute_query(query, tuple(params) if params else None)
        reviews_list = dicts_from_rows(reviews)

        return jsonify({'success': True, 'reviews': reviews_list})

    except Exception as e:
        print(f"Get reviews error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500


@api_bp.route('/reviews', methods=['POST'])
@api_login_required
def create_review():
    """Create a new review"""
    data = request.get_json()
    user_id = session.get('user_id')
    db = get_db()

    try:
        # Validate required fields
        required_fields = ['bud_reference_id', 'overall_rating']
        for field in required_fields:
            if field not in data or data[field] is None:
                return jsonify({'error': f'กรุณากรอก {field}'}), 400

        # Extract review data
        bud_reference_id = data.get('bud_reference_id')
        overall_rating = data.get('overall_rating')
        aroma_flavors = data.get('aroma_flavors')
        mental_effects = data.get('mental_effects', [])
        physical_effects = data.get('physical_effects', [])
        full_review_content = data.get('full_review_content')
        review_images_list = data.get('review_images', [])
        video_review_url = data.get('video_review_url')

        # Get aroma_rating from category_ratings if available
        category_ratings = data.get('category_ratings', {})
        aroma_rating = category_ratings.get('aroma')

        # Convert arrays to comma-separated strings
        aroma_flavors_str = ', '.join(aroma_flavors) if aroma_flavors else None

        # Combine mental and physical effects into selected_effects
        all_effects = []
        if mental_effects:
            all_effects.extend(mental_effects)
        if physical_effects:
            all_effects.extend(physical_effects)
        selected_effects_str = ', '.join(all_effects) if all_effects else None

        # Convert review_images array to comma-separated string
        review_images_str = ', '.join(review_images_list) if review_images_list else None

        # Insert review
        review_id = db.execute_insert('''
            INSERT INTO reviews (
                bud_reference_id, reviewer_id, overall_rating,
                aroma_flavors, selected_effects, aroma_rating,
                full_review_content, review_images, video_review_url,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        ''', (
            bud_reference_id, user_id, overall_rating,
            aroma_flavors_str, selected_effects_str, aroma_rating,
            full_review_content, review_images_str, video_review_url
        ))

        return jsonify({
            'success': True,
            'message': 'บันทึกรีวิวสำเร็จ',
            'review_id': review_id
        })

    except Exception as e:
        print(f"Create review error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'เกิดข้อผิดพลาดในการบันทึก'}), 500


@api_bp.route('/user_reviews', methods=['GET'])
@api_login_required
def get_user_reviews():
    """Get current user's reviews"""
    user_id = session.get('user_id')
    db = get_db()

    try:
        reviews = db.execute_query('''
            SELECT
                r.*,
                u.username as reviewer_name,
                u.profile_image_url as reviewer_profile_image,
                b.strain_name_th,
                b.strain_name_en
            FROM reviews r
            LEFT JOIN users u ON r.reviewer_id = u.id
            LEFT JOIN buds_data b ON r.bud_reference_id = b.id
            WHERE r.reviewer_id = ?
            ORDER BY r.created_at DESC
        ''', (user_id,))

        reviews_list = dicts_from_rows(reviews) if reviews else []
        return jsonify({'reviews': reviews_list})

    except Exception as e:
        print(f"Get user reviews error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาด', 'reviews': []}), 500


@api_bp.route('/referrer_info/<referral_code>', methods=['GET'])
def get_referrer_info(referral_code):
    """Get referrer information from referral code"""
    db = get_db()

    try:
        # Get user by referral code with profile image
        user = db.execute_query(
            'SELECT username, profile_image_url FROM users WHERE referral_code = ?',
            (referral_code,)
        )

        if user:
            return jsonify({
                'success': True,
                'username': user[0]['username'],
                'profile_image_url': user[0]['profile_image_url']
            })
        else:
            return jsonify({
                'success': False,
                'error': 'ไม่พบรหัสแนะนำ'
            }), 404

    except Exception as e:
        print(f"Get referrer info error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500


@api_bp.route('/friends_reviews', methods=['GET'])
@api_login_required
def get_friends_reviews():
    """Get reviews from user's friends"""
    user_id = session.get('user_id')
    db = get_db()

    try:
        # Get list of accepted friends
        friends_rows = db.execute_query('''
            SELECT
                CASE
                    WHEN user_id = ? THEN friend_id
                    ELSE user_id
                END as friend_user_id
            FROM friends
            WHERE (user_id = ? OR friend_id = ?)
              AND status = 'accepted'
        ''', (user_id, user_id, user_id))

        if not friends_rows:
            return jsonify({'reviews': []})

        # Extract friend user IDs
        friend_ids = [row['friend_user_id'] for row in friends_rows]

        # Get reviews from these friends with JOIN to get reviewer info and bud info
        placeholders = ','.join('?' * len(friend_ids))
        reviews = db.execute_query(f'''
            SELECT
                r.*,
                u.username as reviewer_name,
                u.profile_image_url as reviewer_profile_image,
                b.strain_name_th,
                b.strain_name_en
            FROM reviews r
            LEFT JOIN users u ON r.reviewer_id = u.id
            LEFT JOIN buds_data b ON r.bud_reference_id = b.id
            WHERE r.reviewer_id IN ({placeholders})
            ORDER BY r.created_at DESC
        ''', tuple(friend_ids))

        reviews_list = dicts_from_rows(reviews) if reviews else []
        return jsonify({'reviews': reviews_list})

    except Exception as e:
        print(f"Get friends reviews error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาด', 'reviews': []}), 500


@api_bp.route('/activities', methods=['GET'])
@api_login_required
def get_activities():
    """Get activities list"""
    db = get_db()
    user_id = session.get('user_id')

    try:
        # Get all activities with participant count and user join status
        activities = db.execute_query('''
            SELECT
                a.*,
                COUNT(DISTINCT ap.user_id) as participant_count,
                MAX(CASE WHEN ap.user_id = ? THEN 1 ELSE 0 END) as user_joined
            FROM activities a
            LEFT JOIN activity_participants ap ON a.id = ap.activity_id
            GROUP BY a.id
            ORDER BY a.created_at DESC
        ''', (user_id,))

        if not activities:
            return jsonify({'success': True, 'activities': []})

        activities_list = dicts_from_rows(activities)
        return jsonify({'success': True, 'activities': activities_list})

    except Exception as e:
        print(f"Get activities error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/pending_friends_count', methods=['GET'])
@api_login_required
def get_pending_friends_count():
    """Get count of pending friend requests"""
    user_id = session.get('user_id')
    db = get_db()

    try:
        pending = db.execute_query('''
            SELECT COUNT(*) as count
            FROM friends
            WHERE friend_id = ? AND status = 'pending'
        ''', (user_id,))

        count = pending[0]['count'] if pending else 0
        return jsonify({'success': True, 'count': count})

    except Exception as e:
        print(f"Get pending friends count error: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/friends', methods=['GET'])
@api_login_required
def get_friends():
    """Get users who signed up via your referral code"""
    user_id = session.get('user_id')
    db = get_db()

    try:
        # Get users who were referred by the current user
        referred_users = db.execute_query('''
            SELECT id, username, profile_image_url, referrer_approved, is_approved, created_at
            FROM users
            WHERE referred_by = ?
            ORDER BY created_at DESC
        ''', (user_id,))

        friends_list = []
        if referred_users:
            for user in referred_users:
                friends_list.append({
                    'id': user['id'],
                    'username': user['username'],
                    'profile_image_url': user['profile_image_url'],
                    'referrer_approved': bool(user['referrer_approved']),
                    'is_approved': bool(user['is_approved']),
                    'created_at': user['created_at']
                })

        # Get current user's referral code
        current_user = db.execute_query('SELECT referral_code FROM users WHERE id = ?', (user_id,))
        referral_code = current_user[0]['referral_code'] if current_user and current_user[0]['referral_code'] else ''

        return jsonify({
            'success': True,
            'friends': friends_list,
            'referral_code': referral_code
        })

    except Exception as e:
        print(f"Get friends error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/approve_referral', methods=['POST'])
@api_login_required
def approve_referral():
    """Approve a user who was referred by you"""
    user_id = session.get('user_id')
    db = get_db()

    try:
        data = request.get_json()
        referred_user_id = data.get('user_id')

        if not referred_user_id:
            return jsonify({'error': 'ไม่พบ user_id'}), 400

        # Check if the user was actually referred by the current user
        referred_user = db.execute_query('''
            SELECT id, username, referred_by, referrer_approved
            FROM users
            WHERE id = ? AND referred_by = ?
        ''', (referred_user_id, user_id))

        if not referred_user:
            return jsonify({'error': 'ไม่พบผู้ใช้หรือคุณไม่ใช่ผู้แนะนำ'}), 403

        if referred_user[0]['referrer_approved']:
            return jsonify({'error': 'ผู้ใช้นี้ได้รับการอนุมัติแล้ว'}), 400

        # Approve the user
        from datetime import datetime
        db.execute_update('''
            UPDATE users
            SET referrer_approved = 1, referrer_approved_at = ?
            WHERE id = ?
        ''', (datetime.now(), referred_user_id))

        return jsonify({
            'success': True,
            'message': f'อนุมัติ {referred_user[0]["username"]} เรียบร้อยแล้ว'
        })

    except Exception as e:
        print(f"Approve referral error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ==================== Admin API ====================

@api_bp.route('/admin/stats', methods=['GET'])
@api_admin_required
def get_admin_stats():
    """Get admin statistics"""
    db = get_db()

    try:
        # Count users
        users_result = db.execute_query('SELECT COUNT(*) as count FROM users')
        total_users = users_result[0]['count'] if users_result else 0

        # Count buds
        buds_result = db.execute_query('SELECT COUNT(*) as count FROM buds_data')
        total_buds = buds_result[0]['count'] if buds_result else 0

        # Count reviews
        reviews_result = db.execute_query('SELECT COUNT(*) as count FROM reviews')
        total_reviews = reviews_result[0]['count'] if reviews_result else 0

        # Count activities
        activities_result = db.execute_query('SELECT COUNT(*) as count FROM activities')
        total_activities = activities_result[0]['count'] if activities_result else 0

        # Count pending users
        pending_result = db.execute_query('SELECT COUNT(*) as count FROM users WHERE is_approved = 0')
        pending_users = pending_result[0]['count'] if pending_result else 0

        return jsonify({
            'success': True,
            'stats': {
                'total_users': total_users,
                'total_buds': total_buds,
                'total_reviews': total_reviews,
                'total_activities': total_activities,
                'pending_users': pending_users
            }
        })

    except Exception as e:
        print(f"Get admin stats error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500


@api_bp.route('/admin/pending_users', methods=['GET'])
@api_admin_required
def get_pending_users():
    """Get list of pending users"""
    db = get_db()

    try:
        users = db.execute_query('''
            SELECT id, username, email, created_at
            FROM users
            WHERE is_approved = 0
            ORDER BY created_at DESC
        ''')

        users_list = dicts_from_rows(users)

        return jsonify({
            'success': True,
            'users': users_list
        })

    except Exception as e:
        print(f"Get pending users error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500


@api_bp.route('/admin/users', methods=['GET'])
@api_admin_required
def get_all_users():
    """Get all users"""
    db = get_db()

    try:
        users = db.execute_query('''
            SELECT id, username, email, referrer_approved, is_approved, is_verified,
                   referred_by, referral_code, created_at
            FROM users
            ORDER BY created_at DESC
        ''')

        users_list = dicts_from_rows(users)

        return jsonify({
            'success': True,
            'users': users_list
        })

    except Exception as e:
        print(f"Get all users error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500


@api_bp.route('/admin/users/<int:user_id>', methods=['DELETE'])
@api_admin_required
def delete_user(user_id):
    """Delete a user (admin only)"""
    admin_id = session.get('user_id')
    db = get_db()

    try:
        # Check if trying to delete yourself
        if user_id == admin_id:
            return jsonify({'error': 'ไม่สามารถลบบัญชีของตัวเองได้'}), 403

        # Check if user exists
        user = db.execute_query('SELECT id, username FROM users WHERE id = ?', (user_id,))
        if not user:
            return jsonify({'error': 'ไม่พบผู้ใช้'}), 404

        username = user[0]['username']

        # Delete user's related data first (to maintain referential integrity)
        # Delete user's buds
        db.execute_update('DELETE FROM buds_data WHERE grower_id = ?', (user_id,))

        # Delete user's reviews
        db.execute_update('DELETE FROM reviews WHERE user_id = ?', (user_id,))

        # Delete user's activity participations
        db.execute_update('DELETE FROM activity_participants WHERE user_id = ?', (user_id,))

        # Update users who were referred by this user (set referred_by to NULL)
        db.execute_update('UPDATE users SET referred_by = NULL WHERE referred_by = ?', (user_id,))

        # Delete the user
        db.execute_update('DELETE FROM users WHERE id = ?', (user_id,))

        return jsonify({
            'success': True,
            'message': f'ลบผู้ใช้ {username} เรียบร้อยแล้ว'
        })

    except Exception as e:
        print(f"Delete user error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาดในการลบผู้ใช้'}), 500


@api_bp.route('/all-buds-report', methods=['GET'])
def get_all_buds_report():
    """Get all buds for report"""
    db = get_db()

    try:
        buds = db.execute_query('''
            SELECT
                b.*,
                u.username as grower_name
            FROM buds_data b
            LEFT JOIN users u ON b.grower_id = u.id
            ORDER BY b.created_at DESC
        ''')

        buds_list = dicts_from_rows(buds)

        return jsonify({
            'success': True,
            'buds': buds_list
        })

    except Exception as e:
        print(f"Get all buds report error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500


@api_bp.route('/strains/search', methods=['GET'])
def search_strains():
    """Search strains by name"""
    db = get_db()

    try:
        query = request.args.get('q', '').strip()
        lang = request.args.get('lang', 'th')
        limit = int(request.args.get('limit', 10))

        if lang == 'en':
            strains = db.execute_query('''
                SELECT DISTINCT strain_name_en as name
                FROM buds_data
                WHERE strain_name_en LIKE ?
                LIMIT ?
            ''', (f'%{query}%', limit))
        else:
            strains = db.execute_query('''
                SELECT DISTINCT strain_name_th as name
                FROM buds_data
                WHERE strain_name_th LIKE ?
                LIMIT ?
            ''', (f'%{query}%', limit))

        results = [{'name': row['name']} for row in strains if row['name']]

        return jsonify(results)

    except Exception as e:
        print(f"Search strains error: {e}")
        return jsonify([]), 200


@api_bp.route('/breeders/search', methods=['GET'])
def search_breeders():
    """Search breeders"""
    db = get_db()

    try:
        query = request.args.get('q', '').strip()
        limit = int(request.args.get('limit', 10))

        breeders = db.execute_query('''
            SELECT DISTINCT breeder
            FROM buds_data
            WHERE breeder LIKE ?
            LIMIT ?
        ''', (f'%{query}%', limit))

        results = [{'name': row['breeder']} for row in breeders if row['breeder']]

        return jsonify(results)

    except Exception as e:
        print(f"Search breeders error: {e}")
        return jsonify([]), 200


@api_bp.route('/search-buds', methods=['POST'])
@api_login_required
def search_buds():
    """Search buds with filters"""
    db = get_db()

    try:
        data = request.get_json()

        # Build query
        conditions = []
        params = []

        # Strain names
        if data.get('strain_name_th'):
            conditions.append('strain_name_th LIKE ?')
            params.append(f"%{data['strain_name_th']}%")

        if data.get('strain_name_en'):
            conditions.append('strain_name_en LIKE ?')
            params.append(f"%{data['strain_name_en']}%")

        # Breeder
        if data.get('breeder'):
            conditions.append('breeder LIKE ?')
            params.append(f"%{data['breeder']}%")

        # Strain type
        if data.get('strain_type'):
            conditions.append('strain_type = ?')
            params.append(data['strain_type'])

        # Grade
        if data.get('grade'):
            conditions.append('grade = ?')
            params.append(data['grade'])

        # THC range
        if data.get('thc_min'):
            conditions.append('thc_percentage >= ?')
            params.append(float(data['thc_min']))

        if data.get('thc_max'):
            conditions.append('thc_percentage <= ?')
            params.append(float(data['thc_max']))

        # CBD range
        if data.get('cbd_min'):
            conditions.append('cbd_percentage >= ?')
            params.append(float(data['cbd_min']))

        if data.get('cbd_max'):
            conditions.append('cbd_percentage <= ?')
            params.append(float(data['cbd_max']))

        # Aroma/Flavor
        if data.get('aroma_flavor'):
            conditions.append('aroma_flavor LIKE ?')
            params.append(f"%{data['aroma_flavor']}%")

        # Terpenes
        if data.get('terpenes'):
            terpene_conditions = []
            for terp in data['terpenes']:
                terpene_conditions.append('(top_terpenes_1 LIKE ? OR top_terpenes_2 LIKE ? OR top_terpenes_3 LIKE ?)')
                params.extend([f"%{terp}%", f"%{terp}%", f"%{terp}%"])
            if terpene_conditions:
                conditions.append(f"({' OR '.join(terpene_conditions)})")

        # Effects
        if data.get('mental_effects_positive'):
            for effect in data['mental_effects_positive']:
                conditions.append('mental_effects_positive LIKE ?')
                params.append(f"%{effect}%")

        if data.get('physical_effects_positive'):
            for effect in data['physical_effects_positive']:
                conditions.append('physical_effects_positive LIKE ?')
                params.append(f"%{effect}%")

        # Recommended time
        if data.get('recommended_time'):
            conditions.append('recommended_time = ?')
            params.append(data['recommended_time'])

        # Build final query
        where_clause = ' AND '.join(conditions) if conditions else '1=1'

        query = f'''
            SELECT
                b.*,
                u.username as grower_name
            FROM buds_data b
            LEFT JOIN users u ON b.grower_id = u.id
            WHERE {where_clause}
            ORDER BY b.created_at DESC
            LIMIT 50
        '''

        results = db.execute_query(query, tuple(params))
        buds_list = dicts_from_rows(results)

        return jsonify({
            'success': True,
            'buds': buds_list,
            'count': len(buds_list)
        })

    except Exception as e:
        print(f"Search buds error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/admin/reviews', methods=['GET'])
@api_admin_required
def get_admin_reviews():
    """Get all reviews for admin"""
    db = get_db()

    try:
        reviews = db.execute_query('''
            SELECT
                r.*,
                u.username as reviewer_name,
                b.strain_name_th,
                b.strain_name_en,
                b.breeder
            FROM reviews r
            LEFT JOIN users u ON r.reviewer_id = u.id
            LEFT JOIN buds_data b ON r.bud_reference_id = b.id
            ORDER BY r.created_at DESC
        ''')

        reviews_list = dicts_from_rows(reviews)

        return jsonify({
            'success': True,
            'reviews': reviews_list
        })

    except Exception as e:
        print(f"Get admin reviews error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500


@api_bp.route('/admin/get_auth_images', methods=['GET'])
@api_admin_required
def get_auth_images():
    """Get authentication images settings"""
    db = get_db()

    try:
        # Get settings from database
        settings = db.execute_query('''
            SELECT key, value FROM admin_settings
            WHERE key LIKE 'auth_image_%'
        ''')

        settings_dict = {row['key']: row['value'] for row in settings} if settings else {}

        return jsonify({
            'success': True,
            'settings': settings_dict
        })

    except Exception as e:
        print(f"Get auth images error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500


@api_bp.route('/admin/update_auth_images', methods=['POST'])
@api_admin_required
def update_auth_images():
    """Update authentication images settings"""
    db = get_db()
    data = request.get_json()

    try:
        # Update or insert settings
        for key, value in data.items():
            if key.startswith('auth_image_'):
                # Check if exists
                existing = db.execute_query(
                    'SELECT key FROM admin_settings WHERE key = ?',
                    (key,)
                )

                if existing:
                    db.execute_update(
                        'UPDATE admin_settings SET value = ?, updated_at = ? WHERE key = ?',
                        (value, datetime.now(), key)
                    )
                else:
                    db.execute_insert(
                        'INSERT INTO admin_settings (key, value, updated_at) VALUES (?, ?, ?)',
                        (key, value, datetime.now())
                    )

        return jsonify({
            'success': True,
            'message': 'บันทึกการตั้งค่าสำเร็จ'
        })

    except Exception as e:
        print(f"Update auth images error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500


@api_bp.route('/admin/get_settings', methods=['GET'])
@api_admin_required
def get_admin_settings():
    """Get all admin settings"""
    db = get_db()

    try:
        # Get all settings from database
        settings = db.execute_query('SELECT key, value FROM admin_settings')
        settings_dict = {row['key']: row['value'] for row in settings} if settings else {}

        return jsonify({
            'success': True,
            'settings': settings_dict
        })

    except Exception as e:
        print(f"Get settings error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500


@api_bp.route('/admin/update_settings', methods=['POST'])
@api_admin_required
def update_admin_settings():
    """Update admin settings"""
    db = get_db()
    data = request.get_json()

    try:
        # Update or insert settings
        for key, value in data.items():
            # Check if exists
            existing = db.execute_query(
                'SELECT key FROM admin_settings WHERE key = ?',
                (key,)
            )

            if existing:
                db.execute_update(
                    'UPDATE admin_settings SET value = ?, updated_at = ? WHERE key = ?',
                    (str(value), datetime.now(), key)
                )
            else:
                db.execute_insert(
                    'INSERT INTO admin_settings (key, value, updated_at) VALUES (?, ?, ?)',
                    (key, str(value), datetime.now())
                )

        return jsonify({
            'success': True,
            'message': 'บันทึกการตั้งค่าสำเร็จ'
        })

    except Exception as e:
        print(f"Update settings error: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500


# ==================== Admin Activities API ====================

@api_bp.route('/admin/activities', methods=['GET'])
@api_admin_required
def get_admin_activities():
    """Get all activities for admin"""
    db = get_db()

    try:
        activities = db.execute_query('''
            SELECT
                a.*,
                COUNT(DISTINCT ap.user_id) as participant_count
            FROM activities a
            LEFT JOIN activity_participants ap ON a.id = ap.activity_id
            GROUP BY a.id
            ORDER BY a.created_at DESC
        ''')

        activities_list = dicts_from_rows(activities) if activities else []
        return jsonify({'success': True, 'activities': activities_list})

    except Exception as e:
        print(f"Get admin activities error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/admin/activities', methods=['POST'])
@api_admin_required
def create_activity():
    """Create a new activity"""
    db = get_db()

    try:
        data = request.get_json()

        # Insert activity
        activity_id = db.execute_insert('''
            INSERT INTO activities (
                name, description, start_registration_date, end_registration_date,
                max_participants, status, judging_criteria,
                first_prize_description, first_prize_value,
                second_prize_description, second_prize_value,
                third_prize_description, third_prize_value,
                allowed_strain_types, allowed_grow_methods, allowed_grades,
                allowed_fertilizer_types, allowed_recommended_times, allowed_flowering_types,
                preferred_terpenes, allowed_status, min_thc, max_thc, min_cbd, max_cbd,
                require_certificate, require_min_images, min_image_count,
                require_min_reviews, min_review_count,
                preferred_aromas, preferred_effects,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ''', (
            data.get('name'),
            data.get('description'),
            data.get('start_registration_date'),
            data.get('end_registration_date'),
            data.get('max_participants', 0),
            data.get('status', 'upcoming'),
            data.get('judging_criteria'),
            data.get('first_prize_description'),
            data.get('first_prize_value', 0),
            data.get('second_prize_description'),
            data.get('second_prize_value', 0),
            data.get('third_prize_description'),
            data.get('third_prize_value', 0),
            data.get('allowed_strain_types'),
            data.get('allowed_grow_methods'),
            data.get('allowed_grades'),
            data.get('allowed_fertilizer_types'),
            data.get('allowed_recommended_times'),
            data.get('allowed_flowering_types'),
            data.get('preferred_terpenes'),
            data.get('allowed_status'),
            data.get('min_thc'),
            data.get('max_thc'),
            data.get('min_cbd'),
            data.get('max_cbd'),
            data.get('require_certificate', False),
            data.get('require_min_images', False),
            data.get('min_image_count'),
            data.get('require_min_reviews', False),
            data.get('min_review_count'),
            data.get('preferred_aromas'),
            data.get('preferred_effects')
        ))

        return jsonify({
            'success': True,
            'message': 'สร้างกิจกรรมสำเร็จ',
            'activity_id': activity_id
        })

    except Exception as e:
        print(f"Create activity error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/admin/activities/<int:activity_id>', methods=['PUT'])
@api_admin_required
def update_activity(activity_id):
    """Update an activity"""
    db = get_db()

    try:
        data = request.get_json()

        # Update activity
        db.execute_update('''
            UPDATE activities SET
                name = ?, description = ?, start_registration_date = ?, end_registration_date = ?,
                max_participants = ?, status = ?, judging_criteria = ?,
                first_prize_description = ?, first_prize_value = ?,
                second_prize_description = ?, second_prize_value = ?,
                third_prize_description = ?, third_prize_value = ?,
                allowed_strain_types = ?, allowed_grow_methods = ?, allowed_grades = ?,
                allowed_fertilizer_types = ?, allowed_recommended_times = ?, allowed_flowering_types = ?,
                preferred_terpenes = ?, allowed_status = ?, min_thc = ?, max_thc = ?, min_cbd = ?, max_cbd = ?,
                require_certificate = ?, require_min_images = ?, min_image_count = ?,
                require_min_reviews = ?, min_review_count = ?,
                preferred_aromas = ?, preferred_effects = ?
            WHERE id = ?
        ''', (
            data.get('name'),
            data.get('description'),
            data.get('start_registration_date'),
            data.get('end_registration_date'),
            data.get('max_participants', 0),
            data.get('status', 'upcoming'),
            data.get('judging_criteria'),
            data.get('first_prize_description'),
            data.get('first_prize_value', 0),
            data.get('second_prize_description'),
            data.get('second_prize_value', 0),
            data.get('third_prize_description'),
            data.get('third_prize_value', 0),
            data.get('allowed_strain_types'),
            data.get('allowed_grow_methods'),
            data.get('allowed_grades'),
            data.get('allowed_fertilizer_types'),
            data.get('allowed_recommended_times'),
            data.get('allowed_flowering_types'),
            data.get('preferred_terpenes'),
            data.get('allowed_status'),
            data.get('min_thc'),
            data.get('max_thc'),
            data.get('min_cbd'),
            data.get('max_cbd'),
            data.get('require_certificate', False),
            data.get('require_min_images', False),
            data.get('min_image_count'),
            data.get('require_min_reviews', False),
            data.get('min_review_count'),
            data.get('preferred_aromas'),
            data.get('preferred_effects'),
            activity_id
        ))

        return jsonify({
            'success': True,
            'message': 'อัปเดตกิจกรรมสำเร็จ'
        })

    except Exception as e:
        print(f"Update activity error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/admin/activities/<int:activity_id>', methods=['DELETE'])
@api_admin_required
def delete_activity(activity_id):
    """Delete an activity"""
    db = get_db()

    try:
        # Delete activity
        db.execute_update('DELETE FROM activities WHERE id = ?', (activity_id,))

        return jsonify({
            'success': True,
            'message': 'ลบกิจกรรมสำเร็จ'
        })

    except Exception as e:
        print(f"Delete activity error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/activities/<int:activity_id>/participants', methods=['GET'])
@api_login_required
def get_activity_participants(activity_id):
    """Get list of participants for an activity (public view)"""
    db = get_db()

    try:
        # Get activity details
        activity_rows = db.execute_query('''
            SELECT * FROM activities WHERE id = ?
        ''', (activity_id,))

        if not activity_rows:
            return jsonify({'error': 'ไม่พบกิจกรรม'}), 404

        activity_data = dict(activity_rows[0])

        # Initialize empty participants list
        participants_list = []

        # Try to get participants - handle gracefully if table doesn't exist
        try:
            participants_rows = db.execute_query('''
                SELECT
                    ap.id,
                    ap.user_id,
                    ap.bud_id,
                    ap.registered_at as joined_at,
                    u.username,
                    u.username as display_name,
                    u.profile_image_url,
                    b.id as bud_id,
                    b.strain_name_th,
                    b.strain_name_en,
                    b.breeder,
                    b.thc_percentage,
                    b.cbd_percentage,
                    b.image_1_url,
                    b.strain_type,
                    b.grade
                FROM activity_participants ap
                LEFT JOIN users u ON ap.user_id = u.id
                LEFT JOIN buds_data b ON ap.bud_id = b.id
                WHERE ap.activity_id = ?
                ORDER BY ap.registered_at DESC
            ''', (activity_id,))

            participants_list = [dict(row) for row in participants_rows] if participants_rows else []
        except Exception as table_error:
            print(f"Warning: Could not fetch participants (table may not exist): {table_error}")
            # Continue with empty list

        return jsonify({
            'success': True,
            'activity': activity_data,
            'participants': participants_list,
            'total': len(participants_list)
        })

    except Exception as e:
        print(f"Get activity participants error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'เกิดข้อผิดพลาดในการโหลดข้อมูล: {str(e)}'}), 500


@api_bp.route('/my_activities', methods=['GET'])
@api_login_required
def get_my_activities():
    """Get activities that the current user has joined"""
    db = get_db()
    user_id = session.get('user_id')

    try:
        # Get activities the user has joined with their submission details
        activities = db.execute_query('''
            SELECT
                a.*,
                ap.id as participation_id,
                ap.bud_id as submitted_bud_id,
                ap.submission_description,
                ap.registered_at as joined_at,
                b.strain_name_th,
                b.strain_name_en,
                b.image_1_url as bud_image,
                COUNT(DISTINCT ap2.user_id) as total_participants
            FROM activity_participants ap
            JOIN activities a ON ap.activity_id = a.id
            LEFT JOIN buds_data b ON ap.bud_id = b.id
            LEFT JOIN activity_participants ap2 ON a.id = ap2.activity_id
            WHERE ap.user_id = ?
            GROUP BY a.id, ap.id
            ORDER BY ap.registered_at DESC
        ''', (user_id,))

        activities_list = dicts_from_rows(activities) if activities else []
        return jsonify({
            'success': True,
            'activities': activities_list
        })

    except Exception as e:
        print(f"Get my activities error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'activities': []}), 500


@api_bp.route('/activities/<int:activity_id>/join', methods=['POST'])
@api_login_required
def join_activity(activity_id):
    """Join an activity with a bud submission"""
    db = get_db()
    user_id = session.get('user_id')

    try:
        data = request.get_json()
        bud_id = data.get('bud_id')
        submission_description = data.get('submission_description', '')

        if not bud_id:
            return jsonify({'error': 'กรุณาเลือกดอกที่ต้องการส่งเข้าประกวด'}), 400

        # Check if activity exists and is open for registration
        activity_rows = db.execute_query('''
            SELECT * FROM activities WHERE id = ?
        ''', (activity_id,))

        if not activity_rows:
            return jsonify({'error': 'ไม่พบกิจกรรมนี้'}), 404

        activity = dict(activity_rows[0])

        # Allow both 'open' and 'registration_open' status
        if activity['status'] not in ['open', 'registration_open']:
            return jsonify({'error': 'กิจกรรมนี้ไม่เปิดรับสมัครแล้ว'}), 400

        # Check if max participants reached
        if activity['max_participants'] > 0:
            participant_count = db.execute_query('''
                SELECT COUNT(*) as count FROM activity_participants
                WHERE activity_id = ?
            ''', (activity_id,))

            if participant_count and participant_count[0]['count'] >= activity['max_participants']:
                return jsonify({'error': 'กิจกรรมเต็มแล้ว'}), 400

        # Check if user already joined
        existing = db.execute_query('''
            SELECT id FROM activity_participants
            WHERE activity_id = ? AND user_id = ?
        ''', (activity_id, user_id))

        if existing:
            return jsonify({'error': 'คุณได้เข้าร่วมกิจกรรมนี้แล้ว'}), 400

        # Check if bud belongs to user (try grower_id first, fallback to user_id)
        try:
            bud_rows = db.execute_query('''
                SELECT * FROM buds_data WHERE id = ? AND grower_id = ?
            ''', (bud_id, user_id))
        except:
            # Fallback to user_id if grower_id doesn't exist
            bud_rows = db.execute_query('''
                SELECT * FROM buds_data WHERE id = ? AND user_id = ?
            ''', (bud_id, user_id))

        if not bud_rows:
            return jsonify({'error': 'ไม่พบดอกที่เลือก หรือดอกนี้ไม่ใช่ของคุณ'}), 404

        # Insert participation record
        from datetime import datetime
        db.execute_update('''
            INSERT INTO activity_participants
            (activity_id, user_id, bud_id, registered_at, submission_description)
            VALUES (?, ?, ?, ?, ?)
        ''', (activity_id, user_id, bud_id, datetime.now(), submission_description))

        return jsonify({
            'success': True,
            'message': 'เข้าร่วมกิจกรรมสำเร็จ!'
        })

    except Exception as e:
        print(f"Join activity error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'เกิดข้อผิดพลาดในการเข้าร่วม: {str(e)}'}), 500


@api_bp.route('/admin/activities/<int:activity_id>/report', methods=['GET'])
@api_admin_required
def get_activity_report(activity_id):
    """Get detailed activity report with participants and submitted buds"""
    db = get_db()

    try:
        # Get activity details
        activity_rows = db.execute_query('''
            SELECT * FROM activities WHERE id = ?
        ''', (activity_id,))

        if not activity_rows:
            return jsonify({'error': 'ไม่พบกิจกรรม'}), 404

        # Convert to dict
        activity_data = dict(activity_rows[0])

        # Initialize empty participants list
        participants_list = []

        # Try to get participants - handle gracefully if table doesn't exist
        try:
            participants_rows = db.execute_query('''
                SELECT
                    ap.id,
                    ap.activity_id,
                    ap.user_id,
                    ap.bud_reference_id,
                    ap.joined_at,
                    ap.status,
                    u.username,
                    u.display_name,
                    u.profile_image_url,
                    b.id as bud_id,
                    b.strain_name_th,
                    b.strain_name_en,
                    b.breeder,
                    b.thc_percentage,
                    b.cbd_percentage,
                    b.image_url_1,
                    b.image_url_2,
                    b.image_url_3,
                    b.image_url_4,
                    b.strain_type,
                    b.grow_method,
                    b.grade,
                    b.overall_rating
                FROM activity_participants ap
                LEFT JOIN users u ON ap.user_id = u.id
                LEFT JOIN buds_data b ON ap.bud_reference_id = b.id
                WHERE ap.activity_id = ?
                ORDER BY ap.joined_at DESC
            ''', (activity_id,))

            # Convert rows to dicts
            if participants_rows:
                for row in participants_rows:
                    participants_list.append(dict(row))
        except Exception as table_error:
            print(f"Warning: Could not fetch participants: {table_error}")
            # Continue with empty list

        # Calculate statistics
        total_participants = len(participants_list)
        total_buds_submitted = len([p for p in participants_list if p.get('bud_id')])

        # Average THC/CBD
        buds_with_thc = [p for p in participants_list if p.get('thc_percentage') is not None]
        buds_with_cbd = [p for p in participants_list if p.get('cbd_percentage') is not None]

        avg_thc = sum(p['thc_percentage'] for p in buds_with_thc) / len(buds_with_thc) if buds_with_thc else 0
        avg_cbd = sum(p['cbd_percentage'] for p in buds_with_cbd) / len(buds_with_cbd) if buds_with_cbd else 0

        # Strain type distribution
        strain_types = {}
        for p in participants_list:
            if p.get('strain_type'):
                strain_types[p['strain_type']] = strain_types.get(p['strain_type'], 0) + 1

        return jsonify({
            'success': True,
            'activity': activity_data,
            'participants': participants_list,
            'statistics': {
                'total_participants': total_participants,
                'total_buds_submitted': total_buds_submitted,
                'avg_thc': round(avg_thc, 2),
                'avg_cbd': round(avg_cbd, 2),
                'strain_type_distribution': strain_types
            }
        })

    except Exception as e:
        print(f"Get activity report error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ==================== Static Files ====================

@api_bp.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)


@api_bp.route('/assets/<path:filename>')
def asset_file(filename):
    """Serve asset files"""
    return send_from_directory(current_app.config['ATTACHED_ASSETS_FOLDER'], filename)


@api_bp.route('/attached_assets/<path:filename>')
def attached_asset_file(filename):
    """Serve attached asset files"""
    return send_from_directory(current_app.config['ATTACHED_ASSETS_FOLDER'], filename)
