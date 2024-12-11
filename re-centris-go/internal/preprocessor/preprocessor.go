package preprocessor

import (
    "bufio"
    "bytes"
    "encoding/json"
    "fmt"
    "io"
    "math"
    "os"
    "os/exec"
    "path/filepath"
    "runtime"
    "sort"
    "strconv"
    "strings"
    "sync"
    "time"
    "github.com/glaslos/tlsh"
    "github.com/your/centris/pkg/database"
    "github.com/your/centris/pkg/utils"
    "go.uber.org/zap"
)

// Cache 实现计算结果缓存
type Cache struct {
    data map[string]interface{}
    expiry map[string]time.Time
    maxSize int
    ttl time.Duration
    mu sync.RWMutex
}

func NewCache(maxSize int, ttl time.Duration) *Cache {
    return &Cache{
        data: make(map[string]interface{}),
        expiry: make(map[string]time.Time),
        maxSize: maxSize,
        ttl: ttl,
    }
}

func (c *Cache) Get(key string) (interface{}, bool) {
    c.mu.RLock()
    defer c.mu.RUnlock()
    
    if val, ok := c.data[key]; ok {
        if time.Now().Before(c.expiry[key]) {
            return val, true
        }
        delete(c.data, key)
        delete(c.expiry, key)
    }
    return nil, false
}

func (c *Cache) Set(key string, value interface{}) {
    c.mu.Lock()
    defer c.mu.Unlock()

    if len(c.data) >= c.maxSize {
        c.evict()
    }
    
    c.data[key] = value
    c.expiry[key] = time.Now().Add(c.ttl)
}

func (c *Cache) evict() {
    var oldestKey string
    var oldestTime time.Time
    
    for k, t := range c.expiry {
        if oldestKey == "" || t.Before(oldestTime) {
            oldestKey = k
            oldestTime = t
        }
    }
    
    if oldestKey != "" {
        delete(c.data, oldestKey)
        delete(c.expiry, oldestKey)
    }
}

// PerformanceMonitor 实现性能监控
type PerformanceMonitor struct {
    startTime time.Time
    processedItems int64
    lastLogTime time.Time
    mu sync.Mutex
}

func NewPerformanceMonitor() *PerformanceMonitor {
    now := time.Now()
    return &PerformanceMonitor{
        startTime: now,
        lastLogTime: now,
    }
}

func (pm *PerformanceMonitor) Update(items int64) {
    pm.mu.Lock()
    defer pm.mu.Unlock()
    
    pm.processedItems += items
    now := time.Now()
    
    if now.Sub(pm.lastLogTime) >= time.Minute {
        elapsed := now.Sub(pm.startTime).Seconds()
        rate := float64(pm.processedItems) / elapsed
        
        utils.Logger.Info("Performance stats",
            zap.Int64("total_items", pm.processedItems),
            zap.Float64("elapsed_seconds", elapsed),
            zap.Float64("items_per_second", rate))
            
        pm.lastLogTime = now
    }
}

// ResourceManager 资源管理器
type ResourceManager struct {
    fileHandles map[string]*os.File
    mu sync.RWMutex
}

func NewResourceManager() *ResourceManager {
    return &ResourceManager{
        fileHandles: make(map[string]*os.File),
    }
}

func (rm *ResourceManager) GetFile(path string, flag int) (*os.File, error) {
    rm.mu.Lock()
    defer rm.mu.Unlock()
    
    key := fmt.Sprintf("%s:%d", path, flag)
    if f, ok := rm.fileHandles[key]; ok {
        return f, nil
    }
    
    f, err := os.OpenFile(path, flag, 0644)
    if err != nil {
        return nil, err
    }
    
    rm.fileHandles[key] = f
    return f, nil
}

func (rm *ResourceManager) Close() {
    rm.mu.Lock()
    defer rm.mu.Unlock()
    
    for _, f := range rm.fileHandles {
        f.Close()
    }
    rm.fileHandles = make(map[string]*os.File)
}

