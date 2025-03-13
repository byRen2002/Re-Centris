package cmd

import (
	"context"

	"github.com/re-centris/re-centris-go/internal/detector"
	"github.com/re-centris/re-centris-go/internal/common/logger"
	"github.com/spf13/cobra"
	"github.com/spf13/viper"
)

var detectCmd = &cobra.Command{
	Use:   "detect [target-files...]",
	Short: "Detect code similarities",
	Long: `Detect code similarities between target files and known files
using TLSH hash comparison.`,
	Args: cobra.MinimumNArgs(1),
	RunE: runDetect,
}

func init() {
	rootCmd.AddCommand(detectCmd)

	detectCmd.Flags().StringP("known-files", "k", "./known-files", "Directory containing known files")
	detectCmd.Flags().StringP("output", "o", "detection-results.json", "Output file for detection results")
	detectCmd.Flags().IntP("workers", "w", 5, "Number of parallel workers")
	detectCmd.Flags().Float64P("threshold", "t", 0.8, "Similarity threshold (0.0-1.0)")

	viper.BindPFlag("detect.known_files", detectCmd.Flags().Lookup("known-files"))
	viper.BindPFlag("detect.output", detectCmd.Flags().Lookup("output"))
	viper.BindPFlag("detect.workers", detectCmd.Flags().Lookup("workers"))
	viper.BindPFlag("detect.threshold", detectCmd.Flags().Lookup("threshold"))
}

func runDetect(cmd *cobra.Command, args []string) error {
	// Create detector options
	opts := detector.DetectorOptions{
		MaxWorkers:         viper.GetInt("detect.workers"),
		SimilarityThreshold: viper.GetFloat64("detect.threshold"),
		KnownFilesDir:      viper.GetString("detect.known_files"),
		Languages: map[string][]string{
			"cpp":    {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp"},
			"java":   {".java"},
			"python": {".py"},
		},
	}

	// Create detector
	d := detector.New(opts)

	// Detect similarities
	logger.Info("Starting similarity detection",
		zap.Int("target_files", len(args)),
		zap.String("known_files_dir", opts.KnownFilesDir))

	results, err := d.DetectSimilarity(context.Background(), args)
	if err != nil {
		return err
	}

	// Save results
	outputFile := viper.GetString("detect.output")
	if err := d.SaveResults(results, outputFile); err != nil {
		return err
	}

	logger.Info("Similarity detection completed",
		zap.String("output_file", outputFile))

	return nil
} 