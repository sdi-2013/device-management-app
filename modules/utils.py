import qrcode
from io import BytesIO
from datetime import datetime, timezone, timedelta
import uuid

def get_kst_now():
    """Returns datetime.now() in KST (UTC+9)"""
    return datetime.now(timezone(timedelta(hours=9)))

def generate_qr_image(data):
    """Generates a QR code image bytes for the given data."""
    qr = qrcode.make(data)
    buf = BytesIO()
    qr.save(buf, format="PNG")
    return buf.getvalue()

def get_current_time_str():
    """Returns current time in YYYY-MM-DD HH:MM format."""
    return get_kst_now().strftime("%Y-%m-%d %H:%M")

def get_current_date_str():
    """Returns current date in YYYY-MM-DD format."""
    return get_kst_now().strftime("%Y-%m-%d")

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

def get_chosung(text):
    """
    한글 문자열에서 초성만 추출합니다. (예: '피복' -> 'ㅍㅂ')
    한글이 아닌 문자는 그대로 유지합니다.
    """
    if not text:
        return ""
    
    CHOSUNG_LIST = ['ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']
    result = []
    
    for char in text:
        code = ord(char)
        if 0xAC00 <= code <= 0xD7A3:
            # 한글 음절인 경우 초성 인덱스 계산
            chosung_index = (code - 0xAC00) // 588
            result.append(CHOSUNG_LIST[chosung_index])
        else:
            result.append(char)
            
    return "".join(result)