// MemoryOptimizer 内存优化器
type MemoryOptimizer struct {
    targetMemory int64
    batchSize    int
    mu           sync.Mutex
}

func NewMemoryOptimizer(targetMemoryMB int64) *MemoryOptimizer {
    return &MemoryOptimizer{
        targetMemory: targetMemoryMB * 1024 * 1024,
        batchSize:    1000,
    }
}

func (mo *MemoryOptimizer) OptimizeBatchSize() int {
    mo.mu.Lock()
    defer mo.mu.Unlock()
    
    var m runtime.MemStats
    runtime.ReadMemStats(&m)
    
    if m.Alloc > uint64(mo.targetMemory) {
        mo.batchSize = int(math.Max(100, float64(mo.batchSize/2)))
    } else {
        mo.batchSize = int(math.Min(10000, float64(mo.batchSize*2)))
    }
    
    return mo.batchSize
}

// Preprocessor 扩展结构体
type Preprocessor struct {
    db          *database.Database
    ctagsPath   string
    concurrency int
    cache       *Cache
    monitor     *PerformanceMonitor
    
    // 配置参数
    theta       float64
    resultPath  string
    verIDXPath  string
    initialDBPath string
    finalDBPath string
    metaPath    string
    funcDatePath string
    rm           *ResourceManager
    mo           *MemoryOptimizer
    weightPath   string
}

// 新增配置选项
type PreprocessorOption func(*Preprocessor)

func WithResultPath(path string) PreprocessorOption {
    return func(p *Preprocessor) {
        p.resultPath = path
    }
}

func WithTheta(theta float64) PreprocessorOption {
    return func(p *Preprocessor) {
        p.theta = theta
    }
}

// NewPreprocessor 构造函数增加配置选项
func NewPreprocessor(db *database.Database, ctagsPath string, concurrency int, opts ...PreprocessorOption) *Preprocessor {
    p := &Preprocessor{
        db:          db,
        ctagsPath:   ctagsPath,
        concurrency: concurrency,
        cache:       NewCache(1000, time.Hour),
        monitor:     NewPerformanceMonitor(),
        theta:       0.1, // 默认值
    }
    
    for _, opt := range opts {
        opt(p)
    }
    
    return p
}

// ExtractVerDate 提取版本日期信息
func (p *Preprocessor) ExtractVerDate(repoName string) (map[string]string, error) {
    verDateDict := make(map[string]string)
    
    repoPath := filepath.Join(p.resultPath, repoName)
    file, err := os.Open(repoPath)
    if err != nil {
        return nil, err
    }
    defer file.Close()
    
    scanner := bufio.NewScanner(file)
    for scanner.Scan() {
        line := scanner.Text()
        if !strings.Contains(line, "tag:") {
            continue
        }
        
        date := line[0:10]
        tags := utils.ExtractTags(line)
        
        for _, tag := range tags {
            if tag != "" {
                verDateDict[tag] = date
            }
        }
    }
    
    return verDateDict, nil
}

// ProcessSingleRepo 处理单个仓库
func (p *Preprocessor) ProcessSingleRepo(repoName string) error {
    utils.Logger.Info("Processing repo", zap.String("repo", repoName))
    
    verDateDict, err := p.ExtractVerDate(repoName)
    if err != nil {
        return fmt.Errorf("extract version dates: %w", err)
    }
    
    funcDateDict := make(map[string]string)
    signature := make(map[string][]string)
    verDict := make(map[string]int)
    
    // 处理版本
    versions, err := p.getVersions(repoName)
    if err != nil {
        return err
    }
    
    for idx, version := range versions {
        verDict[version] = idx
        
        if err := p.processVersion(repoName, version, idx, signature, funcDateDict, verDateDict); err != nil {
            return err
        }
    }
    
    // 保存结果
    if err := p.saveResults(repoName, signature, funcDateDict, verDict); err != nil {
        return err
    }
    
    p.monitor.Update(1)
    return nil
}

