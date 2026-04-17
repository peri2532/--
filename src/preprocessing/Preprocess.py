"""
preprocess.py - 뉴스 텍스트 전처리
=====================================
1. 특수문자 제거
2. 형태소 분석 (kiwipiepy)
3. 품사 태깅 (명사/동사/형용사 추출)
4. 불용어 제거
5. n-그램 생성
6. 단어 빈도 계산
7. Zipf 법칙 검증
8. Heaps 법칙 검증

입력: naver_samsung_news_raw.csv
출력: 
  - naver_samsung_news_preprocessed.csv  (전처리된 데이터)
  - zipf_heaps_result.png                (그래프)

실행: python preprocess.py
"""

import re
import pandas as pd
import numpy as np
from collections import Counter
from kiwipiepy import Kiwi
from tqdm import tqdm
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# ============================================================
# 한글 폰트 설정 (그래프용)
# ============================================================
def set_korean_font():
    """윈도우 한글 폰트 설정"""
    try:
        # 윈도우 기본 한글 폰트
        font_path = "C:/Windows/Fonts/malgun.ttf"
        font_prop = fm.FontProperties(fname=font_path)
        plt.rcParams["font.family"] = font_prop.get_name()
        plt.rcParams["axes.unicode_minus"] = False
        print(f"폰트 설정 완료: {font_prop.get_name()}")
    except Exception as e:
        print(f"폰트 설정 실패: {e} (그래프 한글이 깨질 수 있음)")

set_korean_font()

# ============================================================
# 설정
# ============================================================
INPUT_CSV  = "naver_samsung_news_raw.csv"
OUTPUT_CSV = "naver_samsung_news_preprocessed.csv"
OUTPUT_IMG = "zipf_heaps_result.png"

# 추출할 품사 태그
# NN* = 명사, VV = 동사, VA = 형용사
TARGET_POS = {"NNG", "NNP", "VV", "VA"}
# NNG: 일반명사, NNP: 고유명사, VV: 동사, VA: 형용사

# 불용어 목록 (금융 뉴스에서 의미 없는 단어들)
STOPWORDS = {
    # 일반 불용어
    "것", "수", "등", "및", "이", "그", "저", "년", "월", "일",
    "때", "곳", "들", "제", "와", "과", "은", "는", "이", "가",
    "을", "를", "의", "에", "서", "로", "으로", "도", "만", "에서",
    "하다", "되다", "있다", "없다", "이다", "위하다", "통하다",
    "대하다", "관하다", "따르다", "나타나다", "보이다", "말하다",
    # 뉴스 특수 불용어
    "기자", "특파원", "연합뉴스", "뉴스", "보도", "발표", "공개",
    "관련", "대한", "지난", "올해", "지난해", "올해", "내년",
    "오전", "오후", "현재", "최근", "앞서", "이번", "다음",
    # 숫자/단위 관련
    "억원", "조원", "만원", "달러", "원", "개", "명", "건",
    "퍼센트", "분기", "전년", "동기", "대비",
      # 의미없는 동사 (어간 형태)
    "위하", "밝히", "통하", "따르", "전하", "강조하", "설명하",
    "분석하", "전망하", "예상하", "기록하", "달성하", "확대하",
    "증가하", "감소하", "하락하", "나타나", "이루", "받",
}

# ============================================================
# 1. 텍스트 정제 함수
# ============================================================
def clean_text(text):
    """특수문자 제거 및 기본 정제"""
    if not isinstance(text, str):
        return ""
    
    # URL 제거
    text = re.sub(r"https?://\S+", "", text)
    # 이메일 제거
    text = re.sub(r"\S+@\S+", "", text)
    # HTML 태그 제거
    text = re.sub(r"<[^>]+>", "", text)
    # 특수문자 제거 (한글, 영문, 숫자, 공백만 남김)
    text = re.sub(r"[^\w\s가-힣]", " ", text)
    # 숫자만 있는 단어 제거
    text = re.sub(r"\b\d+\b", "", text)
    # 연속 공백 제거
    text = re.sub(r"\s+", " ", text)
    
    return text.strip()

# ============================================================
# 2. 형태소 분석 + 품사 태깅
# ============================================================
print("Kiwi 형태소 분석기 로딩 중...")
kiwi = Kiwi()
print("로딩 완료!\n")

