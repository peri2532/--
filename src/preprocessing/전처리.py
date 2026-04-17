import pandas as pd
import re
from tqdm import tqdm
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

tqdm.pandas()

# =========================
# 1. 데이터 로드
# =========================
df = pd.read_csv("naver_samsung_news_raw.csv")

# 컬럼 예시: title, content, date, url
df = df.dropna(subset=["title", "content"])

# =========================
# 2. 텍스트 정제
# =========================
def clean_text(text):
    text = re.sub(r"<.*?>", "", text)  # HTML 제거
    text = re.sub(r"\(.*?\)", "", text)  # 괄호 제거
    text = re.sub(r"[^가-힣a-zA-Z0-9\s]", " ", text) # 특수문자 제거
    text = re.sub(r"\s+", " ", text).strip()  # 공백 정리
    return text

df["clean_text"] = df["content"].progress_apply(clean_text)

# =========================
# 3. 날짜 정규화
# =========================
def normalize_date(date_str):
    date_str = date_str.replace("오전", "AM").replace("오후", "PM")
    try:
        return pd.to_datetime(date_str)
    except:
        return None

df["date"] = df["date"].apply(normalize_date)

# =========================
# 4. 1차 중복 제거 (URL)
# =========================
df = df.drop_duplicates(subset="url")

# =========================
# 5. 2차 중복 제거 (제목)
# =========================
df = df.drop_duplicates(subset="title")

# =========================
# 6. 3차 중복 제거 (내용 유사도)
# =========================
def remove_similar_articles(df, threshold=0.9):
    texts = df["clean_text"].tolist()

    vectorizer = TfidfVectorizer(max_features=5000)
    tfidf_matrix = vectorizer.fit_transform(texts)

    sim_matrix = cosine_similarity(tfidf_matrix)

    remove_idx = set()

    for i in range(len(sim_matrix)):
        if i in remove_idx:
            continue
        for j in range(i+1, len(sim_matrix)):
            if sim_matrix[i][j] > threshold:
                remove_idx.add(j)

    return df.drop(df.index[list(remove_idx)])

df = remove_similar_articles(df, threshold=0.9)

# =========================
# 7. 결과 저장
# =========================
df.to_csv("clean_news.csv", index=False)

print("최종 데이터 개수:", len(df))
df = pd.read_csv("clean_news.csv")

print("===== 기본 정보 =====")
print(df.info())

print("\n===== 결측치 =====")
print(df.isnull().sum())

print("\n===== 중복 =====")
print("제목 중복:", df.duplicated(subset=["title"]).sum())
print("내용 중복:", df.duplicated(subset=["content"]).sum())

print("\n===== 길이 통계 =====")
print(df["content"].str.len().describe())

print("\n===== 샘플 =====")
print(df.head(5))