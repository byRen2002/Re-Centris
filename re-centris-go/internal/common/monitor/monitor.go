package monitor

import (
	"runtime"
	"sync"
	"time"

	"github.com/re-centris/re-centris-go/internal/common/logger"
	"go.uber.org/zap"
)

// Stats represents performance statistics
type Stats struct {
	Goroutines  int
	Memory      uint64
	CPU         float64
	StartTime   time.Time
	Operations  uint64
	mutex       sync.RWMutex
}

// Monitor handles performance monitoring
type Monitor struct {
	stats    *Stats
	interval time.Duration
	done     chan struct{}
}

// New creates a new performance monitor
func New(interval time.Duration) *Monitor {
	return &Monitor{
		stats: &Stats{
			StartTime: time.Now(),
		},
		interval: interval,
		done:     make(chan struct{}),
	}
}

// Start starts the monitoring
func (m *Monitor) Start() {
	go m.monitor()
}

// Stop stops the monitoring
func (m *Monitor) Stop() {
	close(m.done)
}

// GetStats returns current statistics
func (m *Monitor) GetStats() Stats {
	m.stats.mutex.RLock()
	defer m.stats.mutex.RUnlock()
	return *m.stats
}

// IncrementOperations increments the operation counter
func (m *Monitor) IncrementOperations() {
	m.stats.mutex.Lock()
	m.stats.Operations++
	m.stats.mutex.Unlock()
}

// monitor periodically collects performance metrics
func (m *Monitor) monitor() {
	ticker := time.NewTicker(m.interval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			m.collectMetrics()
		case <-m.done:
			return
		}
	}
}

// collectMetrics collects current performance metrics
func (m *Monitor) collectMetrics() {
	m.stats.mutex.Lock()
	defer m.stats.mutex.Unlock()

	// Get number of goroutines
	m.stats.Goroutines = runtime.NumGoroutine()

	// Get memory statistics
	var memStats runtime.MemStats
	runtime.ReadMemStats(&memStats)
	m.stats.Memory = memStats.Alloc

	// Log current metrics
	logger.Info("Performance metrics",
		zap.Int("goroutines", m.stats.Goroutines),
		zap.Uint64("memory_bytes", m.stats.Memory),
		zap.Uint64("operations", m.stats.Operations),
		zap.Duration("uptime", time.Since(m.stats.StartTime)),
	)
}

// CheckMemoryLimit checks if memory usage is within limit
func (m *Monitor) CheckMemoryLimit(limit float64) bool {
	var memStats runtime.MemStats
	runtime.ReadMemStats(&memStats)

	totalMemory := float64(memStats.Sys)
	usedMemory := float64(memStats.Alloc)
	memoryUsage := usedMemory / totalMemory

	if memoryUsage > limit {
		logger.Warn("Memory usage exceeds limit",
			zap.Float64("usage", memoryUsage),
			zap.Float64("limit", limit))
		return false
	}

	return true
} 