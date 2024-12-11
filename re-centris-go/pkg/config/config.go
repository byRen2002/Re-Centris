package config

import (
    "github.com/spf13/viper"
)

type Config struct {
    WorkDir     string
    Concurrency int
    Database    DatabaseConfig
    Detector    DetectorConfig
}

type DatabaseConfig struct {
    Path string
}

type DetectorConfig struct {
    Threshold float64
}

func LoadConfig(configPath string) (*Config, error) {
    viper.SetConfigFile(configPath)
    viper.SetDefault("workDir", "./repos")
    viper.SetDefault("concurrency", 4)
    viper.SetDefault("database.path", "./data")
    viper.SetDefault("detector.threshold", 0.8)

    if err := viper.ReadInConfig(); err != nil {
        return nil, err
    }

    var config Config
    if err := viper.Unmarshal(&config); err != nil {
        return nil, err
    }

    return &config, nil
} 