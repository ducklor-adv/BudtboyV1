
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'development-key-change-in-production')

@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'message': 'Server is running'})

@app.route('/bud-report')
def bud_report():
    """Bud report page"""
    bud_id = request.args.get('id')
    if not bud_id:
        return "Missing bud ID", 400
    return render_template('bud_report.html')

@app.route('/api/bud/<int:bud_id>')
def get_bud_api(bud_id):
    """API endpoint to get bud data"""
    # Mock data for testing
    mock_bud = {
        'bud': {
            'id': bud_id,
            'strain_name_th': 'บลูดรีม',
            'strain_name_en': 'Blue Dream',
            'breeder': 'DNA Genetics',
            'strain_type': 'Hybrid',
            'thc_percentage': 19.2,
            'cbd_percentage': 2.0,
            'grade': 'B+',
            'aroma_flavor': 'กาแฟ, สตรอว์เบอร์รี่, บัตเตอร์',
            'grower_name': 'Budt.Boy',
            'grower_id': None,
            'created_by': 1,
            'harvest_date': '2025-07-16',
            'grow_method': 'Indoor',
            'fertilizer_type': 'Organic',
            'flowering_type': 'Photoperiod',
            'image_1_url': 'uploads/20250728_081801_bud_4_image_1_Banana_daddy_indad.jpg',
            'image_2_url': 'uploads/20250728_081801_bud_4_image_2_Gorilla_Punch.jpg',
            'image_3_url': 'uploads/20250728_081801_bud_4_image_3_Gorilla_Cookies.jpg',
            'image_4_url': 'uploads/20250728_081801_bud_4_image_4_Cherry_cola_B.jpg',
            'top_terpenes_1': 'Myrcene',
            'top_terpenes_2': 'Limonene',
            'top_terpenes_3': 'Caryophyllene',
            'mental_effects_positive': 'ผ่อนคลาย, สร้างสรรค์',
            'mental_effects_negative': '',
            'physical_effects_positive': 'บรรเทาปวด, คลายกล้าม',
            'physical_effects_negative': 'ปากแห้ง',
            'recommended_time': 'ตลอดวัน',
            'batch_number': '',
            'grower_license_verified': False,
            'avg_rating': 4.5,
            'review_count': 1
        },
        'reviews': [
            {
                'id': 1,
                'reviewer_id': 1,
                'reviewer_name': 'Budt.Boy',
                'overall_rating': 4,
                'aroma_rating': 4,
                'aroma_flavors': ['กาแฟ', 'สตรอว์เบอร์รี่', 'บัตเตอร์'],
                'selected_effects': ['ผ่อนคลาย', 'สร้างสรรค์'],
                'short_summary': 'ดอกเยี่ยม รสชาติดี',
                'full_review_content': 'Blue Dream นี้เป็นสายพันธุ์ที่ยอดเยี่ยมมาก กลิ่นหอมหวานของเบอร์รี่ผสมซิตรัส',
                'created_at': '2025-01-28T10:00:00Z'
            }
        ]
    }
    return jsonify(mock_bud)

@app.route('/auth')
def auth():
    """Authentication page"""
    return render_template('auth.html')

@app.route('/profile')
def profile():
    """User profile page"""
    return render_template('profile.html')

@app.route('/admin_login')
def admin_login():
    """Admin login page"""
    return render_template('admin_login.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
