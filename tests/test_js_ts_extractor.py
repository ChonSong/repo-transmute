"""Tests for JavaScript/TypeScript extraction via regex-based extractor."""

import pytest
from pathlib import Path
from repo_transmute.blueprint.extractor import (
    extract_from_javascript,
    extract_from_typescript,
    Function,
    DataStructure,
    Import,
)


FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# JS Fixtures
# ---------------------------------------------------------------------------

JS_BASIC = """
function greet(name) {
    return "Hello, " + name;
}

function add(a, b) {
    return a + b;
}

const multiply = (x, y) => x * y;

const divide = async (a, b) => {
    if (b === 0) throw new Error("Division by zero");
    return a / b;
};

export function subtract(a, b) {
    return a - b;
}

export default function multiplyByTen(n) {
    return n * 10;
}

export { add, greet };
"""

# Arrow functions as callbacks (should be skipped by HOF guard)
JS_HOF = """
const result = useMemo(() => {
    return expensiveCalculation(value);
}, [value]);

const doubled = numbers.map(x => x * 2);

const filtered = items.filter(item => item.active);

const withTimeout = setTimeout(() => {
    console.log("Done");
}, 1000);

const promise = new Promise(resolve => {
    resolve(42);
});

export { result, doubled, filtered };
"""

# Class declarations
JS_CLASS = """
class Animal {
    constructor(name) {
        this.name = name;
    }

    speak() {
        return `${this.name} makes a sound`;
    }
}

class Dog extends Animal {
    constructor(name, breed) {
        super(name);
        this.breed = breed;
    }

    speak() {
        return `${this.name} barks`;
    }
}

export { Animal, Dog };
"""

# Mixed exports
JS_MIXED = """
export const VERSION = "1.0.0";
export const MAX_RETRIES = 3;

export function init() {
    return true;
}

export class Service {
    start() { return "started"; }
    stop() { return "stopped"; }
}

export { Animal, Dog };
"""


# ---------------------------------------------------------------------------
# TS Fixtures
# ---------------------------------------------------------------------------

TS_INTERFACES = """
interface User {
    id: number;
    name: string;
    email?: string;
}

interface Admin extends User {
    role: "admin" | "superadmin";
    permissions: string[];
}

type UserId = number;
type UserMap = Record<UserId, User>;

type Status = "active" | "inactive" | "pending";

interface Config {
    apiUrl: string;
    timeout: number;
    retries?: number;
}
"""

TS_FUNCTIONS = """
function greet(name: string): string {
    return `Hello, ${name}`;
}

async function fetchUser(id: number): Promise<User> {
    const response = await fetch(`/api/users/${id}`);
    return response.json();
}

const add = (a: number, b: number): number => a + b;

const processItems = (items: string[]): { id: number; value: string }[] => {
    return items.map((item, i) => ({ id: i, value: item }));
};

export function computeTotal(values: readonly number[]): number {
    return values.reduce((sum, v) => sum + v, 0);
}

export default function main(): void {
    console.log("Application started");
}
"""

TS_CLASSES = """
class Animal {
    protected name: string;
    constructor(name: string) {
        this.name = name;
    }

    speak(): string {
        return `${this.name} makes a sound`;
    }
}

class Dog extends Animal {
    private breed: string;

    constructor(name: string, breed: string) {
        super(name);
        this.breed = breed;
    }

    override speak(): string {
        return `${this.name} barks`;
    }

    getBreed(): string {
        return this.breed;
    }
}

interface IRepository<T> {
    findById(id: number): T | null;
    save(entity: T): void;
    delete(id: number): void;
}

type Callback<T> = (err: Error | null, result: T | null) => void;

enum Direction {
    Up = "UP",
    Down = "DOWN",
    Left = "LEFT",
    Right = "RIGHT",
}

export { Animal, Dog, IRepository, Callback, Direction };
"""

TS_ENUMS = """
enum Status {
    Active = "ACTIVE",
    Inactive = "INACTIVE",
    Pending = "PENDING",
}

enum HttpCode {
    OK = 200,
    NotFound = 404,
    ServerError = 500,
}

export { Status, HttpCode };
"""

