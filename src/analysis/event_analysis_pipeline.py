import os
import re
import math
import hashlib
import requests
from collections import Counter

import pandas as pd
import numpy as np

# =========================
# 설정
# =========================
INPUT_CSV = "C:/Users/wf/Downloads/졸작/data/result/naver_samsung_news_refined.csv"

NEWS_API_URL = "http://localhost:8080/api/news"
EVENT_API_URL = "http://localhost:8080/api/events"

SEND_LIMIT = 100
EVENT_THRESHOLD = 0.5

# =========================
# 유틸
# =========================
def clean_text(text):
    if pd.isna(text):
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()

def make_url_hash(url):
    return hashlib.sha256(str(url).encode("utf-8")).hexdigest()

def sentiment_to_num(x):
    x = str(x).lower()
    if x == "positive":
        return 1
    elif x == "negative":
        return -1
    return 0

# =========================
# 요약 (간단 TextRank)
# =========================
def split_sentences(text):
    text = clean_text(text)
    return re.split(r'(?<=[.!?다요])\s+', text)

def summarize(text):
    sents = split_sentences(text)
    return " ".join(sents[:3])  # 간단 버전

# =========================
# 키워드 추출
# =========================
def extract_keywords(text, top_n=5):
    words = re.findall(r"[가-힣]{2,}", text)
    counter = Counter(words)
    return [w for w, _ in counter.most_common(top_n)]

# =========================
# 뉴스 서버 전송
# =========================
def send_news(row):
    try:
        data = {
            "stockCode": "005930",
            "title": clean_text(row["title"]),
            "content": clean_text(row["content"]),
            "summary": row["summary"],
            "source": "naver",
            "url": row["url"],
            "urlHash": make_url_hash(row["url"]),
            "publishedAt": str(row["date"]).replace(" ", "T"),
            "sentimentScore": float(row.get("sentiment_score", 0.0)),
            "sentimentLabel": str(row.get("final_sentiment", "neutral")).lower(),
            "eventTags": "NONE",
            "isRepresentative": True
        }

        res = requests.post(NEWS_API_URL, json=data)
        print(f"[NEWS {res.status_code}] {data['title']}")

    except Exception as e:
        print("뉴스 전송 실패:", e)

# =========================
# 이벤트 서버 전송
# =========================
def send_event(event):
    try:
        data = {
            "stockCode": "005930",
            "eventDate": str(event["date"]),
            "eventType": event["type"],
            "changeRate": float(event["change"]),
            "keyword": ", ".join(event["keywords"]),
            "summary": event["summary"]
        }

        res = requests.post(EVENT_API_URL, json=data)
        print(f"[EVENT {res.status_code}] {event['type']} {event['date']}")

    except Exception as e:
        print("이벤트 전송 실패:", e)

# =========================
# 이벤트 탐지
# =========================
def detect_events(df):
    daily = (
        df.groupby("date_only")
        .agg(score=("sentiment_num", "mean"))
        .reset_index()
        .sort_values("date_only")
    )

    daily["prev"] = daily["score"].shift(1)
    daily["change"] = daily["score"] - daily["prev"]

    events = daily[abs(daily["change"]) >= EVENT_THRESHOLD]

    return events

# =========================
# 메인
# =========================
def main():

    print("\n[STEP 1] 데이터 로드")
    df = pd.read_csv(INPUT_CSV).head(SEND_LIMIT)

    df["date"] = pd.to_datetime(df["date"])
    df["date_only"] = df["date"].dt.date
    df["sentiment_num"] = df["final_sentiment"].apply(sentiment_to_num)

    print("  → 데이터 준비 완료")

    print("\n[STEP 2] 요약 + 키워드")
    df["summary"] = df["content"].apply(summarize)
    df["keywords"] = df["content"].apply(extract_keywords)

    print("\n[STEP 3] 뉴스 서버 전송")
    for _, row in df.iterrows():
        send_news(row)

    print("\n[STEP 4] 이벤트 탐지")
    events = detect_events(df)

    print(f"  → 이벤트 {len(events)}개 발견")

    print("\n[STEP 5] 이벤트 서버 전송")
    for _, row in events.iterrows():

        subset = df[df["date_only"] == row["date_only"]]

        keywords = extract_keywords(" ".join(subset["content"].tolist()))
        summary = summarize(" ".join(subset["content"].tolist()))

        event_data = {
            "date": row["date_only"],
            "type": "급등" if row["change"] > 0 else "급락",
            "change": row["change"],
            "keywords": keywords,
            "summary": summary
        }

        send_event(event_data)

    print("\n[완료] 전체 파이프라인 종료")


if __name__ == "__main__":
    main()