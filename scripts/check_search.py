"""검색 엔진 응답 확인."""
import re
import sys
sys.path.insert(0, ".")
import requests
from bs4 import BeautifulSoup

# Bing
r = requests.get(
    "https://www.bing.com/search",
    params={"q": "Google employees"},
    timeout=10,
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"},
)
print("Bing status", r.status_code, "len", len(r.text))
hrefs = re.findall(r'href="(https?://[^"]+)"', r.text)
external = [h for h in hrefs if "bing.com" not in h and "microsoft" not in h][:15]
print("Bing external hrefs", len(external))
for h in external[:5]:
    print(" ", h[:72])

# DDG
r2 = requests.get(
    "https://duckduckgo.com/html/",
    params={"q": "Google employees"},
    timeout=10,
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"},
)
print("DDG status", r2.status_code)
uddg = re.findall(r'uddg=([^&"\']+)', r2.text)
print("DDG uddg params", len(uddg))
if uddg:
    from urllib.parse import unquote
    print(" first decoded", unquote(uddg[0])[:72])
