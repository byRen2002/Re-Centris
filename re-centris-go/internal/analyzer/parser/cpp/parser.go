package cpp

import (
	"bufio"
	"bytes"
	"fmt"
	"io"
	"regexp"
	"strings"

	"github.com/re-centris/re-centris-go/internal/analyzer/parser"
	"github.com/re-centris/re-centris-go/internal/analyzer/tlsh"
)

var (
	// Function declaration pattern
	funcPattern = regexp.MustCompile(`^[\s]*(?:virtual\s+)?(?:static\s+)?(?:inline\s+)?(?:explicit\s+)?(?:[\w:]+[\s*&]+)?[\w:~]+[\s*&]*\s*[\w:]+\s*\([^)]*\)\s*(?:const\s*)?(?:noexcept\s*)?(?:override\s*)?(?:final\s*)?(?:=\s*0\s*)?(?:=\s*default\s*)?(?:=\s*delete\s*)?(?:\s*{\s*)?$`)

	// Class declaration pattern
	classPattern = regexp.MustCompile(`^[\s]*(?:class|struct)\s+\w+(?:\s*:\s*(?:public|protected|private)\s+\w+(?:\s*,\s*(?:public|protected|private)\s+\w+)*)?(?:\s*{\s*)?$`)
)

// CPPParser implements the Parser interface for C/C++
type CPPParser struct{}

// New creates a new C/C++ parser
func New() *CPPParser {
	return &CPPParser{}
}

// GetLanguage returns the language name
func (p *CPPParser) GetLanguage() string {
	return "cpp"
}

// GetExtensions returns supported file extensions
func (p *CPPParser) GetExtensions() []string {
	return []string{".c", ".cc", ".cpp", ".cxx", ".h", ".hpp"}
}

// Parse parses C/C++ source code and extracts functions
func (p *CPPParser) Parse(reader io.Reader) ([]parser.Function, error) {
	var (
		functions []parser.Function
		scanner   = bufio.NewScanner(reader)
		lineNum  = 0
		inFunc   = false
		inClass  = false
		curFunc  parser.Function
		content  strings.Builder
	)

	// Stack to track nested braces
	braceCount := 0

	for scanner.Scan() {
		lineNum++
		line := scanner.Text()
		trimmedLine := strings.TrimSpace(line)

		// Skip empty lines and comments
		if trimmedLine == "" || strings.HasPrefix(trimmedLine, "//") {
			continue
		}

		// Handle multi-line comments
		if strings.HasPrefix(trimmedLine, "/*") {
			for scanner.Scan() {
				lineNum++
				if strings.Contains(scanner.Text(), "*/") {
					break
				}
			}
			continue
		}

		// Track braces
		braceCount += strings.Count(line, "{") - strings.Count(line, "}")

		// Check for class/struct declarations
		if classPattern.MatchString(line) {
			inClass = true
			continue
		}

		// Check for function declarations
		if !inFunc && funcPattern.MatchString(line) {
			inFunc = true
			curFunc = parser.Function{
				Name:      extractFunctionName(line),
				StartLine: lineNum,
				Content:   line + "\n",
			}
			continue
		}

		// Inside function
		if inFunc {
			content.WriteString(line)
			content.WriteString("\n")

			// Function ends when braces are balanced
			if braceCount == 0 {
				curFunc.EndLine = lineNum
				curFunc.Content = content.String()

				// Calculate hash
				hash, err := tlsh.New([]byte(curFunc.Content))
				if err == nil {
					curFunc.Hash = hash.String()
				}

				functions = append(functions, curFunc)
				inFunc = false
				content.Reset()
			}
		}

		// Reset class state when closing brace is found
		if inClass && braceCount == 0 {
			inClass = false
		}
	}

	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("error scanning C/C++ code: %v", err)
	}

	return functions, nil
}

// extractFunctionName extracts the function name from the declaration
func extractFunctionName(line string) string {
	// Remove return type and parameters
	line = strings.TrimSpace(line)
	if idx := strings.Index(line, "("); idx > 0 {
		line = strings.TrimSpace(line[:idx])
	}

	// Get the last word before parameters
	parts := strings.Fields(line)
	if len(parts) > 0 {
		return parts[len(parts)-1]
	}

	return ""
} 