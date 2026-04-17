import pandas as pd

events = pd.read_csv("output/events.csv")
news = pd.read_csv("output/news_with_summary.csv")

events["date_only"] = pd.to_datetime(events["date_only"]).dt.date
news["date_only"] = pd.to_datetime(news["date"]).dt.date

# 상위 3개 이벤트 확인
for d in events["date_only"].head(3):
    print("\n날짜:", d)
    print(news[news["date_only"] == d][["title", "final_sentiment"]].head(3))