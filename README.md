# 🎯 LANEIGE Ranking Collector

> Amazon US와 @cosme Japan에서 라네즈 제품 랭킹을 수집하고, **Knowledge Graph 기반 RAG 시스템**으로 인사이트를 제공합니다.

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-88%20passed-green.svg)](#-테스트)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📋 목차

- [주요 기능](#-주요-기능)
- [프로젝트 구조](#-프로젝트-구조)
- [설치 방법](#-설치-방법)
- [사용법](#-사용법)
- [아키텍처](#-아키텍처)
- [API 문서](#-api-문서)
- [테스트](#-테스트)
- [팀 컨벤션](#-팀-컨벤션)

---

## ✨ 주요 기능

| 기능 | 설명 |
|------|------|
| 🕷️ **랭킹 수집** | Amazon US, @cosme Japan에서 자동 수집 |
| 🧠 **Knowledge Graph** | NetworkX 기반 제품-순위-카테고리 관계 그래프 |
| 🔍 **Graph-RAG** | 자연어 질문 → 그래프 검색 → 답변 생성 |
| 📊 **인사이트 분석** | Stable Leader, Rising Star, At Risk 등 자동 탐지 |
| 🌐 **웹 대시보드** | Flask 기반 시각화 및 AI 질의 인터페이스 |
| 🛡️ **컴플라이언스** | Rate Limiting, Robots.txt 준수, Circuit Breaker |

---

## 📁 프로젝트 구조

```
Amore_track7_Star_t/
│
├── 📂 src/
│   ├── collectors/        # 데이터 수집 (Amazon, @cosme)
│   ├── parsers/           # HTML 파싱
│   ├── compliance/        # Rate limit, Robots.txt, Circuit Breaker
│   ├── storage/           # Excel 저장
│   ├── insights/          # 규칙 기반 인사이트 분석
│   │   └── knowledge_engine.py   # R001~R005 규칙 엔진
│   ├── ontology/          # Knowledge Graph (NetworkX)
│   │   ├── entities.py    # ProductNode, RankingRecord 등
│   │   ├── relations.py   # belongsTo, rankedAs 등
│   │   └── graph_builder.py
│   ├── retrieval/         # Graph-RAG Pipeline
│   │   ├── entity_extractor.py   # NER + Intent 분류
│   │   ├── graph_retriever.py    # 그래프 쿼리
│   │   ├── vector_retriever.py   # ChromaDB 벡터 검색
│   │   ├── context_assembler.py  # 컨텍스트 조립
│   │   ├── llm_generator.py      # LLM 응답 생성
│   │   └── rag_pipeline.py       # 통합 파이프라인
│   └── dashboard/         # Flask 웹 대시보드
│
├── 📂 tests/              # 테스트 코드 (88개)
├── 📂 docs/               # 문서 (ontology_schema, knowledge_rules)
├── 📂 data/               # 데이터 파일
├── 📂 .claude/skills/     # Claude AI Skills (8개)
│
├── run_dashboard.py       # 대시보드 실행
├── main.py               # 메인 실행
├── config.yaml           # 설정
└── requirements.txt      # 의존성
```

---

## 🚀 설치 방법

### 1. 레포 클론
```bash
git clone https://github.com/tunatuna1002-lab/Amore_track7_Star_t.git
cd Amore_track7_Star_t
```

### 2. 가상환경 생성 (권장)
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. 의존성 설치
```bash
pip install -r requirements.txt
```

### 4. 테스트 실행
```bash
pytest tests/ -v
```

---

## 💡 사용법

### 웹 대시보드 실행
```bash
# 데모 모드 (샘플 데이터)
python run_dashboard.py --demo

# 실제 데이터
python run_dashboard.py --data data/ranking_data.xlsx
```

**접속**: http://localhost:5000

| 페이지 | URL | 설명 |
|--------|-----|------|
| 대시보드 | `/` | 통계, 차트, 빠른 질문 |
| 순위 목록 | `/rankings` | 필터링, 정렬, CSV 내보내기 |
| 인사이트 | `/insights` | 규칙 기반 분석 결과 |
| AI 질문 | `/query` | 자연어 질의응답 |

### RAG Pipeline 코드 사용
```python
from src.retrieval import create_simple_pipeline

# 파이프라인 생성
pipeline = create_simple_pipeline(ranking_snapshots)

# 질문하기
response = pipeline.query("라네즈 현재 순위는?")
print(response.answer)
# → "LANEIGE Lip Sleeping Mask는 현재 1위입니다 (2024-12-14 기준)"

response = pipeline.query("아마존 립케어 Top 5")
print(response.answer)
```

### 데이터 수집
```bash
# 전체 수집
python main.py

# 특정 마켓만
python main.py --market amazon_us

# 인사이트만 생성
python main.py --insights-only
```

---

## 🏗️ 아키텍처

### RAG Pipeline 흐름

```
사용자 질문
    │
    ▼
┌─────────────────┐
│ Entity Extractor │  ← 브랜드, 카테고리, 시간, Intent 추출
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐ ┌───────┐
│ Graph │ │Vector │  ← 그래프 쿼리 + 벡터 검색
│Retriev│ │Retriev│
└───┬───┘ └───┬───┘
    └────┬────┘
         ▼
┌─────────────────┐
│Context Assembler│  ← 컨텍스트 조립
└────────┬────────┘
         ▼
┌─────────────────┐
│  LLM Generator  │  ← 답변 생성 (Claude API 또는 템플릿)
└────────┬────────┘
         ▼
      응답 반환
```

### Knowledge Graph 구조

```
ProductNode ──belongsTo──▶ CategoryNode
     │                          │
     │──rankedAs──▶ RankingRecord
     │
     │──producedBy──▶ BrandNode
     │
     └──listedOn──▶ PlatformNode
```

### Knowledge Rules (인사이트 규칙)

| Rule ID | 이름 | 조건 | 태그 |
|---------|------|------|------|
| R001 | Stable Leader | Top5 연속 7일+ 유지 | `stable_leader` |
| R002 | Rising Star | 순위 10+ 상승 | `rising_star` |
| R003 | At Risk | 순위 10+ 하락 | `at_risk` |
| R004 | New Entrant | 7일 내 Top100 진입 | `new_entrant` |
| R005 | Recent Exit | 7일 내 Top100 이탈 | `recent_exit` |

---

## 📡 API 문서

### REST Endpoints

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/health` | 헬스 체크 |
| GET | `/api/stats` | 통계 정보 |
| GET | `/api/rankings?limit=100&market=amazon_us` | 순위 조회 |
| GET | `/api/insights` | 인사이트 조회 |
| POST | `/api/query` | RAG 질의 |

### 질의 예시
```bash
curl -X POST http://localhost:5000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "라네즈 현재 순위"}'
```

---

## 🧪 테스트

```bash
# 전체 테스트
pytest tests/ -v

# 특정 모듈 테스트
pytest tests/test_retrieval.py -v
pytest tests/test_ontology.py -v
pytest tests/test_phase4.py -v

# 커버리지 리포트
pytest tests/ --cov=src --cov-report=html
```

**현재 테스트 현황**: ✅ 88 passed, 2 skipped

---

## 📝 팀 컨벤션

### 브랜치 전략
```
main (프로덕션)
  │
  ├── feature/xxx  ← 기능 개발
  ├── fix/xxx      ← 버그 수정
  └── docs/xxx     ← 문서 작업
```

### 커밋 메시지
```
feat: 새 기능 추가
fix: 버그 수정
docs: 문서 수정
refactor: 코드 리팩토링
test: 테스트 추가
```

### PR 체크리스트
- [ ] 테스트 통과 (`pytest tests/ -v`)
- [ ] 코드 리뷰 완료
- [ ] 문서 업데이트 (필요시)

---

## 📊 프로젝트 통계

| 항목 | 수량 |
|------|------|
| Python 소스 | 43개 |
| 테스트 케이스 | 88개 |
| HTML 템플릿 | 7개 |
| Claude Skills | 8개 |

---

## 🛡️ 컴플라이언스 규칙

1. **Robots.txt 준수**: 모든 URL 요청 전 확인
2. **Rate Limiting**: 요청 간 3-8초 랜덤 지연
3. **일일 예산**: 하루 25 요청 제한
4. **Circuit Breaker**: 5회 연속 실패 시 중단
5. **No Evasion**: 프록시, CAPTCHA 우회 없음

---

## 🤝 기여 방법

1. Fork & Clone
2. 브랜치 생성: `git checkout -b feature/my-feature`
3. 커밋: `git commit -m "feat: 새 기능"`
4. Push: `git push origin feature/my-feature`
5. PR 생성

---

## 📞 문의

- **GitHub Issues**: 버그 리포트, 기능 제안

---

## 📜 라이선스

MIT License

---

## 📌 버전 히스토리

| 버전 | 날짜 | 주요 변경사항 |
|------|------|---------------|
| **v2.0** | 2024-12-18 | Phase 1-4 완료: Knowledge Graph, Graph-RAG Pipeline, 웹 대시보드, 벡터 검색 |
| **v1.0** | 2024-12-15 | 초기 버전: 랭킹 수집기, 컴플라이언스, 파서, 기본 인사이트 |

<details>
<summary><b>v1.0 상세 내용 (클릭해서 펼치기)</b></summary>

### v1.0 - 초기 MVP (2024-12-15)

**주요 기능**
- Compliance-first 랭킹 데이터 수집 (Amazon US, @cosme Japan)
- robots.txt 준수, Rate Limiting (3-8초), 일일 25 요청 제한
- Circuit Breaker (5회 연속 실패 시 중단)
- Excel 저장 (append-only, 중복 제거)
- 기본 인사이트: TopN Streak, Rank Shock, New Entry/Exit

**프로젝트 구조**
```
├── src/
│   ├── compliance/    # Compliance guard
│   ├── collectors/    # Amazon, @cosme collectors  
│   ├── parsers/       # HTML parsers
│   ├── storage/       # Excel storage
│   └── insights/      # Basic insights
└── tests/
```

</details>

<details>
<summary><b>v2.0 상세 내용 (클릭해서 펼치기)</b></summary>

### v2.0 - Graph-RAG 시스템 (2024-12-18)

**Phase 1: Skills & Knowledge Base**
- CLAUDE.md 작성
- 8개 Claude Skills 정의
- ontology_schema.yaml, knowledge_rules.yaml

**Phase 2: Ontology Layer**
- NetworkX 기반 Knowledge Graph
- Entities: ProductNode, CategoryNode, RankingRecord, BrandNode, PlatformNode
- Relations: belongsTo, rankedAs, producedBy, listedOn, competesWith
- Knowledge Engine (R001~R005 규칙)

**Phase 3: Graph-RAG Pipeline**
- Entity Extractor (NER + Intent 분류)
- Graph Retriever (8가지 쿼리 패턴)
- Context Assembler (프롬프트 생성)
- RAG Pipeline 통합

**Phase 4: Vector Search & Dashboard**
- ChromaDB 벡터 검색
- LLM Generator (Claude API + 템플릿 fallback)
- Flask 웹 대시보드 (Tailwind CSS)
- REST API 엔드포인트

**통계**
- Python 소스: 43개
- 테스트 케이스: 88개
- HTML 템플릿: 7개

</details>

---

<p align="center">
  Made with ❤️ by <b>Amore Track 7 Star_t Team</b>
</p>
