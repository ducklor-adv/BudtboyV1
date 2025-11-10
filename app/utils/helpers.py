from datetime import datetime


def safe_datetime_format(dt_value):
    """Safely format datetime values, handling both datetime objects and strings"""
    if not dt_value:
        return None
    try:
        # If it's already a string, return as is
        if isinstance(dt_value, str):
            return dt_value
        # If it has strftime method (datetime object), format it
        elif hasattr(dt_value, 'strftime'):
            return dt_value.strftime('%Y-%m-%d %H:%M:%S')
        # Otherwise convert to string
        else:
            return str(dt_value)
    except:
        return str(dt_value) if dt_value else None


def dict_from_row(row):
    """Convert sqlite3.Row to dictionary"""
    if row is None:
        return None
    return dict(row)


def dicts_from_rows(rows):
    """Convert list of sqlite3.Row to list of dictionaries"""
    return [dict(row) for row in rows]


def generate_unique_filename(original_filename):
    """Generate unique filename with timestamp"""
    import secrets
    from datetime import datetime

    # Get file extension inline
    ext = None
    if '.' in original_filename:
        ext = original_filename.rsplit('.', 1)[1].lower()

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    random_str = secrets.token_hex(8)

    if ext:
        return f"{timestamp}_{random_str}.{ext}"
    return f"{timestamp}_{random_str}"
