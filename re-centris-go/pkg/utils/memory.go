package utils

import (
    "runtime"
    "runtime/debug"
    "time"
    "go.uber.org/zap"
)

// MemoryOptimizer 内存优化器
type MemoryOptimizer struct {
    targetUsage float64
    interval    time.Duration
    stopChan    chan struct{}
}

// NewMemoryOptimizer 创建新的内存优化器
func NewMemoryOptimizer(targetUsage float64, interval time.Duration) *MemoryOptimizer {
    if targetUsage <= 0 || targetUsage > 1 {
        targetUsage = 0.8 // 默认目标使用率80%
    }
    if interval <= 0 {
        interval = time.Minute // 默认检查间隔1分钟
    }

    return &MemoryOptimizer{
        targetUsage: targetUsage,
        interval:    interval,
        stopChan:    make(chan struct{}),
    }
}

// Start 启动内存监控
func (m *MemoryOptimizer) Start() {
    go m.monitor()
}

// Stop 停止内存监控
func (m *MemoryOptimizer) Stop() {
    close(m.stopChan)
}

// monitor 监控内存使用
func (m *MemoryOptimizer) monitor() {
    ticker := time.NewTicker(m.interval)
    defer ticker.Stop()

    for {
        select {
        case <-ticker.C:
            m.checkAndOptimize()
        case <-m.stopChan:
            return
        }
    }
}

// checkAndOptimize 检查并优化内存使用
func (m *MemoryOptimizer) checkAndOptimize() {
    var stats runtime.MemStats
    runtime.ReadMemStats(&stats)

    // 计算当前内存使用率
    currentUsage := float64(stats.Alloc) / float64(stats.Sys)

    Logger.Debug("内存使用状态",
        zap.Uint64("已分配(MB)", stats.Alloc/1024/1024),
        zap.Uint64("系统内存(MB)", stats.Sys/1024/1024),
        zap.Float64("使用率", currentUsage),
        zap.Uint32("GC次数", stats.NumGC))

    if currentUsage > m.targetUsage {
        m.forceGC()
    }
}

// forceGC 强制执行垃圾回收
func (m *MemoryOptimizer) forceGC() {
    Logger.Info("执行强制垃圾回收")
    
    // 记录GC前的内存状态
    var statsBefore runtime.MemStats
    runtime.ReadMemStats(&statsBefore)

    // 执行GC
    debug.FreeOSMemory()

    // 记录GC后的内存状态
    var statsAfter runtime.MemStats
    runtime.ReadMemStats(&statsAfter)

    // 计算释放的内存
    freedMem := float64(statsBefore.Alloc-statsAfter.Alloc) / 1024 / 1024

    Logger.Info("垃圾回收完成",
        zap.Float64("释放内存(MB)", freedMem))
}

// GetMemoryStats 获取内存统计信息
func (m *MemoryOptimizer) GetMemoryStats() map[string]interface{} {
    var stats runtime.MemStats
    runtime.ReadMemStats(&stats)

    return map[string]interface{}{
        "alloc_mb":        stats.Alloc / 1024 / 1024,
        "total_alloc_mb":  stats.TotalAlloc / 1024 / 1024,
        "sys_mb":          stats.Sys / 1024 / 1024,
        "gc_count":        stats.NumGC,
        "goroutines":      runtime.NumGoroutine(),
        "heap_objects":    stats.HeapObjects,
        "heap_alloc_mb":   stats.HeapAlloc / 1024 / 1024,
        "heap_sys_mb":     stats.HeapSys / 1024 / 1024,
        "heap_idle_mb":    stats.HeapIdle / 1024 / 1024,
        "heap_inuse_mb":   stats.HeapInuse / 1024 / 1024,
        "stack_inuse_mb":  stats.StackInuse / 1024 / 1024,
        "stack_sys_mb":    stats.StackSys / 1024 / 1024,
        "mspan_inuse_mb":  stats.MSpanInuse / 1024 / 1024,
        "mspan_sys_mb":    stats.MSpanSys / 1024 / 1024,
        "mcache_inuse_mb": stats.MCacheInuse / 1024 / 1024,
        "mcache_sys_mb":   stats.MCacheSys / 1024 / 1024,
    }
}

// SetMemoryLimit 设置内存限制
func (m *MemoryOptimizer) SetMemoryLimit(limitMB int) {
    if limitMB > 0 {
        debug.SetMemoryLimit(int64(limitMB) * 1024 * 1024)
    }
}

// GetMemoryUsage 获取当前内存使用率
func (m *MemoryOptimizer) GetMemoryUsage() float64 {
    var stats runtime.MemStats
    runtime.ReadMemStats(&stats)
    return float64(stats.Alloc) / float64(stats.Sys)
} 