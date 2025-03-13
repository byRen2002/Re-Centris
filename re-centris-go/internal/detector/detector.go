package detector

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"sync"

	"github.com/re-centris/re-centris-go/internal/analyzer"
	"github.com/re-centris/re-centris-go/internal/common/logger"
	"golang.org/x/sync/errgroup"
)

// DetectionResult represents the result of a code similarity detection
type DetectionResult struct {
	TargetFile  string           `json:"target_file"`
	Matches     []Match          `json:"matches"`
	TotalFiles  int             `json:"total_files"`
	MatchCount  int             `json:"match_count"`
}

// Match represents a single match in the detection result
type Match struct {
	File       string  `json:"file"`
	Similarity float64 `json:"similarity"`
	Distance   int     `json:"distance"`
}

// DetectorOptions contains options for the detector
type DetectorOptions struct {
	MaxWorkers      int
	SimilarityThreshold float64
	Languages       map[string][]string
	KnownFilesDir   string
}

// Detector handles code similarity detection
type Detector struct {
	opts     DetectorOptions
	analyzer *analyzer.Analyzer
}

// New creates a new Detector
func New(opts DetectorOptions) *Detector {
	return &Detector{
		opts: opts,
		analyzer: analyzer.New(analyzer.AnalyzerOptions{
			MaxWorkers: opts.MaxWorkers,
			Languages:  opts.Languages,
		}),
	}
}

// DetectSimilarity detects code similarity between target files and known files
func (d *Detector) DetectSimilarity(ctx context.Context, targetFiles []string) ([]*DetectionResult, error) {
	// Load known files
	knownFiles, err := d.loadKnownFiles(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to load known files: %v", err)
	}

	// Process target files in parallel
	var (
		results []*DetectionResult
		resultsMux sync.Mutex
	)

	g, ctx := errgroup.WithContext(ctx)
	g.SetLimit(d.opts.MaxWorkers)

	for _, targetFile := range targetFiles {
		targetFile := targetFile // Create new variable for goroutine
		g.Go(func() error {
			// Analyze target file
			fileInfo, err := d.analyzer.AnalyzeFile(ctx, targetFile)
			if err != nil {
				logger.Error("Failed to analyze target file",
					zap.String("file", targetFile),
					zap.Error(err))
				return err
			}

			// Find similar files
			similar := d.analyzer.FindSimilarFiles(fileInfo, knownFiles, 
				int(100 * (1 - d.opts.SimilarityThreshold)))

			// Create matches
			matches := make([]Match, len(similar))
			for i, s := range similar {
				distance := fileInfo.Hash.Distance(s.Hash)
				similarity := 1.0 - float64(distance)/100.0
				matches[i] = Match{
					File:       s.Path,
					Similarity: similarity,
					Distance:   distance,
				}
			}

			// Sort matches by similarity (descending)
			sort.Slice(matches, func(i, j int) bool {
				return matches[i].Similarity > matches[j].Similarity
			})

			// Create result
			result := &DetectionResult{
				TargetFile:  targetFile,
				Matches:     matches,
				TotalFiles:  len(knownFiles),
				MatchCount:  len(matches),
			}

			// Add to results
			resultsMux.Lock()
			results = append(results, result)
			resultsMux.Unlock()

			return nil
		})
	}

	if err := g.Wait(); err != nil {
		return nil, fmt.Errorf("error while detecting similarities: %v", err)
	}

	return results, nil
}

// loadKnownFiles loads all known files from the specified directory
func (d *Detector) loadKnownFiles(ctx context.Context) ([]*analyzer.FileInfo, error) {
	return d.analyzer.AnalyzeDirectory(ctx, d.opts.KnownFilesDir)
}

// SaveResults saves detection results to a JSON file
func (d *Detector) SaveResults(results []*DetectionResult, outputPath string) error {
	// Create parent directories if they don't exist
	if err := os.MkdirAll(filepath.Dir(outputPath), 0755); err != nil {
		return fmt.Errorf("failed to create directories: %v", err)
	}

	// Marshal results to JSON
	data, err := json.MarshalIndent(results, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal results: %v", err)
	}

	// Write to file
	if err := os.WriteFile(outputPath, data, 0644); err != nil {
		return fmt.Errorf("failed to write results: %v", err)
	}

	return nil
} 