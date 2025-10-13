import os
import time
import tempfile
import shutil
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.storage.cache import PreviewCache, get_preview_cache, clear_preview_cache, cleanup_preview_cache
from app.main import app


class TestPreviewCache:
    """Test the TTL-based preview cache system."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache = PreviewCache(cache_dir=self.temp_dir, ttl_minutes=1)  # 1 minute TTL for testing

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cache_key_generation(self):
        """Test cache key generation for different mailboxes and dates."""
        # Test with mailbox
        key1 = self.cache._get_cache_key("user@example.com", "2025-01-15")
        key2 = self.cache._get_cache_key("user@example.com", "2025-01-15")
        assert key1 == key2  # Same input should produce same key

        # Test with different mailbox
        key3 = self.cache._get_cache_key("other@example.com", "2025-01-15")
        assert key1 != key3  # Different mailbox should produce different key

        # Test with different date
        key4 = self.cache._get_cache_key("user@example.com", "2025-01-16")
        assert key1 != key4  # Different date should produce different key

        # Test with None mailbox
        key5 = self.cache._get_cache_key(None, "2025-01-15")
        key6 = self.cache._get_cache_key("default", "2025-01-15")
        # Note: None and "default" might produce the same hash, which is acceptable
        # The important thing is that different mailboxes produce different keys

    def test_cache_set_and_get(self):
        """Test basic cache set and get operations."""
        html = "<html><body>Test HTML</body></html>"
        context = {"exec_name": "Test User", "meetings": []}

        # Set cache
        self.cache.set("user@example.com", "2025-01-15", html, context)

        # Get cache
        result = self.cache.get("user@example.com", "2025-01-15")

        assert result is not None
        assert result["html"] == html
        assert result["context"] == context

    def test_cache_miss(self):
        """Test cache miss scenarios."""
        # Non-existent entry
        result = self.cache.get("nonexistent@example.com", "2025-01-15")
        assert result is None

        # Different mailbox
        self.cache.set("user@example.com", "2025-01-15", "html", {})
        result = self.cache.get("other@example.com", "2025-01-15")
        assert result is None

        # Different date
        result = self.cache.get("user@example.com", "2025-01-16")
        assert result is None

    def test_cache_expiration(self):
        """Test cache expiration with TTL."""
        html = "<html><body>Test HTML</body></html>"
        context = {"exec_name": "Test User", "meetings": []}

        # Set cache with very short TTL
        short_cache = PreviewCache(cache_dir=self.temp_dir, ttl_minutes=0.01)  # 0.6 seconds
        short_cache.set("user@example.com", "2025-01-15", html, context)

        # Should be available immediately
        result = short_cache.get("user@example.com", "2025-01-15")
        assert result is not None

        # Wait for expiration
        time.sleep(1)

        # Should be expired now
        result = short_cache.get("user@example.com", "2025-01-15")
        assert result is None

    def test_memory_and_filesystem_cache(self):
        """Test that cache works with both memory and filesystem storage."""
        html = "<html><body>Test HTML</body></html>"
        context = {"exec_name": "Test User", "meetings": []}

        # Set cache
        self.cache.set("user@example.com", "2025-01-15", html, context)

        # Verify memory cache
        cache_key = self.cache._get_cache_key("user@example.com", "2025-01-15")
        assert cache_key in self.cache._memory_cache

        # Verify filesystem cache
        cache_file = Path(self.temp_dir) / f"{cache_key}.json"
        assert cache_file.exists()

        # Create new cache instance to test filesystem loading
        new_cache = PreviewCache(cache_dir=self.temp_dir, ttl_minutes=1)
        result = new_cache.get("user@example.com", "2025-01-15")

        assert result is not None
        assert result["html"] == html
        assert result["context"] == context

    def test_cache_clear(self):
        """Test cache clearing functionality."""
        html = "<html><body>Test HTML</body></html>"
        context = {"exec_name": "Test User", "meetings": []}

        # Set multiple cache entries
        self.cache.set("user1@example.com", "2025-01-15", html, context)
        self.cache.set("user2@example.com", "2025-01-15", html, context)
        self.cache.set("user1@example.com", "2025-01-16", html, context)

        # Clear all
        cleared = self.cache.clear()
        assert cleared >= 3

        # Verify all are cleared
        assert self.cache.get("user1@example.com", "2025-01-15") is None
        assert self.cache.get("user2@example.com", "2025-01-15") is None
        assert self.cache.get("user1@example.com", "2025-01-16") is None

    def test_cache_clear_by_mailbox(self):
        """Test cache clearing by mailbox."""
        html = "<html><body>Test HTML</body></html>"
        context = {"exec_name": "Test User", "meetings": []}

        # Set multiple cache entries
        self.cache.set("user1@example.com", "2025-01-15", html, context)
        self.cache.set("user2@example.com", "2025-01-15", html, context)
        self.cache.set("user1@example.com", "2025-01-16", html, context)

        # Clear by mailbox
        cleared = self.cache.clear(mailbox="user1@example.com")
        assert cleared >= 2

        # Verify user1 entries are cleared
        assert self.cache.get("user1@example.com", "2025-01-15") is None
        assert self.cache.get("user1@example.com", "2025-01-16") is None

        # Verify user2 entry still exists
        assert self.cache.get("user2@example.com", "2025-01-15") is not None

    def test_cache_clear_by_date(self):
        """Test cache clearing by date."""
        html = "<html><body>Test HTML</body></html>"
        context = {"exec_name": "Test User", "meetings": []}

        # Set multiple cache entries
        self.cache.set("user1@example.com", "2025-01-15", html, context)
        self.cache.set("user2@example.com", "2025-01-15", html, context)
        self.cache.set("user1@example.com", "2025-01-16", html, context)

        # Clear by date
        cleared = self.cache.clear(date="2025-01-15")
        assert cleared >= 2

        # Verify 2025-01-15 entries are cleared
        assert self.cache.get("user1@example.com", "2025-01-15") is None
        assert self.cache.get("user2@example.com", "2025-01-15") is None

        # Verify 2025-01-16 entry still exists
        assert self.cache.get("user1@example.com", "2025-01-16") is not None

    def test_cleanup_expired(self):
        """Test cleanup of expired entries."""
        html = "<html><body>Test HTML</body></html>"
        context = {"exec_name": "Test User", "meetings": []}

        # Set cache with very short TTL
        short_cache = PreviewCache(cache_dir=self.temp_dir, ttl_minutes=0.01)  # 0.6 seconds
        short_cache.set("user@example.com", "2025-01-15", html, context)

        # Wait for expiration
        time.sleep(1)

        # Cleanup expired entries
        cleaned = short_cache.cleanup_expired()
        assert cleaned >= 1

        # Verify entry is gone
        assert short_cache.get("user@example.com", "2025-01-15") is None

    def test_cache_stats(self):
        """Test cache statistics."""
        html = "<html><body>Test HTML</body></html>"
        context = {"exec_name": "Test User", "meetings": []}

        # Initially empty
        stats = self.cache.get_stats()
        assert stats["memory_entries"] == 0
        assert stats["filesystem_entries"] == 0
        assert stats["ttl_minutes"] == 1

        # Add some entries
        self.cache.set("user1@example.com", "2025-01-15", html, context)
        self.cache.set("user2@example.com", "2025-01-15", html, context)

        stats = self.cache.get_stats()
        assert stats["memory_entries"] == 2
        assert stats["filesystem_entries"] == 2

    def test_corrupted_cache_file_handling(self):
        """Test handling of corrupted cache files."""
        html = "<html><body>Test HTML</body></html>"
        context = {"exec_name": "Test User", "meetings": []}

        # Set cache
        self.cache.set("user@example.com", "2025-01-15", html, context)

        # Clear memory cache to force filesystem read
        self.cache._memory_cache.clear()

        # Corrupt the cache file
        cache_key = self.cache._get_cache_key("user@example.com", "2025-01-15")
        cache_file = Path(self.temp_dir) / f"{cache_key}.json"
        with open(cache_file, 'w') as f:
            f.write("invalid json content")

        # Should handle corruption gracefully
        result = self.cache.get("user@example.com", "2025-01-15")
        assert result is None

        # Corrupted file should be removed
        assert not cache_file.exists()


class TestGlobalCacheFunctions:
    """Test global cache functions."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_preview_cache(self):
        """Test getting the global cache instance."""
        with patch('app.storage.cache.PreviewCache') as mock_cache_class:
            mock_cache = MagicMock()
            mock_cache_class.return_value = mock_cache

            cache1 = get_preview_cache()
            cache2 = get_preview_cache()

            # Should return the same instance
            assert cache1 is cache2
            mock_cache_class.assert_called_once()

    def test_clear_preview_cache(self):
        """Test clearing the global cache."""
        with patch('app.storage.cache.get_preview_cache') as mock_get_cache:
            mock_cache = MagicMock()
            mock_cache.clear.return_value = 5
            mock_get_cache.return_value = mock_cache

            result = clear_preview_cache("user@example.com", "2025-01-15")

            assert result == 5
            mock_cache.clear.assert_called_once_with("user@example.com", "2025-01-15")

    def test_cleanup_preview_cache(self):
        """Test cleaning up the global cache."""
        with patch('app.storage.cache.get_preview_cache') as mock_get_cache:
            mock_cache = MagicMock()
            mock_cache.cleanup_expired.return_value = 3
            mock_get_cache.return_value = mock_cache

            result = cleanup_preview_cache()

            assert result == 3
            mock_cache.cleanup_expired.assert_called_once()


