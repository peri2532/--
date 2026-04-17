"""
crawler.py  -  네이버 뉴스 크롤러 (삼성전자, 2022-2025)
==========================================================
[핵심 수정] CSS class*= 셀렉터 → find_all(class_=lambda) 방식으로 교체
  이유: BeautifulSoup에서 class*='난독화클래스명' 형태의 셀렉터는
        따옴표 중첩으로 인해 실제로 0건을 반환하는 버그가 있음.
        find_all(class_=lambda c: '클래스명' in c) 로 대체하면 정상 동작.

검증 완료 셀렉터 (debug_logic.py 기준):
  카드    : class 에 'OaLkxeV3OLBNnXoC' 포함 div
  제목    : class 에 '_9NVs5F7DbeVKmhcwTTdw' 포함 span
  네이버  : class 에 'GOWcekJV4wHE8GArxPuu' 포함 a
  언론사  : class 에 'sds-comps-profile-info-title-text' 포함 span

실행:  python crawler.py
출력:  naver_samsung_news_raw.csv
"""

import logging, os, random, re, sys, time
from datetime import datetime, timedelta
from pathlib import Path

for pkg in ["pandas", "requests", "bs4", "tqdm"]:
    try:
        __import__(pkg)
    except ImportError:
        sys.exit(f"[오류] {pkg} 미설치 -> pip install {pkg}")

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3.util.retry import Retry


# ============================================================
# 설정
# ============================================================
QUERY           = "삼성전자"
START_DATE      = "2022-01-01"
END_DATE        = "2025-12-31"
TARGET_ARTICLES = 7_000

SEARCH_URL = (
    "https://search.naver.com/search.naver"
    "?where=news&query={query}&pd=3&ds={ds}&de={de}&start={start}&sort=0"
)

MAX_RETRIES         = 3
RETRY_DELAY         = 3.0
SLEEP_MIN           = 0.8
SLEEP_MAX           = 1.5
RESULTS_PER_PAGE    = 10
MAX_PAGES_PER_MONTH = 40
CHECKPOINT_EVERY    = 200

CHECKPOINT_FILE = Path("checkpoint.csv")
OUTPUT_CSV      = Path("naver_samsung_news_raw.csv")
FAILED_LOG      = Path("failed_urls.log")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    # Accept-Encoding 을 명시하지 않으면 requests 가 자동으로
    # gzip 압축을 해제해줌. 명시하면 직접 해제해야 해서 제거.
    "Referer": "https://search.naver.com/",
}

# ── 클래스명 조각 (find_all lambda 방식으로 사용) ──────────────────────────────
# CSS class*= 셀렉터는 BeautifulSoup에서 따옴표 중첩 버그가 있어 사용 금지.
# 대신 아래 문자열을 lambda 함수로 검사한다.
CLS_CARD        = "NeAafkdKXmnzjcAF_y01"
CLS_TITLE       = "_9NVs5F7DbeVKmhcwTTdw"
CLS_NAVER_LINK  = "ByqJOtaiD32azLYpWrSb"
CLS_PRESS       = "sds-comps-profile-info-title-text"

DATE_RE = re.compile(r"\d{4}[.\-]\d{2}[.\-]\d{2}|\d+\s*(시간|분|일)\s*전")


# ============================================================
# 헬퍼: class 조각 검색
# ============================================================
def find_tags(parent, tag, cls_fragment):
    """cls_fragment 를 class 에 포함하는 tag 태그 전체 반환.

    BeautifulSoup class_=lambda 동작 방식:
      lambda 는 각 클래스명(문자열)마다 개별 호출됨.
      c = 'OaLkxeV3OLBNnXoCET9Z' 처럼 단일 문자열로 전달.
      따라서 cls_fragment in c 로 부분 일치 검사하면 됨.
    """
    return parent.find_all(tag, class_=lambda c: c and cls_fragment in c)

def find_one(parent, tag, cls_fragment):
    """find_tags 의 첫 번째 결과. 없으면 None."""
    results = find_tags(parent, tag, cls_fragment)
    return results[0] if results else None


