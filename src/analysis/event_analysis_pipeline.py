import os
import re
import math
from typing import List

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


# =========================
# 0. 설정
# =========================

INPUT_CSV = "data/result/naver_samsung_news_refined.csv"
OUTPUT_DIR = "output"
EVENT_THRESHOLD = 0.5      # 기존 0.3 → 개선
MIN_ARTICLE_COUNT = 5      # 기사 수 필터


# =========================
# 1. 유틸
# =========================

def ensure_output_dir(output_dir):
    os.makedirs(output_dir, exist_ok=True)


def clean_text(text):
    if pd.isna(text):
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def parse_date(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["date_only"] = df["date"].dt.date
    return df


def sentiment_to_num(x):
    x = str(x).lower().strip()
    if x == "positive":
        return 1
    elif x == "negative":
        return -1
    return 0


# =========================
# 2. sentiment_num 재생성
# =========================

def rebuild_sentiment_num(df):
    df = df.copy()
    df["sentiment_num"] = df["final_sentiment"].apply(sentiment_to_num)
    return df


# =========================
# 3. 집계
# =========================

def aggregate_daily(df):
    daily = (
        df.groupby("date_only")
        .agg(
            sentiment_score=("sentiment_num", "mean"),
            article_count=("sentiment_num", "count")
        )
        .reset_index()
        .sort_values("date_only")
    )

    # 기사 수 필터 (노이즈 제거)
    daily = daily[daily["article_count"] >= MIN_ARTICLE_COUNT]

    return daily


# =========================
# 4. 이벤트 탐지
# =========================

def detect_events(daily):
    daily = daily.copy()

    daily["prev"] = daily["sentiment_score"].shift(1)
    daily["change"] = daily["sentiment_score"] - daily["prev"]

    events = daily[abs(daily["change"]) >= EVENT_THRESHOLD].copy()

    return daily, events


# =========================
# 5. TextRank 요약 (안정화)
# =========================

def split_sentences(text):
    text = clean_text(text)
    if not text:
        return []
    sents = re.split(r'(?<=[.!?다요])\s+', text)
    return [s for s in sents if len(s) > 10]


def sentence_similarity(a, b):
    A, B = set(a.split()), set(b.split())
    if not A or not B:
        return 0
    return len(A & B) / (math.log(len(A)+1) + math.log(len(B)+1))


def build_matrix(sents):
    n = len(sents)
    M = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i != j:
                M[i][j] = sentence_similarity(sents[i], sents[j])
    return M


def textrank(M, d=0.85, iters=30):
    n = len(M)
    if n == 0:
        return np.array([])

    row_sum = M.sum(axis=1, keepdims=True)
    M = np.divide(M, row_sum, where=row_sum != 0, out=np.zeros_like(M))

    score = np.ones(n) / n

    for _ in range(iters):
        score = (1-d)/n + d * M.T.dot(score)

    return score


def summarize(text):
    sents = split_sentences(text)
    if len(sents) <= 3:
        return " ".join(sents)

    M = build_matrix(sents)
    scores = textrank(M)

    top = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:3]
    top = sorted(top)

    return " ".join([sents[i] for i in top])


def add_summary(df):
    df = df.copy()
    df["summary"] = df["content"].apply(summarize)
    return df


# =========================
# 6. 이벤트 대표 뉴스
# =========================

def extract_event_news(df, events):
    results = []

    for d in events["date_only"]:
        sub = df[df["date_only"] == d]

        top = sub.sort_values("sentiment_score", ascending=False).head(3)

        for _, row in top.iterrows():
            results.append({
                "date": d,
                "title": row["title"],
                "sentiment": row["final_sentiment"]
            })

    return pd.DataFrame(results)


# =========================
# 7. 시각화
# =========================

def plot_trend(daily):
    plt.figure()
    plt.plot(daily["date_only"], daily["sentiment_score"])
    plt.xticks(rotation=45)
    plt.title("Sentiment Trend")
    plt.tight_layout()
    plt.savefig("output/trend.png")
    plt.close()


def plot_pie(df):
    counts = df["final_sentiment"].value_counts()
    plt.figure()
    plt.pie(counts.values, labels=counts.index, autopct="%1.1f%%")
    plt.title("Sentiment Distribution")
    plt.savefig("output/pie.png")
    plt.close()


# =========================
# 8. 메인
# =========================

def main():
    ensure_output_dir(OUTPUT_DIR)

    df = pd.read_csv(INPUT_CSV)

    df = parse_date(df)
    df = rebuild_sentiment_num(df)

    daily = aggregate_daily(df)
    daily, events = detect_events(daily)

    df = add_summary(df)

    event_news = extract_event_news(df, events)

    plot_trend(daily)
    plot_pie(df)

    df.to_csv("output/news_with_summary.csv", index=False)
    daily.to_csv("output/daily.csv", index=False)
    events.to_csv("output/events.csv", index=False)
    event_news.to_csv("output/event_news.csv", index=False)

    print("\n[완료]")
    print("이벤트 수:", len(events))


if __name__ == "__main__":
    main()