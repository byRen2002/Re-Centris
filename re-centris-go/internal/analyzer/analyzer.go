package analyzer

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"github.com/re-centris/re-centris-go/internal/analyzer/tlsh"
	"github.com/re-centris/re-centris-go/internal/common/logger"
	"golang.org/x/sync/errgroup"
)

// FileInfo represents information about an analyzed file
type FileInfo struct {
	Path     string
	Language string
	Hash     *tlsh.TLSH
	Size     int64
}

// AnalyzerOptions contains options for the analyzer
type AnalyzerOptions struct {
	MaxWorkers int
	Languages  map[string][]string // map of language to file extensions
}

// Analyzer handles code analysis
type Analyzer struct {
	opts AnalyzerOptions
}

// New creates a new Analyzer
func New(opts AnalyzerOptions) *Analyzer {
	return &Analyzer{opts: opts}
}

// AnalyzeFile analyzes a single file and returns its FileInfo
func (a *Analyzer) AnalyzeFile(ctx context.Context, path string) (*FileInfo, error) {
	// Get file extension
	ext := strings.ToLower(filepath.Ext(path))
	
	// Find language for this extension
	var language string
	for lang, exts := range a.opts.Languages {
		for _, e := range exts {
			if e == ext {
				language = lang
				break
			}
		}
		if language != "" {
			break
		}
	}

	if language == "" {
		return nil, fmt.Errorf("unsupported file extension: %s", ext)
	}

	// Open and read file
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("failed to open file: %v", err)
	}
	defer file.Close()

	// Get file size
	stat, err := file.Stat()
	if err != nil {
		return nil, fmt.Errorf("failed to get file stats: %v", err)
	}

	// Read file content
	content, err := io.ReadAll(file)
	if err != nil {
		return nil, fmt.Errorf("failed to read file: %v", err)
	}

	// Calculate TLSH hash
	hash, err := tlsh.New(content)
	if err != nil {
		return nil, fmt.Errorf("failed to calculate TLSH hash: %v", err)
	}

	return &FileInfo{
		Path:     path,
		Language: language,
		Hash:     hash,
		Size:     stat.Size(),
	}, nil
}

// AnalyzeDirectory analyzes all files in a directory and its subdirectories
func (a *Analyzer) AnalyzeDirectory(ctx context.Context, dir string) ([]*FileInfo, error) {
	var (
		files    []*FileInfo
		filesMux sync.Mutex
	)

	// Create error group with context and worker limit
	g, ctx := errgroup.WithContext(ctx)
	g.SetLimit(a.opts.MaxWorkers)

	// Walk through directory
	err := filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}

		// Skip directories
		if info.IsDir() {
			return nil
		}

		// Check if context is cancelled
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		// Process file in goroutine
		g.Go(func() error {
			fileInfo, err := a.AnalyzeFile(ctx, path)
			if err != nil {
				if err == tlsh.ErrDataTooSmall {
					// Skip files that are too small
					return nil
				}
				logger.Error("Failed to analyze file",
					zap.String("path", path),
					zap.Error(err))
				return err
			}

			// Add file info to results
			filesMux.Lock()
			files = append(files, fileInfo)
			filesMux.Unlock()

			return nil
		})

		return nil
	})

	if err != nil {
		return nil, fmt.Errorf("failed to walk directory: %v", err)
	}

	// Wait for all goroutines to complete
	if err := g.Wait(); err != nil {
		return nil, fmt.Errorf("error while analyzing files: %v", err)
	}

	return files, nil
}

// FindSimilarFiles finds files similar to the target file
func (a *Analyzer) FindSimilarFiles(target *FileInfo, candidates []*FileInfo, threshold int) []*FileInfo {
	var similar []*FileInfo
	
	for _, candidate := range candidates {
		// Skip same file
		if target.Path == candidate.Path {
			continue
		}

		// Skip files with different languages
		if target.Language != candidate.Language {
			continue
		}

		// Calculate distance
		distance := target.Hash.Distance(candidate.Hash)
		if distance <= threshold {
			similar = append(similar, candidate)
		}
	}

	return similar
} 