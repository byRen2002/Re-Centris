package parser

import (
	"io"
)

// Function represents a parsed function
type Function struct {
	Name      string
	StartLine int
	EndLine   int
	Content   string
	Hash      string
}

// Parser defines the interface for language-specific parsers
type Parser interface {
	// Parse parses the source code and returns extracted functions
	Parse(reader io.Reader) ([]Function, error)
	
	// GetLanguage returns the language name
	GetLanguage() string
	
	// GetExtensions returns supported file extensions
	GetExtensions() []string
}

// Registry maintains a map of language parsers
type Registry struct {
	parsers map[string]Parser
}

// NewRegistry creates a new parser registry
func NewRegistry() *Registry {
	return &Registry{
		parsers: make(map[string]Parser),
	}
}

// Register registers a parser for a language
func (r *Registry) Register(parser Parser) {
	r.parsers[parser.GetLanguage()] = parser
}

// Get returns a parser for the given language
func (r *Registry) Get(language string) (Parser, bool) {
	parser, ok := r.parsers[language]
	return parser, ok
}

// GetByExtension returns a parser for the given file extension
func (r *Registry) GetByExtension(ext string) (Parser, bool) {
	for _, parser := range r.parsers {
		for _, e := range parser.GetExtensions() {
			if e == ext {
				return parser, true
			}
		}
	}
	return nil, false
} 