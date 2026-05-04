import pandas as pd
import logging
from tqdm import tqdm


import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, "analysis"))
sys.path.append(os.path.join(BASE_DIR, "sentiment"))
# =========================
# 로그 설정
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("sentiment_pipeline")

# =========================
# 설정
# =========================
INPUT_CSV = "crawling/naver_samsung_news_raw.csv"
OUTPUT_CSV = "naver_samsung_news_final.csv"

# =========================
# 1. 감성 분석 함수 import
# =========================
from Sentiment import predict_sentiment_from_row
# =========================
# 2. 보정 함수 import
# =========================
from sentiment_adjust import refine_sentiment


# ============================================================
# 감성 분석
# ============================================================
def run_sentiment(df):
    log.info("[STEP 1] 감성 분석 시작")

    sentiments = []
    scores = []

    for i, row in tqdm(df.iterrows(), total=len(df), desc="감성 분석"):
        label, score = predict_sentiment_from_row(row)

        sentiments.append(label)
        scores.append(score)

        if i % 500 == 0 and i != 0:
            log.info("  %d건 처리 완료", i)

    df["sentiment"] = sentiments
    df["sentiment_score"] = scores

    log.info("[STEP 1 완료] 감성 분석 완료")
    return df


# ============================================================
# 감성 보정
# ============================================================
def run_refine(df):
    log.info("[STEP 2] 감성 보정 시작")

    df["final_sentiment"] = df.apply(refine_sentiment, axis=1)

    log.info("[STEP 2 완료] 감성 보정 완료")
    return df


# ============================================================
# 결과 출력
# ============================================================
def show_result(df):
    log.info("[STEP 3] 결과 출력")

    # 전체 통계
    counts = df["final_sentiment"].value_counts()
    total = len(df)

    log.info("===== 감성 분포 =====")
    for label, count in counts.items():
        pct = count / total * 100
        log.info("  %s: %d건 (%.1f%%)", label, count, pct)

    # 샘플 출력
    sample = df.iloc[0]

    log.info("\n===== 샘플 결과 =====")
    log.info("제목: %s", sample["title"])
    log.info("모델 감성: %s (%.3f)", sample["sentiment"], sample["sentiment_score"])
    log.info("최종 감성: %s", sample["final_sentiment"])


# ============================================================
# 메인 실행
# ============================================================
def main():
    log.info("\n==============================")
    log.info(" 감성 분석 파이프라인 시작")
    log.info("==============================\n")

    # 1. 데이터 로드
    log.info("데이터 로드: %s", INPUT_CSV)
    df = pd.read_csv(INPUT_CSV, encoding="utf-8-sig")
    log.info("총 %d건 로드 완료\n", len(df))

    # ⚠️ 발표용이면 줄여라 (속도)
    # df = df.head(500)

    # 2. 감성 분석
    df = run_sentiment(df)

    # 3. 감성 보정
    df = run_refine(df)

    # 4. 저장
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    log.info("\n저장 완료: %s", OUTPUT_CSV)

    # 5. 결과 출력
    show_result(df)

    log.info("\n==============================")
    log.info(" 파이프라인 완료")
    log.info("==============================")


if __name__ == "__main__":
    main()