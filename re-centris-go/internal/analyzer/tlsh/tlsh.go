package tlsh

import (
	"crypto/sha256"
	"encoding/hex"
	"math"
	"sort"
)

const (
	bucketCount   = 256
	windowSize    = 5
	minDataLength = 50
)

// TLSH represents a Trend Micro Locality Sensitive Hash
type TLSH struct {
	Checksum   byte
	LValue     byte
	Q1Ratio    byte
	Q2Ratio    byte
	QRatios    [2]byte
	Buckets    [bucketCount]byte
	DataLength int
}

// New creates a new TLSH hash from a byte slice
func New(data []byte) (*TLSH, error) {
	if len(data) < minDataLength {
		return nil, ErrDataTooSmall
	}

	tlsh := &TLSH{
		DataLength: len(data),
	}

	// Calculate sliding window
	buckets := make([]int, bucketCount)
	for i := 0; i < len(data)-windowSize; i++ {
		window := data[i : i+windowSize]
		triplet := (int(window[0]) << 16) | (int(window[2]) << 8) | int(window[4])
		bucket := triplet % bucketCount
		buckets[bucket]++
	}

	// Calculate quartiles
	sortedBuckets := make([]int, len(buckets))
	copy(sortedBuckets, buckets)
	sort.Ints(sortedBuckets)

	q1Pos := len(sortedBuckets) / 4
	q2Pos := len(sortedBuckets) / 2
	q3Pos := (3 * len(sortedBuckets)) / 4

	q1 := sortedBuckets[q1Pos]
	q2 := sortedBuckets[q2Pos]
	q3 := sortedBuckets[q3Pos]

	// Calculate ratios
	tlsh.Q1Ratio = byte((float64(q1) / float64(q3)) * 16)
	tlsh.Q2Ratio = byte((float64(q2) / float64(q3)) * 16)

	// Calculate final bucket values
	for i := 0; i < bucketCount; i++ {
		if buckets[i] <= q1 {
			tlsh.Buckets[i] = 0
		} else if buckets[i] <= q2 {
			tlsh.Buckets[i] = 1
		} else if buckets[i] <= q3 {
			tlsh.Buckets[i] = 2
		} else {
			tlsh.Buckets[i] = 3
		}
	}

	// Calculate checksum
	h := sha256.New()
	h.Write(data)
	tlsh.Checksum = h.Sum(nil)[0]

	// Calculate L-Value (log base 2 of the file size)
	tlsh.LValue = byte(math.Log2(float64(len(data))))

	return tlsh, nil
}

// Distance calculates the distance between two TLSH hashes
func (t *TLSH) Distance(other *TLSH) int {
	if t == nil || other == nil {
		return -1
	}

	// Calculate L-Value difference
	lDiff := math.Abs(float64(t.LValue - other.LValue))

	// Calculate bucket difference
	bucketDiff := 0
	for i := 0; i < bucketCount; i++ {
		bucketDiff += int(math.Abs(float64(t.Buckets[i] - other.Buckets[i])))
	}

	// Calculate quartile ratio difference
	q1Diff := math.Abs(float64(t.Q1Ratio - other.Q1Ratio))
	q2Diff := math.Abs(float64(t.Q2Ratio - other.Q2Ratio))

	// Weighted sum of differences
	return int(lDiff*12 + float64(bucketDiff) + (q1Diff+q2Diff)*12)
}

// String returns the hex representation of the TLSH hash
func (t *TLSH) String() string {
	if t == nil {
		return ""
	}

	result := make([]byte, bucketCount/2+4)
	result[0] = t.Checksum
	result[1] = t.LValue
	result[2] = t.Q1Ratio
	result[3] = t.Q2Ratio

	// Pack buckets (2 buckets per byte)
	for i := 0; i < bucketCount/2; i++ {
		result[i+4] = (t.Buckets[i*2] << 4) | t.Buckets[i*2+1]
	}

	return hex.EncodeToString(result)
} 