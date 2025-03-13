package config

// Config represents the main configuration structure
type Config struct {
	Paths       PathConfig       `yaml:"paths"`
	Performance PerformanceConfig `yaml:"performance"`
	Languages   LanguagesConfig  `yaml:"languages"`
}

// PathConfig contains all path-related configurations
type PathConfig struct {
	RepoPath    string `yaml:"repo_path"`
	TagDatePath string `yaml:"tag_date_path"`
	ResultPath  string `yaml:"result_path"`
}

// PerformanceConfig contains performance-related settings
type PerformanceConfig struct {
	MaxWorkers   int     `yaml:"max_workers"`
	CacheSize    int     `yaml:"cache_size"`
	MemoryLimit  float64 `yaml:"memory_limit"`
}

// LanguagesConfig contains settings for supported languages
type LanguagesConfig struct {
	CPP    LanguageSettings `yaml:"cpp"`
	Java   LanguageSettings `yaml:"java"`
	Python LanguageSettings `yaml:"python"`
}

// LanguageSettings contains settings for a specific language
type LanguageSettings struct {
	Enabled    bool     `yaml:"enabled"`
	Extensions []string `yaml:"extensions"`
}

// DefaultConfig returns a default configuration
func DefaultConfig() *Config {
	return &Config{
		Paths: PathConfig{
			RepoPath:    "./repos",
			TagDatePath: "./data/repo_date",
			ResultPath:  "./data/repo_functions",
		},
		Performance: PerformanceConfig{
			MaxWorkers:   0, // 0 means use number of CPU cores
			CacheSize:    1000,
			MemoryLimit: 0.8,
		},
		Languages: LanguagesConfig{
			CPP: LanguageSettings{
				Enabled:    true,
				Extensions: []string{".c", ".cc", ".cpp", ".cxx", ".h", ".hpp"},
			},
			Java: LanguageSettings{
				Enabled:    false,
				Extensions: []string{".java"},
			},
			Python: LanguageSettings{
				Enabled:    false,
				Extensions: []string{".py"},
			},
		},
	}
} 