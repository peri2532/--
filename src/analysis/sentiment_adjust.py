import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix

NEG_WORDS = [
    "급감","적자","악화","부진","결렬","파업",
    "위기","하락","손실","쇼크","감소"
]

POS_WORDS = [
    "상승","반등","승진","확대","협력",
    "성장","개선","증가","타결","수주"
]


def keyword_score(text):
    score = 0
    if pd.isna(text):
        return 0

    text = str(text)

    for w in NEG_WORDS:
        count = text.count(w)
        score -= count

    for w in POS_WORDS:
        count = text.count(w)
        score += count

    return score


def refine_sentiment(row, threshold=0.7):
    model_label = row['sentiment']
    confidence = row['sentiment_score']
    title = row['title']
    content = row['content']

    # 1. confidence 기반 neutral
    if confidence < threshold:
        return "neutral"

    # 2. 키워드 점수
    k_score = keyword_score(title) * 2 + keyword_score(content)

    # 3. 보정 기준 (완화)
    if k_score >= 2:
        return "positive"
    elif k_score <= -2:
        return "negative"

    return model_label


def evaluate(df, label_col="내태깅"):
    y_true = df[label_col]
    y_pred = df['final_sentiment']

    print("\n===== 평가 =====")
    print(classification_report(y_true, y_pred))
    print(confusion_matrix(y_true, y_pred))


def main():
    df = pd.read_csv("naver_samsung_news_labeled.csv")

    df['final_sentiment'] = df.apply(refine_sentiment, axis=1)

    df.to_csv("naver_samsung_news_refined.csv", index=False)

    print("보정 완료")

    evaluate(df)


if __name__ == "__main__":
    main()