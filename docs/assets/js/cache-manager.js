// Cache Manager
// Handles loading and caching of pre-computed data for faster page loads

class CacheManager {
    constructor() {
        this.STORAGE_PREFIX = 'aitrader_cache_';
        this.CACHE_VERSION_KEY = 'cache_version';
        this.CACHE_DATA_KEY = 'cache_data';
        this.CACHE_TIMESTAMP_KEY = 'cache_timestamp';
        this.CACHE_ENABLED_KEY = 'cache_enabled_override';
        this.CACHE_MAX_AGE = 7 * 24 * 60 * 60 * 1000; // 7 days in milliseconds (default, can be overridden by config)
        this.performanceMetrics = {
            lastLoadTime: null,
            cacheHit: null,
            method: null
        };
    }

    /**
     * Check if caching is enabled
     * Priority: URL param > localStorage override > config > default (true)
     */
    isCacheEnabled() {
        // Check URL parameter first (highest priority)
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('nocache')) {
            return urlParams.get('nocache') !== '1';
        }
        if (urlParams.has('cache')) {
            return urlParams.get('cache') === '1';
        }

        // Check localStorage override
        const override = localStorage.getItem(this.CACHE_ENABLED_KEY);
        if (override !== null) {
            return override === 'true';
        }

        // Check config (with safe access)
        try {
            if (window.configLoader && typeof window.configLoader.getCacheConfig === 'function') {
                const config = window.configLoader.getCacheConfig();
                if (config) {
                    return config.enabled !== false;
                }
            }
        } catch (e) {
            console.warn('[CacheManager] Could not access config:', e);
        }

