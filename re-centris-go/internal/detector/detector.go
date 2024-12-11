package detector

import (
    "fmt"
    "strings"
    "sync"
    "github.com/glaslos/tlsh"
    "github.com/your/centris/pkg/database"
    "github.com/your/centris/internal/preprocessor"
    "github.com/your/centris/pkg/utils"
    "go.uber.org/zap"
    "time"
    "os"
    "regexp"
    "runtime"
    "bufio"
    "encoding/json"
    "path/filepath"
    "errors"
)

type Match struct {
    SourceFile  string
    TargetFile  string
    Similarity  float64
    Functions   []FunctionMatch
    PredictedVersion string
    Confidence float64
    Analysis FunctionAnalysis
    CommonFunctions []string
    TotalFunctions float64
}

type FunctionMatch struct {
    SourceFunction string
    TargetFunction string
    Similarity    float64
}

type Cache struct {
    data       map[string]interface{}
    maxSize    int
    expiration time.Duration
    accessTime map[string]time.Time
    mu         sync.RWMutex
}

func NewCache(maxSize int, expiration time.Duration) *Cache {
    return &Cache{
        data:       make(map[string]interface{}),
        maxSize:    maxSize,
        expiration: expiration,
        accessTime: make(map[string]time.Time),
    }
}

func (c *Cache) Get(key string) (interface{}, bool) {
    c.mu.RLock()
    defer c.mu.RUnlock()

    value, exists := c.data[key]
    if !exists {
        return nil, false
    }

    // 检查是否过期
    if time.Since(c.accessTime[key]) > c.expiration {
        go c.Delete(key) // 异步删除过期项
        return nil, false
    }

    c.accessTime[key] = time.Now()
    return value, true
}

func (c *Cache) Set(key string, value interface{}) {
    c.mu.Lock()
    defer c.mu.Unlock()

    // 检查是否需要淘汰
    if len(c.data) >= c.maxSize {
        c.evictOldest()
    }

    c.data[key] = value
    c.accessTime[key] = time.Now()
}

func (c *Cache) Delete(key string) {
    c.mu.Lock()
    defer c.mu.Unlock()

    delete(c.data, key)
    delete(c.accessTime, key)
}

func (c *Cache) evictOldest() {
    var oldestKey string
    var oldestTime time.Time

    // 找到最早访问的项
    for key, accessTime := range c.accessTime {
        if oldestKey == "" || accessTime.Before(oldestTime) {
            oldestKey = key
            oldestTime = accessTime
        }
    }

    if oldestKey != "" {
        delete(c.data, oldestKey)
        delete(c.accessTime, oldestKey)
    }
}

type ResourceManager struct {
    files     map[string]*os.File
    pools     map[string]*WorkerPool
    mu        sync.RWMutex
}

func NewResourceManager() *ResourceManager {
    return &ResourceManager{
        files: make(map[string]*os.File),
        pools: make(map[string]*WorkerPool),
    }
}

func (rm *ResourceManager) GetFile(path string, mode int) (*os.File, error) {
    rm.mu.Lock()
    defer rm.mu.Unlock()

    key := fmt.Sprintf("%s:%d", path, mode)
    if file, exists := rm.files[key]; exists {
        return file, nil
    }

    file, err := os.OpenFile(path, mode, 0644)
    if err != nil {
        return nil, err
    }

    rm.files[key] = file
    return file, nil
}

func (rm *ResourceManager) GetWorkerPool(name string, size int) *WorkerPool {
    rm.mu.Lock()
    defer rm.mu.Unlock()

    if pool, exists := rm.pools[name]; exists {
        return pool
    }

    pool := NewWorkerPool(size)
    rm.pools[name] = pool
    return pool
}

func (rm *ResourceManager) Close() {
    rm.mu.Lock()
    defer rm.mu.Unlock()

    // 关闭所有文件
    for _, file := range rm.files {
        file.Close()
    }

    // 关闭所有工作池
    for _, pool := range rm.pools {
        pool.Close()
    }
}

type MemoryOptimizer struct {
    targetMemory uint64
    batchSize    int
    mu           sync.Mutex
}

func NewMemoryOptimizer(targetMemoryMB int) *MemoryOptimizer {
    return &MemoryOptimizer{
        targetMemory: uint64(targetMemoryMB) * 1024 * 1024,
        batchSize:   1000,
    }
}

