package cmd

import (
	"context"

	"github.com/re-centris/re-centris-go/internal/analyzer"
	"github.com/re-centris/re-centris-go/internal/common/logger"
	"github.com/spf13/cobra"
	"github.com/spf13/viper"
	"go.uber.org/zap"
)

var analyzeCmd = &cobra.Command{
	Use:   "analyze [directory]",
	Short: "Analyze source code files",
	Long: `Analyze source code files in a directory to calculate TLSH hashes
and extract function information.`,
	Args: cobra.ExactArgs(1),
	RunE: runAnalyze,
}

func init() {
	rootCmd.AddCommand(analyzeCmd)

	analyzeCmd.Flags().StringP("output", "o", "./analysis", "Output directory for analysis results")
	analyzeCmd.Flags().IntP("workers", "w", 5, "Number of parallel workers")

	viper.BindPFlag("analyze.output", analyzeCmd.Flags().Lookup("output"))
	viper.BindPFlag("analyze.workers", analyzeCmd.Flags().Lookup("workers"))
}

func runAnalyze(cmd *cobra.Command, args []string) error {
	// Get target directory
	targetDir := args[0]

	// Create analyzer options
	opts := analyzer.AnalyzerOptions{
		MaxWorkers: viper.GetInt("analyze.workers"),
		Languages: map[string][]string{
			"cpp": {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp"},
			"java": {".java"},
			"python": {".py"},
		},
	}

	// Create analyzer
	a := analyzer.New(opts)

	// Analyze directory
	logger.Info("Starting code analysis",
		zap.String("directory", targetDir))

	files, err := a.AnalyzeDirectory(context.Background(), targetDir)
	if err != nil {
		return err
	}

	logger.Info("Code analysis completed",
		zap.Int("total_files", len(files)))

	return nil
} 