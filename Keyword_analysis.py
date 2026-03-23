"""
keyword_analysis.py - 키워드 추출 및 시각화
=============================================
1. TF-IDF 기반 키워드 추출
2. 감성별 키워드 비교 (긍정 vs 부정)
3. 월별 감성 트렌드 그래프
4. 워드클라우드

입력: 
  - naver_samsung_news_preprocessed.csv
  - naver_samsung_news_labeled.csv
출력:
  - keyword_analysis.png   (키워드 분석 그래프)
  - wordcloud_pos.png      (긍정 워드클라우드)
  - wordcloud_neg.png      (부정 워드클라우드)

실행: python keyword_analysis.py
"""

import pandas as pd
import numpy as np
from collections import Counter
from sklearn.feature_extraction.text import TfidfVectorizer
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from wordcloud import WordCloud

# ============================================================
# 한글 폰트 설정
# ============================================================
def set_korean_font():
    try:
        font_path = "C:/Windows/Fonts/malgun.ttf"
        font_prop = fm.FontProperties(fname=font_path)
        plt.rcParams["font.family"] = font_prop.get_name()
        plt.rcParams["axes.unicode_minus"] = False
        print(f"폰트 설정: {font_prop.get_name()}")
        return font_path
    except Exception as e:
        print(f"폰트 설정 실패: {e}")
        return None

font_path = set_korean_font()

# ============================================================
# 데이터 로드
# ============================================================
print("\n데이터 로드 중...")
df_pre = pd.read_csv("naver_samsung_news_preprocessed.csv", encoding="utf-8-sig")
df_lab = pd.read_csv("naver_samsung_news_labeled.csv",      encoding="utf-8-sig")

# 두 데이터 합치기 (URL 기준)
df = df_pre.copy()
df["sentiment"]     = df_lab["sentiment"]
df["sentiment_num"] = df_lab["sentiment_num"]

print(f"총 {len(df)}건 로드 완료")

# 날짜 파싱
df["date"] = pd.to_datetime(df["date"], errors="coerce")
df["year_month"] = df["date"].dt.to_period("M")

# ============================================================
# 1. TF-IDF 기반 키워드 추출
# ============================================================
print("\nTF-IDF 키워드 추출 중...")

# tokens 컬럼 사용 (형태소 분석 완료된 것)
df["tokens"] = df["tokens"].fillna("")

vectorizer = TfidfVectorizer(
    max_features=200,    # 상위 200개 단어만
    min_df=5,            # 최소 5개 문서에 등장한 단어만
    max_df=0.8,          # 80% 이상 문서에 등장하는 단어 제외 (너무 흔한 단어)
)

tfidf_matrix = vectorizer.fit_transform(df["tokens"])
feature_names = vectorizer.get_feature_names_out()

# 전체 TF-IDF 평균 점수
tfidf_mean = tfidf_matrix.mean(axis=0).A1
tfidf_scores = dict(zip(feature_names, tfidf_mean))
top_tfidf = sorted(tfidf_scores.items(), key=lambda x: x[1], reverse=True)[:30]

print("\n=== TF-IDF 상위 30개 키워드 ===")
for word, score in top_tfidf:
    print(f"  {word:15s}: {score:.6f}")

# ============================================================
# 2. 감성별 키워드 비교
# ============================================================
print("\n감성별 키워드 분석 중...")

def get_top_words(df_subset, n=20):
    """해당 데이터프레임에서 상위 n개 단어 반환"""
    all_tokens = []
    for tokens_str in df_subset["tokens"].fillna(""):
        all_tokens.extend(tokens_str.split())
    return Counter(all_tokens).most_common(n)

pos_words = get_top_words(df[df["sentiment"] == "positive"], n=20)
neg_words = get_top_words(df[df["sentiment"] == "negative"], n=20)
neu_words = get_top_words(df[df["sentiment"] == "neutral"],  n=20)

print("\n=== 긍정 뉴스 상위 20개 단어 ===")
for w, c in pos_words:
    print(f"  {w:15s}: {c:,}회")

print("\n=== 부정 뉴스 상위 20개 단어 ===")
for w, c in neg_words:
    print(f"  {w:15s}: {c:,}회")

# ============================================================
# 3. 월별 감성 트렌드
# ============================================================
print("\n월별 감성 트렌드 계산 중...")

monthly = df.groupby("year_month")["sentiment_num"].agg(["mean", "count"]).reset_index()
monthly.columns = ["year_month", "sentiment_avg", "count"]
monthly["year_month_str"] = monthly["year_month"].astype(str)

# ============================================================
# 4. 그래프 생성
# ============================================================
print("\n그래프 생성 중...")

fig, axes = plt.subplots(2, 2, figsize=(16, 12))
fig.suptitle("삼성전자 뉴스 키워드 및 감성 분석", fontsize=16, fontweight="bold")

