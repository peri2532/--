"""
realtime_pipeline.py - 실시간 뉴스 수집 + 감성분석 파이프라인
==============================================================
실행하면 오늘 날짜 삼성전자 뉴스를 수집하고
감성분석까지 자동으로 수행합니다.

실행: python realtime_pipeline.py
출력: realtime_news.csv (누적 저장)
"""

import re
import sys
import time
import random
import logging
from datetime import datetime, timedelta
from pathlib import Path

for pkg in ["pandas", "requests", "bs4", "transformers", "torch"]:
    try:
        __import__(pkg)
    except ImportError:
        sys.exit(f"[오류] {pkg} 미설치 -> py -m pip install {pkg}")

import pandas as pd
import requests
import torch
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from transformers import pipeline

# ============================================================
# 설정
# ============================================================
QUERY      = "삼성전자"
OUTPUT_CSV = Path("realtime_news.csv")

# 오늘 날짜 기준으로 수집 (어제~오늘)
TODAY     = datetime.now().strftime("%Y.%m.%d")
YESTERDAY = (datetime.now() - timedelta(days=1)).strftime("%Y.%m.%d")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://search.naver.com/",
}

SEARCH_URL = (
    "https://search.naver.com/search.naver"
    "?where=news&query={query}&pd=3&ds={ds}&de={de}&start={start}&sort=1"
    # sort=1: 최신순 (실시간 수집이므로 최신순이 더 적합)
)

# 현재 유효한 클래스명 (변경 시 업데이트 필요)
CLS_CARD       = "NeAafkdKXmnzjcAF_y01"
CLS_TITLE      = "_9NVs5F7DbeVKmhcwTTdw"
CLS_NAVER_LINK = "ByqJOtaiD32azLYpWrSb"
CLS_PRESS      = "sds-comps-profile-info-title-text"

BODY_SELS = [
    "#dic_area", "#articleBodyContents",
    ".newsct_article", ".news_end",
    "#articeBody", "#content",
]
HEAD_TITLE_SELS = [
    "h2#title_area span", ".media_end_head_headline",
    "h3#articleTitle", "title",
]
HEAD_DATE_SELS = [
    ".media_end_head_info_datestamp_time",
    "._ARTICLE_DATE_TIME", "span.t11",
]

DATE_RE = re.compile(r"\d{4}[.\-]\d{2}[.\-]\d{2}")

# ============================================================
# 로거
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("realtime")

# ============================================================
# 헬퍼 함수
# ============================================================
def make_session():
    s = requests.Session()
    r = Retry(total=2, backoff_factor=1,
              status_forcelist=[500, 502, 503, 504],
              allowed_methods=["GET"], raise_on_status=False)
    s.mount("https://", HTTPAdapter(max_retries=r))
    s.mount("http://",  HTTPAdapter(max_retries=r))
    return s

def fetch(url):
    s = make_session()
    s.cookies.clear()
    try:
        r = s.get(url, headers=HEADERS, timeout=(5, 15))
        r.raise_for_status()
        return r
    except Exception as e:
        log.warning("요청 실패: %s", e)
        return None

def parse_html(resp):
    try:
        return BeautifulSoup(resp.content, "html.parser")
    except Exception:
        return None

def find_tags(parent, tag, cls_fragment):
    return parent.find_all(tag, class_=lambda c: c and cls_fragment in c)

def find_one(parent, tag, cls_fragment):
    results = find_tags(parent, tag, cls_fragment)
    return results[0] if results else None

def norm(url):
    return url.split("?")[0].rstrip("/")

def sleep():
    time.sleep(random.uniform(0.8, 1.5))

