import logging
import random
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

for pkg in ["pandas", "requests", "bs4", "tqdm"]:
    try:
        __import__(pkg)
    except ImportError:
        sys.exit(f"[오류] {pkg} 미설치 -> pip install {pkg}")

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm
from pandas.errors import EmptyDataError


# ============================================================
# 설정
# ============================================================
QUERY = "삼성전자"
START_DATE = "2022-01-01"
END_DATE = "2025-12-31"
TARGET_ARTICLES = 7000

SEARCH_URL = "https://search.naver.com/search.naver"

MAX_RETRIES = 3
RETRY_DELAY = 3.0

# 녹화용이라 과한 요청 줄임
SLEEP_MIN = 1.2
SLEEP_MAX = 2.2

RESULTS_PER_PAGE = 10
MAX_PAGES_PER_MONTH = 40
CHECKPOINT_EVERY = 200
MAX_WORKERS = 3

CHECKPOINT_FILE = Path("checkpoint.csv")
OUTPUT_CSV = Path("naver_samsung_news_raw.csv")
FAILED_LOG = Path("failed_urls.log")
DEBUG_LOG = Path("crawler_debug.log")
ERROR_LOG = Path("crawler_error.log")

# 터미널에는 핵심만
CONSOLE_VERBOSE = False

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://search.naver.com/",
}

# 클래스 조각
CLS_CARD = "ELMWWjdcsnaP"
CLS_TITLE = "YEVRSdiwUKMHQ22K"
CLS_NAVER_LINK = "_95mf9WS7UBiO8dnDEKF"
CLS_PRESS = "sds-comps-profile-info-title-text"

DATE_RE = re.compile(r"\d{4}[.\-]\d{2}[.\-]\d{2}|\d+\s*(시간|분|일)\s*전")


# ============================================================
# tqdm + logging 충돌 방지
# ============================================================
class TqdmLoggingHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.write(msg)
        except Exception:
            pass


# ============================================================
# 로거
# ============================================================
def make_logger():
    log = logging.getLogger("crawler")
    log.setLevel(logging.DEBUG)
    log.propagate = False

    if log.handlers:
        log.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 콘솔: 핵심만
    ch = TqdmLoggingHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    log.addHandler(ch)

    # 상세 디버그 로그
    fh_debug = logging.FileHandler(DEBUG_LOG, encoding="utf-8")
    fh_debug.setLevel(logging.DEBUG)
    fh_debug.setFormatter(fmt)
    log.addHandler(fh_debug)

    # 에러 전용 로그
    fh_error = logging.FileHandler(ERROR_LOG, encoding="utf-8")
    fh_error.setLevel(logging.WARNING)
    fh_error.setFormatter(fmt)
    log.addHandler(fh_error)

    return log


log = make_logger()


# ============================================================
# 유틸
# ============================================================
def sleep(extra=0.0):
    time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX) + extra)


def log_fail(url, reason=""):
    try:
        with open(FAILED_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}\t{url}\t{reason}\n")
    except Exception:
        pass


def norm(url):
    return url.split("?")[0].rstrip("/")


def make_session():
    s = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


def build_search_url(ds, de, start):
    params = {
        "where": "news",
        "query": QUERY,
        "pd": 3,
        "ds": ds,
        "de": de,
        "start": start,   # 1,11,21...
        "sort": 0,
    }
    req = requests.Request("GET", SEARCH_URL, params=params).prepare()
    return req.url