# 그래프 1: TF-IDF 상위 20개 키워드
ax1 = axes[0, 0]
words  = [w for w, _ in top_tfidf[:20]]
scores = [s for _, s in top_tfidf[:20]]
ax1.barh(range(20), scores, color="steelblue", alpha=0.8)
ax1.set_yticks(range(20))
ax1.set_yticklabels(words, fontsize=9)
ax1.set_xlabel("TF-IDF 점수")
ax1.set_title("TF-IDF 상위 20개 키워드")
ax1.invert_yaxis()
ax1.grid(True, alpha=0.3, axis="x")

# 그래프 2: 긍정 vs 부정 키워드 비교
ax2 = axes[0, 1]
pos_w = [w for w, _ in pos_words[:15]]
pos_c = [c for _, c in pos_words[:15]]
neg_w = [w for w, _ in neg_words[:15]]
neg_c = [c for _, c in neg_words[:15]]

x = np.arange(15)
width = 0.35
ax2.bar(x - width/2, pos_c, width, label="긍정", color="steelblue", alpha=0.8)
ax2.bar(x + width/2, neg_c, width, label="부정", color="coral",     alpha=0.8)
ax2.set_xticks(x)
ax2.set_xticklabels(pos_w, rotation=45, ha="right", fontsize=8)
ax2.set_ylabel("출현 빈도")
ax2.set_title("긍정 vs 부정 뉴스 상위 키워드 비교")
ax2.legend()
ax2.grid(True, alpha=0.3, axis="y")

# 그래프 3: 월별 감성 평균 트렌드
ax3 = axes[1, 0]
x_idx = range(len(monthly))
ax3.plot(x_idx, monthly["sentiment_avg"], 
         color="purple", linewidth=2, marker="o", markersize=4)
ax3.axhline(y=0, color="black", linestyle="--", alpha=0.5, label="중립선")
ax3.fill_between(x_idx, monthly["sentiment_avg"], 0,
                 where=(monthly["sentiment_avg"] >= 0),
                 color="steelblue", alpha=0.3, label="긍정")
ax3.fill_between(x_idx, monthly["sentiment_avg"], 0,
                 where=(monthly["sentiment_avg"] < 0),
                 color="coral", alpha=0.3, label="부정")

# x축 레이블 (6개월 간격)
step = max(1, len(monthly) // 8)
ax3.set_xticks(range(0, len(monthly), step))
ax3.set_xticklabels(monthly["year_month_str"][::step], 
                    rotation=45, ha="right", fontsize=8)
ax3.set_ylabel("평균 감성 점수")
ax3.set_title("월별 감성 트렌드 (1=긍정, 0=중립, -1=부정)")
ax3.legend(fontsize=8)
ax3.grid(True, alpha=0.3)

# 그래프 4: 감성 분포 파이차트
ax4 = axes[1, 1]
sentiment_counts = df["sentiment"].value_counts()
colors = ["steelblue", "lightgray", "coral"]
labels_kr = {"positive": "긍정", "neutral": "중립", "negative": "부정"}
labels = [labels_kr.get(s, s) for s in sentiment_counts.index]
wedges, texts, autotexts = ax4.pie(
    sentiment_counts.values,
    labels=labels,
    colors=colors,
    autopct="%1.1f%%",
    startangle=90,
    textprops={"fontsize": 11}
)
ax4.set_title("감성 분포")

plt.tight_layout()
plt.savefig("keyword_analysis.png", dpi=150, bbox_inches="tight")
print("그래프 저장: keyword_analysis.png")

# ============================================================
# 5. 워드클라우드
# ============================================================
print("\n워드클라우드 생성 중...")

def make_wordcloud(df_subset, title, filename, color):
    all_tokens = []
    for tokens_str in df_subset["tokens"].fillna(""):
        all_tokens.extend(tokens_str.split())
    freq = Counter(all_tokens)

    wc = WordCloud(
        font_path=font_path if font_path else None,
        width=800, height=500,
        background_color="white",
        colormap=color,
        max_words=100,
        max_font_size=120,
    ).generate_from_frequencies(freq)

    plt.figure(figsize=(10, 6))
    plt.imshow(wc, interpolation="bilinear")
    plt.axis("off")
    plt.title(title, fontsize=16, fontweight="bold", pad=20)
    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"저장: {filename}")

make_wordcloud(df[df["sentiment"] == "positive"],
               "긍정 뉴스 워드클라우드", "wordcloud_pos.png", "Blues")
make_wordcloud(df[df["sentiment"] == "negative"],
               "부정 뉴스 워드클라우드", "wordcloud_neg.png", "Reds")

# ============================================================
# 완료
# ============================================================
print("\n=== 완료 ===")
print("생성된 파일:")
print("  - keyword_analysis.png")
print("  - wordcloud_pos.png")
print("  - wordcloud_neg.png")