# ============================================================
# Step 1 - 오늘 뉴스 URL 수집
# ============================================================
def collect_today_urls():
    """오늘 날짜 뉴스 URL 수집 (최대 5페이지)"""
    log.info("오늘 날짜 뉴스 수집 시작: %s ~ %s", YESTERDAY, TODAY)
    
    seen = set()
    results = []

    for page in range(5):  # 최대 5페이지 (50건)
        offset = page * 10
        url = SEARCH_URL.format(
            query=requests.utils.quote(QUERY, safe=""),
            ds=YESTERDAY, de=TODAY, start=offset
        )

        resp = fetch(url)
        if resp is None:
            break

        soup = parse_html(resp)
        if soup is None:
            break

        # 클래스명 확인
        html_text = str(soup)
        log.info("  HTML크기: %d / ByqJOtaiD: %s / 삼성전자: %s",
                 len(html_text),
                 "ByqJOtaiD32azLYpWrSb" in html_text,
                 "삼성전자" in html_text)

        # 네이버 링크 수집
       # 네이버 링크 수집 - href 직접 검색 방식으로 변경
        links = soup.find_all("a", href=lambda h: h and "n.news.naver.com/mnews/article" in str(h))
        added = 0
        for a in links:
            href = a.get("href", "")
            if not href:
                continue

            n = norm(href)
            if n in seen:
                continue
            seen.add(n)

            # 제목 찾기
          # 제목 찾기 - a 태그 텍스트 직접 사용
            # 제목 찾기 - 카드(NeAafkdKXmnzjcAF_y01)의 첫 번째 긴 span
            title = ""
            p = a.parent
            for _ in range(8):
                if p is None:
                    break
                cls = p.get("class", [])
                if "NeAafkdKXmnzjcAF_y01" in cls:
                    # 카드 div 찾음 - 여기서 제목 추출
                    for sp in p.find_all("span"):
                        t = sp.get_text(strip=True)
                        if len(t) > 10 and any("\uac00" <= c <= "\ud7a3" for c in t):
                            title = t
                            break
                    break
                p = p.parent

            # 언론사 찾기
            press = ""
            p = a.parent
            for _ in range(8):
                if p is None:
                    break
                ps = find_one(p, "span", CLS_PRESS)
                if ps:
                    press = ps.get_text(strip=True)
                    break
                p = p.parent

            if not title:
                title = "제목없음"
            results.append({"title": title, "url": n, "press": press})
            added += 1


        log.info("  p%d: +%d건 (누적 %d건)", page + 1, added, len(results))

        if added == 0:
            break
        sleep()

    log.info("URL 수집 완료: %d건", len(results))
    return results

# ============================================================
# Step 2 - 본문 스크래핑
# ============================================================
_CLEAN_PATS = [
    re.compile(r"\[.*?기자\]"),
    re.compile(r"저작권자\s*.\s*.+", re.MULTILINE),
    re.compile(r"^\s*\S+\s+기자\s+[\w.\-@]+\s*$", re.MULTILINE),
    re.compile(r"[▶☞].*$", re.MULTILINE),
    re.compile(r"^.*?@.*?\.(com|co\.kr).*$", re.MULTILINE),
]
_NL3 = re.compile(r"\n{3,}")

def clean_text(text):
    if not isinstance(text, str):
        return ""
    for p in _CLEAN_PATS:
        try:
            text = p.sub("", text)
        except Exception:
            pass
    text = _NL3.sub("\n\n", text)
    text = "\n".join(ln.strip() for ln in text.splitlines() if ln.strip())
    return text.strip()

def scrape_article(meta):
    """기사 본문 스크래핑"""
    url = meta.get("url", "")
    resp = fetch(url)
    if resp is None:
        return None

    soup = parse_html(resp)
    if soup is None:
        return None

    # 본문
    body = None
    for sel in BODY_SELS:
        try:
            c = soup.select_one(sel)
            if c and len(c.get_text(strip=True)) > 30:
                body = c
                break
        except Exception:
            pass

    if body is None:
        return None

    content = clean_text(body.get_text(separator="\n"))
    if len(content) < 50:
        return None

    # 삼성전자 관련 기사 필터링
    # 제목 또는 본문 앞 300자에 삼성 관련 키워드가 없으면 제외
    SAMSUNG_KEYWORDS = ["삼성전자", "삼성", "갤럭시", "Galaxy"]
    title_text = meta.get("title", "")
    if not any(kw in title_text for kw in SAMSUNG_KEYWORDS):
        log.info("  삼성 무관 기사 제외: %s", title_text[:40])
        return None

    # 제목
    title = meta.get("title", "")
    for sel in HEAD_TITLE_SELS:
        try:
            t = soup.select_one(sel)
            if t and t.get_text(strip=True):
                title = t.get_text(strip=True)
                title = re.sub(r"\s*[-|]\s*(네이버\s*뉴스).*$", "", title).strip()
                break
        except Exception:
            pass

    # 날짜
    date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        dt = soup.select_one(".media_end_head_info_datestamp_time")
        if dt and dt.has_attr("data-date-time"):
            date = dt["data-date-time"]
    except Exception:
        pass

    return {
        "title":   title,
        "content": content,
        "date":    date,
        "press":   meta.get("press", ""),
        "url":     url,
    }

