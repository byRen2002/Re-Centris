package preprocessor

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"

	"github.com/re-centris/re-centris-go/internal/analyzer"
	"github.com/re-centris/re-centris-go/internal/common/logger"
	"golang.org/x/sync/errgroup"
)

// FileMetadata contains metadata about a processed file
type FileMetadata struct {
	Path       string            `json:"path"`
	Language   string            `json:"language"`
	Hash       string            `json:"hash"`
	Size       int64            `json:"size"`
	Functions  []FunctionInfo    `json:"functions,omitempty"`
}

// FunctionInfo contains information about a function
type FunctionInfo struct {
	Name       string `json:"name"`
	StartLine  int    `json:"start_line"`
	EndLine    int    `json:"end_line"`
	Hash       string `json:"hash"`
}

// PreprocessorOptions contains options for the preprocessor
type PreprocessorOptions struct {
	MaxWorkers     int
	OutputDir      string
	Languages      map[string][]string
	MinFileSize    int64
	MaxFileSize    int64
}

// Preprocessor handles file preprocessing
type Preprocessor struct {
	opts     PreprocessorOptions
	analyzer *analyzer.Analyzer
}

// New creates a new Preprocessor
func New(opts PreprocessorOptions) *Preprocessor {
	return &Preprocessor{
		opts: opts,
		analyzer: analyzer.New(analyzer.AnalyzerOptions{
			MaxWorkers: opts.MaxWorkers,
			Languages:  opts.Languages,
		}),
	}
}

// ProcessDirectory processes all files in a directory
func (p *Preprocessor) ProcessDirectory(ctx context.Context, dir string) error {
	// Create output directory if it doesn't exist
	if err := os.MkdirAll(p.opts.OutputDir, 0755); err != nil {
		return fmt.Errorf("failed to create output directory: %v", err)
	}

	// Analyze all files in directory
	files, err := p.analyzer.AnalyzeDirectory(ctx, dir)
	if err != nil {
		return fmt.Errorf("failed to analyze directory: %v", err)
	}

	// Process files in parallel
	g, ctx := errgroup.WithContext(ctx)
	g.SetLimit(p.opts.MaxWorkers)

	for _, file := range files {
		file := file // Create new variable for goroutine
		g.Go(func() error {
			// Skip files that are too small or too large
			if file.Size < p.opts.MinFileSize || 
			   (p.opts.MaxFileSize > 0 && file.Size > p.opts.MaxFileSize) {
				return nil
			}

			metadata := &FileMetadata{
				Path:     file.Path,
				Language: file.Language,
				Hash:     file.Hash.String(),
				Size:     file.Size,
			}

			// Extract functions if supported
			if funcs, err := p.extractFunctions(file); err == nil {
				metadata.Functions = funcs
			}

			// Save metadata
			if err := p.saveMetadata(metadata); err != nil {
				logger.Error("Failed to save metadata",
					zap.String("path", file.Path),
					zap.Error(err))
				return err
			}

			return nil
		})
	}

	return g.Wait()
}

// extractFunctions extracts function information from a file
func (p *Preprocessor) extractFunctions(file *analyzer.FileInfo) ([]FunctionInfo, error) {
	// TODO: Implement function extraction using language-specific parsers
	// This is a placeholder that should be replaced with actual implementation
	return nil, nil
}

// saveMetadata saves file metadata to JSON file
func (p *Preprocessor) saveMetadata(metadata *FileMetadata) error {
	// Create output filename based on file path
	relPath, err := filepath.Rel("/", metadata.Path)
	if err != nil {
		relPath = metadata.Path
	}
	outPath := filepath.Join(p.opts.OutputDir, 
		fmt.Sprintf("%s.json", filepath.ToSlash(relPath)))

	// Create parent directories if they don't exist
	if err := os.MkdirAll(filepath.Dir(outPath), 0755); err != nil {
		return fmt.Errorf("failed to create directories: %v", err)
	}

	// Marshal metadata to JSON
	data, err := json.MarshalIndent(metadata, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal metadata: %v", err)
	}

	// Write to file
	if err := os.WriteFile(outPath, data, 0644); err != nil {
		return fmt.Errorf("failed to write metadata: %v", err)
	}

	return nil
} 