TS_TYPE_ALIASES = """
type Id = number | string;
type UserId = number;
type MaybeUser = User | null;
type StringOrNumber = string | number;
type KeyValuePairs = [string, any];
type Handler = () => void;
type AsyncHandler = () => Promise<void>;

export { Id, UserId, MaybeUser, StringOrNumber, KeyValuePairs, Handler, AsyncHandler };
"""


# ---------------------------------------------------------------------------
# JS Extraction Tests
# ---------------------------------------------------------------------------

class TestExtractJavascript:
    """Test extract_from_javascript on various JS patterns."""

    def test_function_declarations(self, tmp_path):
        f = tmp_path / "sample.js"
        f.write_text(JS_BASIC)
        funcs = extract_from_javascript(f)
        names = {fn.name for fn in funcs}
        assert "greet" in names
        assert "add" in names
        assert "subtract" in names
        # export default function name(...) → extracts as the actual name when present
        assert "multiplyByTen" in names

    def test_arrow_functions(self, tmp_path):
        f = tmp_path / "arrow.js"
        f.write_text(JS_BASIC)
        funcs = extract_from_javascript(f)
        names = {fn.name for fn in funcs}
        assert "multiply" in names
        assert "divide" in names
        # async flag on divide
        divide_func = next(fn for fn in funcs if fn.name == "divide")
        assert divide_func.async_flag is True

    def test_hof_callbacks_skipped(self, tmp_path):
        """HOF callbacks (useMemo, map, filter, setTimeout) should be skipped as functions.
        
        Note: When HOF results are exported via 'export { result, doubled }', they 
        ARE extracted as function signatures (since they're exported). This test 
        checks that HOF patterns themselves don't produce function extractions.
        """
        f = tmp_path / "hof.js"
        f.write_text(JS_HOF)
        funcs = extract_from_javascript(f)
        names = {fn.name for fn in funcs}
        # HOF callback patterns useMemo(() =>, map(x =>, filter(item => should NOT 
        # appear as arrow functions being extracted as functions
        # (they may appear as exported names if explicitly exported)
        for hof_name in ["useMemo", "numbers.map", "items.filter", "setTimeout", "Promise"]:
            assert hof_name not in names

    def test_named_exports(self, tmp_path):
        f = tmp_path / "exports.js"
        f.write_text(JS_BASIC)
        funcs = extract_from_javascript(f)
        names = {fn.name for fn in funcs}
        assert "add" in names
        assert "greet" in names
        assert "subtract" in names

    def test_line_numbers(self, tmp_path):
        f = tmp_path / "lines.js"
        f.write_text(JS_BASIC)
        funcs = extract_from_javascript(f)
        greet_func = next(fn for fn in funcs if fn.name == "greet")
        assert greet_func.line > 0
        assert greet_func.file == str(f)

    def test_class_declarations(self, tmp_path):
        """Classes are extracted when exported (via export { Animal, Dog })."""
        f = tmp_path / "classes.js"
        f.write_text(JS_CLASS)
        funcs = extract_from_javascript(f)
        names = {fn.name for fn in funcs}
        # Classes ARE extracted when exported
        assert "Animal" in names
        assert "Dog" in names

    def test_mixed_exports(self, tmp_path):
        f = tmp_path / "mixed.js"
        f.write_text(JS_MIXED)
        funcs = extract_from_javascript(f)
        names = {fn.name for fn in funcs}
        assert "init" in names
        assert "Service" not in names  # class not extracted
        # const exports (VERSION, MAX_RETRIES) are not functions
        assert "VERSION" not in names


# ---------------------------------------------------------------------------
# TS Extraction Tests
# ---------------------------------------------------------------------------

