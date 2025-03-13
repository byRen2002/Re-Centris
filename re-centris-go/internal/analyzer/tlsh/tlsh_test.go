package tlsh

import (
	"testing"
)

func TestTLSH(t *testing.T) {
	tests := []struct {
		name     string
		data     []byte
		wantErr  bool
		distance int // distance with itself should be 0
	}{
		{
			name:     "normal text",
			data:     []byte("This is a test string that is long enough to generate a TLSH hash"),
			wantErr:  false,
			distance: 0,
		},
		{
			name:     "too short",
			data:     []byte("too short"),
			wantErr:  true,
			distance: -1,
		},
		{
			name:     "repeated content",
			data:     []byte("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
			wantErr:  false,
			distance: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			hash1, err1 := New(tt.data)
			if (err1 != nil) != tt.wantErr {
				t.Errorf("New() error = %v, wantErr %v", err1, tt.wantErr)
				return
			}
			if tt.wantErr {
				return
			}

			// Test distance with itself
			if dist := hash1.Distance(hash1); dist != tt.distance {
				t.Errorf("Distance with itself = %v, want %v", dist, tt.distance)
			}

			// Test string representation
			if str := hash1.String(); str == "" {
				t.Error("String() returned empty string")
			}

			// Test with modified data
			modifiedData := make([]byte, len(tt.data))
			copy(modifiedData, tt.data)
			modifiedData[len(modifiedData)-1]++ // modify last byte
			hash2, _ := New(modifiedData)

			// Distance should be non-zero for different data
			if dist := hash1.Distance(hash2); dist == 0 {
				t.Error("Distance should be non-zero for different data")
			}
		})
	}
}

func TestTLSHEdgeCases(t *testing.T) {
	tests := []struct {
		name    string
		data    []byte
		wantErr bool
	}{
		{
			name:    "nil data",
			data:    nil,
			wantErr: true,
		},
		{
			name:    "empty data",
			data:    []byte{},
			wantErr: true,
		},
		{
			name:    "exactly minimum length",
			data:    make([]byte, minDataLength),
			wantErr: false,
		},
		{
			name:    "one byte less than minimum",
			data:    make([]byte, minDataLength-1),
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := New(tt.data)
			if (err != nil) != tt.wantErr {
				t.Errorf("New() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

func BenchmarkTLSH(b *testing.B) {
	data := []byte(`This is a test string that is long enough to generate a TLSH hash.
		We need to make it even longer to ensure we have enough data for meaningful benchmarks.
		Adding more text to make it more realistic and provide better performance measurements.`)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, _ = New(data)
	}
} 