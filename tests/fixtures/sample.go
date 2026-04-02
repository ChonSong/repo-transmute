// Package fixtures is a test package for RepoTransmute Go extraction.
package fixtures

import "fmt"

// Add returns the sum of two integers.
func Add(a, b int) int {
	return a + b
}

// Greet formats a greeting message.
func Greet(name string) string {
	return fmt.Sprintf("Hello, %s", name)
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

// method on Person — belongs to a struct
func (p *Person) Greet() string {
	return fmt.Sprintf("Hi, I'm %s", p.Name)
}

// Sum adds up all the numbers in the slice.
func (p *Person) Sum(nums []int) int {
	sum := 0
	for _, n := range nums {
		sum += n
	}
	return sum
}
