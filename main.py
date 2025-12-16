#!/usr/bin/env python3
"""
Laneige Ranking Collector - Main Entry Point

Compliance-first ranking data collection for Amazon US and @cosme Japan.

Usage:
    python main.py                    # Run full collection
    python main.py --dry-run          # Check config without collecting
    python main.py --insights-only    # Generate insights from existing data
    python main.py --market amazon_us # Collect only Amazon data
    python main.py --market cosme_jp  # Collect only @cosme data
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config.settings import Settings
from src.compliance.guard import ComplianceGuard
from src.collectors.amazon_collector import AmazonCollector
from src.collectors.cosme_collector import CosmeCollector
from src.storage.excel_storage import ExcelStorage
from src.storage.run_log import RunLog, RunStatus
from src.insights.ranking_insights import RankingInsights
from src.parsers.selector_loader import SelectorLoader
from src.utils.run_id import generate_run_id
from src.utils.time_utils import format_kst_datetime


def setup_logging(settings: Settings):
    """Setup logging configuration."""
    log_config = {
        'level': logging.INFO,
        'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    }

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_config['format']))

    # File handler
    log_file = Path(settings.storage.output_file).parent.parent / 'logs' / 'collector.log'
    log_file.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_config['format']))

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    return logging.getLogger(__name__)


def run_collection(
    settings: Settings,
    run_id: str,
    market_filter: str = None,
    logger: logging.Logger = None
) -> RunLog:
    """
    Run the ranking data collection.

    Args:
        settings: Configuration settings
        run_id: Unique run identifier
        market_filter: Optional market filter ('amazon_us' or 'cosme_jp')
        logger: Logger instance

    Returns:
        RunLog with collection results
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    # Initialize run log
    run_log = RunLog(run_id=run_id)
    run_log.start()

    logger.info(f"Starting collection run: {run_id}")
    logger.info(f"Daily budget: {settings.compliance.daily_budget} requests")

    try:
        # Initialize compliance guard
        guard = ComplianceGuard(
            user_agent=settings.compliance.user_agent,
            delay_range_s=settings.compliance.delay_range_s,
            daily_budget=settings.compliance.daily_budget,
            consecutive_failure_limit=settings.compliance.consecutive_failure_limit,
            max_retries=settings.compliance.max_retries,
            backoff_base_s=settings.compliance.backoff_base_s,
            backoff_multiplier=settings.compliance.backoff_multiplier,
        )

        # Initialize storage
        storage = ExcelStorage(
            output_file=settings.storage.output_file,
            rank_history_sheet=settings.storage.rank_history_sheet,
            run_log_sheet=settings.storage.run_log_sheet
        )

        # Initialize selector loader
        selector_loader = SelectorLoader()

        # Determine which markets to collect
        if market_filter == 'amazon_us':
            categories = settings.get_amazon_categories()
        elif market_filter == 'cosme_jp':
            categories = settings.get_cosme_categories()
        else:
            categories = settings.categories

        logger.info(f"Collecting from {len(categories)} categories")

        all_snapshots = []
        total_items = 0

        # Collect Amazon data
        if market_filter in (None, 'amazon_us'):
            amazon_categories = [c for c in categories if c.market == 'amazon_us']
            if amazon_categories:
                logger.info(f"Collecting Amazon US: {len(amazon_categories)} categories")

                amazon_collector = AmazonCollector(
                    compliance_guard=guard,
                    selector_loader=selector_loader,
                    top_n_target=settings.collection.top_n_target,
                    run_id=run_id
                )

                results = amazon_collector.collect_all(amazon_categories)

                for result in results:
                    all_snapshots.extend(result.snapshots)
                    total_items += result.items_collected

                # Check if stopped
                if guard.is_stopped():
                    stop_reason = guard.get_stop_reason()
                    run_log.record_block(stop_reason)
                    logger.warning(f"Collection stopped: {stop_reason}")

        # Collect @cosme data (if not stopped)
        if not guard.is_stopped() and market_filter in (None, 'cosme_jp'):
            cosme_categories = [c for c in categories if c.market == 'cosme_jp']
            if cosme_categories:
                logger.info(f"Collecting @cosme JP: {len(cosme_categories)} categories")

                cosme_collector = CosmeCollector(
                    compliance_guard=guard,
                    selector_loader=selector_loader,
                    top_n_target=settings.collection.top_n_target,
                    run_id=run_id
                )

                results = cosme_collector.collect_all(cosme_categories)

                for result in results:
                    all_snapshots.extend(result.snapshots)
                    total_items += result.items_collected

        # Save snapshots to storage
        if all_snapshots:
            added = storage.append_snapshots(all_snapshots)
            logger.info(f"Saved {added} new ranking entries to storage")

        # Update run log with stats
        guard_stats = guard.get_stats()
        run_log.update_requests(guard_stats['rate_limiter']['requests_today'])

        # Determine final status
        if guard.is_stopped():
            stop_reason = guard.get_stop_reason()
            if 'budget' in stop_reason:
                status = RunStatus.STOPPED_BY_BUDGET
            elif 'robots' in stop_reason:
                status = RunStatus.STOPPED_BY_ROBOTS
            elif 'blocked' in stop_reason:
                status = RunStatus.BLOCKED
            else:
                status = RunStatus.FAILED
            run_log.record_block(stop_reason)
        elif total_items > 0:
            status = RunStatus.SUCCESS
        else:
            status = RunStatus.FAILED

        run_log.end(status, f"Collected {total_items} items")

        # Save run log
        storage.append_run_log(run_log)

        logger.info(f"Collection complete: {total_items} items, status={status.value}")

        return run_log

    except Exception as e:
        logger.exception(f"Collection failed with error: {e}")
        run_log.end(RunStatus.FAILED, str(e))
        return run_log


