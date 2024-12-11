package collector

import (
    "crypto/sha256"
    "encoding/hex"
    "encoding/json"
    "fmt"
    "io"
    "os"
    "path/filepath"
    "sync"
    "time"

    "github.com/your/centris/pkg/utils"
    "go.uber.org/zap"
)

// Collector 代码收集器
type Collector struct {
    baseDir      string
    concurrency  int
    cache        *utils.Cache
    monitor      *utils.PerformanceMonitor
    memOptimizer *utils.MemoryOptimizer
    rm           *utils.ResourceManager
    parser       *Parser
}

// FileInfo 文件信息
type FileInfo struct {
    Path     string    // 文件路径
    Size     int64     // 文件大小
    SHA256   string    // SHA256哈希值
    TLSH     string    // TLSH哈希值，用于相似度比较
    Type     string    // 文件类型
    ModTime  time.Time // 修改时间
}

// FunctionInfo 函数信息
type FunctionInfo struct {
    Name     string // 函数名
    Start    int    // 起始行
    End      int    // 结束行
    Content  string // 函数内容
    TLSH     string // TLSH哈希值
    FilePath string // 所在文件路径
}

// SimilarPair 相似函数对
type SimilarPair struct {
    Function1 FunctionInfo // 第一个函数
    Function2 FunctionInfo // 第二个函数
    Distance  int         // TLSH距离
}

// FunctionIndex 函数索引
type FunctionIndex struct {
    Functions    []FunctionInfo // 函数列表
    SimilarPairs []SimilarPair // 相似函数对
    Stats        FunctionStats // 统计信息
}

// FunctionStats 函数统计信息
type FunctionStats struct {
    TotalFunctions int            // 总函数数量
    FileStats      map[string]int // 每个文件的函数数量
    SizeStats      map[string]int // 不同大小范围的函数数量
}

// Metadata 元数据
type Metadata struct {
    Name         string     `json:"name"`
    Path         string     `json:"path"`
    Files        []FileInfo `json:"files"`
    TotalSize    int64     `json:"total_size"`
    FileCount    int       `json:"file_count"`
    CollectTime  time.Time `json:"collect_time"`
    GitInfo      GitInfo   `json:"git_info"`
}

// GitInfo Git仓库信息
type GitInfo struct {
    RemoteURL    string    `json:"remote_url"`
    Branch       string    `json:"branch"`
    LastCommit   string    `json:"last_commit"`
    LastModified time.Time `json:"last_modified"`
    Tags         []string  `json:"tags"`
}

// Collector 收集器
type Collector struct {
    baseDir     string
    concurrency int
    cache       *utils.Cache
    monitor     *utils.PerformanceMonitor
    memOptimizer *utils.MemoryOptimizer
    rm          *utils.ResourceManager
}

// NewCollector 创建新的收集器
func NewCollector(baseDir string, concurrency int) *Collector {
    c := &Collector{
        baseDir:      baseDir,
        concurrency:  concurrency,
        cache:        utils.NewCache(1000), // 缓存1000个项目
        monitor:      utils.NewPerformanceMonitor(time.Minute),
        memOptimizer: utils.NewMemoryOptimizer(0.8, time.Minute),
        rm:           utils.NewResourceManager(concurrency),
        parser:       NewParser(),
    }

    // 启动内存优化器
    c.memOptimizer.Start()
    return c
}

// Close 关闭收集器
func (c *Collector) Close() {
    c.rm.CloseAll()
    c.cache.Clear()
    c.memOptimizer.Stop()
}

