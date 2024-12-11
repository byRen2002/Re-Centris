package utils

import (
    "runtime"
    "sync/atomic"
    "time"
    "go.uber.org/zap"
)

// PerformanceMonitor 性能监控器
type PerformanceMonitor struct {
    startTime      time.Time
    processedItems int64
    lastLogTime    time.Time
    interval      time.Duration
}

// NewPerformanceMonitor 创建新的性能监控器
func NewPerformanceMonitor(logInterval time.Duration) *PerformanceMonitor {
    now := time.Now()
    return &PerformanceMonitor{
        startTime:   now,
        lastLogTime: now,
        interval:    logInterval,
    }
}

// Update 更新处理项数并记录性能指标
func (pm *PerformanceMonitor) Update(items int64) {
    atomic.AddInt64(&pm.processedItems, items)
    
    now := time.Now()
    if now.Sub(pm.lastLogTime) >= pm.interval {
        pm.logMetrics()
        pm.lastLogTime = now
    }
}

// logMetrics 记录性能指标
func (pm *PerformanceMonitor) logMetrics() {
    var m runtime.MemStats
    runtime.ReadMemStats(&m)
    
    elapsed := time.Since(pm.startTime).Seconds()
    items := atomic.LoadInt64(&pm.processedItems)
    rate := float64(items) / elapsed
    
    Logger.Info("性能统计",
        zap.Int64("处理项数", items),
        zap.Float64("运行时间(秒)", elapsed),
        zap.Float64("处理速率(项/秒)", rate),
        zap.Uint64("内存使用(MB)", m.Alloc/1024/1024),
        zap.Uint64("总内存分配(MB)", m.TotalAlloc/1024/1024),
        zap.Uint32("Goroutine数量", uint32(runtime.NumGoroutine())),
    )
}

// GetProcessedItems 获取已处理项数
func (pm *PerformanceMonitor) GetProcessedItems() int64 {
    return atomic.LoadInt64(&pm.processedItems)
}

// GetElapsedTime 获取运行时间
func (pm *PerformanceMonitor) GetElapsedTime() time.Duration {
    return time.Since(pm.startTime)
}

// GetProcessingRate 获取处理速率
func (pm *PerformanceMonitor) GetProcessingRate() float64 {
    elapsed := time.Since(pm.startTime).Seconds()
    items := atomic.LoadInt64(&pm.processedItems)
    return float64(items) / elapsed
} 