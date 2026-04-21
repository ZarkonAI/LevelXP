import requests
from app.config import get_settings

s = get_settings()

url = f"{s.supabase_url}/rest/v1/users?select=telegram_id&limit=1"
headers = {
    "apikey": s.supabase_key,
    "Authorization": f"Bearer {s.supabase_key}",
}

r = requests.get(url, headers=headers, timeout=20)
print(r.status_code)
print(r.text[:500])
