package clone

import (
    "bufio"
    "context"
    "fmt"
    "os"
    "path/filepath"
    "regexp"
    "strings"
    "sync"
    "time"
    "github.com/your/centris/pkg/utils"
    "go.uber.org/zap"
)

type RepoInfo struct {
    Author string
    Name   string
    URL    string
}

type Cloner struct {
    workDir     string
    concurrency int
    monitor     *utils.PerformanceMonitor
}

func NewCloner(workDir string, concurrency int) *Cloner {
    return &Cloner{
        workDir:     workDir,
        concurrency: concurrency,
        monitor:     utils.NewPerformanceMonitor(time.Minute),
    }
}

func (c *Cloner) LoadReposFromFile(filename string) ([]RepoInfo, error) {
    file, err := os.Open(filename)
    if err != nil {
        return nil, err
    }
    defer file.Close()

    var repos []RepoInfo
    scanner := bufio.NewScanner(file)
    for scanner.Scan() {
        url := scanner.Text()
        if url = strings.TrimSpace(url); url == "" {
            continue
        }

        repo, err := c.parseRepoURL(url)
        if err != nil {
            utils.Logger.Error("解析仓库URL失败",
                zap.String("url", url),
                zap.Error(err))
            continue
        }
        repos = append(repos, repo)
    }

    return repos, scanner.Err()
}

func (c *Cloner) parseRepoURL(url string) (RepoInfo, error) {
    re := regexp.MustCompile(`github\.com/([^/]+)/([^/]+)`)
    matches := re.FindStringSubmatch(url)
    if matches == nil {
        return RepoInfo{}, fmt.Errorf("无效的GitHub仓库URL: %s", url)
    }

    name := matches[2]
    if strings.HasSuffix(name, ".git") {
        name = name[:len(name)-4]
    }

    return RepoInfo{
        Author: matches[1],
        Name:   name,
        URL:    url,
    }, nil
}

func (c *Cloner) CloneRepositories(ctx context.Context, repos []string) error {
    repoInfos := make([]RepoInfo, 0, len(repos))
    for _, url := range repos {
        info, err := c.parseRepoURL(url)
        if err != nil {
            utils.Logger.Error("解析仓库URL失败",
                zap.String("url", url),
                zap.Error(err))
            continue
        }
        repoInfos = append(repoInfos, info)
    }

    return c.cloneRepos(ctx, repoInfos)
}

func (c *Cloner) cloneRepos(ctx context.Context, repos []RepoInfo) error {
    utils.Logger.Info("开始克隆仓库",
        zap.Int("total_repos", len(repos)),
        zap.Int("concurrency", c.concurrency))

    sem := make(chan struct{}, c.concurrency)
    var wg sync.WaitGroup
    errChan := make(chan error, len(repos))

    for _, repo := range repos {
        wg.Add(1)
        sem <- struct{}{} // 限制并发数

        go func(repo RepoInfo) {
            defer wg.Done()
            defer func() { <-sem }()

            if err := c.cloneSingleRepo(ctx, repo); err != nil {
                errChan <- fmt.Errorf("克隆仓库 %s 失败: %w", repo.URL, err)
                return
            }
            c.monitor.Update(1)
        }(repo)
    }

    wg.Wait()
    close(errChan)

    var errs []error
    for err := range errChan {
        errs = append(errs, err)
    }

    if len(errs) > 0 {
        utils.Logger.Error("部分仓库克隆失败",
            zap.Int("error_count", len(errs)))
        return errs[0]
    }

    utils.Logger.Info("所有仓库克隆完成")
    return nil
}

func (c *Cloner) cloneSingleRepo(ctx context.Context, repo RepoInfo) error {
    folderName := fmt.Sprintf("%s%%%s", repo.Author, repo.Name)
    targetPath := filepath.Join(c.workDir, folderName)

    if _, err := os.Stat(targetPath); err == nil {
        utils.Logger.Info("仓库已存在，跳过克隆",
            zap.String("repo", folderName))
        return nil
    }

    utils.Logger.Info("克隆仓库",
        zap.String("author", repo.Author),
        zap.String("name", repo.Name),
        zap.String("url", repo.URL))

    return utils.CloneRepo(ctx, utils.GitRepo{
        URL:     repo.URL,
        WorkDir: c.workDir,
        Options: []string{
            "--depth", "1",      // 只克隆最新版本
            "--single-branch",   // 只克隆默认分支
            "--no-tags",        // 不克隆标签
        },
    })
} 