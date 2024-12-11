package utils

import (
	"encoding/json"
	"io"
	"os"
	"regexp"
)

// ExtractTags 提取标签
func ExtractTags(line string) []string {
	re := regexp.MustCompile(`tag:\s*([^,)]+)`)
	matches := re.FindAllStringSubmatch(line, -1)
	
	var tags []string
	for _, match := range matches {
		if len(match) > 1 {
			tags = append(tags, match[1])
		}
	}
	return tags
}

// WriteJSON 写入JSON文件
func WriteJSON(path string, data interface{}) error {
	jsonData, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return err
	}
	
	return os.WriteFile(path, jsonData, 0644)
}

// ReadJSON 读取JSON文件
func ReadJSON(path string, v interface{}) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	
	return json.Unmarshal(data, v)
}

// CopyFile 复制文件
func CopyFile(src, dst string) error {
	source, err := os.Open(src)
	if err != nil {
		return err
	}
	defer source.Close()
	
	destination, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer destination.Close()
	
	_, err = io.Copy(destination, source)
	return err
} 