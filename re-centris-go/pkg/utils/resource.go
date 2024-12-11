package utils

import (
    "os"
    "sync"
    "runtime"
)

// ResourceManager 管理系统资源
type ResourceManager struct {
    maxWorkers int
    files      map[string]*os.File
    mu         sync.RWMutex
}

// NewResourceManager 创建新的资源管理器
func NewResourceManager(maxWorkers int) *ResourceManager {
    if maxWorkers <= 0 {
        maxWorkers = runtime.NumCPU()
    }
    return &ResourceManager{
        maxWorkers: maxWorkers,
        files:      make(map[string]*os.File),
    }
}

// GetFile 获取文件句柄
func (rm *ResourceManager) GetFile(path string, flag int) (*os.File, error) {
    rm.mu.Lock()
    defer rm.mu.Unlock()

    if f, exists := rm.files[path]; exists {
        return f, nil
    }

    f, err := os.OpenFile(path, flag, 0644)
    if err != nil {
        return nil, err
    }

    rm.files[path] = f
    return f, nil
}

// CloseFile 关闭文件句柄
func (rm *ResourceManager) CloseFile(path string) error {
    rm.mu.Lock()
    defer rm.mu.Unlock()

    if f, exists := rm.files[path]; exists {
        delete(rm.files, path)
        return f.Close()
    }
    return nil
}

// CloseAll 关闭所有文件句柄
func (rm *ResourceManager) CloseAll() {
    rm.mu.Lock()
    defer rm.mu.Unlock()

    for _, f := range rm.files {
        f.Close()
    }
    rm.files = make(map[string]*os.File)
}

// GetMaxWorkers 获取最大工作协程数
func (rm *ResourceManager) GetMaxWorkers() int {
    return rm.maxWorkers
}

// GetOpenFiles 获取当前打开的文件数
func (rm *ResourceManager) GetOpenFiles() int {
    rm.mu.RLock()
    defer rm.mu.RUnlock()
    return len(rm.files)
} 