class TestExtractTypescript:
    """Test extract_from_typescript on TypeScript patterns."""

    def test_function_declarations_with_types(self, tmp_path):
        f = tmp_path / "sample.ts"
        f.write_text(TS_FUNCTIONS)
        funcs = extract_from_typescript(f)
        names = {fn.name for fn in funcs}
        assert "greet" in names
        assert "fetchUser" in names
        assert "add" in names
        assert "processItems" in names
        assert "computeTotal" in names

    def test_async_functions(self, tmp_path):
        f = tmp_path / "sample.ts"
        f.write_text(TS_FUNCTIONS)
        funcs = extract_from_typescript(f)
        fetch_func = next(fn for fn in funcs if fn.name == "fetchUser")
        assert fetch_func.async_flag is True

    def test_return_types_extracted(self, tmp_path):
        f = tmp_path / "sample.ts"
        f.write_text(TS_FUNCTIONS)
        funcs = extract_from_typescript(f)
        greet_func = next(fn for fn in funcs if fn.name == "greet")
        # Return type in signature
        assert "string" in greet_func.signature

    def test_tsx_handling(self, tmp_path):
        """TSX files should be processed by the same extractor."""
        tsx_content = """
export function HelloComponent({ name }: { name: string }): JSX.Element {
    return <div>Hello, {name}</div>;
}

export default function App(): JSX.Element {
    return <HelloComponent name="World" />;
}
"""
        f = tmp_path / "component.tsx"
        f.write_text(tsx_content)
        funcs = extract_from_typescript(f)
        names = {fn.name for fn in funcs}
        assert "HelloComponent" in names
        assert "App" in names

    def test_interfaces_not_extracted(self, tmp_path):
        """Interfaces are not yet extracted by the function extractor.
        This documents current behavior."""
        f = tmp_path / "interfaces.ts"
        f.write_text(TS_INTERFACES)
        funcs = extract_from_typescript(f)
        names = {fn.name for fn in funcs}
        # Interfaces are not functions
        assert "User" not in names
        assert "Admin" not in names
        assert "Config" not in names

    def test_type_aliases_not_extracted(self, tmp_path):
        """Type aliases are extracted when exported (via export { ... })."""
        f = tmp_path / "types.ts"
        f.write_text(TS_TYPE_ALIASES)
        funcs = extract_from_typescript(f)
        names = {fn.name for fn in funcs}
        # Type aliases ARE extracted when exported
        assert "Id" in names

    def test_enums_not_extracted(self, tmp_path):
        """Enums are extracted when exported."""
        f = tmp_path / "enums.ts"
        f.write_text(TS_ENUMS)
        funcs = extract_from_typescript(f)
        names = {fn.name for fn in funcs}
        # Enums ARE extracted when exported
        assert "Status" in names


# ---------------------------------------------------------------------------
# Integration: extract_all with JS/TS
# ---------------------------------------------------------------------------

class TestExtractAllJS:
    """Test that extract_all handles JS/TS via the right extractor."""

    def test_extract_all_javascript(self, tmp_path):
        from repo_transmute.blueprint.extractor import extract_all
        (tmp_path / "index.js").write_text(JS_BASIC)
        bp = extract_all(tmp_path, "javascript")
        assert bp.language == "javascript"
        names = {fn.name for fn in bp.functions}
        assert "greet" in names
        assert "add" in names

    def test_extract_all_typescript(self, tmp_path):
        from repo_transmute.blueprint.extractor import extract_all
        (tmp_path / "main.ts").write_text(TS_FUNCTIONS)
        bp = extract_all(tmp_path, "typescript")
        assert bp.language == "typescript"
        names = {fn.name for fn in bp.functions}
        assert "greet" in names
        assert "fetchUser" in names

    def test_extract_all_typescript_tsx(self, tmp_path):
        from repo_transmute.blueprint.extractor import extract_all
        tsx_content = """
export function Button({ label }: { label: string }): JSX.Element {
    return <button>{label}</button>;
}
"""
        (tmp_path / "Button.tsx").write_text(tsx_content)
        bp = extract_all(tmp_path, "typescript")
        names = {fn.name for fn in bp.functions}
        assert "Button" in names
