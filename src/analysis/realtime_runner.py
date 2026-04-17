import os
import time
import pandas as pd
import re

from Realtime_pipeline import crawl_realtime_news
from Sentiment import predict_sentiment_from_row  # ⭐ 핵심 변경

# =====================
# 설정
# =====================
DATA_PATH = "data/result/naver_samsung_news_refined.csv"
OUTPUT_DIR = "output"

SLEEP_SECONDS = 300  # 5분
EVENT_THRESHOLD = 0.5
MIN_ARTICLE_COUNT = 5

# =====================
# 유틸
# =====================
def ensure_dir():
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

def sentiment_to_num(x):
    x = str(x).lower().strip()
    return 1 if x == "positive" else -1 if x == "negative" else 0

def clean_text(text):
    if pd.isna(text):
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()

# =====================
# 감성 분석 (수정됨)
# =====================
def apply_sentiment(df):
    # ⭐ 제목 + 본문 기반 분석 (Sentiment.py 로직 재사용)
    results = df.apply(predict_sentiment_from_row, axis=1)

    df["sentiment"] = results.apply(lambda x: x[0])
    df["sentiment_score"] = results.apply(lambda x: x[1])

    return df

# =====================
# 보정
# =====================
def refine(df):
    df["sentiment_num"] = df["sentiment"].apply(sentiment_to_num)
    df["final_sentiment"] = df["sentiment"]
    return df

# =====================
# 기존 데이터 로드
# =====================
def load_existing():
    if os.path.exists(DATA_PATH):
        return pd.read_csv(DATA_PATH)
    return pd.DataFrame()

# =====================
# 중복 제거
# =====================
def remove_duplicates(new_df, existing_df):
    if existing_df.empty:
        return new_df
    return new_df[~new_df["url"].isin(existing_df["url"])]

# =====================
# append 저장
# =====================
def append_data(new_df, existing_df):
    combined = pd.concat([existing_df, new_df], ignore_index=True)
    combined.to_csv(DATA_PATH, index=False, encoding="utf-8-sig")
    return combined

# =====================
# 집계 (최근 30일만)
# =====================
def update_daily(df):
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["date_only"] = df["date"].dt.date

    recent = df[df["date"] > (pd.Timestamp.now() - pd.Timedelta(days=30))]

    daily = (
        recent.groupby("date_only")
        .agg(
            sentiment_score=("sentiment_num", "mean"),
            article_count=("sentiment_num", "count")
        )
        .reset_index()
    )

    daily = daily[daily["article_count"] >= MIN_ARTICLE_COUNT]

    return daily

# =====================
# 이벤트
# =====================
def detect_events(daily):
    daily["prev"] = daily["sentiment_score"].shift(1)
    daily["change"] = daily["sentiment_score"] - daily["prev"]
    events = daily[abs(daily["change"]) >= EVENT_THRESHOLD]
    return daily, events

# =====================
# 요약
# =====================
def summarize(text):
    sents = re.split(r'(?<=[.!?다요])\s+', clean_text(text))
    return " ".join(sents[:3])

# =====================
# 이벤트 뉴스
# =====================
def extract_event_news(df, events):
    result = []
    df["date_only"] = pd.to_datetime(df["date"]).dt.date

    for d in events["date_only"]:
        sub = df[df["date_only"] == d]
        top = sub.sort_values("sentiment_score", ascending=False).head(3)

        for _, row in top.iterrows():
            result.append({
                "date": d,
                "title": row["title"],
                "sentiment": row["final_sentiment"]
            })

    return pd.DataFrame(result)

# =====================
# 핵심 처리 함수
# =====================
def process_new_data(new_df):
    existing_df = load_existing()

    # 중복 제거
    new_df = remove_duplicates(new_df, existing_df)

    if len(new_df) == 0:
        print("신규 데이터 없음")
        return

    print(f"신규 뉴스 {len(new_df)}개")

    # 감성 분석
    new_df = apply_sentiment(new_df)

    # 보정
    new_df = refine(new_df)

    # 요약
    new_df["summary"] = new_df["content"].apply(summarize)

    # append
    combined = append_data(new_df, existing_df)

    # 집계
    daily = update_daily(combined)

    # 이벤트
    daily, events = detect_events(daily)

    # 이벤트 뉴스
    event_news = extract_event_news(combined, events)

    # 저장
    daily.to_csv(f"{OUTPUT_DIR}/daily.csv", index=False)
    events.to_csv(f"{OUTPUT_DIR}/events.csv", index=False)
    event_news.to_csv(f"{OUTPUT_DIR}/event_news.csv", index=False)

    print("이벤트 수:", len(events))

# =====================
# 메인 루프
# =====================
def main():
    ensure_dir()

    while True:
        try:
            new_df = crawl_realtime_news()

            if new_df is not None and len(new_df) > 0:
                process_new_data(new_df)
            else:
                print("크롤링 결과 없음")

        except Exception as e:
            print("에러:", e)

        print("대기중...\n")
        time.sleep(SLEEP_SECONDS)

# =====================
# 실행
# =====================
if __name__ == "__main__":
    main()