func (mo *MemoryOptimizer) GetMemoryUsage() uint64 {
    var m runtime.MemStats
    runtime.ReadMemStats(&m)
    return m.Alloc
}

func (mo *MemoryOptimizer) OptimizeBatchSize() int {
    mo.mu.Lock()
    defer mo.mu.Unlock()

    currentMemory := mo.GetMemoryUsage()
    
    if currentMemory > mo.targetMemory {
        mo.batchSize = int(float64(mo.batchSize) * 0.8)
        if mo.batchSize < 100 {
            mo.batchSize = 100
        }
    } else {
        mo.batchSize = int(float64(mo.batchSize) * 1.2)
        if mo.batchSize > 10000 {
            mo.batchSize = 10000
        }
    }

    return mo.batchSize
}

type PerformanceMonitor struct {
    startTime      time.Time
    processedItems int64
    lastLogTime    time.Time
    mu            sync.Mutex
}

func NewPerformanceMonitor() *PerformanceMonitor {
    now := time.Now()
    return &PerformanceMonitor{
        startTime:   now,
        lastLogTime: now,
    }
}

func (pm *PerformanceMonitor) Update(items int) {
    pm.mu.Lock()
    defer pm.mu.Unlock()

    pm.processedItems += int64(items)
    now := time.Now()

    // 每分钟记录一次性能指标
    if now.Sub(pm.lastLogTime) >= time.Minute {
        elapsed := now.Sub(pm.startTime).Seconds()
        rate := float64(pm.processedItems) / elapsed

        utils.Logger.Info("Performance stats",
            zap.Int64("processed_items", pm.processedItems),
            zap.Float64("items_per_second", rate),
            zap.Float64("elapsed_seconds", elapsed))

        pm.lastLogTime = now
    }
}

type WorkerPool struct {
    tasks chan func()
    wg    sync.WaitGroup
}

func NewWorkerPool(size int) *WorkerPool {
    pool := &WorkerPool{
        tasks: make(chan func(), 1000),
    }

    // 启动工作协程
    for i := 0; i < size; i++ {
        go func() {
            for task := range pool.tasks {
                task()
                pool.wg.Done()
            }
        }()
    }

    return pool
}

func (p *WorkerPool) Submit(task func()) {
    p.wg.Add(1)
    p.tasks <- task
}

func (p *WorkerPool) Wait() {
    p.wg.Wait()
}

func (p *WorkerPool) Close() {
    close(p.tasks)
}

type FunctionExtractor struct {
    ctagsPath string
}

func NewFunctionExtractor(ctagsPath string) *FunctionExtractor {
    return &FunctionExtractor{
        ctagsPath: ctagsPath,
    }
}

func (fe *FunctionExtractor) ExtractFunctions(filePath string) ([]database.Function, error) {
    // 调用ctags提取函数信息
    output, err := utils.ExecuteCommand(fe.ctagsPath, "-f", "-", "--kinds-C=*", "--fields=neKSt", filePath)
    if err != nil {
        return nil, fmt.Errorf("ctags execution failed: %w", err)
    }

    // 解析ctags输出
    var functions []database.Function
    lines := strings.Split(output, "\n")
    
    for _, line := range lines {
        if line == "" {
            continue
        }

        fields := strings.Split(line, "\t")
        if len(fields) < 8 {
            continue
        }

        // 解析函数位置信息
        startLine := utils.ParseInt(strings.TrimPrefix(fields[4], "line:"))
        endLine := utils.ParseInt(strings.TrimPrefix(fields[7], "end:"))
        
        // 读取函数体
        body, err := fe.extractFunctionBody(filePath, startLine, endLine)
        if err != nil {
            utils.Logger.Warn("Failed to extract function body",
                zap.String("file", filePath),
                zap.Int("start", startLine),
                zap.Int("end", endLine),
                zap.Error(err))
            continue
        }

        functions = append(functions, database.Function{
            Name:      fields[0],
            FilePath:  filePath,
            StartLine: startLine,
            EndLine:   endLine,
            Body:      body,
        })
    }

    return functions, nil
}

