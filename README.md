# Laneige Ranking Collector

**Compliance-first ranking data collection for Amazon US Best Sellers and @cosme Japan.**

This MVP collects **ranking data only** (no reviews, no full review text) from fixed category URLs, stores daily snapshots in append-only Excel sheets, and generates ranking-focused insights.

## Key Features

- **Compliance-First**: All requests go through `ComplianceGuard` which enforces:
  - robots.txt verification per domain
  - Random delay (3-8 seconds) between requests
  - Crawl-delay from robots.txt (if specified)
  - Daily request budget (hard stop at 25 requests)
  - Circuit breaker for failures (stops after 5 consecutive failures)
  - No proxy rotation, no CAPTCHA bypass, no stealth tactics

- **Ranking-Only Data**: Collects product rankings, names, URLs, and brands (when available)

- **Append-Only Storage**: Excel file with deduplication via deterministic row keys

- **Ranking Insights**:
  1. TopN Streak: Consecutive days inside Top5/Top10/Top100
  2. Rank Shock: Significant day-to-day rank changes (±3 or more)
  3. New Entry/Exit: First entry into TopN or recent exit within 7 days

## Project Structure

```
├── config.yaml           # Main configuration
├── selectors.yaml        # CSS/XPath selectors (externalized)
├── main.py               # Entry point
├── requirements.txt      # Python dependencies
├── src/
│   ├── compliance/       # Compliance guard, robots.txt, rate limiting
│   ├── collectors/       # Amazon and @cosme collectors
│   ├── config/           # Settings management
│   ├── insights/         # Ranking insights generation
│   ├── parsers/          # HTML parsers with selector fallback
│   ├── storage/          # Excel storage with openpyxl
│   └── utils/            # Utility functions
├── tests/
│   ├── fixtures/         # HTML fixtures for testing
│   └── test_*.py         # Unit tests
└── data/                 # Output directory (created automatically)
```

## Installation

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Mac/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Run Full Collection

```bash
python main.py
```

### Dry Run (Validate Config)

```bash
python main.py --dry-run
```

### Generate Insights Only (No Collection)

```bash
python main.py --insights-only
```

### Collect Specific Market Only

```bash
# Amazon US only
python main.py --market amazon_us

# @cosme Japan only
python main.py --market cosme_jp
```

## Configuration

### config.yaml

Key settings:

```yaml
compliance:
  daily_budget: 25              # Hard request limit per day
  delay_range_s:
    min: 3
    max: 8
  consecutive_failure_limit: 5  # Circuit breaker threshold

collection:
  top_n_target: 100             # Rankings to collect per category

categories:
  # 5 Amazon US + 5 @cosme JP categories
  - url: "https://www.amazon.com/Best-Sellers-Beauty..."
    category_key: "beauty_overall"
    market: "amazon_us"
```

### selectors.yaml

Externalized CSS selectors for easy maintenance:

```yaml
amazon_us:
  primary:
    product_card: "div[data-asin]"
    rank:
      css: "span.zg-bdg-text"
    product_name:
      css: "a.a-link-normal span div"
  fallback:
    # Backup selectors if primary fails
  heuristic:
    # Structural patterns for last-resort parsing
```

**Important**: Selectors must be verified against live pages. The provided selectors are templates that may need updating.

## Data Output

### Excel File: `data/ranking_data.xlsx`

**Sheet: `rank_history_min`**
| Column | Description |
|--------|-------------|
| date_kst | Collection date (YYYY-MM-DD) |
| market | amazon_us or cosme_jp |
| category_key | Category identifier |
| category_url | Source URL |
| rank | Product rank (1, 2, 3...) |
| product_name_raw | Product name |
| brand_raw | Brand (if available) |
| product_url | Product detail URL |
| run_id | Collection run identifier |
| parse_status | ok / partial / failed |
| notes | Additional notes |

**Sheet: `run_log`**
| Column | Description |
|--------|-------------|
| run_id | Unique run identifier |
| started_at_kst | Run start time |
| ended_at_kst | Run end time |
| status | success / partial / failed / stopped_by_* |
| requests_used | Total requests made |
| blocked_reason | If blocked, the reason |
| notes | Additional notes |

## Compliance Rules (Hard Requirements)

1. **Respect robots.txt**: All URLs checked against robots.txt before fetching
2. **Rate Limiting**: 3-8 second random delay between requests
3. **Crawl-delay**: Obey if specified in robots.txt
4. **Daily Budget**: Hard stop at 25 requests/day
5. **Circuit Breaker**: Stop after 5 consecutive failures
6. **No Evasion**: No proxy rotation, no CAPTCHA bypass, no stealth

If blocked (HTTP 429/403/503, CAPTCHA detection):
- Stop immediately
- Record in run_log with blocked_reason
- Do NOT retry aggressively

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=src

# Run specific test file
pytest tests/test_parsers.py -v
```

### Generating Test Fixtures

1. Open the actual Amazon Best Sellers or @cosme ranking page in your browser
2. Right-click → "Save page as..." → "Webpage, Complete"
3. Copy the saved HTML file to `tests/fixtures/`
4. Update the fixture path in tests if needed

## TODO / Known Issues

- [ ] **Verify selectors**: The CSS selectors in `selectors.yaml` are templates. Verify against live pages before production use.
- [ ] **Pagination**: Amazon pagination may require selector verification
- [ ] **@cosme structure**: @cosme page structure may vary by category
- [ ] **Brand extraction**: Brand data may not be reliably available on list pages

## Architecture Notes

### ComplianceGuard

Central gate for ALL HTTP requests:
```python
guard = ComplianceGuard(...)
result = guard.fetch(url)  # The ONLY way to make requests
```

### Parser Fallback Strategy

1. **Primary selectors**: Try configured selectors first
2. **Fallback selectors**: Try alternate selectors if primary fails
3. **Heuristic parsing**: Structural pattern matching as last resort

### Deduplication

Rows are deduplicated by deterministic key:
```
MD5(date_kst | market | category_key | rank | product_url)
```

## License

Internal project for research purposes.

## Contact

For questions about this project, please contact the development team.