def fetch(url):
    s = make_session()
    s.cookies.clear()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = s.get(url, headers=HEADERS, timeout=(5, 15))

            if r.status_code == 404:
                log.debug("404: %s", url)
                return None

            if r.status_code == 429:
                log.debug("[%d/%d] 429: %s", attempt, MAX_RETRIES, url)
                time.sleep(12 * attempt)
                continue

            if r.status_code == 403:
                # 콘솔에는 안 시끄럽게, 파일에만 남김
                log.debug("[%d/%d] 403: %s", attempt, MAX_RETRIES, url)
                time.sleep(5 * attempt)
                continue

            r.raise_for_status()
            return r

        except requests.exceptions.Timeout:
            log.debug("[%d/%d] 타임아웃: %s", attempt, MAX_RETRIES, url)
        except requests.exceptions.ConnectionError as e:
            log.debug("[%d/%d] 연결 오류: %s | %s", attempt, MAX_RETRIES, e, url)
        except requests.exceptions.HTTPError as e:
            log.debug("[%d/%d] HTTP 오류: %s | %s", attempt, MAX_RETRIES, e, url)
        except Exception as e:
            log.warning("예상치 못한 오류: %s | %s", e, url)
            log_fail(url, str(e))
            return None

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY * attempt)

    log_fail(url, f"재시도 {MAX_RETRIES}회 초과")
    return None


def parse_html(resp):
    try:
        return BeautifulSoup(resp.content, "html.parser")
    except Exception as e:
        log.warning("HTML 파싱 실패: %s", e)
        return None


# ============================================================
# 헬퍼: class 조각 검색
# ============================================================
def find_tags(parent, tag, cls_fragment):
    return parent.find_all(tag, class_=lambda c: c and cls_fragment in c)


def find_one(parent, tag, cls_fragment):
    results = find_tags(parent, tag, cls_fragment)
    return results[0] if results else None


# ============================================================
# Step 1 - 월 범위 생성
# ============================================================
def month_ranges(start, end):
    cur = datetime.strptime(start, "%Y-%m-%d")
    final = datetime.strptime(end, "%Y-%m-%d")
    out = []

    while cur <= final:
        if cur.month == 12:
            last = cur.replace(day=31)
            nxt = cur.replace(year=cur.year + 1, month=1, day=1)
        else:
            last = cur.replace(month=cur.month + 1, day=1) - timedelta(days=1)
            nxt = cur.replace(month=cur.month + 1, day=1)

        last = min(last, final)
        out.append((cur.strftime("%Y.%m.%d"), last.strftime("%Y.%m.%d")))
        cur = nxt

    return out


# ============================================================
# Step 2 - 카드 파싱
# ============================================================
def card_to_item(card):
    try:
        naver_a = find_one(card, "a", CLS_NAVER_LINK)
        if not naver_a:
            naver_a = card.find("a", href=re.compile(r"n\.news\.naver\.com/mnews/article"))
        if not naver_a:
            return None

        url = naver_a.get("href", "").strip()
        if not url or "news.naver.com" not in url:
            return None

        title_span = find_one(card, "span", CLS_TITLE)
        if title_span:
            title = title_span.get_text(strip=True)
        else:
            candidates = [
                s.get_text(strip=True)
                for s in card.find_all("span")
                if re.search(r"[가-힣]", s.get_text(strip=True))
            ]
            title = max(candidates, key=len) if candidates else ""

        if not title or len(title) < 5:
            return None

        press_span = find_one(card, "span", CLS_PRESS)
        press = press_span.get_text(strip=True) if press_span else ""

        date = ""
        for sp in card.find_all("span"):
            t = sp.get_text(strip=True)
            if DATE_RE.search(t) and len(t) < 30:
                date = t
                break

        return {
            "title": title,
            "url": url,
            "press": press,
            "date": date
        }

    except Exception as e:
        log.debug("카드 파싱 오류: %s", e)
        return None