// SaveMetaInfos 保存元信息
func (p *Preprocessor) SaveMetaInfos() error {
    aveFuncJson := NewSafeMap()
    allFuncJson := NewSafeMap()
    unique := NewSafeMap()
    
    repos, err := os.ReadDir(p.initialDBPath)
    if err != nil {
        return err
    }
    
    var wg sync.WaitGroup
    errChan := make(chan error, len(repos))
    
    for _, repo := range repos {
        wg.Add(1)
        go func(repoName string) {
            defer wg.Done()
            if err := p.processRepoMeta(repoName, aveFuncJson, allFuncJson, unique); err != nil {
                errChan <- err
            }
        }(repo.Name())
    }
    
    wg.Wait()
    close(errChan)
    
    for err := range errChan {
        if err != nil {
            return err
        }
    }
    
    // 安全地转换和保存
    aveFunc := make(map[string]int)
    allFunc := make(map[string]int)
    uniqueMap := make(map[string]string)
    
    for k, v := range aveFuncJson.data {
        if val, ok := v.(int); ok {
            aveFunc[k] = val
        }
    }
    
    for k, v := range allFuncJson.data {
        if val, ok := v.(int); ok {
            allFunc[k] = val
        }
    }
    
    for k, v := range unique.data {
        if val, ok := v.(string); ok {
            uniqueMap[k] = val
        }
    }
    
    return p.saveMetaResults(aveFunc, allFunc, uniqueMap)
}

// CodeSegmentation 代码分割
func (p *Preprocessor) CodeSegmentation() error {
    aveFuncs, err := p.getAveFuncs()
    if err != nil {
        return err
    }
    
    uniqueFuncs, err := p.getUniqueFuncs()
    if err != nil {
        return err
    }
    
    repos, err := os.ReadDir(p.initialDBPath)
    if err != nil {
        return err
    }
    
    var wg sync.WaitGroup
    errChan := make(chan error, len(repos))
    
    for _, repo := range repos {
        wg.Add(1)
        go func(repoName string) {
            defer wg.Done()
            
            if err := p.processRepoSegmentation(repoName, aveFuncs, uniqueFuncs); err != nil {
                errChan <- err
            }
        }(repo.Name())
    }
    
    wg.Wait()
    close(errChan)
    
    // 检查错误
    for err := range errChan {
        if err != nil {
            return err
        }
    }
    
    return nil
}

// Process 主处理函数
func (p *Preprocessor) Process() error {
    defer p.rm.Close() // 确保资源被清理
    
    // 初始化
    if err := p.Init(); err != nil {
        return fmt.Errorf("initialization: %w", err)
    }
    
    // 1. 消除冗余
    if err := p.redundancyElimination(); err != nil {
        return fmt.Errorf("redundancy elimination: %w", err)
    }
    
    // 2. 保存元信息
    if err := p.SaveMetaInfos(); err != nil {
        return fmt.Errorf("save meta infos: %w", err)
    }
    
    // 3. 代码分割
    if err := p.CodeSegmentation(); err != nil {
        return fmt.Errorf("code segmentation: %w", err)
    }
    
    return nil
}

// getVersions 获取版本列表
func (p *Preprocessor) getVersions(repoName string) ([]string, error) {
    versionPath := filepath.Join(p.resultPath, repoName)
    entries, err := os.ReadDir(versionPath)
    if err != nil {
        return nil, err
    }
    
    var versions []string
    for _, entry := range entries {
        if strings.HasPrefix(entry.Name(), "fuzzy_") && strings.HasSuffix(entry.Name(), ".hidx") {
            version := strings.TrimPrefix(entry.Name(), "fuzzy_")
            version = strings.TrimSuffix(version, ".hidx")
            if version != "" && version != " " {
                versions = append(versions, version)
            }
        }
    }
    
    sort.Strings(versions)
    return versions, nil
}

