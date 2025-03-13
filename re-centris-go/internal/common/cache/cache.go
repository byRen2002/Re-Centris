package cache

import (
	"container/list"
	"sync"
)

// Cache is a thread-safe LRU cache
type Cache struct {
	capacity int
	items    map[string]*list.Element
	queue    *list.List
	mutex    sync.RWMutex
}

// item represents a cache item
type item struct {
	key   string
	value interface{}
}

// New creates a new cache with the given capacity
func New(capacity int) *Cache {
	return &Cache{
		capacity: capacity,
		items:    make(map[string]*list.Element),
		queue:    list.New(),
	}
}

// Get retrieves a value from the cache
func (c *Cache) Get(key string) (interface{}, bool) {
	c.mutex.RLock()
	if element, exists := c.items[key]; exists {
		c.mutex.RUnlock()
		c.mutex.Lock()
		c.queue.MoveToFront(element)
		c.mutex.Unlock()
		return element.Value.(*item).value, true
	}
	c.mutex.RUnlock()
	return nil, false
}

// Set adds or updates a value in the cache
func (c *Cache) Set(key string, value interface{}) {
	c.mutex.Lock()
	defer c.mutex.Unlock()

	// If key exists, update its value and move to front
	if element, exists := c.items[key]; exists {
		c.queue.MoveToFront(element)
		element.Value.(*item).value = value
		return
	}

	// Add new item
	element := c.queue.PushFront(&item{key: key, value: value})
	c.items[key] = element

	// Remove oldest item if cache is full
	if c.queue.Len() > c.capacity {
		oldest := c.queue.Back()
		if oldest != nil {
			c.queue.Remove(oldest)
			delete(c.items, oldest.Value.(*item).key)
		}
	}
}

// Delete removes a value from the cache
func (c *Cache) Delete(key string) {
	c.mutex.Lock()
	defer c.mutex.Unlock()

	if element, exists := c.items[key]; exists {
		c.queue.Remove(element)
		delete(c.items, key)
	}
}

// Clear removes all items from the cache
func (c *Cache) Clear() {
	c.mutex.Lock()
	defer c.mutex.Unlock()

	c.items = make(map[string]*list.Element)
	c.queue = list.New()
}

// Len returns the number of items in the cache
func (c *Cache) Len() int {
	c.mutex.RLock()
	defer c.mutex.RUnlock()
	return len(c.items)
}

// Keys returns all keys in the cache
func (c *Cache) Keys() []string {
	c.mutex.RLock()
	defer c.mutex.RUnlock()

	keys := make([]string, 0, len(c.items))
	for key := range c.items {
		keys = append(keys, key)
	}
	return keys
} 