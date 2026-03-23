# check_title.py 로 저장 후 실행
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

TODAY     = datetime.now().strftime("%Y.%m.%d")
YESTERDAY = (datetime.now() - timedelta(days=1)).strftime("%Y.%m.%d")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://search.naver.com/",
}

url = f"https://search.naver.com/search.naver?where=news&query=%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90&pd=3&ds={YESTERDAY}&de={TODAY}&start=0&sort=1"
r = requests.get(url, headers=HEADERS, timeout=10)
soup = BeautifulSoup(r.content, "html.parser")

links = soup.find_all("a", href=lambda h: h and "n.news.naver.com/mnews/article" in str(h))
print(f"링크 수: {len(links)}")

# 첫 번째 링크 주변 텍스트 구조 확인
a = links[0]
print(f"\n링크 텍스트: {a.get_text(strip=True)[:50]}")
print(f"링크 class: {a.get('class', [])}")

# 부모 8단계 텍스트 출력
p = a.parent
for i in range(8):
    if p is None:
        break
    texts = [s.get_text(strip=True) for s in p.find_all("span") if len(s.get_text(strip=True)) > 5]
    print(f"\n부모{i+1} tag={p.name} class={p.get('class',[][:2])}")
    print(f"  span 텍스트들: {texts[:5]}")
    p = p.parent