// processVersion 处理单个版本
func (p *Preprocessor) processVersion(repoName, version string, idx int,
    signature *SafeMap, funcDateDict *SafeMap,
    verDateDict map[string]string) error {
    
    versionFile := filepath.Join(p.resultPath, repoName, "fuzzy_"+version+".hidx")
    file, err := p.rm.GetFile(versionFile, os.O_RDONLY)
    if err != nil {
        utils.Logger.Error("Failed to open version file",
            zap.String("file", versionFile),
            zap.Error(err))
        return err
    }
    
    scanner := bufio.NewScanner(file)
    scanner.Scan() // Skip header
    
    for scanner.Scan() {
        line := scanner.Text()
        if line == "" || line == " " {
            continue
        }
        
        hashval := strings.Split(line, "\t")[0]
        
        // 安全地更新 maps
        if val, ok := signature.Get(hashval); !ok {
            signature.Set(hashval, []string{})
            funcDateDict.Set(hashval, []string{})
        }
        
        if val, ok := signature.Get(hashval); ok {
            if vers, ok := val.([]string); ok {
                vers = append(vers, strconv.Itoa(idx))
                signature.Set(hashval, vers)
            }
        }
        
        if val, ok := funcDateDict.Get(hashval); ok {
            if dates, ok := val.([]string); ok {
                if date, ok := verDateDict[version]; ok {
                    dates = append(dates, date)
                } else {
                    dates = append(dates, "NODATE")
                }
                funcDateDict.Set(hashval, dates)
            }
        }
    }
    
    if err := scanner.Err(); err != nil {
        utils.Logger.Error("Scanner error",
            zap.String("file", versionFile),
            zap.Error(err))
        return err
    }
    
    return nil
}

// getAveFuncs 获取平均函数数
func (p *Preprocessor) getAveFuncs() (map[string]int, error) {
    aveFuncs := make(map[string]int)
    data, err := os.ReadFile(filepath.Join(p.metaPath, "aveFuncs"))
    if err != nil {
        return nil, err
    }
    
    if err := json.Unmarshal(data, &aveFuncs); err != nil {
        return nil, err
    }
    
    return aveFuncs, nil
}

// getUniqueFuncs 获取唯一函数
func (p *Preprocessor) getUniqueFuncs() (map[string][]string, error) {
    uniqueFuncs := make(map[string][]string)
    data, err := os.ReadFile(filepath.Join(p.metaPath, "uniqueFuncs"))
    if err != nil {
        return nil, err
    }
    
    var uniqueJson []struct {
        Hash string   `json:"hash"`
        OSS  []string `json:"OSS"`
    }
    
    if err := json.Unmarshal(data, &uniqueJson); err != nil {
        return nil, err
    }
    
    for _, item := range uniqueJson {
        uniqueFuncs[item.Hash] = item.OSS
    }
    
    return uniqueFuncs, nil
}

// getMatchedFuncs 获取匹配的函数
func (p *Preprocessor) getMatchedFuncs(sigs []map[string]interface{}, oss string) []string {
    var matched []string
    for _, sig := range sigs {
        hashval := sig["hash"].(string)
        matched = append(matched, hashval)
    }
    return matched
}

// redundancyElimination 冗余消除
func (p *Preprocessor) redundancyElimination() error {
    repos, err := os.ReadDir(p.resultPath)
    if err != nil {
        return err
    }
    
    var wg sync.WaitGroup
    errChan := make(chan error, len(repos))
    
    for _, repo := range repos {
        wg.Add(1)
        go func(repoName string) {
            defer wg.Done()
            if err := p.ProcessSingleRepo(repoName); err != nil {
                errChan <- err
            }
        }(repo.Name())
    }
    
    wg.Wait()
    close(errChan)
    
    for err := range errChan {
        if err != nil {
            return err
        }
    }
    
    return nil
}

