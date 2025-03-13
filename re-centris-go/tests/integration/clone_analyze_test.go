package integration

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/re-centris/re-centris-go/internal/analyzer"
	"github.com/re-centris/re-centris-go/internal/collector/clone"
	"github.com/re-centris/re-centris-go/internal/common/config"
)

func TestCloneAndAnalyze(t *testing.T) {
	// Skip if running in CI environment
	if os.Getenv("CI") != "" {
		t.Skip("Skipping integration test in CI environment")
	}

	// Create temporary directories
	tmpDir, err := os.MkdirTemp("", "re-centris-test-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	repoDir := filepath.Join(tmpDir, "repos")
	analysisDir := filepath.Join(tmpDir, "analysis")

	// Create test configuration
	cfg := &config.Config{
		Clone: config.CloneConfig{
			OutputPath: repoDir,
			Workers:    2,
		},
		Analysis: config.AnalysisConfig{
			OutputPath: analysisDir,
			Workers:    2,
		},
		Languages: config.LanguagesConfig{
			CPP: config.LanguageConfig{
				Enabled:    true,
				Extensions: []string{".cpp", ".h"},
			},
		},
	}

	// Test repository to clone (use a small, public repo)
	testRepo := "https://github.com/google/googletest.git"

	// Initialize cloner
	cloner := clone.New(cfg)

	// Clone repository
	err = cloner.Clone([]string{testRepo})
	if err != nil {
		t.Fatalf("Failed to clone repository: %v", err)
	}

	// Verify repository was cloned
	if _, err := os.Stat(repoDir); os.IsNotExist(err) {
		t.Errorf("Repository directory was not created")
	}

	// Initialize analyzer
	analyzer := analyzer.New(cfg)

	// Analyze cloned repository
	err = analyzer.Analyze(repoDir)
	if err != nil {
		t.Fatalf("Failed to analyze repository: %v", err)
	}

	// Verify analysis output
	if _, err := os.Stat(analysisDir); os.IsNotExist(err) {
		t.Errorf("Analysis directory was not created")
	}

	// Check for analysis results
	files, err := filepath.Glob(filepath.Join(analysisDir, "*.json"))
	if err != nil {
		t.Fatalf("Failed to list analysis files: %v", err)
	}
	if len(files) == 0 {
		t.Error("No analysis results were generated")
	}
}

func TestAnalyzeWithInvalidInput(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "re-centris-test-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	cfg := &config.Config{
		Analysis: config.AnalysisConfig{
			OutputPath: tmpDir,
			Workers:    1,
		},
	}

	analyzer := analyzer.New(cfg)

	// Test with non-existent directory
	err = analyzer.Analyze("/nonexistent/path")
	if err == nil {
		t.Error("Expected error when analyzing non-existent directory")
	}

	// Test with empty directory
	emptyDir := filepath.Join(tmpDir, "empty")
	if err := os.MkdirAll(emptyDir, 0755); err != nil {
		t.Fatalf("Failed to create empty directory: %v", err)
	}

	err = analyzer.Analyze(emptyDir)
	if err != nil {
		t.Errorf("Unexpected error analyzing empty directory: %v", err)
	}
} 