class TestPreviewCacheEndpoint:
    """Test the preview cache endpoint integration."""

    def setup_method(self):
        """Set up test environment."""
        from app.storage.cache import reset_preview_cache, clear_preview_cache
        reset_preview_cache()
        clear_preview_cache()

    def test_preview_latest_cache_hit(self):
        """Test /preview/latest endpoint with cache hit."""
        client = TestClient(app)

        # Clear any existing cache first
        from app.storage.cache import clear_preview_cache
        clear_preview_cache()

        # First, generate a preview to cache it
        response1 = client.get("/digest/preview.json?source=sample&mailbox=sorum.crofts@rpck.com")
        assert response1.status_code == 200

        # Check that cache was populated
        from app.storage.cache import get_preview_cache
        from datetime import datetime
        cache = get_preview_cache()
        today = datetime.now().strftime("%Y-%m-%d")
        cached_data = cache.get("sorum.crofts@rpck.com", today)
        assert cached_data is not None, "Cache should be populated after first request"

        # Now try to get the latest cached version as JSON
        response2 = client.get("/digest/preview/latest.json?mailbox=sorum.crofts@rpck.com")
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        # Should return the same data
        assert data1["exec_name"] == data2["exec_name"]
        assert data1["source"] == data2["source"]
        assert len(data1["meetings"]) == len(data2["meetings"])

    def test_preview_latest_cache_miss(self):
        """Test /preview/latest endpoint with cache miss."""
        client = TestClient(app)

        # Try to get latest without any cached data
        response = client.get("/digest/preview/latest?mailbox=nonexistent@example.com")
        assert response.status_code == 404
        assert "No cached preview available" in response.json()["detail"]

    def test_preview_latest_html_format(self):
        """Test /preview/latest endpoint with HTML format."""
        client = TestClient(app)

        # First, generate a preview to cache it
        response1 = client.get("/digest/preview?source=sample&mailbox=sorum.crofts@rpck.com")
        assert response1.status_code == 200

        # Now try to get the latest cached version as HTML
        response2 = client.get("/digest/preview/latest?mailbox=sorum.crofts@rpck.com")
        assert response2.status_code == 200
        assert "text/html" in response2.headers["content-type"]

    def test_preview_latest_json_format(self):
        """Test /preview/latest endpoint with JSON format."""
        client = TestClient(app)

        # First, generate a preview to cache it
        response1 = client.get("/digest/preview.json?source=sample&mailbox=sorum.crofts@rpck.com")
        assert response1.status_code == 200

        # Now try to get the latest cached version as JSON
        response2 = client.get("/digest/preview/latest.json?mailbox=sorum.crofts@rpck.com")
        assert response2.status_code == 200
        assert "application/json" in response2.headers["content-type"]

        data = response2.json()
        assert "exec_name" in data
        assert "meetings" in data

    def test_preview_latest_with_accept_header(self):
        """Test /preview/latest endpoint with Accept header."""
        client = TestClient(app)

        # First, generate a preview to cache it
        response1 = client.get("/digest/preview.json?source=sample&mailbox=sorum.crofts@rpck.com")
        assert response1.status_code == 200

        # Now try to get the latest cached version with Accept header
        response2 = client.get(
            "/digest/preview/latest?mailbox=sorum.crofts@rpck.com",
            headers={"Accept": "application/json"}
        )
        assert response2.status_code == 200
        assert "application/json" in response2.headers["content-type"]

    def test_preview_latest_different_mailboxes(self):
        """Test /preview/latest endpoint with different mailboxes."""
        client = TestClient(app)

        # Generate previews for different mailboxes
        response1 = client.get("/digest/preview.json?source=sample&mailbox=sorum.crofts@rpck.com")
        response2 = client.get("/digest/preview.json?source=sample&mailbox=chintan@rpck.com")

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Get latest for each mailbox
        latest1 = client.get("/digest/preview/latest.json?mailbox=sorum.crofts@rpck.com")
        latest2 = client.get("/digest/preview/latest.json?mailbox=chintan@rpck.com")

        assert latest1.status_code == 200
        assert latest2.status_code == 200

        data1 = latest1.json()
        data2 = latest2.json()

        # Should have different exec names
        assert data1["exec_name"] == "Sorum Crofts"
        assert data2["exec_name"] == "Chintan Panchal"

    def test_preview_latest_default_mailbox(self):
        """Test /preview/latest endpoint with default mailbox."""
        client = TestClient(app)

        # Generate preview with default mailbox
        response1 = client.get("/digest/preview.json?source=sample")
        assert response1.status_code == 200

        # Get latest with no mailbox (should use default)
        response2 = client.get("/digest/preview/latest.json")
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        # Should return the same data
        assert data1["exec_name"] == data2["exec_name"]

    def test_preview_caching_behavior(self):
        """Test that preview endpoints cache their results."""
        client = TestClient(app)

        # Clear any existing cache
        clear_preview_cache()

        # First request should generate and cache
        response1 = client.get("/digest/preview.json?source=sample&mailbox=sorum.crofts@rpck.com")
        assert response1.status_code == 200

        # Second request should use cache
        response2 = client.get("/digest/preview/latest.json?mailbox=sorum.crofts@rpck.com")
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        # Should be identical
        assert data1 == data2

    def test_preview_cache_ttl_configuration(self):
        """Test that cache respects TTL configuration."""
        with patch.dict(os.environ, {"PREVIEW_CACHE_TTL_MIN": "0.01"}):  # Very short TTL
            # Reset the global cache to pick up the new TTL
            from app.storage.cache import reset_preview_cache
            reset_preview_cache()
            client = TestClient(app)

            # Generate preview
            response1 = client.get("/digest/preview.json?source=sample&mailbox=sorum.crofts@rpck.com")
            assert response1.status_code == 200

            # Should be available immediately
            response2 = client.get("/digest/preview/latest.json?mailbox=sorum.crofts@rpck.com")
            assert response2.status_code == 200

            # Wait for expiration
            time.sleep(1)

            # Should be expired now
            response3 = client.get("/digest/preview/latest.json?mailbox=sorum.crofts@rpck.com")
            assert response3.status_code == 404