func (fe *FunctionExtractor) extractFunctionBody(filePath string, start, end int) (string, error) {
    file, err := os.Open(filePath)
    if err != nil {
        return "", err
    }
    defer file.Close()

    scanner := bufio.NewScanner(file)
    var lines []string
    lineNum := 0

    for scanner.Scan() {
        lineNum++
        if lineNum >= start && lineNum <= end {
            lines = append(lines, scanner.Text())
        }
        if lineNum > end {
            break
        }
    }

    return strings.Join(lines, "\n"), scanner.Err()
}

type Detector struct {
    db           *database.Database
    preprocessor *preprocessor.Preprocessor
    threshold    float64
    concurrency  int
    cache        *Cache
    resources    *ResourceManager
    memOptimizer *MemoryOptimizer
    perfMonitor  *PerformanceMonitor
    extractor    *FunctionExtractor
    config       *Config
}

type Config struct {
    WeightPath   string
    VerIDXPath   string
    CtagsPath    string
    ResultPath   string
    MetaPath     string
    FinalDBPath  string
    InitialDBPath string
    RepoFuncPath string
}

func NewDetector(db *database.Database, preprocessor *preprocessor.Preprocessor, config *Config) *Detector {
    return &Detector{
        db:           db,
        preprocessor: preprocessor,
        threshold:    0.7, // 默认阈值
        concurrency:  runtime.NumCPU(),
        cache:        NewCache(1000, time.Hour),
        resources:    NewResourceManager(),
        memOptimizer: NewMemoryOptimizer(1024),
        perfMonitor:  NewPerformanceMonitor(),
        extractor:    NewFunctionExtractor(config.CtagsPath),
        config:       config,
    }
}

func (d *Detector) normalizeCode(code string) string {
    // 移除注释
    code = removeComments(code)
    
    // 标准化处理
    code = strings.ReplaceAll(code, "\n", "")
    code = strings.ReplaceAll(code, "\r", "")
    code = strings.ReplaceAll(code, "\t", "")
    code = strings.ReplaceAll(code, "{", "")
    code = strings.ReplaceAll(code, "}", "")
    code = strings.Join(strings.Fields(code), "")
    code = strings.ToLower(code)
    
    return code
}

func removeComments(code string) string {
    // 移除单行注释
    singleLineComment := regexp.MustCompile(`//.*`)
    code = singleLineComment.ReplaceAllString(code, "")
    
    // 移除多行注释
    multiLineComment := regexp.MustCompile(`/\*[\s\S]*?\*/`)
    code = multiLineComment.ReplaceAllString(code, "")
    
    return code
}

type VersionPredictor struct {
    weights map[string]float64
    db      *database.Database
}

func NewVersionPredictor(db *database.Database) *VersionPredictor {
    return &VersionPredictor{
        weights: make(map[string]float64),
        db:      db,
    }
}

func (vp *VersionPredictor) PredictVersion(functionMatches []FunctionMatch) (string, float64) {
    versionScores := make(map[string]float64)
    
    // 计算每个版本的得分
    for _, match := range functionMatches {
        weight := vp.weights[match.SourceFunction]
        for version := range vp.db.GetVersions() {
            if vp.db.HasFunction(version, match.TargetFunction) {
                versionScores[version] += weight * match.Similarity
            }
        }
    }
    
    // 找出得分最高的版本
    var bestVersion string
    var bestScore float64
    for version, score := range versionScores {
        if score > bestScore {
            bestVersion = version
            bestScore = score
        }
    }
    
    return bestVersion, bestScore
}

type FunctionAnalysis struct {
    Used      int
    Unused    int
    Modified  int
    StrChange bool
}

func (d *Detector) AnalyzeFunctionUsage(matches []FunctionMatch) FunctionAnalysis {
    analysis := FunctionAnalysis{}
    
    for _, match := range matches {
        if match.Similarity >= 0.9 { // 完全匹配阈值
            analysis.Used++
        } else if match.Similarity >= 0.7 { // 修改阈值
            analysis.Modified++
            
            // 检查结构变化
            if d.hasStructuralChange(match) {
                analysis.StrChange = true
            }
        } else {
            analysis.Unused++
        }
    }
    
    return analysis
}

func (d *Detector) hasStructuralChange(match FunctionMatch) bool {
    sourcePath := d.db.GetFunctionPath(match.SourceFunction)
    targetPath := d.db.GetFunctionPath(match.TargetFunction)
    
    // 检查函数路径是否发生显著变化
    return !strings.Contains(targetPath, sourcePath)
}

