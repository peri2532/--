import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf

# =====================
# 1. 감성 데이터 로드
# =====================
sentiment = pd.read_csv("output/daily.csv")

sentiment["date_only"] = pd.to_datetime(sentiment["date_only"])

# =====================
# 2. 주가 데이터 가져오기
# =====================
stock = yf.download("005930.KS", start="2022-01-01", end="2025-12-31")

# ⭐ 핵심 수정
stock.columns = stock.columns.get_level_values(0)

stock = stock.reset_index()
stock = stock[["Date", "Close"]]

stock.rename(columns={"Date": "date_only"}, inplace=True)
# =====================
# 3. 데이터 병합
# =====================
df = pd.merge(sentiment, stock, on="date_only", how="inner")

# =====================
# 4. 변화량 계산
# =====================
df["stock_change"] = df["Close"].pct_change().shift(-1)
df["sentiment_change"] = df["sentiment_score"].diff()

# =====================
# 5. 그래프 비교
# =====================
plt.figure(figsize=(12,6))

plt.plot(df["date_only"], df["sentiment_score"], label="Sentiment")
plt.plot(df["date_only"], df["stock_change"], label="Stock Change")

plt.legend()
plt.title("Sentiment vs Stock Change")
plt.xticks(rotation=45)

plt.tight_layout()
plt.savefig("output/sentiment_vs_stock.png")
plt.show()

# =====================
# 6. 상관계수
# =====================
corr = df["sentiment_score"].corr(df["stock_change"])

print("\n상관계수:", corr)