# ============================================================
# Step 3 - 감성분석
# ============================================================
def analyze_sentiment(articles):
    """수집된 기사에 감성분석 적용"""
    log.info("감성분석 시작 (모델: snunlp/KR-FinBert-SC)")
    
    device = 0 if torch.cuda.is_available() else -1
    classifier = pipeline(
        "text-classification",
        model="snunlp/KR-FinBert-SC",
        device=device,
        max_length=512,
        truncation=True,
    )

    score_map = {"positive": 1, "neutral": 0, "negative": -1}

    for art in articles:
        text = art["title"] + " " + art["title"] + " " + art["content"][:200]
        try:
            result = classifier(text[:512])[0]
            label = result["label"].lower()
            score = result["score"]
            if score < 0.6:
                label = "neutral"
            art["sentiment"]     = label
            art["sentiment_score"] = round(score, 4)
            art["sentiment_num"] = score_map.get(label, 0)
        except Exception as e:
            log.warning("감성분석 실패: %s", e)
            art["sentiment"]       = "neutral"
            art["sentiment_score"] = 0.0
            art["sentiment_num"]   = 0

    log.info("감성분석 완료")
    return articles

# ============================================================
# Step 4 - CSV 저장 (누적)
# ============================================================
def save_to_csv(articles):
    """기존 CSV에 새 기사 추가 (중복 제거)"""
    df_new = pd.DataFrame(articles)

    if OUTPUT_CSV.exists():
        df_old = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig")
        # URL 기준 중복 제거
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
        df_combined = df_combined.drop_duplicates(subset=["url"], keep="last")
        # 날짜 기준 정렬
        df_combined = df_combined.sort_values("date", ascending=False)
    else:
        df_combined = df_new

    df_combined.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    return df_combined

# ============================================================
# 메인
# ============================================================
def main():
    print("=" * 55)
    print("  삼성전자 실시간 뉴스 수집 + 감성분석 파이프라인")
    print(f"  수집 기간: {YESTERDAY} ~ {TODAY}")
    print("=" * 55)

    # Step 1: URL 수집
    url_list = collect_today_urls()
    if not url_list:
        log.error("수집된 URL이 없습니다. 클래스명 변경 여부 확인하세요.")
        return

    # 기존 CSV의 URL 로드 (중복 방지)
    existing_urls = set()
    if OUTPUT_CSV.exists():
        df_old = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig")
        existing_urls = set(df_old["url"].dropna().tolist())
        log.info("기존 데이터: %d건 (중복 제거 기준)", len(existing_urls))

    # Step 2: 본문 스크래핑
    articles = []
    new_count = 0
    log.info("\n본문 스크래핑 시작...")
    for i, meta in enumerate(url_list):
        if meta["url"] in existing_urls:
            log.info("  [%d/%d] 중복 스킵: %s", i+1, len(url_list), meta["title"][:30])
            continue

        art = scrape_article(meta)
        if art:
            articles.append(art)
            new_count += 1
            log.info("  [%d/%d] 수집: %s", i+1, len(url_list), art["title"][:40])
        sleep()

    if not articles:
        log.info("새로운 기사가 없습니다.")
        return

    log.info("새 기사 수집 완료: %d건", new_count)

    # Step 3: 감성분석
    articles = analyze_sentiment(articles)

    # Step 4: 저장
    df = save_to_csv(articles)
    log.info("\n저장 완료: %s (%d건)", OUTPUT_CSV, len(df))

    # 결과 출력
    print("\n=== 오늘 수집된 기사 ===")
    df_today = pd.DataFrame(articles)
    for _, row in df_today.iterrows():
        emoji = {"positive": "😊", "negative": "😟", "neutral": "😐"}.get(
            row.get("sentiment", "neutral"), "😐")
        print(f"  {emoji} [{row.get('sentiment','?'):8s}] {row['title'][:45]}")

    print("\n=== 감성 분포 ===")
    counts = df_today["sentiment"].value_counts()
    for label, count in counts.items():
        print(f"  {label:10s}: {count}건")

    print(f"\n총 누적 데이터: {len(df)}건")
    print(f"저장 위치: {OUTPUT_CSV.resolve()}")

if __name__ == "__main__":
    main()