// CollectMetadata 收集元数据
func (c *Collector) CollectMetadata(path string) (*Metadata, error) {
    utils.Logger.Info("开始收集元数据",
        zap.String("path", path))

    metadata := &Metadata{
        Name:        filepath.Base(path),
        Path:        path,
        CollectTime: time.Now(),
    }

    // 获取Git信息
    gitInfo, err := c.collectGitInfo(path)
    if err != nil {
        utils.Logger.Warn("获取Git信息失败",
            zap.String("path", path),
            zap.Error(err))
    } else {
        metadata.GitInfo = gitInfo
    }

    // 获取版本信息
    versions, err := c.collectVersionInfo(path)
    if err != nil {
        utils.Logger.Warn("获取版本信息失败",
            zap.String("path", path),
            zap.Error(err))
    } else {
        // 生成并保存版本索引
        index := c.generateVersionIndex(versions)
        if err := c.saveVersionIndex(index, path); err != nil {
            utils.Logger.Error("保存版本索引失败",
                zap.Error(err))
        }
    }

    // 并发处理文件
    filesChan := make(chan string)
    resultsChan := make(chan FileInfo)
    functionsChan := make(chan []FunctionInfo)
    errorsChan := make(chan error, c.concurrency)
    var wg sync.WaitGroup

    // 启动工作协程
    for i := 0; i < c.concurrency; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            for file := range filesChan {
                // 处理文件元数据
                info, err := c.processFile(file)
                if err != nil {
                    errorsChan <- fmt.Errorf("处理文件 %s 失败: %w", file, err)
                    continue
                }
                resultsChan <- info

                // 如果是目标文件类型，提取函数信息
                if c.isTargetFile(file) {
                    functions, err := c.extractFunctions(file)
                    if err != nil {
                        utils.Logger.Error("提取函数信息失败",
                            zap.String("file", file),
                            zap.Error(err))
                    } else {
                        functionsChan <- functions
                    }
                }

                c.monitor.Update(1)
            }
        }()
    }

    // 遍历目录
    go func() {
        filepath.Walk(path, func(path string, info os.FileInfo, err error) error {
            if err != nil {
                return err
            }
            if !info.IsDir() {
                filesChan <- path
            }
            return nil
        })
        close(filesChan)
    }()

    // 收集结果
    go func() {
        wg.Wait()
        close(resultsChan)
        close(functionsChan)
        close(errorsChan)
    }()

    // 处理文件结果
    var allFunctions []FunctionInfo
    for {
        select {
        case info, ok := <-resultsChan:
            if !ok {
                resultsChan = nil
                continue
            }
            metadata.Files = append(metadata.Files, info)
            metadata.TotalSize += info.Size
            metadata.FileCount++

        case functions, ok := <-functionsChan:
            if !ok {
                functionsChan = nil
                continue
            }
            allFunctions = append(allFunctions, functions...)

        case err := <-errorsChan:
            utils.Logger.Error("处理过程中发生错误", zap.Error(err))
        }

        if resultsChan == nil && functionsChan == nil {
            break
        }
    }

    // 生成并保存函数索引
    if len(allFunctions) > 0 {
        index := c.generateFunctionIndex(allFunctions)
        if err := c.saveFunctionIndex(index, path); err != nil {
            utils.Logger.Error("保存函数索引失败",
                zap.Error(err))
        }
    }

    // 保存元数据
    if err := c.saveMetadata(metadata); err != nil {
        utils.Logger.Error("保存元数据失败",
            zap.Error(err))
    }

    // 记录性能统计
    stats := map[string]interface{}{
        "file_stats":   c.monitor.GetStats(),
        "memory_stats": c.memOptimizer.GetMemoryStats(),
        "cache_stats": map[string]interface{}{
            "items":    c.cache.Len(),
            "hit_rate": c.cache.GetHitRate(),
        },
    }

    utils.Logger.Info("元数据收���完成",
        zap.Int("file_count", metadata.FileCount),
        zap.Int64("total_size", metadata.TotalSize),
        zap.Int("function_count", len(allFunctions)),
        zap.Any("stats", stats))

    return metadata, nil
}