def tokenize(text):
    """형태소 분석 후 명사/동사/형용사만 추출"""
    if not text or len(text) < 2:
        return []
    
    try:
        result = kiwi.analyze(text)
        tokens = []
        
        # result[0][0] = 첫 번째 분석 결과의 토큰 리스트
        for token in result[0][0]:
            word = token.form      # 단어
            pos  = token.tag       # 품사
            
            # 품사 필터링 (명사/동사/형용사만)
            pos_prefix = str(pos)[:3]  # 앞 3글자 (NNG, NNP, VV, VA)
            if pos_prefix not in TARGET_POS:
                continue
            
            # 길이 필터 (1글자 제거)
            if len(word) < 2:
                continue
            
            # 불용어 제거
            if word in STOPWORDS:
                continue
            
            tokens.append(word)
        
        return tokens
    
    except Exception:
        return []

# ============================================================
# 3. n-그램 생성
# ============================================================
def make_ngrams(tokens, n=2):
    """바이그램(2-gram) 생성"""
    if len(tokens) < n:
        return []
    return [" ".join(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]

# ============================================================
# 4. 데이터 로드 및 전처리 실행
# ============================================================
print(f"데이터 로드: {INPUT_CSV}")
df = pd.read_csv(INPUT_CSV, encoding="utf-8-sig")
print(f"총 {len(df)}건\n")

# 제목 + 본문 합치기
df["full_text"] = df["title"].fillna("") + " " + df["content"].fillna("")

print("전처리 시작...")
cleaned_texts = []
token_lists   = []
bigram_lists  = []

for text in tqdm(df["full_text"], desc="형태소 분석"):
    # 1단계: 특수문자 제거
    cleaned = clean_text(text)
    cleaned_texts.append(cleaned)
    
    # 2단계: 형태소 분석 + 품사 태깅
    tokens = tokenize(cleaned)
    token_lists.append(tokens)
    
    # 3단계: 바이그램 생성
    bigrams = make_ngrams(tokens, n=2)
    bigram_lists.append(bigrams)

df["cleaned_text"] = cleaned_texts
df["tokens"]       = [" ".join(t) for t in token_lists]   # 공백으로 구분해서 저장
df["bigrams"]      = [" | ".join(b) for b in bigram_lists] # | 로 구분

# ============================================================
# 5. 단어 빈도 계산
# ============================================================
print("\n단어 빈도 계산 중...")

# 전체 토큰 합치기
all_tokens  = [t for tokens in token_lists  for t in tokens]
all_bigrams = [b for bigrams in bigram_lists for b in bigrams]

word_freq   = Counter(all_tokens)
bigram_freq = Counter(all_bigrams)

print(f"고유 단어 수 (유니그램): {len(word_freq):,}개")
print(f"고유 바이그램 수: {len(bigram_freq):,}개")
print(f"전체 토큰 수: {len(all_tokens):,}개")

print("\n=== 상위 30개 단어 ===")
for word, count in word_freq.most_common(30):
    print(f"  {word:15s}: {count:6,}회")

print("\n=== 상위 20개 바이그램 ===")
for bigram, count in bigram_freq.most_common(20):
    print(f"  {bigram:25s}: {count:6,}회")

# ============================================================
# 6. Zipf 법칙 검증
# ============================================================
print("\nZipf 법칙 검증 중...")

# 빈도 순으로 정렬
sorted_freq = sorted(word_freq.values(), reverse=True)
ranks       = np.arange(1, len(sorted_freq) + 1)

# 로그 변환
log_ranks  = np.log10(ranks)
log_freqs  = np.log10(sorted_freq)

# 선형 회귀 (기울기가 -1에 가까우면 Zipf 법칙 성립)
coeffs = np.polyfit(log_ranks, log_freqs, 1)
slope  = coeffs[0]
print(f"Zipf 기울기: {slope:.4f} (이상적인 값: -1.0)")
if abs(slope + 1) < 0.3:
    print("✅ Zipf 법칙 성립 (기울기가 -1에 가까움)")
else:
    print(f"⚠️  Zipf 법칙 부분 성립 (기울기: {slope:.4f})")

# ============================================================
# 7. Heaps 법칙 검증
# ============================================================
print("\nHeaps 법칙 검증 중...")

# 문서가 추가될수록 새 단어가 얼마나 늘어나는지
vocab     = set()
vocab_sizes   = []
token_counts  = []
total_tokens  = 0

for tokens in token_lists:
    for token in tokens:
        vocab.add(token)
        total_tokens += 1
    vocab_sizes.append(len(vocab))
    token_counts.append(total_tokens)

# 로그 변환
log_token_counts = np.log10([max(t, 1) for t in token_counts])
log_vocab_sizes  = np.log10([max(v, 1) for v in vocab_sizes])

# 선형 회귀 (기울기 β: 보통 0.4~0.6)
heaps_coeffs = np.polyfit(log_token_counts, log_vocab_sizes, 1)
heaps_beta   = heaps_coeffs[0]
print(f"Heaps β 값: {heaps_beta:.4f} (일반적인 범위: 0.4~0.6)")
if 0.3 <= heaps_beta <= 0.7:
    print("✅ Heaps 법칙 성립")
else:
    print(f"⚠️  Heaps 법칙 부분 성립 (β: {heaps_beta:.4f})")

# ============================================================
# 8. 그래프 저장
# ============================================================
print("\n그래프 생성 중...")

fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle("삼성전자 뉴스 텍스트 분석", fontsize=16, fontweight="bold")

# 그래프 1: Zipf 법칙 (로그-로그)
ax1 = axes[0, 0]
ax1.scatter(log_ranks[:5000], log_freqs[:5000], alpha=0.3, s=5, color="steelblue")
zipf_line = np.poly1d(coeffs)
ax1.plot(log_ranks[:5000], zipf_line(log_ranks[:5000]), "r-", 
         linewidth=2, label=f"기울기: {slope:.3f}")
ax1.set_xlabel("log(순위)")
ax1.set_ylabel("log(빈도)")
ax1.set_title("Zipf 법칙 검증 (로그-로그 스케일)")
ax1.legend()
ax1.grid(True, alpha=0.3)

# 그래프 2: Heaps 법칙
ax2 = axes[0, 1]
ax2.plot(log_token_counts, log_vocab_sizes, color="green", linewidth=1.5)
heaps_line = np.poly1d(heaps_coeffs)
ax2.plot(log_token_counts, heaps_line(log_token_counts), "r--",
         linewidth=2, label=f"β: {heaps_beta:.3f}")
ax2.set_xlabel("log(전체 토큰 수)")
ax2.set_ylabel("log(어휘 크기)")
ax2.set_title("Heaps 법칙 검증")
ax2.legend()
ax2.grid(True, alpha=0.3)

# 그래프 3: 상위 20개 단어 빈도
ax3 = axes[1, 0]
top20_words  = [w for w, _ in word_freq.most_common(20)]
top20_counts = [c for _, c in word_freq.most_common(20)]
bars = ax3.barh(range(20), top20_counts, color="steelblue", alpha=0.8)
ax3.set_yticks(range(20))
ax3.set_yticklabels(top20_words, fontsize=9)
ax3.set_xlabel("출현 빈도")
ax3.set_title("상위 20개 단어")
ax3.invert_yaxis()
ax3.grid(True, alpha=0.3, axis="x")

# 그래프 4: 상위 15개 바이그램
ax4 = axes[1, 1]
top15_bigrams = [b for b, _ in bigram_freq.most_common(15)]
top15_counts  = [c for _, c in bigram_freq.most_common(15)]
ax4.barh(range(15), top15_counts, color="coral", alpha=0.8)
ax4.set_yticks(range(15))
ax4.set_yticklabels(top15_bigrams, fontsize=8)
ax4.set_xlabel("출현 빈도")
ax4.set_title("상위 15개 바이그램 (2-gram)")
ax4.invert_yaxis()
ax4.grid(True, alpha=0.3, axis="x")

plt.tight_layout()
plt.savefig(OUTPUT_IMG, dpi=150, bbox_inches="tight")
print(f"그래프 저장: {OUTPUT_IMG}")

# ============================================================
# 9. 결과 저장
# ============================================================
df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
print(f"\n전처리 결과 저장: {OUTPUT_CSV}")

print("\n=== 완료 ===")
print(f"전체 문서 수     : {len(df):,}건")
print(f"전체 토큰 수     : {len(all_tokens):,}개")
print(f"고유 단어 수     : {len(word_freq):,}개")
print(f"고유 바이그램 수 : {len(bigram_freq):,}개")
print(f"Zipf 기울기      : {slope:.4f}")
print(f"Heaps β          : {heaps_beta:.4f}")