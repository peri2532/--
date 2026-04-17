"""
Sentiment.py - 감성분석 (비지도 학습 + 실시간 예측 함수 지원)
=========================================================
snunlp/KR-FinBert-SC 모델 사용
  - 한국어 금융 특화 BERT 모델
  - 긍정(positive) / 부정(negative) / 중립(neutral) 분류

기능 1) 배치 분석
입력: naver_samsung_news_raw.csv
출력: naver_samsung_news_labeled.csv

실행:
    python Sentiment.py

기능 2) 실시간/개별 예측
    from Sentiment import predict_sentiment
    label, score = predict_sentiment("삼성전자 실적 증가")
"""

import pandas as pd
from transformers import pipeline
from tqdm import tqdm
import torch

# ============================================================
# 설정
# ============================================================
INPUT_CSV = "naver_samsung_news_raw.csv"
OUTPUT_CSV = "naver_samsung_news_labeled.csv"
MODEL_NAME = "snunlp/KR-FinBert-SC"
BATCH_SIZE = 16
MAX_LENGTH = 512
SCORE_THRESHOLD = 0.6

# GPU 사용 가능 여부 확인
device = 0 if torch.cuda.is_available() else -1
print(f"사용 디바이스: {'GPU' if device == 0 else 'CPU'}")

# ============================================================
# 모델 로드
# ============================================================
print(f"\n모델 로딩 중: {MODEL_NAME}")
print("(처음 실행 시 모델 다운로드로 1~2분 걸릴 수 있습니다)")

classifier = pipeline(
    "text-classification",
    model=MODEL_NAME,
    device=device,
    max_length=MAX_LENGTH,
    truncation=True,
)

print("모델 로드 완료!\n")


# ============================================================
# 공통 함수
# ============================================================
def make_text(row):
    """
    제목 + 본문 앞 200자를 합쳐 분석용 텍스트 생성
    제목은 2회 반복해 가중치 부여
    """
    title = str(row.get("title", "") or "")
    content = str(row.get("content", "") or "")
    return (title + " " + title + " " + content[:200]).strip()


def predict_sentiment(text):
    """
    실시간/단일 텍스트 감성 예측 함수
    반환:
        (label, score)
        예: ("positive", 0.9132)
    """
    if not text or str(text).strip() == "":
        return "neutral", 0.0

    try:
        result = classifier(str(text))[0]

        label = result["label"].lower()
        score = result["score"]

        if score < SCORE_THRESHOLD:
            label = "neutral"

        return label, round(score, 4)

    except Exception as e:
        print("감성분석 오류:", e)
        return "neutral", 0.0


def predict_sentiment_from_row(row):
    """
    row(title, content)를 받아 make_text 후 감성 예측
    """
    text = make_text(row)
    return predict_sentiment(text)


# ============================================================
# 배치 실행 함수
# ============================================================
def run_batch_sentiment_analysis(
    input_csv=INPUT_CSV,
    output_csv=OUTPUT_CSV,
    batch_size=BATCH_SIZE
):
    print(f"데이터 로드: {input_csv}")
    df = pd.read_csv(input_csv, encoding="utf-8-sig")
    print(f"총 {len(df)}건 로드 완료\n")

    texts = df.apply(make_text, axis=1).tolist()

    print("감성분석 시작...")
    labels = []
    scores = []

    for i in tqdm(range(0, len(texts), batch_size), desc="분석 중"):
        batch = texts[i:i + batch_size]

        try:
            results = classifier(batch)

            for r in results:
                label = r["label"].lower()
                score = r["score"]

                if score < SCORE_THRESHOLD:
                    label = "neutral"

                labels.append(label)
                scores.append(round(score, 4))

        except Exception as e:
            print(f"\n배치 오류 (인덱스 {i}): {e}")
            labels.extend(["neutral"] * len(batch))
            scores.extend([0.0] * len(batch))

    df["sentiment"] = labels
    df["sentiment_score"] = scores

    score_map = {"positive": 1, "neutral": 0, "negative": -1}
    df["sentiment_num"] = df["sentiment"].map(score_map)

    df.to_csv(output_csv, index=False, encoding="utf-8-sig")
    print(f"\n저장 완료: {output_csv}")

    print("\n=== 감성분석 결과 요약 ===")
    counts = df["sentiment"].value_counts()
    total = len(df)

    for label, count in counts.items():
        pct = count / total * 100
        print(f"  {label:10s}: {count:5d}건 ({pct:.1f}%)")

    print(f"\n  전체: {total}건")
    print(f"  평균 확신도: {df['sentiment_score'].mean():.3f}")

    print("\n=== 샘플 (긍정 3건) ===")
    pos = df[df["sentiment"] == "positive"][["title", "sentiment", "sentiment_score"]].head(3)
    print(pos.to_string(index=False))

    print("\n=== 샘플 (부정 3건) ===")
    neg = df[df["sentiment"] == "negative"][["title", "sentiment", "sentiment_score"]].head(3)
    print(neg.to_string(index=False))


# ============================================================
# 직접 실행 시에만 배치 분석 수행
# ============================================================
if __name__ == "__main__":
    run_batch_sentiment_analysis()