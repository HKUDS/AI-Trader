from datetime import datetime

def parse_date(date_str):
    """Parse a date string in either 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS' format."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError("Date must be in YYYY-MM-DD or YYYY-MM-DD HH:MM:SS format")