import os
import time
import json
import hashlib
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
from datetime import datetime, timezone

from app.core.config import load_config


class PreviewCache:
    """TTL-based cache for storing latest HTML renders and JSON context."""

    def __init__(self, cache_dir: Optional[str] = None, ttl_minutes: Optional[int] = None):
        """
        Initialize the preview cache.

        Args:
            cache_dir: Directory to store cache files. If None, uses temp directory.
            ttl_minutes: TTL in minutes. If None, uses PREVIEW_CACHE_TTL_MIN env var or 10.
        """
        self.cache_dir = Path(cache_dir) if cache_dir else Path("/tmp/gary-preview-cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        if ttl_minutes is None:
            ttl_minutes = float(os.getenv("PREVIEW_CACHE_TTL_MIN", "10"))
        self.ttl_seconds = ttl_minutes * 60

        # In-memory cache for faster access
        self._memory_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}

    def _get_cache_key(self, mailbox: Optional[str], date: str) -> str:
        """
        Generate a cache key for the given mailbox and date.

        Args:
            mailbox: Mailbox address (None for default)
            date: Date string (YYYY-MM-DD)

        Returns:
            Cache key string
        """
        key_data = f"{mailbox or 'default'}:{date}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def _is_expired(self, timestamp: float) -> bool:
        """Check if a cache entry is expired."""
        return time.time() - timestamp > self.ttl_seconds

    def get(self, mailbox: Optional[str], date: str) -> Optional[Dict[str, Any]]:
        """
        Get cached preview data for the given mailbox and date.

        Args:
            mailbox: Mailbox address (None for default)
            date: Date string (YYYY-MM-DD)

        Returns:
            Cached data dict with 'html' and 'context' keys, or None if not found/expired
        """
        cache_key = self._get_cache_key(mailbox, date)

        # Check memory cache first
        if cache_key in self._memory_cache:
            data, timestamp = self._memory_cache[cache_key]
            if not self._is_expired(timestamp):
                return data
            else:
                # Remove expired entry
                del self._memory_cache[cache_key]

        # Check filesystem cache
        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)

                # Check if expired
                if self._is_expired(cache_data.get('timestamp', 0)):
                    cache_file.unlink()  # Remove expired file
                    return None

                # Load into memory cache
                data = {
                    'html': cache_data['html'],
                    'context': cache_data['context']
                }
                self._memory_cache[cache_key] = (data, cache_data['timestamp'])
                return data

            except (json.JSONDecodeError, KeyError, IOError):
                # Remove corrupted file
                cache_file.unlink()
                return None

        return None

    def set(self, mailbox: Optional[str], date: str, html: str, context: Dict[str, Any]) -> None:
        """
        Cache preview data for the given mailbox and date.

        Args:
            mailbox: Mailbox address (None for default)
            date: Date string (YYYY-MM-DD)
            html: Rendered HTML content
            context: JSON context data
        """
        cache_key = self._get_cache_key(mailbox, date)
        timestamp = time.time()

        data = {
            'html': html,
            'context': context,
            'timestamp': timestamp,
            'mailbox': mailbox,
            'date': date
        }

        # Store in memory cache
        self._memory_cache[cache_key] = (data, timestamp)

        # Store in filesystem cache
        cache_file = self.cache_dir / f"{cache_key}.json"
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError:
            # If filesystem write fails, at least we have it in memory
            pass

    def clear(self, mailbox: Optional[str] = None, date: Optional[str] = None) -> int:
        """
        Clear cache entries.

        Args:
            mailbox: If provided, only clear entries for this mailbox
            date: If provided, only clear entries for this date

        Returns:
            Number of entries cleared
        """
        cleared = 0

        # Clear memory cache
        keys_to_remove = []
        for cache_key, (data, timestamp) in self._memory_cache.items():
            if mailbox and data.get('mailbox') != mailbox:
                continue
            if date and data.get('date') != date:
                continue
            keys_to_remove.append(cache_key)

        for key in keys_to_remove:
            del self._memory_cache[key]
            cleared += 1

        # Clear filesystem cache
        if self.cache_dir.exists():
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)

                    if mailbox and cache_data.get('mailbox') != mailbox:
                        continue
                    if date and cache_data.get('date') != date:
                        continue

                    cache_file.unlink()
                    cleared += 1

                except (json.JSONDecodeError, KeyError, IOError):
                    # Remove corrupted file
                    cache_file.unlink()
                    cleared += 1

        return cleared

    def cleanup_expired(self) -> int:
        """
        Clean up expired cache entries.

        Returns:
            Number of entries cleaned up
        """
        cleaned = 0

        # Clean memory cache
        keys_to_remove = []
        for cache_key, (data, timestamp) in self._memory_cache.items():
            if self._is_expired(timestamp):
                keys_to_remove.append(cache_key)

        for key in keys_to_remove:
            del self._memory_cache[key]
            cleaned += 1

        # Clean filesystem cache
        if self.cache_dir.exists():
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)

                    if self._is_expired(cache_data.get('timestamp', 0)):
                        cache_file.unlink()
                        cleaned += 1

                except (json.JSONDecodeError, KeyError, IOError):
                    # Remove corrupted file
                    cache_file.unlink()
                    cleaned += 1

        return cleaned

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        memory_count = len(self._memory_cache)
        filesystem_count = 0

        if self.cache_dir.exists():
            filesystem_count = len(list(self.cache_dir.glob("*.json")))

        return {
            'memory_entries': memory_count,
            'filesystem_entries': filesystem_count,
            'ttl_minutes': self.ttl_seconds / 60,
            'cache_dir': str(self.cache_dir)
        }


# Global cache instance
_preview_cache: Optional[PreviewCache] = None


def get_preview_cache() -> PreviewCache:
    """Get the global preview cache instance."""
    global _preview_cache
    if _preview_cache is None:
        _preview_cache = PreviewCache()
    return _preview_cache


def reset_preview_cache() -> None:
    """Reset the global preview cache instance."""
    global _preview_cache
    _preview_cache = None


def clear_preview_cache(mailbox: Optional[str] = None, date: Optional[str] = None) -> int:
    """Clear the global preview cache."""
    return get_preview_cache().clear(mailbox, date)


def cleanup_preview_cache() -> int:
    """Clean up expired entries in the global preview cache."""
    return get_preview_cache().cleanup_expired()
