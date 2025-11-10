from flask import Blueprint, render_template, session, redirect, url_for, send_from_directory, current_app
from app.utils import login_required
import os

main_bp = Blueprint('main', __name__)


def get_db():
    """Get database instance"""
    from flask import current_app
    return current_app.db


@main_bp.route('/')
def index():
    """Home page - redirect based on login status"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login_page'))
    return redirect(url_for('main.profile'))


@main_bp.route('/profile')
@login_required
def profile():
    """User profile page"""
    return render_template('profile.html')


@main_bp.route('/add-buds')
@login_required
def add_buds():
    """Add buds page"""
    return render_template('add_buds.html')


@main_bp.route('/edit-bud', methods=['GET'])
@main_bp.route('/edit-bud/<int:bud_id>', methods=['GET'])
@login_required
def edit_bud(bud_id=None):
    """Edit bud page"""
    from flask import request

    # Support both query string (?id=1) and path parameter (/1)
    if bud_id is None:
        bud_id = request.args.get('id', type=int)

    return render_template('edit_bud.html', bud_id=bud_id)


@main_bp.route('/add-review')
@login_required
def add_review():
    """Add review page"""
    from flask import request

    # Get bud_id from query parameter if provided
    bud_id = request.args.get('bud_id', type=int)

    return render_template('add_review.html', bud_id=bud_id)


@main_bp.route('/edit-review', methods=['GET'])
@main_bp.route('/edit-review/<int:review_id>', methods=['GET'])
@login_required
def edit_review(review_id=None):
    """Edit review page"""
    from flask import request

    # Support both query string (?id=1) and path parameter (/1)
    if review_id is None:
        review_id = request.args.get('id', type=int)

    return render_template('edit_review.html', review_id=review_id)


@main_bp.route('/my-reviews')
@login_required
def my_reviews():
    """User's reviews page"""
    return render_template('my_reviews.html')


@main_bp.route('/report')
@login_required
def report():
    """Report page"""
    return render_template('report.html')


@main_bp.route('/bud-report')
@login_required
def bud_report():
    """Bud report page - full report and all reviews for a specific bud"""
    return render_template('bud_report.html')


@main_bp.route('/friends')
@login_required
def friends():
    """Friends page"""
    return render_template('friends.html')


@main_bp.route('/friends-reviews')
@login_required
def friends_reviews():
    """Friends reviews page"""
    return render_template('friends_reviews.html')


@main_bp.route('/activities')
@login_required
def activities():
    """Activities list page"""
    return render_template('activities.html')


@main_bp.route('/activity')
@login_required
def activity():
    """User activity page - my buds and reviews"""
    return render_template('activity.html')


@main_bp.route('/activity/<int:activity_id>')
@login_required
def activity_detail(activity_id):
    """Activity detail page"""
    return render_template('activity.html', activity_id=activity_id)


@main_bp.route('/activities/<int:activity_id>/participants')
@login_required
def activity_participants(activity_id):
    """Activity participants page"""
    return render_template('activity_participants.html', activity_id=activity_id)


@main_bp.route('/activities/<int:activity_id>/join')
@login_required
def activity_join(activity_id):
    """Activity join page"""
    return render_template('activity_join.html', activity_id=activity_id)


@main_bp.route('/search')
@login_required
def search():
    """Search page"""
    return render_template('search_tool.html')


@main_bp.route('/search-tool')
@login_required
def search_tool():
    """Search tool page (alias)"""
    return render_template('search_tool.html')


@main_bp.route('/healthz')
def health_check():
    """Health check endpoint"""
    return {'status': 'ok'}, 200


@main_bp.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    upload_folder = current_app.config['UPLOAD_FOLDER']
    # Convert to absolute path if relative
    if not os.path.isabs(upload_folder):
        upload_folder = os.path.join(current_app.root_path, '..', upload_folder)
        upload_folder = os.path.abspath(upload_folder)
    print(f"Serving file: {filename} from {upload_folder}")
    return send_from_directory(upload_folder, filename)


@main_bp.route('/assets/<path:filename>')
def asset_file(filename):
    """Serve asset files"""
    return send_from_directory(current_app.config['ATTACHED_ASSETS_FOLDER'], filename)
