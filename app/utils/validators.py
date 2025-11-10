import re
from email_validator import validate_email as email_validate, EmailNotValidError


def validate_email(email):
    """
    Validate email address
    Returns (is_valid, error_message)
    """
    try:
        email_validate(email)
        return True, None
    except EmailNotValidError as e:
        return False, str(e)


def validate_username(username):
    """
    Validate username
    Returns (is_valid, error_message)
    """
    if not username or len(username) < 3:
        return False, "ชื่อผู้ใช้ต้องมีอย่างน้อย 3 ตัวอักษร"

    if len(username) > 50:
        return False, "ชื่อผู้ใช้ยาวเกินไป"

    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "ชื่อผู้ใช้ต้องประกอบด้วยตัวอักษร ตัวเลข และ _ เท่านั้น"

    return True, None


def validate_birth_year(year):
    """
    Validate birth year
    Returns (is_valid, error_message)
    """
    if not year:
        return True, None  # Optional field

    try:
        year = int(year)
        if year < 1900 or year > 2024:
            return False, "ปีเกิดไม่ถูกต้อง"
        return True, None
    except (ValueError, TypeError):
        return False, "ปีเกิดต้องเป็นตัวเลข"


def validate_phone_number(phone):
    """
    Validate Thai phone number
    Returns (is_valid, error_message)
    """
    if not phone:
        return True, None  # Optional field

    # Remove spaces and dashes
    phone = re.sub(r'[\s-]', '', phone)

    # Thai phone format: 0X-XXXX-XXXX or +66X-XXXX-XXXX
    if re.match(r'^0[0-9]{9}$', phone) or re.match(r'^\+66[0-9]{9}$', phone):
        return True, None

    return False, "หมายเลขโทรศัพท์ไม่ถูกต้อง"


def allowed_file(filename, allowed_extensions):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions


def sanitize_filename(filename):
    """Sanitize filename to prevent directory traversal"""
    # Remove any path components
    filename = filename.replace('\\', '').replace('/', '')
    # Remove any non-alphanumeric characters except dots, dashes, and underscores
    filename = re.sub(r'[^a-zA-Z0-9._-]', '', filename)
    return filename


def validate_file_size(file, max_size_mb=16):
    """
    Validate file size
    Args:
        file: FileStorage object from Flask request
        max_size_mb: Maximum file size in megabytes
    Returns:
        (is_valid, error_message)
    """
    try:
        # Seek to end to get file size
        file.seek(0, 2)
        file_size = file.tell()
        # Reset to beginning
        file.seek(0)

        max_size_bytes = max_size_mb * 1024 * 1024

        if file_size > max_size_bytes:
            return False, f"ไฟล์มีขนาดใหญ่เกินไป (สูงสุด {max_size_mb} MB)"

        if file_size == 0:
            return False, "ไฟล์ว่างเปล่า"

        return True, None
    except Exception as e:
        return False, f"ไม่สามารถตรวจสอบขนาดไฟล์ได้: {str(e)}"
