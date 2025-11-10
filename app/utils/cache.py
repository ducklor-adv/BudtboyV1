import time
import threading


class CacheManager:
    """Simple in-memory cache with TTL support"""

    def __init__(self):
        self.cache = {}
        self.cache_lock = threading.Lock()

    def get(self, key, ttl=900):
        """Get cached data if not expired"""
        with self.cache_lock:
            if key in self.cache:
                data, timestamp, cache_ttl = self.cache[key]
                if time.time() - timestamp < cache_ttl:
                    return data
                del self.cache[key]
        return None

    def set(self, key, data, ttl=900):
        """Set cache with automatic cleanup"""
        with self.cache_lock:
            self.cache[key] = (data, time.time(), ttl)
            # Periodic cleanup
            if len(self.cache) > 1000:
                self._cleanup()

    def clear_pattern(self, pattern):
        """Clear cache keys matching a pattern"""
        with self.cache_lock:
            keys_to_delete = [key for key in self.cache.keys() if pattern in key]
            for key in keys_to_delete:
                del self.cache[key]

    def clear_all(self):
        """Clear all cache"""
        with self.cache_lock:
            self.cache.clear()

    def _cleanup(self):
        """Clean up expired cache entries"""
        current_time = time.time()
        expired_keys = [
            k for k, (_, ts, cache_ttl) in self.cache.items()
            if current_time - ts > cache_ttl
        ]
        for k in expired_keys[:100]:
            del self.cache[k]
