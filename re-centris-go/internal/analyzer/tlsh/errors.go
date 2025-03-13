package tlsh

import "errors"

var (
	// ErrDataTooSmall is returned when input data is too small for TLSH calculation
	ErrDataTooSmall = errors.New("input data must be at least 50 bytes")

	// ErrInvalidHash is returned when trying to parse an invalid TLSH hash string
	ErrInvalidHash = errors.New("invalid TLSH hash format")

	// ErrNilHash is returned when trying to operate on a nil TLSH hash
	ErrNilHash = errors.New("nil TLSH hash")
) 