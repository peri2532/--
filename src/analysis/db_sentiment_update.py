import pandas as pd
import jaydebeapi
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# =========================
# 1. 설정
# =========================

H2_JAR_PATH = "C:/Users/peri2/새 폴더/--/src/analysis/h2-2.3.232.jar"
JDBC_DRIVER = "org.h2.Driver"
JDBC_URL = "jdbc:h2:mem:testdb"
DB_USER = "sa"
DB_PASSWORD = ""

MODEL_NAME = "snunlp/KR-FinBERT-SC"

LABELS = ["negative", "neutral", "positive"]

# =========================
# 2. 모델 로드
# =========================

print("[1] 모델 로드 중...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
model.eval()
print("[완료] 모델 로드 완료")

# =========================
# 3. 감성 예측 함수
# =========================

def predict_sentiment(text: str):
    if not isinstance(text, str):
        text = str(text)

    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=512
    )

    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.softmax(outputs.logits, dim=1)

    score, pred = torch.max(probs, dim=1)

    sentiment = LABELS[pred.item()]
    sentiment_score = float(score.item())

    return sentiment, sentiment_score

# =========================
# 4. DB 연결
# =========================

print("[2] DB 연결 중...")
conn = jaydebeapi.connect(
    JDBC_DRIVER,
    JDBC_URL,
    [DB_USER, DB_PASSWORD],
    H2_JAR_PATH
)
cursor = conn.cursor()
print("[완료] DB 연결 완료")

# =========================
# 5. 데이터 조회
# =========================

print("[3] NEWS 데이터 조회 중...")
query = "SELECT ID, TITLE, CONTENT FROM NEWS"
df = pd.read_sql(query, conn)
print(f"[완료] 조회 건수: {len(df)}")

# =========================
# 6. 컬럼 추가 시도
# =========================

print("[4] sentiment / score 컬럼 확인 중...")
try:
    cursor.execute("ALTER TABLE NEWS ADD sentiment VARCHAR(20)")
    print("sentiment 컬럼 추가 완료")
except Exception:
    print("sentiment 컬럼 이미 존재하거나 추가 실패")

try:
    cursor.execute("ALTER TABLE NEWS ADD score DOUBLE")
    print("score 컬럼 추가 완료")
except Exception:
    print("score 컬럼 이미 존재하거나 추가 실패")

conn.commit()

# =========================
# 7. 감성 분석
# =========================

print("[5] 감성분석 시작...")
sentiments = []
scores = []

for idx, row in df.iterrows():
    text = f"{row['TITLE']} {row['CONTENT']}"
    sentiment, score = predict_sentiment(text)

    sentiments.append(sentiment)
    scores.append(score)

    if (idx + 1) % 50 == 0:
        print(f"{idx + 1}건 처리 완료")

df["sentiment"] = sentiments
df["score"] = scores
print("[완료] 감성분석 완료")

# =========================
# 8. DB 업데이트
# =========================

print("[6] DB 업데이트 시작...")
update_sql = """
UPDATE NEWS
SET sentiment = ?, score = ?
WHERE id = ?
"""

for idx, row in df.iterrows():
    cursor.execute(
        update_sql,
        [row["sentiment"], float(row["score"]), int(row["ID"])]
    )

conn.commit()
print("[완료] DB 업데이트 완료")

# =========================
# 9. 결과 확인
# =========================

print("[7] 결과 분포 확인")
result_df = pd.read_sql(
    "SELECT sentiment, COUNT(*) AS cnt FROM NEWS GROUP BY sentiment",
    conn
)
print(result_df)

cursor.close()
conn.close()
print("[전체 완료]")