        // Default to enabled
        return true;
    }

    /**
     * Enable caching (saves to localStorage)
     */
    enableCache() {
        localStorage.setItem(this.CACHE_ENABLED_KEY, 'true');
        console.log('[CacheManager] ✅ Caching ENABLED');
    }

    /**
     * Disable caching (saves to localStorage)
     */
    disableCache() {
        localStorage.setItem(this.CACHE_ENABLED_KEY, 'false');
        console.log('[CacheManager] ❌ Caching DISABLED');
    }

    /**
     * Clear cache enabled override
     */
    clearCacheOverride() {
        localStorage.removeItem(this.CACHE_ENABLED_KEY);
        console.log('[CacheManager] 🔄 Cache override cleared, using config setting');
    }

    /**
     * Get cache max age from config
     */
    getCacheMaxAge() {
        try {
            if (window.configLoader && typeof window.configLoader.getCacheConfig === 'function') {
                const config = window.configLoader.getCacheConfig();
                if (config && config.max_age_days) {
                    return config.max_age_days * 24 * 60 * 60 * 1000;
                }
            }
        } catch (e) {
            console.warn('[CacheManager] Could not get max age from config:', e);
        }
        return this.CACHE_MAX_AGE;
    }

    /**
     * Check if performance metrics should be shown
     */
    shouldShowPerformanceMetrics() {
        try {
            if (window.configLoader && typeof window.configLoader.getCacheConfig === 'function') {
                const config = window.configLoader.getCacheConfig();
                return config?.show_performance_metrics !== false;
            }
        } catch (e) {
            console.warn('[CacheManager] Could not get performance metrics setting from config:', e);
        }
        // Default to true
        return true;
    }

    /**
     * Get the full localStorage key for a market
     */
    getStorageKey(market, key) {
        return `${this.STORAGE_PREFIX}${market}_${key}`;
    }

    /**
     * Load pre-computed cache from server (static JSON file)
     */
    async loadServerCache(market) {
        try {
            console.log(`[CacheManager] Loading server cache for ${market} market...`);

            // Add cache-busting to prevent browser HTTP cache from serving stale files
            // This ensures we always check for the latest version from the server
            const timestamp = Date.now();
            const response = await fetch(`./data/${market}_cache.json?v=${timestamp}`, {
                cache: 'no-store',
                headers: {
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                }
            });

            if (!response.ok) {
                console.warn(`[CacheManager] Server cache not found for ${market} (${response.status})`);
                return null;
            }

            const cache = await response.json();
            console.log(`[CacheManager] ✓ Server cache loaded for ${market}:`, {
                version: cache.version,
                generatedAt: cache.generatedAt,
                agents: Object.keys(cache.agentsData).length
            });

            return cache;
        } catch (error) {
            console.warn(`[CacheManager] Failed to load server cache for ${market}:`, error);
            return null;
        }
    }

    /**
     * Load cached data from localStorage
     */
    loadLocalCache(market) {
        try {
            const versionKey = this.getStorageKey(market, this.CACHE_VERSION_KEY);
            const dataKey = this.getStorageKey(market, this.CACHE_DATA_KEY);
            const timestampKey = this.getStorageKey(market, this.CACHE_TIMESTAMP_KEY);

            const version = localStorage.getItem(versionKey);
            const dataStr = localStorage.getItem(dataKey);
            const timestamp = localStorage.getItem(timestampKey);

            if (!version || !dataStr || !timestamp) {
                console.log(`[CacheManager] No local cache found for ${market}`);
                return null;
            }

            // Check if cache is too old (use config value)
            const maxAge = this.getCacheMaxAge();
            const age = Date.now() - parseInt(timestamp);
            if (age > maxAge) {
                console.log(`[CacheManager] Local cache for ${market} is too old (${Math.floor(age / (24 * 60 * 60 * 1000))} days)`);
                this.clearLocalCache(market);
                return null;
            }

            const data = JSON.parse(dataStr);
            console.log(`[CacheManager] ✓ Local cache loaded for ${market}:`, {
                version: version,
                agents: Object.keys(data).length,
                age: `${Math.floor(age / (60 * 60 * 1000))} hours`
            });

            return {
                version: version,
                agentsData: data
            };
        } catch (error) {
            console.warn(`[CacheManager] Failed to load local cache for ${market}:`, error);
            this.clearLocalCache(market);
            return null;
        }
    }

    /**
     * Save cache to localStorage
     */
    saveLocalCache(market, version, agentsData) {
        try {
            const versionKey = this.getStorageKey(market, this.CACHE_VERSION_KEY);
            const dataKey = this.getStorageKey(market, this.CACHE_DATA_KEY);
            const timestampKey = this.getStorageKey(market, this.CACHE_TIMESTAMP_KEY);

            localStorage.setItem(versionKey, version);
            localStorage.setItem(dataKey, JSON.stringify(agentsData));
            localStorage.setItem(timestampKey, Date.now().toString());

            console.log(`[CacheManager] ✓ Local cache saved for ${market} (version: ${version})`);
        } catch (error) {
            console.warn(`[CacheManager] Failed to save local cache for ${market}:`, error);
            // localStorage might be full, try to clear old data
            this.clearLocalCache(market);
        }
    }

    /**
     * Clear local cache for a market
     */
    clearLocalCache(market) {
        try {
            const versionKey = this.getStorageKey(market, this.CACHE_VERSION_KEY);
            const dataKey = this.getStorageKey(market, this.CACHE_DATA_KEY);
            const timestampKey = this.getStorageKey(market, this.CACHE_TIMESTAMP_KEY);

            localStorage.removeItem(versionKey);
            localStorage.removeItem(dataKey);
            localStorage.removeItem(timestampKey);

            console.log(`[CacheManager] Local cache cleared for ${market}`);
        } catch (error) {
            console.warn(`[CacheManager] Failed to clear local cache for ${market}:`, error);
        }
    }

    /**
     * Clear all local caches
     */
    clearAllLocalCaches() {
        try {
            const keys = Object.keys(localStorage);
            const cacheKeys = keys.filter(key => key.startsWith(this.STORAGE_PREFIX));

            cacheKeys.forEach(key => localStorage.removeItem(key));

            console.log(`[CacheManager] Cleared ${cacheKeys.length} cache entries`);
        } catch (error) {
            console.warn(`[CacheManager] Failed to clear all caches:`, error);
        }
    }

    /**
     * Load cache with fallback strategy:
     * 1. Check if caching is enabled
     * 2. Try local cache (localStorage)
     * 3. Try server cache (static JSON file)
     * 4. Return null (caller will do live calculation)
     */
    async loadCache(market) {
        const startTime = performance.now();

        console.log(`[CacheManager] 🔍 Loading cache for market: "${market}"`);

        // Check if caching is enabled
        if (!this.isCacheEnabled()) {
            console.log(`[CacheManager] ⚠️  Caching is DISABLED (config/override/URL param)`);
            console.log(`[CacheManager] 💡 To enable: window.cacheManager.enableCache() or remove ?nocache=1`);
            this.performanceMetrics = {
                lastLoadTime: null,
                cacheHit: false,
                method: 'disabled'
            };
            return null;
        }

        console.log(`[CacheManager] ✓ Caching is ENABLED, loading cache for ${market} market...`);

        // Step 1: Try local cache first (fastest)
        const localCache = this.loadLocalCache(market);

        // Step 2: Load server cache
        const serverCache = await this.loadServerCache(market);

        // If no server cache exists, use local cache if available
        if (!serverCache) {
            if (localCache) {
                const loadTime = performance.now() - startTime;
                this.performanceMetrics = {
                    lastLoadTime: loadTime,
                    cacheHit: true,
                    method: 'localStorage (no server cache)'
                };
                if (this.shouldShowPerformanceMetrics()) {
                    console.log(`[CacheManager] ⚡ Cache load time: ${loadTime.toFixed(2)}ms (localStorage)`);
                }
                console.log(`[CacheManager] Using local cache (no server cache available)`);
                console.log(`[CacheManager] 📊 Loaded ${Object.keys(localCache.agentsData).length} agents`);
                return localCache.agentsData;
            }
            const loadTime = performance.now() - startTime;
            this.performanceMetrics = {
                lastLoadTime: loadTime,
                cacheHit: false,
                method: 'no cache available'
            };
            console.log(`[CacheManager] No cache available, will use live calculation`);
            return null;
        }

        // If local cache exists and versions match, use local cache
        if (localCache && localCache.version === serverCache.version) {
            const loadTime = performance.now() - startTime;
            this.performanceMetrics = {
                lastLoadTime: loadTime,
                cacheHit: true,
                method: 'localStorage'
            };
            if (this.shouldShowPerformanceMetrics()) {
                console.log(`[CacheManager] ⚡ Cache load time: ${loadTime.toFixed(2)}ms (localStorage hit)`);
            }
            console.log(`[CacheManager] ✓ Cache hit! Using local cache (version ${localCache.version})`);
            console.log(`[CacheManager] 📊 Loaded ${Object.keys(localCache.agentsData).length} agents`);
            return localCache.agentsData;
        }

        // Server cache is newer or local cache doesn't exist
        if (localCache) {
            console.log(`[CacheManager] Cache version mismatch (local: ${localCache.version}, server: ${serverCache.version})`);
        }

        // Save server cache to localStorage for next time
        console.log(`[CacheManager] Updating local cache from server...`);
        this.saveLocalCache(market, serverCache.version, serverCache.agentsData);

        const loadTime = performance.now() - startTime;
        this.performanceMetrics = {
            lastLoadTime: loadTime,
            cacheHit: true,
            method: 'server cache'
        };
        if (this.shouldShowPerformanceMetrics()) {
            console.log(`[CacheManager] ⚡ Cache load time: ${loadTime.toFixed(2)}ms (server cache)`);
        }
        console.log(`[CacheManager] 📊 Loaded ${Object.keys(serverCache.agentsData).length} agents from server`);

        return serverCache.agentsData;
    }

    /**
     * Get cache statistics
     */
    getStats() {
        const stats = {
            enabled: this.isCacheEnabled(),
            enabledSource: this.getCacheEnabledSource(),
            performanceMetrics: this.performanceMetrics,
            localCaches: [],
            totalSize: 0
        };

        try {
            const keys = Object.keys(localStorage);
            const cacheKeys = keys.filter(key => key.startsWith(this.STORAGE_PREFIX));

            cacheKeys.forEach(key => {
                const value = localStorage.getItem(key);
                const size = value ? value.length : 0;
                stats.totalSize += size;
            });

            stats.totalSize = `${(stats.totalSize / 1024).toFixed(2)} KB`;

            // Get info for each market
            ['us', 'cn'].forEach(market => {
                const versionKey = this.getStorageKey(market, this.CACHE_VERSION_KEY);
                const timestampKey = this.getStorageKey(market, this.CACHE_TIMESTAMP_KEY);

                const version = localStorage.getItem(versionKey);
                const timestamp = localStorage.getItem(timestampKey);

                if (version && timestamp) {
                    const age = Date.now() - parseInt(timestamp);
                    stats.localCaches.push({
                        market: market,
                        version: version,
                        age: `${Math.floor(age / (60 * 60 * 1000))} hours`,
                        timestamp: new Date(parseInt(timestamp)).toISOString()
                    });
                }
            });
        } catch (error) {
            console.warn('[CacheManager] Failed to get stats:', error);
        }

        return stats;
    }

    /**
     * Get the source of cache enabled setting
     */
    getCacheEnabledSource() {
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('nocache') || urlParams.has('cache')) {
            return 'URL parameter';
        }

        const override = localStorage.getItem(this.CACHE_ENABLED_KEY);
        if (override !== null) {
            return 'localStorage override';
        }

        try {
            if (window.configLoader && typeof window.configLoader.getCacheConfig === 'function') {
                const config = window.configLoader.getCacheConfig();
                if (config) {
                    return 'config.yaml';
                }
            }
        } catch (e) {
            // Ignore
        }

        return 'default';
    }

    /**
     * Get performance metrics from last load
     */
    getPerformanceMetrics() {
        return this.performanceMetrics;
    }
}

// Export for use in other modules
window.CacheManager = CacheManager;
