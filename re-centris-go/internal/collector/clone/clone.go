package clone

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"

	"github.com/re-centris/re-centris-go/internal/common/logger"
	"golang.org/x/sync/errgroup"
)

// RepoInfo contains information about a repository
type RepoInfo struct {
	Author string
	Name   string
	URL    string
}

// CloneOptions contains options for cloning repositories
type CloneOptions struct {
	TargetDir  string
	MaxWorkers int
}

// ParseRepoURL parses a GitHub repository URL and returns RepoInfo
func ParseRepoURL(url string) (*RepoInfo, error) {
	parts := strings.Split(url, "/")
	if len(parts) < 2 {
		return nil, fmt.Errorf("invalid repository URL: %s", url)
	}

	name := parts[len(parts)-1]
	author := parts[len(parts)-2]

	// Remove .git suffix if present
	name = strings.TrimSuffix(name, ".git")

	return &RepoInfo{
		Author: author,
		Name:   name,
		URL:    url,
	}, nil
}

// CloneRepository clones a single repository
func CloneRepository(ctx context.Context, info *RepoInfo, targetDir string) error {
	folderName := fmt.Sprintf("%s%%%s", info.Author, info.Name)
	targetPath := filepath.Join(targetDir, folderName)

	// Check if repository already exists
	if _, err := os.Stat(targetPath); !os.IsNotExist(err) {
		logger.Info("Repository already exists, skipping", 
			zap.String("repo", folderName))
		return nil
	}

	// Prepare git clone command
	cmd := exec.CommandContext(ctx, "git", "clone",
		"--depth", "1",
		"--single-branch",
		"--no-tags",
		info.URL,
		targetPath,
	)

	// Execute command
	if output, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("failed to clone repository %s: %v\nOutput: %s", 
			info.URL, err, string(output))
	}

	logger.Info("Successfully cloned repository",
		zap.String("repo", folderName))
	return nil
}

// CloneRepositories clones multiple repositories in parallel
func CloneRepositories(ctx context.Context, urls []string, opts CloneOptions) error {
	// Create target directory if it doesn't exist
	if err := os.MkdirAll(opts.TargetDir, 0755); err != nil {
		return fmt.Errorf("failed to create target directory: %v", err)
	}

	// Create error group with context
	g, ctx := errgroup.WithContext(ctx)
	g.SetLimit(opts.MaxWorkers)

	// Process each repository URL
	for _, url := range urls {
		url := url // Create new variable for goroutine
		g.Go(func() error {
			info, err := ParseRepoURL(url)
			if err != nil {
				logger.Error("Failed to parse repository URL",
					zap.String("url", url),
					zap.Error(err))
				return err
			}

			return CloneRepository(ctx, info, opts.TargetDir)
		})
	}

	// Wait for all goroutines to complete
	if err := g.Wait(); err != nil {
		return fmt.Errorf("error while cloning repositories: %v", err)
	}

	return nil
} 