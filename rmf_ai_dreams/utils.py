"""
RMF AI Dreams - Utility Functions
Helper functions for the platform
"""

import hashlib
import secrets
import string
import random
from datetime import datetime
from typing import List, Dict, Any, Optional
import json
from cryptography.fernet import Fernet
from config import SECRET_KEY, ADJECTIVES, TECH_WORDS, USERNAME_PATTERNS

# Encryption key (derive from SECRET_KEY)
def get_encryption_key():
    """Generate encryption key from secret"""
    key = hashlib.sha256(SECRET_KEY.encode()).digest()
    return Fernet(key[:32].hex()[:43].encode() + b'=')

# Password utilities
def generate_strong_password(length: int = 16) -> str:
    """Generate a cryptographically strong password"""
    characters = string.ascii_letters + string.digits + string.punctuation
    # Ensure at least one of each type
    password = [
        random.choice(string.ascii_uppercase),
        random.choice(string.ascii_lowercase),
        random.choice(string.digits),
        random.choice(string.punctuation)
    ]
    # Fill the rest
    password += [secrets.choice(characters) for _ in range(length - 4)]
    random.shuffle(password)
    return ''.join(password)

def hash_password(password: str) -> str:
    """Hash password with SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash"""
    return hash_password(password) == password_hash

# Username generation
def generate_username(name: str = None, category: str = "tech") -> List[str]:
    """Generate creative username suggestions"""
    usernames = []

    if name:
        base_name = name.lower().replace(" ", "_")
    else:
        base_name = random.choice(ADJECTIVES)

    patterns = [
        f"{base_name}_{random.choice(TECH_WORDS)}",
        f"{random.choice(ADJECTIVES)}_{base_name}",
        f"{base_name}_{random.randint(100, 999)}",
        f"{base_name}_official",
        f"the_{base_name}",
        f"{base_name}_{datetime.now().year}",
        f"{random.choice(ADJECTIVES)}_{random.choice(TECH_WORDS)}_{random.randint(10, 99)}",
    ]

    # Generate 10 unique usernames
    for _ in range(10):
        username = random.choice(patterns)
        if username not in usernames:
            usernames.append(username)

    return usernames[:8]

# Email generation
def generate_email(username: str, domain: str = None) -> str:
    """Generate email from username"""
    if not domain:
        domains = ["gmail.com", "protonmail.com", "outlook.com", "yahoo.com"]
        domain = random.choice(domains)

    return f"{username}@{domain}"

# Encryption utilities
def encrypt_data(data: str) -> str:
    """Encrypt sensitive data"""
    try:
        cipher = get_encryption_key()
        encrypted = cipher.encrypt(data.encode())
        return encrypted.decode()
    except Exception as e:
        print(f"Encryption error: {e}")
        return data

def decrypt_data(encrypted_data: str) -> str:
    """Decrypt sensitive data"""
    try:
        cipher = get_encryption_key()
        decrypted = cipher.decrypt(encrypted_data.encode())
        return decrypted.decode()
    except Exception as e:
        print(f"Decryption error: {e}")
        return encrypted_data

# JSON utilities
def safe_json_loads(json_str: str, default: Any = None) -> Any:
    """Safely parse JSON string"""
    try:
        return json.loads(json_str)
    except:
        return default or {}

def safe_json_dumps(obj: Any) -> str:
    """Safely convert object to JSON"""
    try:
        return json.dumps(obj)
    except:
        return "{}"

# Date/Time utilities
def format_datetime(dt: datetime) -> str:
    """Format datetime for display"""
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def parse_datetime(dt_str: str) -> Optional[datetime]:
    """Parse datetime string"""
    try:
        return datetime.fromisoformat(dt_str)
    except:
        return None

# Text utilities
def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to max length"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix

def clean_filename(filename: str) -> str:
    """Clean filename for safe storage"""
    # Remove or replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename

