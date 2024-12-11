package collector

import (
    "bufio"
    "bytes"
    "encoding/json"
    "fmt"
    "os"
    "os/exec"
    "path/filepath"
    "strconv"
    "strings"
    "github.com/glaslos/tlsh"
    "go.uber.org/zap"
)

// FunctionInfo 函数信息
type FunctionInfo struct {
    Name       string   `json:"name"`
    FilePath   string   `json:"file_path"`
    StartLine  int      `json:"start_line"`
    EndLine    int      `json:"end_line"`
    Content    []string `json:"content"`
    Hash       string   `json:"hash"`
    Language   string   `json:"language"`
    Size       int      `json:"size"`
    Complexity int      `json:"complexity"`
}

// FunctionIndex 函数索引
type FunctionIndex struct {
    Functions []FunctionInfo `json:"functions"`
    Stats     IndexStats    `json:"stats"`
}

// IndexStats 索引统计
type IndexStats struct {
    TotalFunctions int            `json:"total_functions"`
    ByLanguage    map[string]int `json:"by_language"`
    BySize        map[string]int `json:"by_size"`
}

// extractFunctions 提取文件中的函数信息
func (c *Collector) extractFunctions(filePath string) ([]FunctionInfo, error) {
    // 检查缓存
    if cached, ok := c.cache.Get("func:" + filePath); ok {
        return cached.([]FunctionInfo), nil
    }

    // 使用ctags提取函数信息
    cmd := exec.Command("ctags", "--fields=+ne", "-f", "-", "--language-force=C++", filePath)
    var out bytes.Buffer
    cmd.Stdout = &out
    if err := cmd.Run(); err != nil {
        return nil, fmt.Errorf("ctags执行失败: %w", err)
    }

    var functions []FunctionInfo
    scanner := bufio.NewScanner(&out)
    for scanner.Scan() {
        line := scanner.Text()
        function, err := c.parseCtagsLine(line, filePath)
        if err != nil {
            utils.Logger.Debug("解析ctags行失败",
                zap.String("line", line),
                zap.Error(err))
            continue
        }
        functions = append(functions, function)
    }

    // 缓存结果
    c.cache.Put("func:"+filePath, functions)

    return functions, nil
}

// parseCtagsLine 解析ctags输出行
func (c *Collector) parseCtagsLine(line string, filePath string) (FunctionInfo, error) {
    fields := strings.Split(line, "\t")
    if len(fields) < 4 {
        return FunctionInfo{}, fmt.Errorf("无效的ctags输出格式")
    }

    // 解析行号范围
    lineRange := strings.Split(fields[3], ",")
    if len(lineRange) != 2 {
        return FunctionInfo{}, fmt.Errorf("无效的行号范围")
    }

    startLine, _ := strconv.Atoi(lineRange[0])
    endLine, _ := strconv.Atoi(lineRange[1])

    // 读取函数内容
    content, err := c.readFunctionContent(filePath, startLine, endLine)
    if err != nil {
        return FunctionInfo{}, err
    }

    // 计算TLSH哈希
    hash, err := c.calculateTLSHHash(content)
    if err != nil {
        return FunctionInfo{}, err
    }

    return FunctionInfo{
        Name:       fields[0],
        FilePath:   filePath,
        StartLine:  startLine,
        EndLine:    endLine,
        Content:    content,
        Hash:       hash,
        Language:   c.detectLanguage(filePath),
        Size:       len(content),
        Complexity: c.calculateComplexity(content),
    }, nil
}

// readFunctionContent 读取函数内容
func (c *Collector) readFunctionContent(filePath string, startLine, endLine int) ([]string, error) {
    file, err := c.rm.GetFile(filePath, os.O_RDONLY)
    if err != nil {
        return nil, err
    }
    defer c.rm.CloseFile(filePath)

    var lines []string
    scanner := bufio.NewScanner(file)
    currentLine := 1

    for scanner.Scan() {
        if currentLine >= startLine && currentLine <= endLine {
            lines = append(lines, scanner.Text())
        }
        if currentLine > endLine {
            break
        }
        currentLine++
    }

    return lines, scanner.Err()
}

// calculateTLSHHash 计算TLSH哈希
func (c *Collector) calculateTLSHHash(content []string) (string, error) {
    // 预处理代码，移除注释和空白
    processedContent := c.preprocessCode(content)
    
    // 计算TLSH哈希
    hash, err := tlsh.HashBytes([]byte(strings.Join(processedContent, "\n")))
    if err != nil {
        return "", err
    }
    
    return hash.String(), nil
}

// preprocessCode 预处理代码
func (c *Collector) preprocessCode(content []string) []string {
    var processed []string
    inComment := false

    for _, line := range content {
        // 移除单行注释
        if idx := strings.Index(line, "//"); idx >= 0 {
            line = line[:idx]
        }

        // 处理多行注释
        if !inComment {
            if idx := strings.Index(line, "/*"); idx >= 0 {
                inComment = true
                line = line[:idx]
            }
        } else {
            if idx := strings.Index(line, "*/"); idx >= 0 {
                inComment = false
                line = line[idx+2:]
            } else {
                continue
            }
        }

        // 移��空白
        line = strings.TrimSpace(line)
        if line != "" {
            processed = append(processed, line)
        }
    }

    return processed
}

// calculateComplexity 计算函数复杂度
func (c *Collector) calculateComplexity(content []string) int {
    complexity := 1 // 基础复杂度

    for _, line := range content {
        line = strings.TrimSpace(line)
        // 增加控制流复杂度
        if strings.HasPrefix(line, "if ") ||
           strings.HasPrefix(line, "for ") ||
           strings.HasPrefix(line, "while ") ||
           strings.HasPrefix(line, "case ") ||
           strings.Contains(line, "?") {
            complexity++
        }
    }

    return complexity
}

// generateFunctionIndex 生成函数索引
func (c *Collector) generateFunctionIndex(functions []FunctionInfo) *FunctionIndex {
    index := &FunctionIndex{
        Functions: functions,
        Stats: IndexStats{
            TotalFunctions: len(functions),
            ByLanguage:    make(map[string]int),
            BySize:        make(map[string]int),
        },
    }

    // 统计信息
    for _, f := range functions {
        // 按语言统计
        index.Stats.ByLanguage[f.Language]++

        // 按大小统计
        sizeCategory := c.categorizeFunctionSize(f.Size)
        index.Stats.BySize[sizeCategory]++
    }

    return index
}

// categorizeFunctionSize 对函数大小进行分类
func (c *Collector) categorizeFunctionSize(size int) string {
    switch {
    case size <= 10:
        return "small"
    case size <= 50:
        return "medium"
    case size <= 100:
        return "large"
    default:
        return "very_large"
    }
}

// saveFunctionIndex 保存函数索引
func (c *Collector) saveFunctionIndex(index *FunctionIndex, basePath string) error {
    // 创建输出目录
    outDir := filepath.Join(c.baseDir, "functions")
    if err := os.MkdirAll(outDir, 0755); err != nil {
        return err
    }

    // 生成输出文件名
    outFile := filepath.Join(outDir, fmt.Sprintf("functions_%s.json",
        filepath.Base(basePath)))

    // 序列化索引
    data, err := json.MarshalIndent(index, "", "  ")
    if err != nil {
        return err
    }

    // 写入文件
    return os.WriteFile(outFile, data, 0644)
} 