# ============================================================
# 로거
# ============================================================
def make_logger():
    log = logging.getLogger("crawler")
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(sh)
    try:
        fh = logging.FileHandler("crawler.log", encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except Exception:
        pass
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
    r = Retry(total=2, backoff_factor=1,
              status_forcelist=[500, 502, 503, 504],
              allowed_methods=["GET"], raise_on_status=False)
    s.mount("https://", HTTPAdapter(max_retries=r))
    s.mount("http://",  HTTPAdapter(max_retries=r))
    return s

def fetch(url, session=None):
    # Session 쿠키 누적으로 봇 감지되므로 매번 새 Session 사용
    s = make_session()
    s.cookies.clear()  # 쿠키 완전 초기화
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = s.get(url, headers=HEADERS, timeout=(5, 15))
            if r.status_code == 404:
                return None
            if r.status_code == 429:
                time.sleep(15 * attempt)
                continue
            if r.status_code == 403:
                sleep(extra=5.0)
            r.raise_for_status()
            return r
        except requests.exceptions.Timeout:
            log.warning("[%d/%d] 타임아웃: %s", attempt, MAX_RETRIES, url)
        except requests.exceptions.ConnectionError as e:
            log.warning("[%d/%d] 연결 오류: %s", attempt, MAX_RETRIES, e)
        except requests.exceptions.HTTPError as e:
            log.warning("[%d/%d] HTTP 오류: %s", attempt, MAX_RETRIES, e)
        except Exception as e:
            log.error("예상치 못한 오류: %s | %s", e, url)
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
# Step 1 - 월 범위 생성
# ============================================================
def month_ranges(start, end):
    cur   = datetime.strptime(start, "%Y-%m-%d")
    final = datetime.strptime(end,   "%Y-%m-%d")
    out   = []
    while cur <= final:
        if cur.month == 12:
            last = cur.replace(day=31)
            nxt  = cur.replace(year=cur.year + 1, month=1, day=1)
        else:
            last = cur.replace(month=cur.month + 1, day=1) - timedelta(days=1)
            nxt  = cur.replace(month=cur.month + 1, day=1)
        last = min(last, final)
        out.append((cur.strftime("%Y.%m.%d"), last.strftime("%Y.%m.%d")))
        cur = nxt
    return out


# ============================================================
# Step 2 - 카드 파싱 (find_all lambda 방식)
# ============================================================
def card_to_item(card):
    """
    카드 div 1개 -> {title, url, press, date} 또는 None.

    find_all(class_=lambda) 방식 사용 이유:
      CSS class*= 셀렉터에 난독화 클래스명을 넣으면
      BeautifulSoup이 0건을 반환하는 버그가 있음.
    """
    try:
        # ① 네이버 URL
        # CLS_NAVER_LINK 를 class 에 포함하는 <a> 태그
        naver_a = find_one(card, "a", CLS_NAVER_LINK)
        if not naver_a:
            # 폴백: href 에 mnews/article 포함
            naver_a = card.find("a", href=re.compile(r"n\.news\.naver\.com/mnews/article"))
        if not naver_a:
            return None
        url = naver_a.get("href", "").strip()
        if not url or "news.naver.com" not in url:
            return None

        # ② 제목
        # CLS_TITLE 을 class 에 포함하는 <span>
        title_span = find_one(card, "span", CLS_TITLE)
        if title_span:
            title = title_span.get_text(strip=True)
        else:
            # 폴백: 카드 내 한글 포함 가장 긴 span
            candidates = [
                s.get_text(strip=True)
                for s in card.find_all("span")
                if re.search(r"[가-힣]", s.get_text(strip=True))
            ]
            title = max(candidates, key=len) if candidates else ""

        if not title or len(title) < 5:
            return None

        # ③ 언론사
        press_span = find_one(card, "span", CLS_PRESS)
        press = press_span.get_text(strip=True) if press_span else ""

        # ④ 날짜
        date = ""
        for sp in card.find_all("span"):
            t = sp.get_text(strip=True)
            if DATE_RE.search(t) and len(t) < 30:
                date = t
                break

        return {"title": title, "url": url, "press": press, "date": date}

    except Exception as e:
        log.warning("카드 파싱 오류: %s", e)
        return None


def parse_page(soup):
    """
    검색 결과 페이지 -> 기사 메타 목록.
    1순위: CLS_CARD div 카드 파싱
    2순위: CLS_NAVER_LINK 링크 직접 수집
    """
    items = []

    # 1순위: CLS_CARD 클래스를 포함하는 div 탐색
    cards = find_tags(soup, "div", CLS_CARD)
    # 진단: HTML 크기와 클래스명 존재 여부 직접 확인
    html_text = str(soup)
    log.info("    HTML 크기: %d bytes", len(html_text))
    log.info("    OaLkxeV3 포함: %s", "OaLkxeV3" in html_text)
    log.info("    GOWcekJV4 포함: %s", "GOWcekJV4" in html_text)
    log.info("    카드 발견: %d개", len(cards))

    for card in cards:
        item = card_to_item(card)
        if item:
            items.append(item)

    if items:
        log.info("    카드 파싱 성공: %d건", len(items))
        return items

    # 2순위 폴백: CLS_NAVER_LINK 링크 직접 수집
    log.info("    카드 파싱 0건 -> 링크 직접 수집 폴백")
    seen = set()

    naver_links = find_tags(soup, "a", CLS_NAVER_LINK)
    log.info("    CLS_NAVER_LINK 링크: %d개", len(naver_links))

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
            items.append({"title": title, "url": url,
                          "press": press, "date": date})

    return items


# ============================================================
# Step 3&4 - 월별 URL 수집
# ============================================================
def collect_month(session, ds, de, seen_urls):
    results     = []
    empty_streak = 0

    for page in range(MAX_PAGES_PER_MONTH):
        offset = page * RESULTS_PER_PAGE
        try:
            surl = SEARCH_URL.format(
                query=requests.utils.quote(QUERY, safe=""),
                ds=ds, de=de, start=offset,
            )
        except Exception as e:
            log.error("URL 생성 실패: %s", e)
            break

        resp = fetch(surl, session)
        if resp is None:
            empty_streak += 1
            if empty_streak >= 3:
                break
            sleep()
            continue

        s = parse_html(resp)
        if s is None:
            empty_streak += 1
            if empty_streak >= 3:
                break
            sleep()
            continue

        try:
            items = parse_page(s)
        except Exception as e:
            log.error("페이지 파싱 예외: %s", e)
            items = []

        if not items:
            empty_streak += 1
            log.info("    %s p%d: 0건 (연속 빈 %d회)", ds[:7], page + 1, empty_streak)
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

        log.info("    %s p%d: +%d건 (페이지 %d건)", ds[:7], page + 1, added, len(items))
        sleep()

        if added == 0 and page > 0:
            break

    return results


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

def scrape(session, meta):
    url = meta.get("url", "")
    if not url:
        return None

    resp = fetch(url, session)
    if resp is None:
        return None

    soup = parse_html(resp)
    if soup is None:
        log_fail(url, "파싱 실패")
        return None

    # =========================
    # 1. 본문 추출
    # =========================
    body = None
    for s in BODY_SELS:
        try:
            c = soup.select_one(s)
            if c and len(c.get_text(strip=True)) > 30:
                body = c
                break
        except:
            pass

    if body is None:
        log_fail(url, "본문 없음")
        return None

    raw = body.get_text(separator="\n")

    # =========================
    # 2. 제목
    # =========================
    title = first_text(soup, HEAD_TITLE_SELS) or meta.get("title", "")
    title = re.sub(r"\s*[-|]\s*(네이버\s*뉴스|Naver\s*News).*$", "", title).strip()

    # =========================
    # 3. 날짜 (🔥 핵심 수정)
    # =========================
    date = None

    # 1순위: data-date-time (가장 정확)
    try:
        date_tag = soup.select_one(".media_end_head_info_datestamp_time")
        if date_tag and date_tag.has_attr("data-date-time"):
            date = date_tag["data-date-time"]
    except:
        pass

    # 2순위: meta 태그 (언론사 사이트 대응)
    if not date:
        try:
            meta_date = soup.select_one("meta[property='article:published_time']")
            if meta_date:
                date = meta_date.get("content")
        except:
            pass

    # 3순위: 기존 방식 fallback
    if not date:
        date = first_text(soup, HEAD_DATE_SELS) or meta.get("date", "")

    # =========================
    # 4. 언론사
    # =========================
    press = meta.get("press", "")
    try:
        for s in [".media_end_head_top_logo img", "#cp_news_top_logo img"]:
            img = soup.select_one(s)
            if img and img.get("alt", "").strip():
                press = img["alt"].strip()
                break
    except:
        pass

    # =========================
    # 5. 본문 정제
    # =========================
    content = clean_text(raw)

    if len(content) < 50:
        log_fail(url, f"본문 짧음({len(content)}자)")
        return None

    return {
        "title": title,
        "content": content,
        "date": date,
        "press": press,
        "url": url
    }
# ============================================================
# 체크포인트
# ============================================================
def save_cp(arts):
    if not arts:
        return
    try:
        pd.DataFrame(arts, columns=["title", "content", "date", "press", "url"]) \
          .to_csv(CHECKPOINT_FILE, index=False, encoding="utf-8-sig")
        log.info("체크포인트 저장: %d건", len(arts))
    except Exception as e:
        log.warning("체크포인트 저장 실패: %s", e)

def load_cp():
    if not CHECKPOINT_FILE.exists():
        return []
    try:
        arts = pd.read_csv(CHECKPOINT_FILE, encoding="utf-8-sig").to_dict("records")
        log.info("체크포인트 로드: %d건", len(arts))
        return arts
    except Exception as e:
        log.warning("체크포인트 로드 실패: %s", e)
        return []


# ============================================================
# 메인
# ============================================================
def run(resume=True):
    log.info("=" * 60)
    log.info("네이버 뉴스 크롤러")
    log.info("  검색어 : %s | 기간: %s ~ %s | 목표: %d건",
             QUERY, START_DATE, END_DATE, TARGET_ARTICLES)
    log.info("=" * 60)

    arts     = load_cp() if resume else []
    seen     = {norm(a["url"]) for a in arts if a.get("url")}
    all_meta = []
    session  = make_session()
    ranges   = month_ranges(START_DATE, END_DATE)

    log.info("총 %d개월 | 이미 수집: %d건", len(ranges), len(arts))

    # Phase 1: URL 수집
    log.info("\n[Phase 1] URL 수집 시작")
    with tqdm(ranges, desc="월별 수집", unit="월") as bar:
        for ds, de in bar:
            bar.set_postfix({"월": ds[:7], "URL": len(seen)})
            try:
                m = collect_month(session, ds, de, seen)
                all_meta.extend(m)
                log.info("  %s 완료: +%d건 (누적 %d개)", ds[:7], len(m), len(seen))
            except KeyboardInterrupt:
                log.info("중단 - 수집된 URL로 Phase 2 진행")
                break
            except Exception as e:
                log.error("월 %s 오류 (스킵): %s", ds[:7], e)
            if len(all_meta) >= TARGET_ARTICLES * 1.5:
                log.info("URL 충분히 확보 - Phase 1 종료")
                break

    log.info("[Phase 1] 완료 - 후보 URL: %d개", len(all_meta))

    if not all_meta:
        log.error(
            "URL 수집 0건!\n"
            "  가능한 원인:\n"
            "  1) 네이버 클래스명 변경 -> CLS_CARD / CLS_TITLE 확인\n"
            "  2) 봇 차단 -> SLEEP_MIN/MAX 늘리기\n"
            "  3) 네트워크 오류 -> crawler.log 확인"
        )
        return pd.DataFrame(arts, columns=["title", "content", "date", "press", "url"])

    # Phase 2: 본문 스크래핑
    remaining  = TARGET_ARTICLES - len(arts)
    candidates = all_meta[: remaining * 2]
    log.info("\n[Phase 2] 본문 스크래핑 (후보 %d건, 목표 추가 %d건)",
             len(candidates), remaining)

    with tqdm(candidates, desc="본문 수집", unit="건") as bar:
        for meta in bar:
            if len(arts) >= TARGET_ARTICLES:
                log.info("목표 달성 (%d건)", TARGET_ARTICLES)
                break
            bar.set_postfix({"저장": len(arts)})
            try:
                art = scrape(session, meta)
            except KeyboardInterrupt:
                log.info("중단")
                break
            except Exception as e:
                log.error("스크래핑 오류: %s | %s", e, meta.get("url", ""))
                continue
            if art:
                arts.append(art)
                if len(arts) % CHECKPOINT_EVERY == 0:
                    save_cp(arts)
            sleep()

    log.info("[Phase 2] 완료 - 최종: %d건", len(arts))

    try:
        return pd.DataFrame(arts, columns=["title", "content", "date", "press", "url"])
    except Exception:
        return pd.DataFrame(arts)


def main():
    t0 = time.time()
    try:
        df = run(resume=True)
    except KeyboardInterrupt:
        log.info("중단됨.")
        try:
            df = pd.read_csv(CHECKPOINT_FILE, encoding="utf-8-sig")
        except Exception:
            df = pd.DataFrame(columns=["title", "content", "date", "press", "url"])
    except Exception as e:
        log.error("비정상 종료: %s", e)
        raise

    if df.empty:
        log.warning("수집 0건 - CSV 저장 생략")
    else:
        saved = False
        for path in [OUTPUT_CSV, Path.home() / OUTPUT_CSV.name]:
            try:
                df.to_csv(path, index=False, encoding="utf-8-sig")
                log.info("저장 완료: %s", path.resolve())
                saved = True
                break
            except Exception as e:
                log.error("저장 실패 (%s): %s", path, e)
        if saved:
            try:
                CHECKPOINT_FILE.unlink(missing_ok=True)
            except Exception:
                pass

    el = time.time() - t0
    log.info("=" * 60)
    log.info("완료 | %d건 | %d분 %d초", len(df), int(el // 60), int(el % 60))
    log.info("=" * 60)

    if not df.empty:
        print("\n-- 샘플 3건 --")
        try:
            print(df[["title", "press", "date"]].head(3).to_string(index=False))
        except Exception:
            print(df.head(3))
        try:
            print(f"\n본문 길이:\n{df['content'].str.len().describe().to_string()}")
        except Exception:
            pass


if __name__ == "__main__":
    main()