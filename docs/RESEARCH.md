# TT Research: Tools, Libraries & Best Practices

Research findings for building the TypeScript-to-Python Translation Tool (TT).

## Rule Clarification

> **Q**: Is it allowed to use public Python libs which parse JavaScript into AST?
> **A** (Pal de Vibe, organizer): "Yes, if these libraries are fully in Python."

This confirms `tree-sitter` + `tree-sitter-typescript` are allowed (Python bindings to a C library, installed via pip, no Node.js involved).

See [COMPLIANCE.md](./COMPLIANCE.md) for the full compliance audit: licensing (both MIT), runtime evidence (no node/js, no subprocess), per-rule verdicts (Rules 1/5/6/9), and rule-checker impact analysis.

## Parsing: tree-sitter

**tree-sitter is the only viable Python-native TypeScript parser.** Alternatives (pyjsparser, slimit, esprima-python) only handle ES5 JavaScript, not TypeScript syntax (no type annotations, interfaces, enums, etc.).

### Installation

```bash
pip install tree-sitter tree-sitter-typescript
```

- `tree-sitter` (v0.25.2) -- Python bindings to the C library
- `tree-sitter-typescript` (v0.23.2) -- pre-compiled TypeScript/TSX grammars
- Python >=3.9, works fine on 3.11+

### Usage

```python
import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Parser

TS_LANGUAGE = Language(tstypescript.language_typescript())
parser = Parser(TS_LANGUAGE)
source = b'class Foo { bar(x: number): string { return "hi"; } }'
tree = parser.parse(source)
root = tree.root_node
```

### Traversal

```python
# Direct child access
for child in root.children:
    print(child.type, child.text.decode())

# Field-based access (grammar-defined fields like "name", "body", "parameters")
func_node = root.children[0]
name = func_node.child_by_field_name("name")
body = func_node.child_by_field_name("body")

# TreeCursor (efficient for large files)
cursor = tree.walk()
cursor.goto_first_child()
while cursor.goto_next_sibling():
    print(cursor.node.type)
```

### Pattern Matching with Queries

```python
query = TS_LANGUAGE.query("""
  (class_declaration name: (type_identifier) @class.name)
  (import_statement) @import
  (method_definition name: (property_identifier) @method.name
                     body: (statement_block) @method.body)
""")
captures = query.captures(root)
for name, nodes in captures.items():
    for node in nodes:
        print(f"{name}: {node.text.decode()}")
```

### Key TypeScript Node Types

`class_declaration`, `interface_declaration`, `type_alias_declaration`, `enum_declaration`, `import_statement`, `export_statement`, `function_declaration`, `method_definition`, `type_annotation`, `type_parameters`, `property_signature`, `required_parameter`, `optional_parameter`

### Gotchas

- **CST, not AST**: tree-sitter produces a Concrete Syntax Tree (includes every token, comma, semicolon). You must filter out noise yourself.
- **No semantic analysis**: parses syntax only. No type resolution, no symbol table, no understanding of import targets.
- **Encoding**: `parser.parse()` requires `bytes`, not `str`. Always encode with UTF-8.
- **TS vs TSX**: separate grammars. Use `language_typescript()` for `.ts` and `language_tsx()` for `.tsx`.
- **`identifier` vs `type_identifier`**: Enums/variables use `identifier`, interfaces/type aliases use `type_identifier`.

---

## Code Generation Strategy

### Recommended: String Emitter + Black

**Best approach**: Custom `PythonEmitter` class with `emit_class()`, `emit_function()`, `emit_line()` methods managing indentation. This is 3.3x less code than building Python `ast` nodes programmatically.

