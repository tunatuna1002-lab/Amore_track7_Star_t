#!/usr/bin/env python
"""
Run the LANEIGE Ranking Dashboard.

Usage:
    python run_dashboard.py                    # Basic demo mode
    python run_dashboard.py --data data.xlsx   # With data file
    python run_dashboard.py --port 8080        # Custom port
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


def generate_demo_data():
    """Generate demo ranking data."""
    base_date = datetime(2024, 12, 1)
    snapshots = []
    
    # LANEIGE Lip Sleeping Mask - Berry (improving trend)
    ranks_lsm = [8, 7, 6, 5, 4, 4, 3, 3, 2, 2, 1, 1, 1, 1]
    for i, rank in enumerate(ranks_lsm):
        snapshots.append({
            "date_kst": (base_date + timedelta(days=i)).strftime("%Y-%m-%d"),
            "market": "amazon_us",
            "category_key": "lip_care",
            "category_url": "https://amazon.com/lip-care",
            "rank": rank,
            "product_name_raw": "LANEIGE Lip Sleeping Mask - Berry",
            "brand_raw": "LANEIGE",
            "product_url": "https://amazon.com/dp/B00BXZZZZZ",
            "parse_status": "full",
            "run_id": f"run_{i:03d}",
        })
    
    # LANEIGE Water Sleeping Mask (stable)
    for i in range(14):
        snapshots.append({
            "date_kst": (base_date + timedelta(days=i)).strftime("%Y-%m-%d"),
            "market": "amazon_us",
            "category_key": "face_mask",
            "category_url": "https://amazon.com/face-mask",
            "rank": 5 + (i % 3),
            "product_name_raw": "LANEIGE Water Sleeping Mask",
            "brand_raw": "LANEIGE",
            "product_url": "https://amazon.com/dp/B00WSSSSS",
            "parse_status": "full",
            "run_id": f"run_{i:03d}",
        })
    
    # Competitor: Burt's Bees
    for i in range(14):
        snapshots.append({
            "date_kst": (base_date + timedelta(days=i)).strftime("%Y-%m-%d"),
            "market": "amazon_us",
            "category_key": "lip_care",
            "category_url": "https://amazon.com/lip-care",
            "rank": 2 if i < 10 else 3,
            "product_name_raw": "Burt's Bees 100% Natural Lip Balm",
            "brand_raw": "Burt's Bees",
            "product_url": "https://amazon.com/dp/BURTSBEES",
            "parse_status": "full",
            "run_id": f"run_{i:03d}",
        })
    
    # Competitor: Vaseline
    for i in range(14):
        snapshots.append({
            "date_kst": (base_date + timedelta(days=i)).strftime("%Y-%m-%d"),
            "market": "amazon_us",
            "category_key": "lip_care",
            "category_url": "https://amazon.com/lip-care",
            "rank": 4 + (i % 2),
            "product_name_raw": "Vaseline Lip Therapy",
            "brand_raw": "Vaseline",
            "product_url": "https://amazon.com/dp/VASELINE",
            "parse_status": "full",
            "run_id": f"run_{i:03d}",
        })
    
    # @cosme Japan data
    ranks_cosme = [3, 3, 2, 2, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1]
    for i, rank in enumerate(ranks_cosme):
        snapshots.append({
            "date_kst": (base_date + timedelta(days=i)).strftime("%Y-%m-%d"),
            "market": "cosme_jp",
            "category_key": "lip_care",
            "category_url": "https://cosme.net/lip-care",
            "rank": rank,
            "product_name_raw": "ラネージュ リップスリーピングマスク",
            "brand_raw": "LANEIGE",
            "product_url": "https://cosme.net/product/laneige-lsm",
            "parse_status": "full",
            "run_id": f"run_{i:03d}",
        })
    
    return snapshots


def main():
    parser = argparse.ArgumentParser(description="LANEIGE Ranking Dashboard")
    parser.add_argument("--data", type=str, help="Path to Excel data file")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind to")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--demo", action="store_true", help="Run with demo data")
    args = parser.parse_args()
    
    print("=" * 60)
    print("🚀 LANEIGE Ranking Dashboard")
    print("=" * 60)
    
    # Import here to avoid circular imports
    from src.retrieval import create_simple_pipeline
    from src.dashboard.app import create_app, DashboardApp
    
    # Load or generate data
    if args.data and Path(args.data).exists():
        print(f"📂 Loading data from: {args.data}")
        # Load from Excel
        from src.storage import ExcelStorage
        storage = ExcelStorage(args.data)
        snapshots = storage.get_rank_history()
    elif args.data:
        # 파일 경로 지정했지만 파일이 없는 경우
        print(f"⚠️ 파일을 찾을 수 없음: {args.data}")
        print("🎭 데모 데이터로 대체합니다...")
        snapshots = generate_demo_data()
    else:
        print("🎭 Using demo data...")
        snapshots = generate_demo_data()
    
    print(f"📊 Loaded {len(snapshots)} ranking records")
    
    # Create RAG pipeline
    print("🔧 Initializing RAG pipeline...")
    pipeline = create_simple_pipeline(snapshots)
    
    # Create dashboard app
    dashboard_app = DashboardApp(rag_pipeline=pipeline)
    dashboard_app.set_sample_data(snapshots)
    
    # Create Flask app
    app = create_app(dashboard_app, debug=args.debug)
    
    print()
    print(f"🌐 Dashboard ready at: http://{args.host}:{args.port}")
    print(f"📖 API docs at: http://{args.host}:{args.port}/api/health")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 60)
    
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
