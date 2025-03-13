package main

import (
	"log"

	"github.com/re-centris/re-centris-go/internal/cmd"
)

func main() {
	if err := cmd.Execute(); err != nil {
		log.Fatal(err)
	}
} 