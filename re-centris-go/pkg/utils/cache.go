package utils

import (
    "container/list"
    "sync"
    "sync/atomic"
)

// Cache 是一个线程安全的LRU缓存实现
type Cache struct {
    capacity    int
    items       map[string]*list.Element
    queue       *list.List
    mu          sync.RWMutex
    hits        uint64
    misses      uint64
    evictions   uint64
}

type entry struct {
    key   string
    value interface{}
}

// NewCache 创建一个新的缓存实例
func NewCache(capacity int) *Cache {
    return &Cache{
        capacity: capacity,
        items:    make(map[string]*list.Element),
        queue:    list.New(),
    }
}

// Get 获取缓存值
func (c *Cache) Get(key string) (interface{}, bool) {
    c.mu.Lock()
    defer c.mu.Unlock()

    if elem, ok := c.items[key]; ok {
        c.queue.MoveToFront(elem)
        atomic.AddUint64(&c.hits, 1)
        return elem.Value.(*entry).value, true
    }
    atomic.AddUint64(&c.misses, 1)
    return nil, false
}

// Put 存入缓存值
func (c *Cache) Put(key string, value interface{}) {
    c.mu.Lock()
    defer c.mu.Unlock()

    if elem, ok := c.items[key]; ok {
        c.queue.MoveToFront(elem)
        elem.Value.(*entry).value = value
        return
    }

    if c.queue.Len() >= c.capacity {
        oldest := c.queue.Back()
        if oldest != nil {
            delete(c.items, oldest.Value.(*entry).key)
            c.queue.Remove(oldest)
            atomic.AddUint64(&c.evictions, 1)
        }
    }

    elem := c.queue.PushFront(&entry{key, value})
    c.items[key] = elem
}

// Clear 清空缓存
func (c *Cache) Clear() {
    c.mu.Lock()
    defer c.mu.Unlock()

    c.items = make(map[string]*list.Element)
    c.queue = list.New()
    atomic.StoreUint64(&c.hits, 0)
    atomic.StoreUint64(&c.misses, 0)
    atomic.StoreUint64(&c.evictions, 0)
}

// Len 返回当前缓存项数量
func (c *Cache) Len() int {
    c.mu.RLock()
    defer c.mu.RUnlock()
    return len(c.items)
}

// GetHitRate 获取缓存命中率
func (c *Cache) GetHitRate() float64 {
    hits := atomic.LoadUint64(&c.hits)
    misses := atomic.LoadUint64(&c.misses)
    total := hits + misses
    if total == 0 {
        return 0
    }
    return float64(hits) / float64(total)
}

// GetStats 获取缓存统计信息
func (c *Cache) GetStats() map[string]interface{} {
    hits := atomic.LoadUint64(&c.hits)
    misses := atomic.LoadUint64(&c.misses)
    evictions := atomic.LoadUint64(&c.evictions)
    total := hits + misses

    return map[string]interface{}{
        "capacity":    c.capacity,
        "size":        c.Len(),
        "hits":        hits,
        "misses":      misses,
        "evictions":   evictions,
        "hit_rate":    float64(hits) / float64(total),
        "miss_rate":   float64(misses) / float64(total),
        "total_ops":   total,
    }
} 