// saveResults 保存处理结果
func (p *Preprocessor) saveResults(repoName string, signature map[string][]string,
    funcDateDict map[string][]string, verDict map[string]int) error {
    
    // 保存函数日期
    funcDateFile := filepath.Join(p.funcDatePath, repoName+"_funcdate")
    f, err := os.Create(funcDateFile)
    if err != nil {
        return err
    }
    defer f.Close()
    
    for hashval, dates := range funcDateDict {
        sort.Strings(dates)
        fmt.Fprintf(f, "%s\t%s\n", hashval, dates[0])
    }
    
    // 保存版本引用
    verIdxFile := filepath.Join(p.verIDXPath, repoName+"_idx")
    verJson := make([]map[string]string, 0)
    for ver, idx := range verDict {
        verJson = append(verJson, map[string]string{
            "ver": ver,
            "idx": strconv.Itoa(idx),
        })
    }
    
    if err := utils.WriteJSON(verIdxFile, verJson); err != nil {
        return err
    }
    
    // 保存签名
    sigFile := filepath.Join(p.initialDBPath, repoName+"_sig")
    sigJson := make([]map[string]interface{}, 0)
    for hashval, vers := range signature {
        sigJson = append(sigJson, map[string]interface{}{
            "hash": hashval,
            "vers": vers,
        })
    }
    
    return utils.WriteJSON(sigFile, sigJson)
}

// processRepoMeta 处理仓库元信息
func (p *Preprocessor) processRepoMeta(repoName string,
    aveFuncJson, allFuncJson, unique *SafeMap) error {
    
    weightJson := make(map[string]float64)
    
    versions, err := p.getVersions(repoName)
    if err != nil {
        utils.Logger.Error("Failed to get versions",
            zap.String("repo", repoName),
            zap.Error(err))
        return err
    }
    totVers := len(versions)
    
    if totVers == 0 {
        return nil
    }
    
    var sigs []map[string]interface{}
    sigFile := filepath.Join(p.initialDBPath, repoName+"_sig")
    if err := utils.ReadJSON(sigFile, &sigs); err != nil {
        utils.Logger.Error("Failed to read signatures",
            zap.String("file", sigFile),
            zap.Error(err))
        return err
    }
    
    totFuncs := len(sigs)
    for _, sig := range sigs {
        hashval := sig["hash"].(string)
        vers := sig["vers"].([]string)
        
        unique.Set(hashval, repoName)
        weightJson[hashval] = math.Log(float64(totVers) / float64(len(vers)))
    }
    
    aveFuncJson.Set(repoName, totFuncs/totVers)
    allFuncJson.Set(repoName, totFuncs)
    
    weightFile := filepath.Join(p.weightPath, repoName+"_weights")
    return utils.WriteJSON(weightFile, weightJson)
}

// saveMetaResults 保存元信息结果
func (p *Preprocessor) saveMetaResults(aveFuncJson, allFuncJson map[string]int,
    unique map[string]string) error {
    
    // 保存平均函数数
    if err := utils.WriteJSON(filepath.Join(p.metaPath, "aveFuncs"), aveFuncJson); err != nil {
        return err
    }
    
    // 保存总函数数
    if err := utils.WriteJSON(filepath.Join(p.metaPath, "allFuncs"), allFuncJson); err != nil {
        return err
    }
    
    // 保存唯一函数
    var uniqueJson []map[string]interface{}
    for hash, oss := range unique {
        uniqueJson = append(uniqueJson, map[string]interface{}{
            "hash": hash,
            "OSS":  []string{oss},
        })
    }
    
    return utils.WriteJSON(filepath.Join(p.metaPath, "uniqueFuncs"), uniqueJson)
}

// compareFunctions 比较函数相似度
func (p *Preprocessor) compareFunctions(hashval, oss string,
    verDateDict *verDateDictMap) int {
    
    if dates, ok := verDateDict.Get(oss); !ok {
        dates, err := p.loadFunctionDates(oss)
        if err != nil {
            utils.Logger.Error("Failed to load function dates",
                zap.String("repo", oss),
                zap.Error(err))
            return math.MaxInt32
        }
        verDateDict.Set(oss, dates)
    }
    
    dates, _ := verDateDict.Get(oss)
    score := tlsh.DiffXlen(hashval, dates[hashval])
    return score
}