# Validation utilities
def is_valid_email(email: str) -> bool:
    """Basic email validation"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def is_valid_username(username: str) -> bool:
    """Validate username format"""
    import re
    # 3-30 characters, alphanumeric and underscores only
    pattern = r'^[a-zA-Z0-9_]{3,30}$'
    return re.match(pattern, username) is not None

def is_strong_password(password: str) -> Dict[str, Any]:
    """Check password strength"""
    checks = {
        'length': len(password) >= 8,
        'uppercase': any(c.isupper() for c in password),
        'lowercase': any(c.islower() for c in password),
        'digit': any(c.isdigit() for c in password),
        'special': any(c in string.punctuation for c in password)
    }

    strength_score = sum(checks.values())

    return {
        'is_strong': strength_score >= 4,
        'score': strength_score,
        'checks': checks,
        'level': 'Weak' if strength_score < 3 else 'Medium' if strength_score < 5 else 'Strong'
    }

# Color utilities
def hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex color to RGB"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB to hex color"""
    return f'#{r:02x}{g:02x}{b:02x}'

# List utilities
def chunk_list(lst: List, chunk_size: int) -> List[List]:
    """Split list into chunks"""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

def deduplicate_list(lst: List) -> List:
    """Remove duplicates while preserving order"""
    seen = set()
    return [x for x in lst if not (x in seen or seen.add(x))]

# Status badge generator
def get_status_badge(status: str) -> str:
    """Get HTML badge for status"""
    badges = {
        'completed': '<span class="status-done">✅ COMPLETED</span>',
        'executing': '<span class="status-executing">⚡ EXECUTING</span>',
        'planning': '<span class="status-thinking">🧠 PLANNING</span>',
        'pending': '<span class="status-thinking">⏳ PENDING</span>',
        'cancelled': '<span style="background: #666; padding: 4px 12px; border-radius: 20px;">❌ CANCELLED</span>',
        'failed': '<span style="background: #FF0055; padding: 4px 12px; border-radius: 20px;">💥 FAILED</span>',
    }
    return badges.get(status.lower(), status)

# Risk level color
def get_risk_color(risk_level: str) -> str:
    """Get color for risk level"""
    colors = {
        'low': '#00FF88',
        'medium': '#FFB800',
        'high': '#FF0055',
        'critical': '#FF0000'
    }
    return colors.get(risk_level.lower(), '#FFFFFF')

# Progress calculator
def calculate_progress(completed: int, total: int) -> float:
    """Calculate progress percentage"""
    if total == 0:
        return 0.0
    return round((completed / total) * 100, 1)

# File size formatter
def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

# Random color generator (for charts)
def generate_random_color(seed: str = None) -> str:
    """Generate random hex color"""
    if seed:
        random.seed(seed)
    r = random.randint(0, 255)
    g = random.randint(0, 255)
    b = random.randint(0, 255)
    return rgb_to_hex(r, g, b)

# Browser user agent generator
def generate_user_agent() -> str:
    """Generate realistic user agent string"""
    agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    ]
    return random.choice(agents)

# Markdown formatter
def format_as_markdown_list(items: List[str], ordered: bool = False) -> str:
    """Format list as markdown"""
    if ordered:
        return '\n'.join([f"{i+1}. {item}" for i, item in enumerate(items)])
    return '\n'.join([f"- {item}" for item in items])

# Safe division
def safe_divide(a: float, b: float, default: float = 0.0) -> float:
    """Safely divide two numbers"""
    try:
        return a / b if b != 0 else default
    except:
        return default

# Timer decorator
def timer(func):
    """Decorator to time function execution"""
    import time
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        print(f"{func.__name__} took {end - start:.2f} seconds")
        return result
    return wrapper

# Cache decorator (simple in-memory cache)
_cache = {}

def cache(func):
    """Simple cache decorator"""
    def wrapper(*args, **kwargs):
        key = str(args) + str(kwargs)
        if key in _cache:
            return _cache[key]
        result = func(*args, **kwargs)
        _cache[key] = result
        return result
    return wrapper

# Export all utilities
__all__ = [
    'generate_strong_password',
    'hash_password',
    'verify_password',
    'generate_username',
    'generate_email',
    'encrypt_data',
    'decrypt_data',
    'safe_json_loads',
    'safe_json_dumps',
    'format_datetime',
    'parse_datetime',
    'truncate_text',
    'clean_filename',
    'is_valid_email',
    'is_valid_username',
    'is_strong_password',
    'get_status_badge',
    'get_risk_color',
    'calculate_progress',
    'format_file_size',
    'generate_user_agent',
    'timer',
    'cache'
]