```python
class PythonEmitter:
    def __init__(self):
        self.lines = []
        self.indent = 0

    def emit_line(self, code: str):
        self.lines.append("    " * self.indent + code)

    def emit_class(self, name, bases, body_fn):
        base_str = f"({', '.join(bases)})" if bases else ""
        self.emit_line(f"class {name}{base_str}:")
        self.indent += 1
        body_fn()
        self.indent -= 1

    def emit_function(self, name, params, body_fn):
        self.emit_line(f"def {name}({', '.join(params)}):")
        self.indent += 1
        body_fn()
        self.indent -= 1

    def get_code(self) -> str:
        return "\n".join(self.lines)
```

Post-process with `black.format_str()` for PEP 8 compliance (~3ms per file).
Validate with `ast.parse()` to catch syntax errors (~0.06ms per file).

### What NOT to use

| Tool | Why not |
|------|---------|
| `astor` | Dead. Broken on Python 3.12+ (uses removed `ast.Str`, `ast.Num`) |
| `libcst` | Overkill for generation from scratch (designed for transforming existing code) |
| Python `ast` module (for building nodes) | Extremely verbose (~3.3x more code), every node needs `ctx=ast.Load()`, `posonlyargs=[]`, etc. |
| `autopep8` | Use `black` instead, it's the industry standard |

---

## Library Mappings

### Big.js -> `decimal.Decimal` (stdlib)

Python's `decimal.Decimal` is the direct equivalent of Big.js for arbitrary-precision decimal arithmetic. No third-party library needed.

| Big.js | Python `decimal.Decimal` | Notes |
|--------|--------------------------|-------|
| `new Big(0)` | `Decimal('0')` | Always pass strings for exact values |
| `new Big(value)` | `Decimal(str(value))` | If value is float, convert to string first |
| `.plus(y)` | `x + y` | Operator overloaded |
| `.minus(y)` | `x - y` | |
| `.times(y)` | `x * y` | |
| `.div(y)` | `x / y` | True division |
| `.eq(y)` | `x == y` | |
| `.gt(y)` / `.lt(y)` | `x > y` / `x < y` | |
| `.gte(y)` / `.lte(y)` | `x >= y` / `x <= y` | |
| `.toNumber()` | `float(x)` | Loses precision (same as big.js) |
| `.toString()` | `str(x)` | |
| `.abs()` | `abs(x)` | Built-in works with Decimal |
| `.round(dp, rm)` | `x.quantize(Decimal('1e-{dp}'), rounding=...)` | See rounding section |
| `.toFixed(dp)` | `format(x, f'.{dp}f')` | Returns string |
| `.sqrt()` | `x.sqrt()` | Method on Decimal |
| `.pow(n)` | `x ** n` | Operator overloaded |
| `.cmp(y)` | `(x > y) - (x < y)` | Returns -1, 0, or 1 |
| Chained: `a.plus(b).times(c)` | `(a + b) * c` | Natural Python operators |

#### Rounding Mode Mapping

| Big.js `RM` | Value | Python equivalent |
|-------------|-------|-------------------|
| `roundDown` | 0 | `ROUND_DOWN` |
| `roundHalfUp` | 1 (default) | `ROUND_HALF_UP` |
| `roundHalfEven` | 2 | `ROUND_HALF_EVEN` (Python default) |
| `roundUp` | 3 | `ROUND_UP` |

**Critical**: Big.js defaults to `ROUND_HALF_UP`. Python Decimal defaults to `ROUND_HALF_EVEN`. To match:

```python
from decimal import getcontext, ROUND_HALF_UP
getcontext().rounding = ROUND_HALF_UP
```

#### Edge Cases

- **Always construct from strings**: `Decimal('0.1')`, never `Decimal(0.1)` (float precision loss)
- **Division by zero**: both raise exceptions by default (matching behavior)
- **NaN**: `Decimal('NaN')` succeeds silently in Python; Big.js throws. Keep `InvalidOperation` trap enabled.
- **Negative zero**: both `Decimal('-0') == Decimal('0')` is `True`, same as Big.js

### date-fns -> `datetime` (stdlib)

No third-party date library needed. Python's stdlib `datetime` covers every date-fns function.

#### Format String Mapping