def parse_page(soup):
    items = []
    cards = find_tags(soup, "div", CLS_CARD)

    for card in cards:
        item = card_to_item(card)
        if item:
            items.append(item)

    if items:
        return items

    # 폴백
    seen = set()
    naver_links = find_tags(soup, "a", CLS_NAVER_LINK)

    for a in naver_links:
        href = a.get("href", "")
        if "mnews/article" not in href:
            continue

        url = norm(href)
        if url in seen:
            continue
        seen.add(url)

        title, press, date = "", "", ""
        p = a.parent

        for _ in range(7):
            if p is None:
                break

            if not title:
                ts = find_one(p, "span", CLS_TITLE)
                if ts:
                    t = ts.get_text(strip=True)
                    if len(t) > 5:
                        title = t

            if not press:
                pt = find_one(p, "span", CLS_PRESS)
                if pt:
                    press = pt.get_text(strip=True)

            if not date:
                for sp in p.find_all("span"):
                    t = sp.get_text(strip=True)
                    if DATE_RE.search(t) and len(t) < 30:
                        date = t
                        break

            if title and press:
                break

            p = p.parent

        if title:
            items.append({
                "title": title,
                "url": url,
                "press": press,
                "date": date
            })

    return items


# ============================================================
# Step 3&4 - 월별 URL 수집
# ============================================================
def collect_month(ds, de, seen_urls):
    results = []
    empty_streak = 0
    blocked_count = 0

    for page in range(MAX_PAGES_PER_MONTH):
        start = 1 + page * RESULTS_PER_PAGE
        surl = build_search_url(ds, de, start)

        resp = fetch(surl)
        if resp is None:
            blocked_count += 1
            empty_streak += 1

            if empty_streak >= 3:
                break

            sleep(0.5)
            continue

        soup = parse_html(resp)
        if soup is None:
            empty_streak += 1
            if empty_streak >= 3:
                break
            sleep()
            continue

        try:
            items = parse_page(soup)
        except Exception as e:
            log.debug("페이지 파싱 예외: %s", e)
            items = []

        if not items:
            empty_streak += 1
            if empty_streak >= 3:
                break
            sleep()
            continue

        empty_streak = 0
        added = 0

        for item in items:
            url = item.get("url", "").strip()
            if not url or not url.startswith("http"):
                continue
            if "news.naver.com" not in url:
                continue

            n = norm(url)
            if n in seen_urls:
                continue

            seen_urls.add(n)
            item["url"] = n
            results.append(item)
            added += 1

        sleep()

        # 이미 중복만 계속 나오면 빨리 종료
        if added == 0 and page > 5:
            break

    return results, blocked_count


# ============================================================
# Step 5 - 기사 본문 스크래핑
# ============================================================
BODY_SELS = [
    "#dic_area", "#articleBodyContents",
    ".newsct_article", ".news_end",
    "#articeBody", "div[class*='article_body']", "#content",
]

HEAD_TITLE_SELS = [
    "h2#title_area span", ".media_end_head_headline",
    "h3#articleTitle", ".news_headline h4", "title",
]

HEAD_DATE_SELS = [
    ".media_end_head_info_datestamp_time",
    "._ARTICLE_DATE_TIME", "span.t11", ".article_date", "time",
]

