// Package fixtures is a test package for RepoTransmute Go extraction.
package fixtures

import (
	"fmt"
	"io"
	"os"
)

// Add returns the sum of two integers.
func Add(a, b int) int {
	return a + b
}

// Greet formats a greeting message.
func Greet(name string) string {
	return fmt.Sprintf("Hello, %s", name)
}

// ProcessWithCallback applies fn to each item in items.
func ProcessWithCallback(items []int, fn func(int) int) []int {
	result := make([]int, len(items))
	for i, v := range items {
		result[i] = fn(v)
	}
	return result
}

// Person represents a human being with a name and age.
type Person struct {
	Name string
	Age  int
}

// Animal represents an animal with a species and name.
type Animal struct {
	Species string `json:"species"`
	Name    string
}

// Reader is an interface for reading bytes.
type Reader interface {
	Read(p []byte) (n int, err error)
}

// Writer is an interface for writing bytes.
type Writer interface {
	Write(p []byte) (n int, err error)
}

// ReadWriter combines Reader and Writer interfaces.
type ReadWriter interface {
	Reader
	Writer
}

// Greet is a method on Person — belongs to a struct.
func (p *Person) Greet() string {
	return fmt.Sprintf("Hi, I'm %s", p.Name)
}

// Sum sums all the numbers.
func (p *Person) Sum(nums []int) int {
	total := 0
	for _, n := range nums {
		total += n
	}
	return total
}

// Config holds configuration with nested struct.
type Config struct {
	Host string
	Port int
	DB   struct {
		User     string
		Password string
		Name     string
	}
}

// EmptyStruct is a struct with no fields.
type EmptyStruct struct {
}

// WithDefaults initializes with sensible defaults.
func WithDefaults() *Config {
	return &Config{
		Host: "localhost",
		Port: 8080,
	}
}

// LongMethod is a method with a very long body that spans multiple
// lines and has nested control structures.
func (c *Config) LongMethod(input []string) error {
	for _, s := range input {
		if s == "error" {
			return io.ErrUnexpectedEOF
		}
		for i := 0; i < len(s); i++ {
			if s[i] == '!' {
				fmt.Println("Found!")
			}
		}
	}
	fmt.Println("Processed", len(input), "items")
	return nil
}

// StringWithBraces returns a string that contains { and } characters.
func StringWithBraces() string {
	return "{hello} and {world}"
}

// MultiLineString is a raw string with special chars.
func MultiLineString() string {
	return `{"key": "value", "nested": {"a": 1, "b": 2}}`
}
