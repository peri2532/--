# debug_check.py
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://search.naver.com/",
}

url = "https://search.naver.com/search.naver?where=news&query=삼성전자&pd=3&ds=2024.01.01&de=2024.01.31&start=0&sort=0"
resp = requests.get(url, headers=HEADERS, timeout=15)
soup = BeautifulSoup(resp.content, "html.parser")

print(f"상태코드: {resp.status_code}")
print(f"HTML 크기: {len(resp.content)} bytes")

# 뉴스 링크 포함 a태그 전체 출력
print("\n=== news.naver.com 링크 ===")
for a in soup.find_all("a", href=True):
    href = a.get("href", "")
    if "news.naver.com" in href or "mnews" in href:
        print(f"  href: {href[:80]}")
        print(f"  class: {a.get('class')}")
        print()

# 모든 div/article 클래스 샘플링
print("\n=== 뉴스카드 후보 태그 ===")
for tag in soup.find_all(["div", "article", "li"], class_=True):
    classes = " ".join(tag.get("class", []))
    text = tag.get_text(strip=True)[:30]
    if text and len(tag.find_all("a")) > 0:
        print(f"  <{tag.name} class='{classes[:60]}'> {text}")