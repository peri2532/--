"""
debug_logic.py  —  collect_urls_for_month 로직 직접 실행
"""
import re, sys, requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://search.naver.com/",
}

QUERY = "삼성전자"
_DATE_RE = re.compile(r"\d{4}[.\-]\d{2}[.\-]\d{2}|\d+\s*(시간|분|일)\s*전")

CARD_SELECTORS = [
    "div[class*='OaLkxeV3OLBNnXoC']",
    "div[class*='iSXLcjplJYeJhPKDxTPS']",
]
TITLE_SPAN_SELECTORS = [
    "span[class*='_9NVs5F7DbeVKmhcwTTdw']",
    "span[class*='sds-comps-text-ellipsis-1']",
]
NAVER_LINK_SELECTORS = [
    "a[class*='GOWcekJV4wHE8GArxPuu']",
    "a[href*='n.news.naver.com/mnews/article']",
]

def normalize_url(url):
    return url.split("?")[0].rstrip("/")

def extract_item_from_card(card):
    naver_url = ""
    for sel in NAVER_LINK_SELECTORS:
        a = card.select_one(sel)
        if a:
            naver_url = a.get("href", "").strip()
            break
    if not naver_url or "news.naver.com" not in naver_url:
        print(f"    → URL 없음 또는 naver 아님: {naver_url!r:.50}")
        return None

    title = ""
    for sel in TITLE_SPAN_SELECTORS:
        span = card.select_one(sel)
        if span:
            t = span.get_text(strip=True)
            if len(t) > 5:
                title = t
                break
    if not title:
        best = ""
        for span in card.find_all("span"):
            t = span.get_text(strip=True)
            if re.search(r"[가-힣]", t) and len(t) > len(best):
                best = t
        title = best

    if not title or len(title) < 5:
        print(f"    → 제목 없음")
        return None

    press_tag = card.select_one(".sds-comps-profile-info-title-text")
    press = press_tag.get_text(strip=True) if press_tag else ""

    date = ""
    for span in card.find_all("span"):
        t = span.get_text(strip=True)
        if _DATE_RE.search(t) and len(t) < 30:
            date = t
            break

    return {"title": title, "url": naver_url, "press": press, "date": date}


# ── 실제 2022.01 요청 ────────────────────────────────────────────────────────
url = (
    f"https://search.naver.com/search.naver"
    f"?where=news&query={requests.utils.quote(QUERY, safe='')}"
    f"&pd=3&ds=2022.01.01&de=2022.01.31&start=0&sort=0"
)

print(f"요청 URL: {url}\n")
resp = requests.get(url, headers=HEADERS, timeout=10)
print(f"HTTP: {resp.status_code} | 크기: {len(resp.content):,} bytes")

resp.encoding = resp.apparent_encoding or "utf-8"
soup = BeautifulSoup(resp.text, "html.parser")

# ── 카드 파싱 ────────────────────────────────────────────────────────────────
print("\n[카드 파싱]")
items = []
for card_sel in CARD_SELECTORS:
    cards = soup.select(card_sel)
    print(f"  셀렉터 '{card_sel}': {len(cards)}개")
    if not cards:
        continue
    for i, card in enumerate(cards):
        item = extract_item_from_card(card)
        if item:
            items.append(item)
            print(f"  카드[{i}] ✅ 제목: {item['title'][:40]!r} | URL: {item['url'][:50]}")
        else:
            print(f"  카드[{i}] ❌ 추출 실패")
    if items:
        break

print(f"\n파싱된 items: {len(items)}개")

# ── URL 필터 ─────────────────────────────────────────────────────────────────
print("\n[URL 필터 통과 테스트]")
seen_urls = set()
new_count = 0
for item in items:
    url = item.get("url", "").strip()
    print(f"  원본 URL: {url[:70]}")
    if not url or not url.startswith("http"):
        print(f"    → ❌ http 아님")
        continue
    if "news.naver.com" not in url:
        print(f"    → ❌ naver 아님")
        continue
    norm = normalize_url(url)
    if norm in seen_urls:
        print(f"    → ❌ 중복")
        continue
    seen_urls.add(norm)
    new_count += 1
    print(f"    → ✅ 통과 (정규화: {norm[:60]})")

print(f"\nnew_count = {new_count}")
print(f"seen_urls = {len(seen_urls)}개")

if new_count == 0:
    print("\n❌ new_count가 0 — 여기서 break 됩니다!")
    print("   원인: 위의 ❌ 표시 확인")
else:
    print(f"\n✅ {new_count}건 정상 통과 — 크롤러가 수집해야 합니다")
    print("   → 크롤러에서 여전히 0건이면 다른 곳에 버그가 있습니다")