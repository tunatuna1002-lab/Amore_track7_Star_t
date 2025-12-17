"""
Web Dashboard for Laneige Ranking Collector.

Provides a web interface for:
- Viewing ranking data
- Querying the Graph-RAG system
- Visualizing trends and insights
"""

from .app import create_app, DashboardApp

__all__ = ["create_app", "DashboardApp"]
