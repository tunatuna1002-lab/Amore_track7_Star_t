# Laneige Ranking Collector - Graph-RAG System

## 🎯 프로젝트 개요

Amazon US와 @cosme Japan에서 라네즈 제품 랭킹을 수집하고,
Knowledge Graph 기반 RAG 시스템으로 인사이트를 제공하는 시스템입니다.

## 📁 프로젝트 구조

```
Amore_track7_Star_t/
├── CLAUDE.md                          # AI 어시스턴트 가이드
├── requirements.txt                   # Python 의존성
├── run_dashboard.py                   # 대시보드 실행 스크립트
│
├── src/
│   ├── collectors/                    # 데이터 수집
│   │   ├── amazon_collector.py
│   │   ├── cosme_collector.py
│   │   └── base_collector.py
│   │
│   ├── parsers/                       # HTML 파싱
│   │   ├── amazon_parser.py
│   │   ├── cosme_parser.py
│   │   ├── base_parser.py
│   │   └── selector_loader.py
│   │
│   ├── compliance/                    # 컴플라이언스
│   │   ├── guard.py                   # 통합 가드
│   │   ├── rate_limiter.py
│   │   ├── circuit_breaker.py
│   │   └── robots_handler.py
│   │
│   ├── storage/                       # 데이터 저장
│   │   ├── excel_storage.py
│   │   └── run_log.py
│   │
│   ├── insights/                      # 인사이트 분석
│   │   ├── streak_analyzer.py         # R001: Stable Leader
│   │   ├── shock_detector.py          # R002/R003: Rising/At Risk
│   │   ├── entry_exit_tracker.py      # R004/R005: Entry/Exit
│   │   ├── ranking_insights.py        # 통합 분석
│   │   └── knowledge_engine.py        # 규칙 엔진
│   │
│   ├── ontology/                      # Knowledge Graph
│   │   ├── entities.py                # Entity 정의
│   │   ├── relations.py               # Relation 정의
│   │   └── graph_builder.py           # NetworkX 그래프
│   │
│   ├── retrieval/                     # Graph-RAG Pipeline
│   │   ├── entity_extractor.py        # NER + Intent 분류
│   │   ├── graph_retriever.py         # 그래프 쿼리
│   │   ├── vector_retriever.py        # ChromaDB 벡터 검색
│   │   ├── context_assembler.py       # 컨텍스트 조립
│   │   ├── llm_generator.py           # LLM 응답 생성
│   │   └── rag_pipeline.py            # 통합 파이프라인
│   │
│   └── dashboard/                     # 웹 대시보드
│       ├── app.py                     # Flask 앱
│       └── templates/                 # HTML 템플릿
│           ├── base.html
│           ├── index.html             # 메인 대시보드
│           ├── rankings.html          # 순위 테이블
│           ├── insights.html          # 인사이트
│           └── query.html             # AI 질문
│
├── .claude/skills/                    # Claude Skills (8개)
│   ├── ComplianceGuardian/
│   ├── SelectorValidator/
│   ├── DataQualityGuard/
│   ├── InsightRuleEngine/
│   ├── TestCoverageGuardian/
│   ├── OntologyValidator/
│   ├── GraphRAGBuilder/
│   └── web-artifacts-builder/
│
├── docs/
│   ├── ontology_schema.yaml           # 온톨로지 스키마
│   ├── knowledge_rules.yaml           # 지식 규칙
│   └── PROJECT_SUMMARY.md             # 이 문서
│
└── tests/
    ├── test_compliance.py
    ├── test_parsers.py
    ├── test_insights.py
    ├── test_ontology.py
    ├── test_retrieval.py
    └── test_phase4.py
```

## 🔧 설치 및 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 테스트 실행
pytest tests/ -v

# 대시보드 실행 (데모 모드)
python run_dashboard.py --demo

