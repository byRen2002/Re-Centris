package security

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/re-centris/re-centris-go/internal/analyzer"
	"github.com/re-centris/re-centris-go/internal/common/config"
	"github.com/re-centris/re-centris-go/internal/common/monitor"
)

func TestPathTraversal(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "re-centris-security-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	maliciousPaths := []string{
		"../../../etc/passwd",
		"..\\..\\..\\Windows\\System32",
		"/etc/shadow",
		"C:\\Windows\\System32\\config",
		filepath.Join(tmpDir, ".."),
	}

	cfg := &config.Config{
		Analysis: config.AnalysisConfig{
			OutputPath: tmpDir,
		},
	}

	analyzer := analyzer.New(cfg)

	for _, path := range maliciousPaths {
		err := analyzer.Analyze(path)
		if err == nil {
			t.Errorf("Expected error for malicious path: %s", path)
		}
	}
}

func TestMemoryLimit(t *testing.T) {
	mon := monitor.New(100 * time.Millisecond)
	mon.Start()
	defer mon.Stop()

	// Allocate memory gradually
	var slices [][]byte
	defer func() {
		slices = nil
	}()

	// Try to allocate memory until we hit the limit
	for i := 0; i < 100; i++ {
		if !mon.CheckMemoryLimit(0.8) { // 80% memory limit
			// Memory limit reached, test passed
			return
		}
		// Allocate 1MB
		slices = append(slices, make([]byte, 1024*1024))
	}

	t.Error("Memory limit was not enforced")
}

func TestConcurrentAccess(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "re-centris-security-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	cfg := &config.Config{
		Analysis: config.AnalysisConfig{
			OutputPath: tmpDir,
			Workers:    4,
		},
	}

	analyzer := analyzer.New(cfg)

	// Create test files
	testFiles := make([]string, 10)
	for i := range testFiles {
		file := filepath.Join(tmpDir, fmt.Sprintf("test%d.cpp", i))
		if err := os.WriteFile(file, []byte("int main() { return 0; }"), 0644); err != nil {
			t.Fatalf("Failed to create test file: %v", err)
		}
		testFiles[i] = file
	}

	// Test concurrent access
	var wg sync.WaitGroup
	errors := make(chan error, len(testFiles))

	for _, file := range testFiles {
		wg.Add(1)
		go func(f string) {
			defer wg.Done()
			if err := analyzer.Analyze(f); err != nil {
				errors <- err
			}
		}(file)
	}

	// Wait for all goroutines to finish
	wg.Wait()
	close(errors)

	// Check for errors
	for err := range errors {
		t.Errorf("Concurrent analysis error: %v", err)
	}
}

func TestResourceExhaustion(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "re-centris-security-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	cfg := &config.Config{
		Analysis: config.AnalysisConfig{
			OutputPath: tmpDir,
			Workers:    1000, // Excessive number of workers
		},
	}

	analyzer := analyzer.New(cfg)

	// Create a large file
	largeFile := filepath.Join(tmpDir, "large.cpp")
	f, err := os.Create(largeFile)
	if err != nil {
		t.Fatalf("Failed to create large file: %v", err)
	}

	// Write 100MB of data
	data := make([]byte, 1024)
	for i := 0; i < 1024*100; i++ {
		if _, err := f.Write(data); err != nil {
			f.Close()
			t.Fatalf("Failed to write to large file: %v", err)
		}
	}
	f.Close()

	// Set timeout for the test
	done := make(chan bool)
	go func() {
		err := analyzer.Analyze(largeFile)
		if err != nil {
			t.Logf("Analysis error (expected): %v", err)
		}
		done <- true
	}()

	select {
	case <-done:
		// Test completed within timeout
	case <-time.After(30 * time.Second):
		t.Error("Analysis took too long, possible resource exhaustion")
	}
}

func TestInputValidation(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "re-centris-security-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	cfg := &config.Config{
		Analysis: config.AnalysisConfig{
			OutputPath: tmpDir,
		},
	}

	analyzer := analyzer.New(cfg)

	invalidInputs := []struct {
		name string
		path string
	}{
		{"empty path", ""},
		{"space only", "   "},
		{"invalid chars", string([]byte{0x00, 0x01, 0x02})},
		{"very long path", strings.Repeat("a", 4096)},
	}

	for _, tc := range invalidInputs {
		t.Run(tc.name, func(t *testing.T) {
			err := analyzer.Analyze(tc.path)
			if err == nil {
				t.Errorf("Expected error for invalid input: %s", tc.name)
			}
		})
	}
} 