| date-fns token | Python token | Meaning |
|----------------|-------------|---------|
| `yyyy` | `%Y` | 4-digit year |
| `yy` | `%y` | 2-digit year |
| `MMMM` | `%B` | Full month name |
| `MMM` | `%b` | Abbreviated month name |
| `MM` | `%m` | Zero-padded month (01-12) |
| `dd` | `%d` | Zero-padded day (01-31) |
| `HH` | `%H` | 24-hour hour |
| `mm` | `%M` | Minutes |
| `ss` | `%S` | Seconds |

Constant: `DATE_FORMAT = 'yyyy-MM-dd'` becomes `DATE_FORMAT = '%Y-%m-%d'`

#### Function Mapping

| date-fns | Python | Notes |
|----------|--------|-------|
| `format(d, 'yyyy-MM-dd')` | `d.strftime('%Y-%m-%d')` or `d.isoformat()` | |
| `differenceInDays(a, b)` | `(a - b).days` | Returns int, can be negative |
| `eachDayOfInterval({start, end})` | Generator with `timedelta(days=step)` | See helper below |
| `eachYearOfInterval({start, end})` | `[date(y, 1, 1) for y in range(s.year, e.year + 1)]` | |
| `endOfDay(d)` | `datetime.combine(d.date(), time.max)` | |
| `startOfDay(d)` | `datetime.combine(d.date(), time.min)` | |
| `endOfYear(d)` | `date(d.year, 12, 31)` | |
| `startOfYear(d)` | `date(d.year, 1, 1)` | |
| `isAfter(a, b)` | `a > b` | Direct comparison |
| `isBefore(a, b)` | `a < b` | |
| `isWithinInterval(d, {s, e})` | `s <= d <= e` | |
| `min([dates])` | `min(dates)` | Built-in works on date/datetime |
| `subDays(d, n)` | `d - timedelta(days=n)` | |
| `addMilliseconds(d, n)` | `d + timedelta(milliseconds=n)` | |
| `isThisYear(d)` | `d.year == date.today().year` | |
| `parseISO(str)` | `date.fromisoformat(str)` | Python 3.7+ |
| `subYears(d, n)` | `d - relativedelta(years=n)` | Needs `dateutil` for leap year safety |
| `getMonth(d)` | `d.month` | date-fns is 0-based, Python is 1-based |

#### Helper for `eachDayOfInterval`

```python
from datetime import date, timedelta

def each_day_of_interval(start: date, end: date, step: int = 1) -> list[date]:
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=step)
    return days
```

### lodash -> Python stdlib

No third-party library needed. Stdlib covers most lodash functions directly.

| lodash | Python | Notes |
|--------|--------|-------|
| `sortBy(arr, fn)` | `sorted(arr, key=fn)` | Returns new list |
| `cloneDeep(obj)` | `copy.deepcopy(obj)` | `import copy` |
| `isNumber(v)` | `isinstance(v, (int, float))` | Includes NaN, Infinity |
| `sum(arr)` | `sum(arr)` | Built-in |
| `first(arr)` | `arr[0]` or `arr[0] if arr else None` | |
| `last(arr)` | `arr[-1]` | Python supports negative indexing |
| `isEmpty(v)` | `not v` | Covers `[]`, `{}`, `""`, `None`, `0` |

#### Helpers Needed (3 functions)

```python
def uniq_by(array, key_fn):
    """Lodash uniqBy: deduplicate by key function."""
    seen = set()
    result = []
    for item in array:
        k = key_fn(item)
        if k not in seen:
            seen.add(k)
            result.append(item)
    return result

def group_by(array, key_fn):
    """Lodash groupBy: group all elements by key (NOT itertools.groupby!)."""
    from collections import defaultdict
    result = defaultdict(list)
    for item in array:
        result[key_fn(item)].append(item)
    return dict(result)

def deep_merge(base, *updates):
    """Lodash merge: recursive deep merge of dicts."""
    import copy
    result = copy.deepcopy(base)
    for update in updates:
        for key, value in update.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
    return result
```

