"""
Configuration loader utilities.
"""

import os
from pathlib import Path
from typing import Any, Dict

import yaml


def get_project_root() -> Path:
    """Get the project root directory."""
    # Start from this file's directory and go up
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "config.yaml").exists():
            return parent
    # Fallback to current working directory
    return Path.cwd()


def load_config(config_path: str = None) -> Dict[str, Any]:
    """
    Load the main configuration from config.yaml.

    Args:
        config_path: Optional path to config file. If None, looks in project root.

    Returns:
        Configuration dictionary
    """
    if config_path is None:
        config_path = get_project_root() / "config.yaml"

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # Ensure data directory exists
    output_file = config.get('storage', {}).get('output_file', 'data/ranking_data.xlsx')
    output_dir = Path(output_file).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Ensure logs directory exists
    log_file = config.get('logging', {}).get('file', 'logs/collector.log')
    log_dir = Path(log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    return config


def load_selectors(selectors_path: str = None) -> Dict[str, Any]:
    """
    Load selectors configuration from selectors.yaml.

    Args:
        selectors_path: Optional path to selectors file. If None, looks in project root.

    Returns:
        Selectors dictionary
    """
    if selectors_path is None:
        selectors_path = get_project_root() / "selectors.yaml"

    with open(selectors_path, 'r', encoding='utf-8') as f:
        selectors = yaml.safe_load(f)

    return selectors


def get_category_by_key(config: Dict[str, Any], category_key: str) -> Dict[str, Any]:
    """
    Get a category configuration by its key.

    Args:
        config: Configuration dictionary
        category_key: The category key to find

    Returns:
        Category configuration or None
    """
    for category in config.get('categories', []):
        if category.get('category_key') == category_key:
            return category
    return None


def get_categories_by_market(config: Dict[str, Any], market: str) -> list:
    """
    Get all categories for a specific market.

    Args:
        config: Configuration dictionary
        market: Market identifier (amazon_us, cosme_jp)

    Returns:
        List of category configurations
    """
    return [
        cat for cat in config.get('categories', [])
        if cat.get('market') == market
    ]
