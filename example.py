import pandas as pd

df = pd.read_csv("data/result/naver_samsung_news_refined.csv")

mapping = {
    "positive": 1,
    "neutral": 0,
    "negative": -1
}

df["sentiment_num"] = df["final_sentiment"].map(mapping)

df.to_csv("data/result/naver_samsung_news_refined.csv", index=False, encoding="utf-8-sig")

print("sentiment_num 재생성 완료")