_CLEAN_PATS = [
    re.compile(r"\[.*?기자\]"),
    re.compile(r"(c)\s*.+?무단\s*전재.*?재배포\s*금지", re.DOTALL),
    re.compile(r"저작권자\s*.\s*.+", re.MULTILINE),
    re.compile(r"^\s*\S+\s+기자\s+[\w.\-@]+\s*$", re.MULTILINE),
    re.compile(r"^\s*\S+\s+특파원\s*$", re.MULTILINE),
    re.compile(r"[▶☞].*$", re.MULTILINE),
    re.compile(r"【.*?】"),
    re.compile(r"\(끝\)\s*$", re.MULTILINE),
    re.compile(r"^.*?@.*?\.(com|co\.kr|net|org).*$", re.MULTILINE),
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

    try:
        text = _NL3.sub("\n\n", text)
        text = "\n".join(ln.strip() for ln in text.splitlines() if ln.strip())
    except Exception:
        pass

    return text.strip()


def first_text(soup, sels):
    for s in sels:
        try:
            t = soup.select_one(s)
            if t:
                v = t.get_text(strip=True)
                if v:
                    return v
        except Exception:
            pass
    return ""


def scrape(meta):
    url = meta.get("url", "")
    if not url:
        return None

    resp = fetch(url)
    if resp is None:
        return None

    soup = parse_html(resp)
    if soup is None:
        log_fail(url, "파싱 실패")
        return None

    body = None
    for s in BODY_SELS:
        try:
            c = soup.select_one(s)
            if c and len(c.get_text(strip=True)) > 30:
                body = c
                break
        except Exception:
            pass

    if body is None:
        log_fail(url, "본문 없음")
        return None

    raw = body.get_text(separator="\n")

    title = first_text(soup, HEAD_TITLE_SELS) or meta.get("title", "")
    title = re.sub(r"\s*[-|]\s*(네이버\s*뉴스|Naver\s*News).*$", "", title).strip()

    date = None
    try:
        date_tag = soup.select_one(".media_end_head_info_datestamp_time")
        if date_tag and date_tag.has_attr("data-date-time"):
            date = date_tag["data-date-time"]
    except Exception:
        pass

    if not date:
        try:
            meta_date = soup.select_one("meta[property='article:published_time']")
            if meta_date:
                date = meta_date.get("content")
        except Exception:
            pass

    if not date:
        date = first_text(soup, HEAD_DATE_SELS) or meta.get("date", "")

    press = meta.get("press", "")
    try:
        for s in [".media_end_head_top_logo img", "#cp_news_top_logo img"]:
            img = soup.select_one(s)
            if img and img.get("alt", "").strip():
                press = img["alt"].strip()
                break
    except Exception:
        pass

    content = clean_text(raw)

    if len(content) < 50:
        log_fail(url, f"본문 짧음({len(content)}자)")
        return None

    return {
        "title": title,
        "content": content,
        "date": date,
        "press": press,
        "url": url,
    }


# ============================================================
# 체크포인트
# ============================================================
def save_cp(arts):
    if not arts:
        return
    try:
        pd.DataFrame(
            arts,
            columns=["title", "content", "date", "press", "url"]
        ).to_csv(CHECKPOINT_FILE, index=False, encoding="utf-8-sig")
        log.info("체크포인트 저장: %d건", len(arts))
    except Exception as e:
        log.warning("체크포인트 저장 실패: %s", e)


def load_cp():
    if not CHECKPOINT_FILE.exists():
        return []

    try:
        if CHECKPOINT_FILE.stat().st_size == 0:
            return []

        arts = pd.read_csv(CHECKPOINT_FILE, encoding="utf-8-sig").to_dict("records")
        if arts:
            log.info("체크포인트 로드: %d건", len(arts))
        return arts

    except EmptyDataError:
        return []
    except Exception as e:
        log.warning("체크포인트 로드 실패: %s", e)
        return []


# ============================================================
# 메인
# ============================================================
def run(resume=True):
    log.info("=" * 60)
    log.info("[START] 네이버 뉴스 크롤링 시작")
    log.info("검색어: %s", QUERY)
    log.info("수집 기간: %s ~ %s", START_DATE, END_DATE)
    log.info("목표 기사 수: %d건", TARGET_ARTICLES)
    log.info("=" * 60)

    arts = load_cp() if resume else []
    seen = {norm(a["url"]) for a in arts if a.get("url")}
    all_meta = []
    ranges = month_ranges(START_DATE, END_DATE)

    log.info("총 %d개월 | 기존 수집: %d건", len(ranges), len(arts))
    log.info("[Phase 1] URL 수집 시작")

    with tqdm(ranges, desc="월별 URL 수집", unit="월", ncols=90) as bar:
        for idx, (ds, de) in enumerate(bar, start=1):
            try:
                month_items, blocked = collect_month(ds, de, seen)
                all_meta.extend(month_items)

                log.info(
                    "[%02d/%02d] %s 완료 | 신규 URL %d건 | 누적 %d건%s",
                    idx,
                    len(ranges),
                    ds[:7],
                    len(month_items),
                    len(all_meta),
                    f" | 차단/실패 {blocked}회" if blocked else ""
                )

            except KeyboardInterrupt:
                log.info("사용자 중단 - URL 수집 종료")
                break
            except Exception as e:
                log.warning("월 %s 처리 중 오류: %s", ds[:7], e)

            if len(all_meta) >= TARGET_ARTICLES * 1.5:
                log.info("후보 URL 충분 확보 - Phase 1 종료")
                break

    log.info("[Phase 1] 완료 | 후보 URL %d건", len(all_meta))

    if not all_meta:
        log.warning("URL 수집 0건 - 로그 파일(crawler_debug.log) 확인")
        return pd.DataFrame(arts, columns=["title", "content", "date", "press", "url"])

    remaining = TARGET_ARTICLES - len(arts)
    candidates = all_meta[: remaining * 2]

    log.info("[Phase 2] 본문 수집 시작 | 후보 %d건 | 목표 추가 %d건", len(candidates), remaining)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_meta = {executor.submit(scrape, meta): meta for meta in candidates}

        with tqdm(total=len(candidates), desc="본문 수집", unit="건", ncols=90) as bar:
            for future in as_completed(future_to_meta):
                if len(arts) >= TARGET_ARTICLES:
                    log.info("목표 기사 수 달성")
                    break

                meta = future_to_meta[future]

                try:
                    art = future.result()
                except KeyboardInterrupt:
                    log.info("사용자 중단 - 본문 수집 종료")
                    break
                except Exception as e:
                    log.warning("본문 수집 오류: %s | %s", e, meta.get("url", ""))
                    bar.update(1)
                    continue

                if art:
                    arts.append(art)

                    if len(arts) % CHECKPOINT_EVERY == 0:
                        save_cp(arts)

                    # 녹화용: 100건마다만 출력
                    if len(arts) % 100 == 0:
                        log.info("본문 저장 %d건", len(arts))

                bar.update(1)

    log.info("[Phase 2] 완료 | 최종 %d건", len(arts))

    return pd.DataFrame(arts, columns=["title", "content", "date", "press", "url"])


def main():
    t0 = time.time()

    try:
        df = run(resume=True)
    except KeyboardInterrupt:
        log.info("중단됨")
        try:
            if CHECKPOINT_FILE.exists() and CHECKPOINT_FILE.stat().st_size > 0:
                df = pd.read_csv(CHECKPOINT_FILE, encoding="utf-8-sig")
            else:
                df = pd.DataFrame(columns=["title", "content", "date", "press", "url"])
        except Exception:
            df = pd.DataFrame(columns=["title", "content", "date", "press", "url"])
    except Exception as e:
        log.warning("비정상 종료: %s", e)
        raise

    if df.empty:
        log.warning("수집 결과 0건 - CSV 저장 생략")
    else:
        saved = False
        for path in [OUTPUT_CSV, Path.home() / OUTPUT_CSV.name]:
            try:
                df.to_csv(path, index=False, encoding="utf-8-sig")
                log.info("저장 완료: %s", path.resolve())
                saved = True
                break
            except Exception as e:
                log.warning("저장 실패 (%s): %s", path, e)

        if saved:
            try:
                CHECKPOINT_FILE.unlink(missing_ok=True)
            except Exception:
                pass

    elapsed = time.time() - t0
    log.info("=" * 60)
    log.info("완료 | %d건 | %d분 %d초", len(df), int(elapsed // 60), int(elapsed % 60))
    log.info("=" * 60)

    if not df.empty:
        sample = df.iloc[0]
        log.info("[SAMPLE] 제목: %s", sample["title"])
        log.info("[SAMPLE] 언론사: %s", sample["press"])
        log.info("[SAMPLE] 날짜: %s", sample["date"])
        log.info("[SAMPLE] 본문 길이: %d자", len(sample["content"]))


if __name__ == "__main__":
    main()