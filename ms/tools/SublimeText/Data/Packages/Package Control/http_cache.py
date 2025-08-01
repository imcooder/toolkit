import os
import time

from .file_not_found_error import FileNotFoundError
from .open_compat import open_compat, read_compat
from .sys_path import pc_cache_dir


class HttpCache(object):

    """
    A data store for caching HTTP response data.
    """

    def __init__(self, ttl):
        self.base_path = os.path.join(pc_cache_dir(), 'http_cache')
        if not os.path.exists(self.base_path):
            os.mkdir(self.base_path)
        self.clear(int(ttl))

    def clear(self, ttl):
        """
        Removes all cache entries older than the TTL

        :param ttl:
            The number of seconds a cache entry should be valid for
        """

        ttl = int(ttl)

        for filename in os.listdir(self.base_path):
            path = os.path.join(self.base_path, filename)
            # There should not be any folders in the cache dir, but we
            # ignore to prevent an exception
            if os.path.isdir(path):
                continue
            mtime = os.stat(path).st_mtime
            if mtime < time.time() - ttl:
                os.unlink(path)

    def get(self, key):
        """
        Returns a cached value

        :param key:
            The key to fetch the cache for

        :return:
            The (binary) cached value, or False
        """
        try:
            cache_file = os.path.join(self.base_path, key)
            with open_compat(cache_file, 'rb') as f:
                return read_compat(f)
        except FileNotFoundError:
            return False

    def has(self, key):
        cache_file = os.path.join(self.base_path, key)
        return os.path.exists(cache_file)

    def path(self, key):
        """
        Returns the filesystem path to the key

        :param key:
            The key to get the path for

        :return:
            The absolute filesystem path to the cache file
        """

        return os.path.join(self.base_path, key)

    def set(self, key, content):
        """
        Saves a value in the cache

        :param key:
            The key to save the cache with

        :param content:
            The (binary) content to cache
        """

        cache_file = os.path.join(self.base_path, key)
        with open_compat(cache_file, 'wb') as f:
            f.write(content)
