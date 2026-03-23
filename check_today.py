# check_today.py 로 저장 후 실행
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
print("요청 URL:", url)

r = requests.get(url, headers=HEADERS, timeout=10)
soup = BeautifulSoup(r.content, "html.parser")

links = soup.find_all("a", href=lambda h: h and "n.news.naver.com/mnews/article" in str(h))
print(f"오늘 날짜 링크 수: {len(links)}개")
print("ByqJOtaiD32azLYpWrSb 포함:", "ByqJOtaiD32azLYpWrSb" in r.text)
print("삼성전자 포함:", "삼성전자" in r.text)
if links:
    print("첫 번째:", links[0]["href"][:70])
