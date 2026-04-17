import pandas as pd

df = pd.read_csv("data/result/naver_samsung_news_refined.csv")

print(df[['final_sentiment', 'sentiment_num']].head(10))
print(df['sentiment_num'].value_counts())