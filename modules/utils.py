import qrcode
from io import BytesIO
from datetime import datetime
import uuid

def generate_qr_image(data):
    """Generates a QR code image bytes for the given data."""
    qr = qrcode.make(data)
    buf = BytesIO()
    qr.save(buf, format="PNG")
    return buf.getvalue()

def get_current_time_str():
    """Returns current time in YYYY-MM-DD HH:MM format."""
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def get_current_date_str():
    """Returns current date in YYYY-MM-DD format."""
    return datetime.now().strftime("%Y-%m-%d")

def normalize_id(val):
    """Normalizes ID strings (handles float string issues from pandas)."""
    if val is None: return ""
    s = str(val).strip()
    if s.lower() == 'nan': return ""
    if s.endswith('.0'): return str(int(float(s)))
    return s.upper()

def get_unique_id():
    """Generates a UUID string."""
    return str(uuid.uuid4())
