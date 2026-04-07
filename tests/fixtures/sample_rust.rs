//! Sample Rust source for testing the rust extractor.

use std::collections::HashMap;

/// A simple calculator struct.
struct Calculator {
    value: f64,
}

impl Calculator {
    /// Creates a new calculator with initial value.
    fn new(initial: f64) -> Self {
        Calculator { value: initial }
    }

    /// Adds a number to the current value.
    fn add(&mut self, n: f64) -> f64 {
        self.value += n;
        self.value
    }

    /// Subtracts a number from the current value.
    fn subtract(&mut self, n: f64) -> f64 {
        self.value -= n;
        self.value
    }
}

/// Represents the status of an operation.
enum Status {
    Ok,
    Err(String),
    Pending,
}

/// Represents a paginated response.
enum Page<T> {
    Single(T),
    Multi { items: Vec<T>, total: usize },
    Empty,
}

/// A user entity.
struct User {
    id: u64,
    name: String,
    email: String,
}

/// Application state.
struct AppState {
    users: HashMap<u64, User>,
    version: String,
}

impl AppState {
    fn new() -> Self {
        AppState {
            users: HashMap::new(),
            version: String::from("1.0.0"),
        }
    }

    fn add_user(&mut self, user: User) {
        self.users.insert(user.id, user);
    }

    fn get_user(&self, id: u64) -> Option<&User> {
        self.users.get(&id)
    }
}

/// Adds two numbers.
fn add(a: i32, b: i32) -> i32 {
    a + b
}

/// Multiplies two numbers.
async fn multiply(a: i32, b: i32) -> i32 {
    a * b
}

/// Divides two numbers, returning an Option to handle division by zero.
fn divide(a: f64, b: f64) -> Option<f64> {
    if b == 0.0 {
        None
    } else {
        Some(a / b)
    }
}

/// Returns a greeting for the given name.
fn greet(name: &str) -> String {
    format!("Hello, {}!", name)
}

/// Processes a batch of items.
fn process_batch<T>(items: Vec<T>, handler: fn(T) -> T) -> Vec<T> {
    items.into_iter().map(handler).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_add() {
        assert_eq!(add(2, 3), 5);
    }

    #[test]
    fn test_divide_ok() {
        assert_eq!(divide(10.0, 2.0), Some(5.0));
    }

    #[test]
    fn test_divide_by_zero() {
        assert_eq!(divide(10.0, 0.0), None);
    }
}
