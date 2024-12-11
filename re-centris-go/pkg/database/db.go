package database

import (
    "encoding/json"
    "os"
    "path/filepath"
    "sync"
)

type Database struct {
    path string
    mu   sync.RWMutex
}

type Signature struct {
    FunctionName string
    Hash        string
    FilePath    string
    Lines       []string
}

func NewDatabase(path string) (*Database, error) {
    if err := os.MkdirAll(path, 0755); err != nil {
        return nil, err
    }
    
    return &Database{
        path: path,
    }, nil
}

func (db *Database) SaveSignature(sig Signature) error {
    db.mu.Lock()
    defer db.mu.Unlock()
    
    filename := filepath.Join(db.path, sig.Hash+".json")
    
    data, err := json.Marshal(sig)
    if err != nil {
        return err
    }
    
    return os.WriteFile(filename, data, 0644)
}

func (db *Database) GetSignature(hash string) (*Signature, error) {
    db.mu.RLock()
    defer db.mu.RUnlock()
    
    filename := filepath.Join(db.path, hash+".json")
    
    data, err := os.ReadFile(filename)
    if err != nil {
        return nil, err
    }
    
    var sig Signature
    if err := json.Unmarshal(data, &sig); err != nil {
        return nil, err
    }
    
    return &sig, nil
}

func (db *Database) ListSignatures() ([]Signature, error) {
    db.mu.RLock()
    defer db.mu.RUnlock()
    
    pattern := filepath.Join(db.path, "*.json")
    matches, err := filepath.Glob(pattern)
    if err != nil {
        return nil, err
    }
    
    var signatures []Signature
    for _, match := range matches {
        data, err := os.ReadFile(match)
        if err != nil {
            continue
        }
        
        var sig Signature
        if err := json.Unmarshal(data, &sig); err != nil {
            continue
        }
        
        signatures = append(signatures, sig)
    }
    
    return signatures, nil
} 