// processFile 处理单个文件
// 提取文件信息并计算哈希值
func (c *Collector) processFile(filePath string) (FileInfo, error) {
    info := FileInfo{
        Path: filePath,
    }

    // 读取文件内容
    content, err := os.ReadFile(filePath)
    if err != nil {
        return info, err
    }

    // 计算文件大小
    info.Size = int64(len(content))

    // 计算SHA256哈希
    sha256Hash := sha256.Sum256(content)
    info.SHA256 = hex.EncodeToString(sha256Hash[:])

    // 计算TLSH哈希
    info.TLSH = utils.Hash(content)

    // 获取文件类型
    info.Type = filepath.Ext(filePath)

    // 获取修改时间
    if stat, err := os.Stat(filePath); err == nil {
        info.ModTime = stat.ModTime()
    }

    return info, nil
}

// isTargetFile 判断是否为目标文件
func (c *Collector) isTargetFile(path string) bool {
    ext := strings.ToLower(filepath.Ext(path))
    switch ext {
    case ".c", ".h", ".cpp", ".hpp", ".cc", ".cxx":
        return true
    default:
        return false
    }
}

// detectLanguage 检��文件语言
func (c *Collector) detectLanguage(path string) string {
    ext := strings.ToLower(filepath.Ext(path))
    switch ext {
    case ".c", ".h":
        return "C"
    case ".cpp", ".hpp", ".cc", ".cxx":
        return "C++"
    default:
        return "Unknown"
    }
}

// collectGitInfo 收集Git信息
func (c *Collector) collectGitInfo(path string) (GitInfo, error) {
    gitInfo := GitInfo{}

    // 获取远程URL
    remoteURL, err := utils.RunGitCommand(path, "remote", "get-url", "origin")
    if err == nil {
        gitInfo.RemoteURL = strings.TrimSpace(remoteURL)
    }

    // 获取当前分支
    branch, err := utils.RunGitCommand(path, "rev-parse", "--abbrev-ref", "HEAD")
    if err == nil {
        gitInfo.Branch = strings.TrimSpace(branch)
    }

    // 获取最后提交
    lastCommit, err := utils.RunGitCommand(path, "rev-parse", "HEAD")
    if err == nil {
        gitInfo.LastCommit = strings.TrimSpace(lastCommit)
    }

    // 获取最后修改时间
    lastModified, err := utils.RunGitCommand(path, "log", "-1", "--format=%ct")
    if err == nil {
        timestamp, err := strconv.ParseInt(strings.TrimSpace(lastModified), 10, 64)
        if err == nil {
            gitInfo.LastModified = time.Unix(timestamp, 0)
        }
    }

    // 获取���签
    tags, err := utils.RunGitCommand(path, "tag", "--sort=-creatordate")
    if err == nil {
        gitInfo.Tags = strings.Split(strings.TrimSpace(tags), "\n")
    }

    return gitInfo, nil
}

// saveMetadata 保存元数据
func (c *Collector) saveMetadata(metadata *Metadata) error {
    // 创建输出目录
    outDir := filepath.Join(c.baseDir, "metadata")
    if err := os.MkdirAll(outDir, 0755); err != nil {
        return err
    }

    // 生成输出文件名
    outFile := filepath.Join(outDir, fmt.Sprintf("%s_%s.json",
        metadata.Name,
        metadata.CollectTime.Format("20060102_150405")))

    // 序列化元数据
    data, err := json.MarshalIndent(metadata, "", "  ")
    if err != nil {
        return err
    }

    // 写入文件
    return os.WriteFile(outFile, data, 0644)
}

// GetStats 获取收集器统计信息
func (c *Collector) GetStats() map[string]interface{} {
    return map[string]interface{}{
        "processed_files":    c.monitor.GetProcessedItems(),
        "elapsed_time":       c.monitor.GetElapsedTime().Seconds(),
        "processing_rate":    c.monitor.GetProcessingRate(),
        "cache_items":        c.cache.Len(),
        "open_files":         c.rm.GetOpenFiles(),
        "goroutine_count":    runtime.NumGoroutine(),
    }
}