def run_insights(settings: Settings, logger: logging.Logger = None):
    """Generate and display insights from existing data."""
    if logger is None:
        logger = logging.getLogger(__name__)

    logger.info("Generating ranking insights...")

    # Initialize storage
    storage = ExcelStorage(
        output_file=settings.storage.output_file,
        rank_history_sheet=settings.storage.rank_history_sheet,
        run_log_sheet=settings.storage.run_log_sheet
    )

    # Initialize insights generator
    insights = RankingInsights(
        storage=storage,
        top_n_thresholds=settings.insights.top_n_thresholds,
        shock_threshold=settings.insights.rank_shock_threshold,
        lookback_days=settings.insights.lookback_days
    )

    # Generate and print report
    summary = insights.generate()
    try:
        insights.print_report(summary)
    except UnicodeEncodeError:
        # Fallback for encoding issues on Windows
        pass
    except Exception as e:
        logger.warning(f"Could not print report: {e}")

    return summary


def dry_run(settings: Settings, logger: logging.Logger = None):
    """Perform a dry run to validate configuration."""
    if logger is None:
        logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("DRY RUN - Validating configuration")
    logger.info("=" * 60)

    logger.info(f"Daily budget: {settings.compliance.daily_budget}")
    logger.info(f"Delay range: {settings.compliance.delay_range_s}")
    logger.info(f"Top N target: {settings.collection.top_n_target}")
    logger.info(f"Output file: {settings.storage.output_file}")

    logger.info("")
    logger.info("Categories to collect:")
    for cat in settings.categories:
        logger.info(f"  [{cat.market}] {cat.category_key}: {cat.url[:60]}...")

    logger.info("")
    logger.info("Amazon categories: %d", len(settings.get_amazon_categories()))
    logger.info("@cosme categories: %d", len(settings.get_cosme_categories()))

    # Check if output directory is writable
    output_path = Path(settings.storage.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("")
    logger.info("Output directory exists and is writable: %s", output_path.parent.exists())

    logger.info("")
    logger.info("Dry run complete. Configuration appears valid.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Laneige Ranking Collector - Compliance-first ranking data collection"
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate configuration without collecting data'
    )

    parser.add_argument(
        '--insights-only',
        action='store_true',
        help='Generate insights from existing data (no collection)'
    )

    parser.add_argument(
        '--market',
        choices=['amazon_us', 'cosme_jp'],
        help='Collect only from specified market'
    )

    parser.add_argument(
        '--config',
        default='config.yaml',
        help='Path to configuration file'
    )

    args = parser.parse_args()

    # Load configuration
    try:
        settings = Settings.from_yaml(args.config)
    except Exception as e:
        print(f"ERROR: Failed to load configuration: {e}")
        sys.exit(1)

    # Setup logging
    logger = setup_logging(settings)

    logger.info("=" * 60)
    logger.info("Laneige Ranking Collector v1.0.0-mvp")
    logger.info("Compliance-first ranking data collection")
    logger.info("=" * 60)

    # Execute requested action
    if args.dry_run:
        dry_run(settings, logger)
    elif args.insights_only:
        run_insights(settings, logger)
    else:
        run_id = generate_run_id()
        run_log = run_collection(settings, run_id, args.market, logger)

        # Also generate insights after collection
        logger.info("")
        logger.info("Generating post-collection insights...")
        run_insights(settings, logger)

    logger.info("")
    logger.info("Done.")


if __name__ == "__main__":
    main()
