# Collectors module
from .base_collector import BaseCollector, CollectionResult
from .amazon_collector import AmazonCollector
from .cosme_collector import CosmeCollector

__all__ = [
    "BaseCollector",
    "CollectionResult",
    "AmazonCollector",
    "CosmeCollector",
]