# 대시보드 실행 (데이터 파일)
python run_dashboard.py --data ranking_data.xlsx --port 8080
```

## 🌐 웹 대시보드

```
http://localhost:5000/          # 메인 대시보드
http://localhost:5000/rankings  # 순위 테이블
http://localhost:5000/insights  # AI 인사이트
http://localhost:5000/query     # 자연어 질의
```

### API 엔드포인트
- `GET /api/health` - 헬스 체크
- `GET /api/stats` - 통계
- `GET /api/rankings?limit=100&market=amazon_us` - 순위 조회
- `GET /api/insights` - 인사이트 조회
- `POST /api/query` - RAG 질의 (`{"query": "라네즈 순위"}`)

## 🧠 Knowledge Graph 구조

### Entities
| Entity | 설명 | Primary Key |
|--------|------|-------------|
| ProductNode | 제품 정보 | MD5(product_url) |
| CategoryNode | 랭킹 카테고리 | market_category_key |
| PlatformNode | 플랫폼 (Amazon, @cosme) | market enum |
| RankingRecord | 순위 기록 (시계열) | MD5(composite_key) |
| BrandNode | 브랜드 정보 | brand_id |
| EventNode | 이벤트 (프라임데이 등) | event_id |

### Relations
| Relation | From → To | 설명 |
|----------|-----------|------|
| belongsTo | Product → Category | 카테고리 소속 |
| listedOn | Product → Platform | 플랫폼 등록 |
| rankedAs | Product → Ranking | 순위 기록 |
| competesWith | Product ↔ Product | 경쟁 관계 |
| producedBy | Product → Brand | 브랜드 소속 |

## 📊 Knowledge Rules

| Rule ID | 이름 | 조건 |
|---------|------|------|
| R001 | Stable Leader | Top5 연속 7일+ 유지 |
| R002 | Rising Star | 순위 10+ 상승 |
| R003 | At Risk | 순위 10+ 하락 |
| R004 | New Entrant | 7일 내 Top100 진입 |
| R005 | Recent Exit | 7일 내 Top100 이탈 |

## 🔍 RAG Pipeline

```
User Query → Entity Extraction → Graph Retrieval → Vector Search → Context Assembly → LLM Generation
     │              │                    │              │                │              │
     │       • 브랜드 인식        • 순위 조회      • 유사 제품       • 그래프 결과      • Claude API
     │       • 카테고리 인식      • 히스토리       • 관련 인사이트    • 규칙 매칭       • 또는 템플릿
     │       • 시간 표현 인식     • 경쟁사 분석                      • 벡터 결과       • 근거 제시
     │       • Intent 분류       • Top N 조회
```

### 지원 Intent
- CURRENT_RANK: "현재 순위는?"
- RANK_HISTORY: "순위 변동 추이"
- TOP_N: "Top 10 제품"
- COMPARISON: "경쟁사 대비"
- TREND: "트렌드 분석"

## 📈 통계 (Phase 1-4 완료)

| 항목 | 수량 |
|------|------|
| Python 소스 파일 | 45개 |
| 테스트 파일 | 7개 |
| 테스트 케이스 | 88개 통과 (2개 스킵) |
| Skills | 8개 |
| HTML 템플릿 | 6개 |

## ✅ 완료된 Phase

### Phase 1: Skills & Knowledge Base ✅
- CLAUDE.md, Skills (5개), ontology_schema.yaml, knowledge_rules.yaml

### Phase 2: Ontology Layer ✅
- entities.py, relations.py, graph_builder.py, knowledge_engine.py
- OntologyValidator SKILL, GraphRAGBuilder SKILL

### Phase 3: Graph-RAG Pipeline ✅
- entity_extractor.py, graph_retriever.py, context_assembler.py, rag_pipeline.py

### Phase 4: Vector Search, LLM, Dashboard ✅
- vector_retriever.py (ChromaDB)
- llm_generator.py (Claude API + Fallback)
- dashboard/ (Flask + Tailwind CSS)

---

Created: 2024-12-17
Updated: 2024-12-18
Version: 2.0.0
