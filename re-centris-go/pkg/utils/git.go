package utils

import (
    "context"
    "os/exec"
    "path/filepath"
    "github.com/go-git/go-git/v5"
    "github.com/go-git/go-git/v5/plumbing"
    "go.uber.org/zap"
)

type GitRepo struct {
    URL      string
    WorkDir  string
    Options  []string
    Branch   string
    Depth    int
}

// RunGitCommand 在指定目录执行Git命令
func RunGitCommand(dir string, args ...string) (string, error) {
    cmd := exec.Command("git", args...)
    cmd.Dir = dir
    output, err := cmd.Output()
    if err != nil {
        return "", err
    }
    return string(output), nil
}

func CloneRepo(ctx context.Context, repo GitRepo) error {
    Logger.Info("克隆仓库",
        zap.String("url", repo.URL),
        zap.String("workdir", repo.WorkDir))

    targetPath := filepath.Join(repo.WorkDir, filepath.Base(repo.URL))
    
    // 配置克隆选项
    cloneOpts := &git.CloneOptions{
        URL:      repo.URL,
        Progress: nil,
    }

    // 设置分支
    if repo.Branch != "" {
        cloneOpts.ReferenceName = plumbing.NewBranchReferenceName(repo.Branch)
        cloneOpts.SingleBranch = true
    }

    // 设置深度
    if repo.Depth > 0 {
        cloneOpts.Depth = repo.Depth
    }

    // 应用其他选项
    for i := 0; i < len(repo.Options); i += 2 {
        switch repo.Options[i] {
        case "--depth":
            if i+1 < len(repo.Options) {
                cloneOpts.Depth = 1 // 简化处理，固定为1
            }
        case "--single-branch":
            cloneOpts.SingleBranch = true
        case "--no-tags":
            cloneOpts.Tags = git.NoTags
        }
    }
    
    _, err := git.PlainCloneContext(ctx, targetPath, false, cloneOpts)
    
    if err != nil {
        Logger.Error("克隆仓库失败",
            zap.String("url", repo.URL),
            zap.Error(err))
        return err
    }

    Logger.Info("仓库克隆成功",
        zap.String("url", repo.URL),
        zap.String("path", targetPath))
    
    return nil
} 