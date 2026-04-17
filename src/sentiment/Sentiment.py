"""
sentiment.py - 감성분석 (비지도 학습)
========================================
snunlp/KR-FinBert-SC 모델 사용
  - 한국어 금융 특화 BERT 모델 (서울대 NLP 연구실)
  - 긍정(positive) / 부정(negative) / 중립(neutral) 분류

입력: naver_samsung_news_raw.csv
출력: naver_samsung_news_labeled.csv

실행: python sentiment.py
"""

import pandas as pd
from transformers import pipeline
from tqdm import tqdm
import torch

# ============================================================
# 설정
# ============================================================
INPUT_CSV  = "naver_samsung_news_raw.csv"
OUTPUT_CSV = "naver_samsung_news_labeled.csv"
MODEL_NAME = "snunlp/KR-FinBert-SC"
BATCH_SIZE = 16       # 한 번에 처리할 기사 수 (메모리 부족 시 8로 줄이기)
MAX_LENGTH = 512      # BERT 최대 토큰 수
SCORE_THRESHOLD = 0.6 # 확신도가 이 값 미만이면 중립으로 처리

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
# 데이터 로드
# ============================================================
print(f"데이터 로드: {INPUT_CSV}")
df = pd.read_csv(INPUT_CSV, encoding="utf-8-sig")
print(f"총 {len(df)}건 로드 완료\n")

# 분석할 텍스트 준비
# 제목 + 본문 앞 200자를 합쳐서 분석 (본문 전체는 512 토큰 초과 가능)
def make_text(row):
    title   = str(row.get("title",   "") or "")
    content = str(row.get("content", "") or "")
    # 제목은 감성에 중요한 정보가 많으므로 2번 반복해서 가중치 부여
    return (title + " " + title + " " + content[:200]).strip()

texts = df.apply(make_text, axis=1).tolist()

# ============================================================
# 감성분석 실행
# ============================================================
print("감성분석 시작...")
labels = []
scores = []

for i in tqdm(range(0, len(texts), BATCH_SIZE), desc="분석 중"):
    batch = texts[i : i + BATCH_SIZE]
    try:
        results = classifier(batch)
        for r in results:
            label = r["label"].lower()   # positive / negative / neutral
            score = r["score"]

            # 확신도가 낮으면 중립으로 처리
            if score < SCORE_THRESHOLD:
                label = "neutral"

            labels.append(label)
            scores.append(round(score, 4))
    except Exception as e:
        print(f"\n배치 오류 (인덱스 {i}): {e}")
        labels.extend(["neutral"] * len(batch))
        scores.extend([0.0] * len(batch))

# ============================================================
# 결과 저장
# ============================================================
df["sentiment"]       = labels   # positive / negative / neutral
df["sentiment_score"] = scores   # 확신도 (0~1)

# 감성을 숫자로도 저장 (그래프 그릴 때 편함)
# positive=1, neutral=0, negative=-1
score_map = {"positive": 1, "neutral": 0, "negative": -1}
df["sentiment_num"] = df["sentiment"].map(score_map)

df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
print(f"\n저장 완료: {OUTPUT_CSV}")

# ============================================================
# 결과 요약
# ============================================================
print("\n=== 감성분석 결과 요약 ===")
counts = df["sentiment"].value_counts()
total  = len(df)

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