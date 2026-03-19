"""
dump_response.py
크롤러와 완전히 동일한 방식으로 요청을 보내고
실제로 받는 HTML을 crawler_response.html 로 저장합니다.
"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://search.naver.com/",
}

URL = (
    "https://search.naver.com/search.naver"
    "?where=news&query=%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90"
    "&pd=3&ds=2022.01.01&de=2022.01.31&start=0&sort=0"
)

# 크롤러와 동일: 새 Session, 쿠키 초기화
s = requests.Session()
retry = Retry(total=2, backoff_factor=1,
              status_forcelist=[500, 502, 503, 504],
              allowed_methods=["GET"], raise_on_status=False)
s.mount("https://", HTTPAdapter(max_retries=retry))
s.cookies.clear()

# 인코딩 utf-8 고정 (크롤러와 동일)
r = s.get(URL, headers=HEADERS, timeout=(5, 15))
r.encoding = "utf-8"

print(f"HTTP 상태: {r.status_code}")
print(f"응답 크기: {len(r.content):,} bytes")
print(f"OaLkxeV3 포함: {'OaLkxeV3' in r.text}")
print(f"GOWcekJV4 포함: {'GOWcekJV4' in r.text}")
print(f"삼성전자 포함:  {'삼성전자' in r.text}")

# HTML 저장
with open("crawler_response.html", "w", encoding="utf-8") as f:
    f.write(r.text)
print("\ncrawler_response.html 저장 완료")

# 페이지 title 확인
from bs4 import BeautifulSoup
soup = BeautifulSoup(r.text, "html.parser")
title = soup.find("title")
print(f"페이지 제목: {title.get_text() if title else '없음'}")

# 리다이렉트 여부 확인
print(f"최종 URL: {r.url}")
print(f"리다이렉트 횟수: {len(r.history)}")

# 응답의 처음 500자 출력
print("\n=== 응답 HTML 앞부분 (500자) ===")
print(r.text[:500])