#### CRITICAL: `itertools.groupby` is NOT lodash `groupBy`

`itertools.groupby` only groups **consecutive** elements with the same key (like Unix `uniq`). If input is `[A, B, A]`, you get three groups `[A], [B], [A]`, not two. lodash `groupBy` scans the entire array. **Always use the `defaultdict(list)` pattern above.**

### Type Mapping

```python
TS_TO_PY_TYPE_MAP = {
    "string": "str",
    "number": "float",
    "boolean": "bool",
    "any": "Any",
    "void": "None",
    "null": "None",
    "undefined": "None",
    "object": "dict",
    "Array": "list",
    "Record": "dict",
    "Map": "dict",
    "Set": "set",
    "Promise": "Awaitable",
    "Date": "datetime",
}
```

---

## Prior Art

### Most Relevant Projects

1. **ccxt/ast-transpiler** (70 stars, https://github.com/ccxt/ast-transpiler)
   - Financial domain TS-to-Python transpiler, battle-tested by CCXT (41k-star crypto exchange library)
   - Uses override maps for method replacements: `FullPropertyAccessReplacements` (e.g., `JSON.parse` -> `json.loads`), `LeftPropertyAccessReplacements` (`this` -> `self`), `RightPropertyAccessReplacements` (`toUpperCase` -> `upper`), `CallExpressionReplacements` (`parseInt` -> `float`)
   - Does NOT handle imports/exports (returns them separately)
   - Study `pythonTranspiler.ts` (14.6KB) and `baseTranspiler.ts` (82.6KB)
   - Supports snake_casing identifiers automatically

2. **py2many** (https://github.com/py2many/py2many)
   - Python AST visitor pattern transpiler (Python to 10+ languages)
   - Gold standard architecture: `DeclarationExtractor` + visitor pattern
   - `_type_map` (primitives) + `_container_type_map` (generics) split
   - Each language transpiler overrides `visit_ClassDef()`, `visit_FunctionDef()`, etc.

3. **DuoGlot** (NUS, OOPSLA 2023, https://github.com/HALOCORE/DuoGlot)
   - Tree-sitter-based transpiler with learnable translation rules
   - 90% accuracy with just 142 rules
   - Uses tree-edit distance for matching patterns between source and target ASTs

4. **jecki/ts2python** (pip: `ts2python`, https://github.com/jecki/ts2python)
   - PEG-based parser, Python-native
   - Only handles interfaces/types, not executable code
   - Author admits skipping the IR step was a design mistake

5. **harshkedia177/axon** (https://github.com/harshkedia177/axon)
   - Tree-sitter TS parser extracting symbols into structured dataclasses
   - Good model for intermediate representation: `SymbolInfo(name, kind, start_line, ...)`, `ImportInfo(module, names, is_relative)`, `TypeRef`, `CallInfo`

### No Existing Ghostfolio Python Port

No one has done a direct TypeScript-to-Python translation of Ghostfolio's codebase.

---

## Recommended Architecture

```
TS Source -> tree-sitter parse -> CST walk -> Python string emission -> black format -> output
```

### Priority Order for Transforms (by test-pass-rate impact)

1. **Class declarations**, `this` -> `self`, constructors -> `__init__`
2. **Big.js -> Decimal** (core financial calculations)
3. Method definitions with type annotations
4. Variable declarations (`const`/`let`/`var` -> bare assignment)
5. Import mapping (via `tt_import_map.json`)
6. date-fns -> datetime
7. lodash -> stdlib
8. Control flow (if/else, for loops, switch -> if/elif)
9. Array/Object methods (`.push()` -> `.append()`, `.filter()` -> list comprehension)
10. Enum declarations -> Python `Enum`

### Key Dependencies

```
tree-sitter           # TS parsing
tree-sitter-typescript # TS grammar
black                 # Code formatting
```

Python stdlib provides everything else (decimal, datetime, copy, collections).