// loadFunctionDates 加载函数日期
func (p *Preprocessor) loadFunctionDates(repoName string) (map[string]string, error) {
    dates := make(map[string]string)
    
    file := filepath.Join(p.funcDatePath, repoName+"_funcdate")
    f, err := p.rm.GetFile(file, os.O_RDONLY)
    if err != nil {
        return nil, err
    }
    // 不需要close，ResourceManager会处理
    
    scanner := bufio.NewScanner(f)
    for scanner.Scan() {
        parts := strings.Split(scanner.Text(), "\t")
        if len(parts) == 2 {
            dates[parts[0]] = parts[1]
        }
    }
    
    return dates, nil
}

// processRepoSegmentation 处理仓库分割
func (p *Preprocessor) processRepoSegmentation(repoName string,
    aveFuncs map[string]int, uniqueFuncs map[string][]string) error {
    
    possibleMembers := make(map[string][]string)
    candiX := make(map[string]int)
    var removedFuncs []string
    verDateDict := make(map[string]map[string]string)
    
    // 读取签名
    var sigs []map[string]interface{}
    sigFile := filepath.Join(p.initialDBPath, repoName+"_sig")
    if err := utils.ReadJSON(sigFile, &sigs); err != nil {
        return err
    }
    
    if len(sigs) == 0 {
        return nil
    }
    
    // 处理每个签名
    for _, sig := range sigs {
        hashval := sig["hash"].(string)
        
        for _, oss := range uniqueFuncs[hashval] {
            if oss == repoName {
                continue
            }
            
            if _, ok := candiX[oss]; !ok {
                candiX[oss] = 0
            }
            
            // 比较函数
            score := p.compareFunctions(hashval, oss, verDateDict)
            if score <= 30 {
                candiX[oss]++
            }
        }
    }
    
    // 检查候选项
    for oss, count := range candiX {
        if aveFuncs[oss] == 0 {
            continue
        }
        
        if float64(count)/float64(aveFuncs[oss]) >= p.theta {
            possibleMembers[repoName] = append(possibleMembers[repoName], oss)
            removedFuncs = append(removedFuncs, p.getMatchedFuncs(sigs, oss)...)
        }
    }
    
    // 保存结果
    if len(possibleMembers[repoName]) == 0 {
        // 复制原文件
        return utils.CopyFile(
            filepath.Join(p.initialDBPath, repoName+"_sig"),
            filepath.Join(p.finalDBPath, repoName+"_sig"),
        )
    }
    
    // 保存过滤后的签名
    var finalSigs []map[string]interface{}
    removedSet := make(map[string]bool)
    for _, f := range removedFuncs {
        removedSet[f] = true
    }
    
    for _, sig := range sigs {
        if !removedSet[sig["hash"].(string)] {
            finalSigs = append(finalSigs, sig)
        }
    }
    
    return utils.WriteJSON(filepath.Join(p.finalDBPath, repoName+"_sig"), finalSigs)
}

// 添加常量定义
const (
    separator = "#@#"
    sepLen    = len(separator)
)

// 添加配置初始化函数
func (p *Preprocessor) Init() error {
    // 创建必要目录
    dirs := []string{
        p.verIDXPath,
        p.initialDBPath,
        p.finalDBPath,
        p.metaPath,
        p.funcDatePath,
        p.weightPath,
    }
    
    for _, dir := range dirs {
        if err := os.MkdirAll(dir, 0755); err != nil {
            return fmt.Errorf("create directory %s: %w", dir, err)
        }
        utils.Logger.Info("Created directory", zap.String("path", dir))
    }
    
    // 初始化资源管理器
    p.rm = NewResourceManager()
    p.mo = NewMemoryOptimizer(1024) // 1GB target memory
    
    return nil
}

// 添加并发安全的map包装器
type SafeMap struct {
    data map[string]interface{}
    mu   sync.RWMutex
}

func NewSafeMap() *SafeMap {
    return &SafeMap{
        data: make(map[string]interface{}),
    }
}

func (sm *SafeMap) Set(key string, value interface{}) {
    sm.mu.Lock()
    defer sm.mu.Unlock()
    sm.data[key] = value
}

func (sm *SafeMap) Get(key string) (interface{}, bool) {
    sm.mu.RLock()
    defer sm.mu.RUnlock()
    v, ok := sm.data[key]
    return v, ok
}
  