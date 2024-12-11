package utils

import (
    "go.uber.org/zap"
    "go.uber.org/zap/zapcore"
)

var Logger *zap.Logger

func InitLogger(debug bool) error {
    config := zap.NewProductionConfig()
    if debug {
        config.Level = zap.NewAtomicLevelAt(zap.DebugLevel)
    }
    
    config.EncoderConfig.TimeKey = "timestamp"
    config.EncoderConfig.EncodeTime = zapcore.ISO8601TimeEncoder
    
    var err error
    Logger, err = config.Build()
    if err != nil {
        return err
    }
    
    return nil
}

func Debug(msg string, fields ...zap.Field) {
    Logger.Debug(msg, fields...)
}

func Info(msg string, fields ...zap.Field) {
    Logger.Info(msg, fields...)
}

func Error(msg string, fields ...zap.Field) {
    Logger.Error(msg, fields...)
}

func Fatal(msg string, fields ...zap.Field) {
    Logger.Fatal(msg, fields...)
}

// 字段构造函数
func String(key string, value string) zap.Field {
    return zap.String(key, value)
}

func Int(key string, value int) zap.Field {
    return zap.Int(key, value)
}

func Int64(key string, value int64) zap.Field {
    return zap.Int64(key, value)
}

func Float64(key string, value float64) zap.Field {
    return zap.Float64(key, value)
}

func Error(err error) zap.Field {
    return zap.Error(err)
} 