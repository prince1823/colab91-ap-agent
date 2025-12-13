"""LRU Cache implementation for supplier profiles."""

import threading
from collections import OrderedDict
from typing import Dict, Optional, TypeVar

T = TypeVar('T')


class LRUCache:
    """Simple LRU cache implementation with size limit and thread safety."""

    def __init__(self, max_size: int = 1000):
        """
        Initialize LRU cache.

        Args:
            max_size: Maximum number of items to cache
        """
        self.cache: OrderedDict[str, T] = OrderedDict()
        self.max_size = max_size
        self._lock = threading.Lock()  # Thread safety for concurrent access

    def get(self, key: str) -> Optional[T]:
        """
        Get item from cache (thread-safe).

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        with self._lock:
            if key in self.cache:
                # Move to end (most recently used)
                self.cache.move_to_end(key)
                return self.cache[key]
        return None

    def set(self, key: str, value: T) -> None:
        """
        Set item in cache (thread-safe).

        Args:
            key: Cache key
            value: Value to cache
        """
        with self._lock:
            if key in self.cache:
                # Update existing item and move to end
                self.cache.move_to_end(key)
            self.cache[key] = value

            # Evict oldest item if cache is full
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)

    def clear(self) -> None:
        """Clear all items from cache (thread-safe)."""
        with self._lock:
            self.cache.clear()

    def __len__(self) -> int:
        """Return number of items in cache (thread-safe)."""
        with self._lock:
            return len(self.cache)

    def __contains__(self, key: str) -> bool:
        """Check if key is in cache (thread-safe)."""
        with self._lock:
            return key in self.cache

