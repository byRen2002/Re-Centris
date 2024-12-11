package collector

import (
    "encoding/json"
    "fmt"
    "os"
    "path/filepath"
    "sort"
    "strings"
    "strconv"
    "time"
    "github.com/your/centris/pkg/utils"
    "go.uber.org/zap"
)

// VersionInfo 版本信息
type VersionInfo struct {
    Tag           string    `json:"tag"`           // 标签名
    CommitHash    string    `json:"commit_hash"`   // 提交哈希
    Author        string    `json:"author"`        // 作者
    Date          time.Time `json:"date"`          // 提交日期
    Message       string    `json:"message"`       // 提交信息
    Files         []string  `json:"files"`         // 变更文件列表
    ChangedFiles  int       `json:"changed_files"` // 变更文件数量
    Insertions    int       `json:"insertions"`    // 插入行数
    Deletions     int       `json:"deletions"`     // 删除行数
}

// VersionIndex 版本索引
type VersionIndex struct {
    Versions []VersionInfo `json:"versions"` // 版本列表
    Stats    VersionStats  `json:"stats"`    // 统计信息
}

// VersionStats 版本统计
type VersionStats struct {
    TotalVersions  int            `json:"total_versions"` // 总版本数
    AuthorStats    map[string]int `json:"author_stats"`   // 作者贡献统计
    MonthlyStats   map[string]int `json:"monthly_stats"`  // 月度统计
    FileStats      map[string]int `json:"file_stats"`     // 文件类型统计
}

// collectVersionInfo 收集版本信息
func (c *Collector) collectVersionInfo(repoPath string) ([]VersionInfo, error) {
    // 获取所有标签
    tags, err := utils.RunGitCommand(repoPath, "tag", "--sort=-creatordate")
    if err != nil {
        return nil, fmt.Errorf("获取标签失败: %w", err)
    }

    var versions []VersionInfo
    for _, tag := range strings.Split(strings.TrimSpace(tags), "\n") {
        if tag == "" {
            continue
        }

        // 获取标签信息
        info, err := c.getTagInfo(repoPath, tag)
        if err != nil {
            utils.Logger.Error("获取标签信息失败",
                zap.String("tag", tag),
                zap.Error(err))
            continue
        }
        versions = append(versions, info)
    }

    return versions, nil
}

// getTagInfo 获取标签详细信息
func (c *Collector) getTagInfo(repoPath, tag string) (VersionInfo, error) {
    info := VersionInfo{Tag: tag}

    // 获取提交哈希
    hash, err := utils.RunGitCommand(repoPath, "rev-list", "-n", "1", tag)
    if err != nil {
        return info, err
    }
    info.CommitHash = strings.TrimSpace(hash)

    // 获取作者信息
    author, err := utils.RunGitCommand(repoPath, "log", "-1", "--format=%an", tag)
    if err != nil {
        return info, err
    }
    info.Author = strings.TrimSpace(author)

    // 获取提交日期
    date, err := utils.RunGitCommand(repoPath, "log", "-1", "--format=%ct", tag)
    if err != nil {
        return info, err
    }
    timestamp, _ := strconv.ParseInt(strings.TrimSpace(date), 10, 64)
    info.Date = time.Unix(timestamp, 0)

    // 获取提交信息
    message, err := utils.RunGitCommand(repoPath, "log", "-1", "--format=%B", tag)
    if err != nil {
        return info, err
    }
    info.Message = strings.TrimSpace(message)

    // 获取变更统计
    stats, err := utils.RunGitCommand(repoPath, "diff", "--numstat", tag+"^", tag)
    if err == nil {
        info.Files = make([]string, 0)
        for _, line := range strings.Split(stats, "\n") {
            if line = strings.TrimSpace(line); line == "" {
                continue
            }
            fields := strings.Fields(line)
            if len(fields) >= 3 {
                insertions, _ := strconv.Atoi(fields[0])
                deletions, _ := strconv.Atoi(fields[1])
                info.Files = append(info.Files, fields[2])
                info.ChangedFiles++
                info.Insertions += insertions
                info.Deletions += deletions
            }
        }
    }

    return info, nil
}

// generateVersionIndex 生成版本索引
func (c *Collector) generateVersionIndex(versions []VersionInfo) *VersionIndex {
    index := &VersionIndex{
        Versions: versions,
        Stats: VersionStats{
            TotalVersions: len(versions),
            AuthorStats:   make(map[string]int),
            MonthlyStats:  make(map[string]int),
            FileStats:     make(map[string]int),
        },
    }

    for _, v := range versions {
        // 作者统计
        index.Stats.AuthorStats[v.Author]++

        // 月度统计
        month := v.Date.Format("2006-01")
        index.Stats.MonthlyStats[month]++

        // 文件统计
        for _, file := range v.Files {
            ext := filepath.Ext(file)
            if ext != "" {
                index.Stats.FileStats[ext]++
            }
        }
    }

    return index
}

// saveVersionIndex 保存版本索引
func (c *Collector) saveVersionIndex(index *VersionIndex, basePath string) error {
    // 创建输出目录
    outDir := filepath.Join(c.baseDir, "versions")
    if err := os.MkdirAll(outDir, 0755); err != nil {
        return err
    }

    // 生成输出文件名
    outFile := filepath.Join(outDir, fmt.Sprintf("versions_%s.json",
        filepath.Base(basePath)))

    // 序列化索引
    data, err := json.MarshalIndent(index, "", "  ")
    if err != nil {
        return err
    }

    // 写入文件
    return os.WriteFile(outFile, data, 0644)
}

// GetVersionStats 获取版本统计信息
func (c *Collector) GetVersionStats(versions []VersionInfo) map[string]interface{} {
    stats := make(map[string]interface{})
    
    // 计算时间范围
    if len(versions) > 0 {
        sort.Slice(versions, func(i, j int) bool {
            return versions[i].Date.Before(versions[j].Date)
        })
        stats["first_version_date"] = versions[0].Date
        stats["last_version_date"] = versions[len(versions)-1].Date
        stats["version_count"] = len(versions)
    }

    // 计算作者贡献
    authorStats := make(map[string]int)
    for _, v := range versions {
        authorStats[v.Author]++
    }
    stats["author_stats"] = authorStats

    // 计算变更统计
    var totalChangedFiles, totalInsertions, totalDeletions int
    for _, v := range versions {
        totalChangedFiles += v.ChangedFiles
        totalInsertions += v.Insertions
        totalDeletions += v.Deletions
    }
    stats["total_changed_files"] = totalChangedFiles
    stats["total_insertions"] = totalInsertions
    stats["total_deletions"] = totalDeletions

    return stats
} 