// 从 clone.go 整合的类型定义
type CloneType int

const (
    Type1 CloneType = iota + 1
    Type2
    Type3
)

type Clone struct {
    Type     CloneType
    Fragment1 string
    Fragment2 string
    Similarity float64
}

// 整合克隆相关方法
func (d *Detector) DetectClones(code string) []Clone {
    // 克隆检测逻辑
}

func (d *Detector) AnalyzeMatch(match Match) string {
    var analysis strings.Builder

    analysis.WriteString(fmt.Sprintf("Clone detected in file: %s\n", match.SourceFile))
    analysis.WriteString(fmt.Sprintf("Overall similarity: %.2f%%\n", match.Similarity*100))
    analysis.WriteString("\nMatched functions:\n")

    for _, fn := range match.Functions {
        analysis.WriteString(fmt.Sprintf("- %s matches %s (%.2f%% similar)\n",
            fn.SourceFunction,
            fn.TargetFunction,
            fn.Similarity*100))
    }

    return analysis.String()
}

func (d *Detector) getAveFuncs() (map[string]float64, error) {
    aveFuncsPath := filepath.Join(d.config.MetaPath, "aveFuncs")
    data, err := os.ReadFile(aveFuncsPath)
    if err != nil {
        return nil, fmt.Errorf("failed to read average functions file: %w", err)
    }

    var aveFuncs map[string]float64
    if err := json.Unmarshal(data, &aveFuncs); err != nil {
        return nil, fmt.Errorf("failed to parse average functions data: %w", err)
    }

    return aveFuncs, nil
}

func (d *Detector) readComponentDB() (map[string][]string, error) {
    componentDB := make(map[string][]string)
    
    entries, err := os.ReadDir(d.config.FinalDBPath)
    if err != nil {
        return nil, fmt.Errorf("failed to read component database directory: %w", err)
    }

    for _, entry := range entries {
        if entry.IsDir() {
            continue
        }

        ossName := entry.Name()
        componentDB[ossName] = make([]string, 0)

        data, err := os.ReadFile(filepath.Join(d.config.FinalDBPath, ossName))
        if err != nil {
            return nil, fmt.Errorf("failed to read component file %s: %w", ossName, err)
        }

        var jsonList []struct {
            Hash string `json:"hash"`
        }
        if err := json.Unmarshal(data, &jsonList); err != nil {
            return nil, fmt.Errorf("failed to parse component data %s: %w", ossName, err)
        }

        for _, item := range jsonList {
            componentDB[ossName] = append(componentDB[ossName], item.Hash)
        }
    }

    return componentDB, nil
}

func (d *Detector) readAllVers(repoName string) ([]string, map[int]string, error) {
    indexPath := filepath.Join(d.config.VerIDXPath, repoName+"_idx")
    data, err := os.ReadFile(indexPath)
    if err != nil {
        return nil, nil, fmt.Errorf("failed to read version index: %w", err)
    }

    var versions []struct {
        Ver string `json:"ver"`
        Idx int    `json:"idx"`
    }
    if err := json.Unmarshal(data, &versions); err != nil {
        return nil, nil, fmt.Errorf("failed to parse version index: %w", err)
    }

    verList := make([]string, 0, len(versions))
    idx2Ver := make(map[int]string)

    for _, v := range versions {
        verList = append(verList, v.Ver)
        idx2Ver[v.Idx] = v.Ver
    }

    return verList, idx2Ver, nil
}

func (d *Detector) readWeights(repoName string) (map[string]float64, error) {
    weightPath := filepath.Join(d.config.WeightPath, repoName+"_weights")
    data, err := os.ReadFile(weightPath)
    if err != nil {
        return nil, fmt.Errorf("failed to read weight file: %w", err)
    }

    var weights map[string]float64
    if err := json.Unmarshal(data, &weights); err != nil {
        return nil, fmt.Errorf("failed to parse weight data: %w", err)
    }

    return weights, nil
}

// 从 tlsh.go 整合的功能
type tlshHash struct {
    // TLSH 相关字段
}

func calculateTLSH(data []byte) *tlshHash {
    // TLSH 计算逻辑
}

func (d *Detector) compareWithTLSH(fragment1, fragment2 string) float64 {
    // 使用 TLSH 进行相似度比较
} 