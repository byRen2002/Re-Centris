package cpp

import (
	"strings"
	"testing"
)

func TestCPPParser_GetLanguage(t *testing.T) {
	parser := New()
	if lang := parser.GetLanguage(); lang != "cpp" {
		t.Errorf("GetLanguage() = %v, want cpp", lang)
	}
}

func TestCPPParser_GetExtensions(t *testing.T) {
	parser := New()
	exts := parser.GetExtensions()
	expected := []string{".c", ".cc", ".cpp", ".cxx", ".h", ".hpp"}

	if len(exts) != len(expected) {
		t.Errorf("GetExtensions() returned %d extensions, want %d", len(exts), len(expected))
	}

	for i, ext := range expected {
		if exts[i] != ext {
			t.Errorf("GetExtensions()[%d] = %v, want %v", i, exts[i], ext)
		}
	}
}

func TestCPPParser_Parse(t *testing.T) {
	tests := []struct {
		name          string
		code          string
		wantFunctions int
		wantNames     []string
	}{
		{
			name: "simple function",
			code: `
				int add(int a, int b) {
					return a + b;
				}
			`,
			wantFunctions: 1,
			wantNames:     []string{"add"},
		},
		{
			name: "class method",
			code: `
				class Calculator {
				public:
					int add(int a, int b) {
						return a + b;
					}
					virtual void process() = 0;
				};
			`,
			wantFunctions: 2,
			wantNames:     []string{"add", "process"},
		},
		{
			name: "multiple functions",
			code: `
				void init() {}
				int calculate(double x) {
					return static_cast<int>(x);
				}
				namespace test {
					void helper() {}
				}
			`,
			wantFunctions: 3,
			wantNames:     []string{"init", "calculate", "helper"},
		},
		{
			name: "complex function",
			code: `
				template<typename T>
				static inline T* createObject(const std::string& name) noexcept {
					return new T(name);
				}
			`,
			wantFunctions: 1,
			wantNames:     []string{"createObject"},
		},
	}

	parser := New()
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			reader := strings.NewReader(tt.code)
			functions, err := parser.Parse(reader)
			
			if err != nil {
				t.Errorf("Parse() error = %v", err)
				return
			}

			if len(functions) != tt.wantFunctions {
				t.Errorf("Parse() got %v functions, want %v", len(functions), tt.wantFunctions)
				return
			}

			for i, wantName := range tt.wantNames {
				if i >= len(functions) {
					t.Errorf("Missing function %v", wantName)
					continue
				}
				if functions[i].Name != wantName {
					t.Errorf("Function[%d].Name = %v, want %v", i, functions[i].Name, wantName)
				}
				if functions[i].Hash == "" {
					t.Errorf("Function[%d].Hash is empty", i)
				}
			}
		})
	}
}

func TestCPPParser_ParseEdgeCases(t *testing.T) {
	tests := []struct {
		name    string
		code    string
		wantErr bool
	}{
		{
			name:    "empty code",
			code:    "",
			wantErr: false,
		},
		{
			name: "only comments",
			code: `
				// This is a comment
				/* This is a
				   multi-line comment */
			`,
			wantErr: false,
		},
		{
			name: "incomplete function",
			code: `
				int add(int a, int b) {
					return a + b;
				// missing closing brace
			`,
			wantErr: false, // parser should handle this gracefully
		},
		{
			name: "nested functions",
			code: `
				void outer() {
					void inner() {
						// nested function (invalid in C++)
					}
				}
			`,
			wantErr: false,
		},
	}

	parser := New()
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			reader := strings.NewReader(tt.code)
			_, err := parser.Parse(reader)
			if (err != nil) != tt.wantErr {
				t.Errorf("Parse() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

func BenchmarkCPPParser_Parse(b *testing.B) {
	code := `
		class Example {
		public:
			void method1() { }
			int method2(int x) { return x * 2; }
			virtual void method3() = 0;
		};

		namespace test {
			void function1() {
				// some code
			}
			
			int function2(double x) {
				return static_cast<int>(x);
			}
		}
	`
	
	parser := New()
	b.ResetTimer()
	
	for i := 0; i < b.N; i++ {
		reader := strings.NewReader(code)
		_, _ = parser.Parse(reader)
	}
} 