# check2.py 로 저장 후 실행
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://search.naver.com/",
}

r = requests.get(
    "https://search.naver.com/search.naver?where=news&query=%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90&pd=3&ds=2022.01.01&de=2022.01.31&start=0&sort=0",
    headers=HEADERS, timeout=10
)

print("크기:", len(r.content))
print("OaLkxeV3:", "OaLkxeV3" in r.text)
print("삼성전자:", "삼성전자" in r.text)
print("URL:", r.url)

# 페이지 제목 확인
from bs4 import BeautifulSoup
soup = BeautifulSoup(r.content, "html.parser")
title = soup.find("title")
print("페이지 제목:", title.text if title else "없음")
# 기존 코드 아래에 추가
with open("live2.html", "w", encoding="utf-8") as f:
    f.write(r.text)
print("live2.html 저장 완료")

# 네이버뉴스 링크 찾기
links = soup.find_all("a", href=lambda h: h and "n.news.naver.com/mnews/article" in h)
print(f"\nn.news.naver.com 링크 수: {len(links)}")
if links:
    a = links[0]
    print("첫 번째 링크 href:", a.get("href", "")[:80])
    print("첫 번째 링크 class:", a.get("class", []))
    # 부모 태그 클래스 확인
    p = a.parent
    for i in range(5):
        if p:
            print(f"  부모{i+1} tag={p.name} class={p.get('class', [])[:2]}")
            p = p.parent
# 기존 코드 아래에 추가
# 카드 div 찾기 - 네이버뉴스 링크를 포함하는 가장 가까운 공통 조상 찾기
print("\n=== 링크 주변 구조 탐색 ===")
a = links[0]
p = a.parent
for i in range(10):
    if p is None:
        break
    classes = p.get("class", [])
    # 형제 링크가 여러 개 있는 div = 카드일 가능성 높음
    child_links = p.find_all("a", href=lambda h: h and "n.news.naver.com" in str(h))
    print(f"부모{i+1} tag={p.name} links={len(child_links)} class={classes[:3]}")
    if len(child_links) >= 1 and p.name == "div":
        print(f"  ^^^ 카드 후보! 클래스: {classes}")
    p = p.parent

# 전체 기사 카드처럼 보이는 구조 찾기
print("\n=== 전체 구조에서 카드 패턴 찾기 ===")
all_links = soup.find_all("a", href=lambda h: h and "n.news.naver.com/mnews/article" in str(h))
print(f"총 네이버뉴스 링크: {len(all_links)}개")
for a in all_links[:3]:
    print(f"\nhref: {a['href'][:60]}")
    print(f"class: {a.get('class', [])}")
