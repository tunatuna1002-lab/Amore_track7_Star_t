# Laneige Ranking Collector

> Compliance-first ranking data collection system for Amazon US and @cosme Japan

## Project Overview

아모레퍼시픽 공모전용 랭킹 수집·분석 에이전트입니다.  
**Compliance-first** 원칙으로 Amazon US와 일본 @cosme의 화장품 랭킹 데이터를 수집하고,  
시계열 인사이트(Streak, Shock, Entry/Exit)를 생성합니다.

## Tech Stack

- **Python 3.12**
- **HTTP**: requests (ComplianceGuard 통해서만 사용)
- **Parsing**: BeautifulSoup4, lxml
- **Storage**: openpyxl (Excel)
- **Config**: PyYAML
- **Testing**: pytest

## Directory Structure

```
src/
├── compliance/     # ComplianceGuard, RobotsHandler, RateLimiter, CircuitBreaker
├── collectors/     # AmazonCollector, CosmeCollector (BaseCollector 상속)
├── parsers/        # HTML 파서 (3단계 Fallback: Primary→Fallback→Heuristic)
├── insights/       # StreakAnalyzer, ShockDetector, EntryExitTracker
├── storage/        # ExcelStorage (MD5 기반 중복 제거)
├── config/         # ConfigLoader, SelectorLoader
└── utils/          # 헬퍼 유틸리티

tests/              # pytest 테스트
data/               # ranking_data.xlsx (출력)
logs/               # collector.log (실행 로그)
```

## ⚠️ Critical Rules (절대 규칙)

### 1. Compliance Rules

```
✅ 모든 HTTP 요청은 반드시 ComplianceGuard.fetch()를 통해서만 수행
✅ robots.txt 준수 필수
✅ 요청 간 딜레이: 3-8초 (랜덤)
✅ 일일 요청 예산: 25건 (하드 리밋)
✅ Circuit Breaker: 5회 연속 실패 시 중단

❌ 절대 금지:
   - requests.get() 직접 호출
   - Proxy Rotation
   - CAPTCHA Bypass
   - User-Agent Spoofing
   - Stealth Tactics
```

### 2. Parser Rules

```
✅ 모든 CSS 셀렉터는 selectors.yaml에서 로드
✅ 3단계 Fallback 체인 필수: Primary → Fallback → Heuristic
❌ 파서 코드에 셀렉터 하드코딩 금지
```

### 3. Data Quality Rules

```
✅ 중복 제거: MD5(date_kst|market|category_key|rank|product_url)
✅ 인코딩: UTF-8 (일본어 @cosme 지원)
✅ 필수 필드: date_kst, market, category_key, rank, product_name_raw
```

## Build & Run Commands

```bash
# 의존성 설치
pip install -r requirements.txt

# 설정 검증 (dry-run)
python main.py --dry-run

# 수집 실행
python main.py

# 특정 마켓만 실행
python main.py --market amazon_us
python main.py --market cosme_jp

# 테스트 실행
pytest tests/ -v

# 커버리지 확인
pytest tests/ --cov=src --cov-report=html
```

## Configuration Files

| 파일 | 용도 |
|------|------|
| `config.yaml` | 마켓 설정, 카테고리 URL, Compliance 파라미터 |
| `selectors.yaml` | CSS 셀렉터 정의 (Primary/Fallback/Heuristic) |

## Insights (인사이트 규칙)

| 인사이트 | 조건 | 클래스 |
|---------|------|--------|
| **Streak** | TopN 연속 N일 유지 | `StreakAnalyzer` |
| **Shock** | 순위 ±3 이상 급변 | `ShockDetector` |
| **Entry** | TopN 신규 진입 (lookback 내) | `EntryExitTracker` |
| **Exit** | TopN 이탈 (lookback 내) | `EntryExitTracker` |

## Related Documentation

- `.claude/skills/` - Claude Skills (워크플로우 가이드라인)
- `docs/ontology_schema.yaml` - 온톨로지 스키마 정의
- `docs/knowledge_rules.yaml` - 비즈니스 규칙 정의

## Key Contacts & References

- **프로젝트**: 아모레퍼시픽 AI Challenge 2026
- **대상 브랜드**: LANEIGE (라네즈)
- **데이터 소스**: Amazon US Best Sellers, @cosme Japan Rankings

---

> 💡 **Tip**: Skills를 통해 자동으로 Compliance, Selector, Data Quality 검증이 트리거됩니다.