// Close 关闭收集器
func (c *Collector) Close() {
    c.rm.CloseAll()
    c.cache.Clear()
    c.memOptimizer.Stop()
}

// extractFunctions 提取函数信息
// 解析源代码并提取函数级别的信息
func (c *Collector) extractFunctions(filePath string) ([]FunctionInfo, error) {
    // 读取文件内容
    content, err := os.ReadFile(filePath)
    if err != nil {
        return nil, err
    }

    // 解析函数
    functions, err := c.parser.ParseFunctions(content)
    if err != nil {
        return nil, err
    }

    var result []FunctionInfo
    for _, f := range functions {
        // 计算函数内容的TLSH哈希
        tlshHash := utils.Hash([]byte(f.Content))
        
        info := FunctionInfo{
            Name:     f.Name,
            Start:    f.Start,
            End:      f.End,
            Content:  f.Content,
            TLSH:     tlshHash,
            FilePath: filePath,
        }
        result = append(result, info)
    }

    return result, nil
}

// generateFunctionIndex 生成函数索引
// 创建函数索引并计算相似度
func (c *Collector) generateFunctionIndex(functions []FunctionInfo) *FunctionIndex {
    index := &FunctionIndex{
        Functions: functions,
        Stats: FunctionStats{
            TotalFunctions: len(functions),
            FileStats:      make(map[string]int),
            SizeStats:      make(map[string]int),
        },
    }

    // 计算统计信息
    for _, f := range functions {
        // 文件统计
        index.Stats.FileStats[f.FilePath]++

        // 大小统计
        size := len(f.Content)
        var sizeRange string
        switch {
        case size < 100:
            sizeRange = "small"
        case size < 500:
            sizeRange = "medium"
        default:
            sizeRange = "large"
        }
        index.Stats.SizeStats[sizeRange]++

        // 计算相似度矩阵
        for _, other := range functions {
            if f.TLSH != "" && other.TLSH != "" && f != other {
                // 创建TLSH实例
                tlsh1 := utils.NewTLSH()
                tlsh2 := utils.NewTLSH()

                // 更新哈希数据
                tlsh1.Update([]byte(f.Content))
                tlsh2.Update([]byte(other.Content))

                // 计算距离
                distance := tlsh1.Distance(tlsh2)
                
                // 如果距离在阈值内，认为是相似的
                if distance >= 0 && distance <= 100 {
                    index.SimilarPairs = append(index.SimilarPairs, SimilarPair{
                        Function1: f,
                        Function2: other,
                        Distance: distance,
                    })
                }
            }
        }
    }

    return index
}

// saveFunctionIndex 保存函数索引
// 将函数索引保存到文件系统
func (c *Collector) saveFunctionIndex(index *FunctionIndex, basePath string) error {
    // 创建输出目录
    outDir := filepath.Join(c.baseDir, "functions")
    if err := os.MkdirAll(outDir, 0755); err != nil {
        return err
    }

    // 生成输出文件名
    outFile := filepath.Join(outDir, fmt.Sprintf("functions_%s.json",
        filepath.Base(basePath)))

    // 序列化��引
    data, err := json.MarshalIndent(index, "", "  ")
    if err != nil {
        return err
    }

    // 写入文件
    return os.WriteFile(outFile, data, 0644)
}

// isTargetFile 检查是否为目标文件类型
func (c *Collector) isTargetFile(path string) bool {
    ext := filepath.Ext(path)
    switch ext {
    case ".c", ".cpp", ".h", ".hpp":
        return true
    default:
        return false
    }
}

// 从 version.go 整合的内容
type Version struct {
    Major int
    Minor int
    Patch int
}

func (c *Collector) GetVersion() Version {
    // 版本相关逻辑
}

// 从 function.go 整合的内容
type Function struct {
    Name     string
    Content  string
    Metadata map[string]interface{}
}

func (c *Collector) ProcessFunction(f Function) error {
    // 函数处理逻辑
}