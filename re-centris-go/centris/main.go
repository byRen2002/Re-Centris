package main

import (
    "context"
    "flag"
    "log"
    "os"
    "path/filepath"
    "github.com/your/centris/internal/clone"
    "github.com/your/centris/internal/collector"
    "github.com/your/centris/internal/preprocessor"
    "github.com/your/centris/internal/detector"
    "github.com/your/centris/pkg/config"
    "github.com/your/centris/pkg/database"
    "github.com/your/centris/pkg/utils"
)

func main() {
    // 命令行参数
    configPath := flag.String("config", "config.yaml", "配置文件路径")
    target := flag.String("target", "", "目标分析目录")
    repoList := flag.String("repo-list", "", "仓库列表文件路径")
    debug := flag.Bool("debug", false, "启用调试日志")
    flag.Parse()

    // 初始化日志
    if err := utils.InitLogger(*debug); err != nil {
        log.Fatal("初始化日志失败:", err)
    }

    // 加载配置
    cfg, err := config.LoadConfig(*configPath)
    if err != nil {
        utils.Fatal("加载配置失败", utils.Error(err))
    }

    // 创建工作目录
    if err := os.MkdirAll(cfg.WorkDir, 0755); err != nil {
        utils.Fatal("创建工作目录失败", utils.Error(err))
    }

    // 初始化数据库
    db, err := database.NewDatabase(cfg.Database.Path)
    if err != nil {
        utils.Fatal("初始化数据库失败", utils.Error(err))
    }

    // 初始化资源管理器
    rm := utils.NewResourceManager(cfg.Concurrency)
    defer rm.CloseAll()

    // 初始化各个模块
    cloner := clone.NewCloner(cfg.WorkDir, cfg.Concurrency)
    collector := collector.NewCollector(cfg.WorkDir, cfg.Concurrency)
    preprocessor := preprocessor.NewPreprocessor(db, "ctags", cfg.Concurrency)
    detector := detector.NewDetector(db, preprocessor, cfg.Detector.Threshold, cfg.Concurrency)

    // 处理目标目录
    if *target != "" {
        targetPath, err := filepath.Abs(*target)
        if err != nil {
            utils.Fatal("无效的目标路径", utils.Error(err))
        }

        // 收集目标目录的元数据
        metadata, err := collector.CollectMetadata(targetPath)
        if err != nil {
            utils.Fatal("收集元数据失败", utils.Error(err))
        }

        // 检测克隆
        matches, err := detector.DetectClones(targetPath)
        if err != nil {
            utils.Fatal("检测克隆失败", utils.Error(err))
        }

        // 输出结果
        for _, match := range matches {
            analysis := detector.AnalyzeMatch(match)
            utils.Info("克隆分析结果", utils.String("analysis", analysis))
        }
    } else if *repoList != "" {
        // 从文件读取仓库列表
        repos, err := cloner.LoadReposFromFile(*repoList)
        if err != nil {
            utils.Fatal("读取仓库列表失败", utils.Error(err))
        }

        // 克隆仓库
        ctx := context.Background()
        repoURLs := make([]string, len(repos))
        for i, repo := range repos {
            repoURLs[i] = repo.URL
        }

        if err := cloner.CloneRepositories(ctx, repoURLs); err != nil {
            utils.Fatal("克隆仓库失败", utils.Error(err))
        }

        // 处理克隆的仓库
        repoPath := filepath.Join(cfg.WorkDir, "repos")
        if err := preprocessor.ProcessDirectory(repoPath); err != nil {
            utils.Fatal("处理仓库失败", utils.Error(err))
        }
    } else {
        utils.Fatal("必须指定目标目录(-target)或仓库列表文件(-repo-list)")
    }

    utils.Info("分析完成")
} 