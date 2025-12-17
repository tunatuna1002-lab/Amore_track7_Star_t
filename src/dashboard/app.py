"""
Flask application for the Laneige Ranking Dashboard.

Provides REST API endpoints and web interface for:
- Ranking data visualization
- Graph-RAG queries
- Insights and trends
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from flask import Flask, render_template, request, jsonify, Response

logger = logging.getLogger(__name__)


class DashboardApp:
    """
    Dashboard application wrapper.
    
    Manages Flask app, RAG pipeline, and data connections.
    """
    
    def __init__(
        self,
        rag_pipeline=None,
        storage=None,
        data_dir: str = "./data",
    ):
        """
        Initialize the dashboard application.
        
        Args:
            rag_pipeline: Optional RAGPipeline instance
            storage: Optional ExcelStorage instance
            data_dir: Directory for data files
        """
        self.rag_pipeline = rag_pipeline
        self.storage = storage
        self.data_dir = Path(data_dir)
        
        # Sample data for demo
        self._sample_data = None
    
    def get_ranking_data(self, limit: int = 100) -> List[dict]:
        """Get ranking data from storage or sample."""
        if self.storage:
            return self.storage.get_rank_history()[-limit:]
        
        if self._sample_data:
            return self._sample_data[-limit:]
        
        return []
    
    def get_insights(self) -> List[dict]:
        """Get insights from knowledge engine."""
        if self.rag_pipeline and hasattr(self.rag_pipeline, 'knowledge_engine'):
            matches = self.rag_pipeline.knowledge_engine.evaluate_all(
                self.get_ranking_data()
            )
            return [m.to_dict() for m in matches]
        return []
    
    def query(self, query_text: str) -> dict:
        """Process a RAG query."""
        if not self.rag_pipeline:
            return {
                "answer": "RAG 파이프라인이 초기화되지 않았습니다.",
                "confidence": 0,
                "sources": [],
            }
        
        response = self.rag_pipeline.query(query_text)
        return response.to_dict()
    
    def set_sample_data(self, data: List[dict]):
        """Set sample data for demo."""
        self._sample_data = data


def create_app(
    dashboard_app: Optional[DashboardApp] = None,
    debug: bool = False,
) -> Flask:
    """
    Create Flask application.
    
    Args:
        dashboard_app: DashboardApp instance
        debug: Enable debug mode
        
    Returns:
        Configured Flask app
    """
    # Get template and static directories
    base_dir = Path(__file__).parent
    template_dir = base_dir / "templates"
    static_dir = base_dir / "static"
    
    app = Flask(
        __name__,
        template_folder=str(template_dir),
        static_folder=str(static_dir),
    )
    app.debug = debug
    
    # Store dashboard app in config
    app.config["DASHBOARD_APP"] = dashboard_app or DashboardApp()
    
    # =========================================================================
    # Web Routes
    # =========================================================================
    
    @app.route("/")
    def index():
        """Main dashboard page."""
        return render_template("index.html")
    
    @app.route("/rankings")
    def rankings_page():
        """Rankings table page."""
        return render_template("rankings.html")
    
    @app.route("/insights")
    def insights_page():
        """Insights page."""
        return render_template("insights.html")
    
    @app.route("/query")
    def query_page():
        """Query interface page."""
        return render_template("query.html")
    
    # =========================================================================
    # API Routes
    # =========================================================================
    
    @app.route("/api/rankings")
    def api_rankings():
        """Get ranking data."""
        dashboard = app.config["DASHBOARD_APP"]
        
        # Query parameters
        limit = request.args.get("limit", 100, type=int)
        market = request.args.get("market")
        brand = request.args.get("brand")
        
        data = dashboard.get_ranking_data(limit)
        
        # Filter by market
        if market:
            data = [d for d in data if d.get("market") == market]
        
        # Filter by brand
        if brand:
            brand_lower = brand.lower()
            data = [
                d for d in data
                if brand_lower in d.get("brand_raw", "").lower()
            ]
        
        return jsonify({
            "success": True,
            "count": len(data),
            "data": data,
        })
    
    @app.route("/api/insights")
    def api_insights():
        """Get insights."""
        dashboard = app.config["DASHBOARD_APP"]
        insights = dashboard.get_insights()
        
        return jsonify({
            "success": True,
            "count": len(insights),
            "data": insights,
        })
    
    @app.route("/api/query", methods=["POST"])
    def api_query():
        """Process RAG query."""
        dashboard = app.config["DASHBOARD_APP"]
        
        data = request.get_json()
        if not data or "query" not in data:
            return jsonify({
                "success": False,
                "error": "Missing 'query' field",
            }), 400
        
        query_text = data["query"]
        result = dashboard.query(query_text)
        
        return jsonify({
            "success": True,
            "result": result,
        })
    
    @app.route("/api/stats")
    def api_stats():
        """Get dashboard statistics."""
        dashboard = app.config["DASHBOARD_APP"]
        data = dashboard.get_ranking_data()
        
        # Calculate stats
        stats = {
            "total_records": len(data),
            "unique_products": len(set(d.get("product_url", "") for d in data)),
            "markets": list(set(d.get("market", "") for d in data if d.get("market"))),
            "date_range": {
                "start": min((d.get("date_kst", "") for d in data), default=""),
                "end": max((d.get("date_kst", "") for d in data), default=""),
            },
        }
        
        # Laneige stats
        laneige_data = [
            d for d in data
            if "laneige" in d.get("brand_raw", "").lower()
        ]
        stats["laneige"] = {
            "total_records": len(laneige_data),
            "unique_products": len(set(d.get("product_url", "") for d in laneige_data)),
        }
        
        return jsonify({
            "success": True,
            "stats": stats,
        })
    
    @app.route("/api/health")
    def api_health():
        """Health check endpoint."""
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
        })
    
    # =========================================================================
    # Error Handlers
    # =========================================================================
    
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found"}), 404
        return render_template("404.html"), 404
    
    @app.errorhandler(500)
    def server_error(e):
        logger.error(f"Server error: {e}")
        if request.path.startswith("/api/"):
            return jsonify({"error": "Internal server error"}), 500
        return render_template("500.html"), 500
    
    return app


def run_dashboard(
    rag_pipeline=None,
    storage=None,
    host: str = "0.0.0.0",
    port: int = 5000,
    debug: bool = True,
):
    """
    Run the dashboard server.
    
    Args:
        rag_pipeline: RAGPipeline instance
        storage: ExcelStorage instance
        host: Host to bind to
        port: Port to bind to
        debug: Enable debug mode
    """
    dashboard_app = DashboardApp(
        rag_pipeline=rag_pipeline,
        storage=storage,
    )
    
    app = create_app(dashboard_app, debug=debug)
    
    print(f"🚀 Dashboard starting at http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)
