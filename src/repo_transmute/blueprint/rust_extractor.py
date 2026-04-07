"""Rust source code extractor using tree-sitter."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import tree_sitter
from tree_sitter import Parser, Language
from tree_sitter_rust import language as rust_lang_module

from repo_transmute.blueprint.extractor import Function, DataStructure, Import


# Lazy-load the Rust language
_rust_language: Optional[Language] = None


def _get_rust_language() -> Language:
    """Get or initialize the Rust language parser."""
    global _rust_language
    if _rust_language is None:
        _rust_language = Language(rust_lang_module())
    return _rust_language


def _get_parser() -> Parser:
    """Get a tree-sitter parser configured for Rust."""
    parser = Parser()
    parser.language = _get_rust_language()
    return parser


def _parse_rust_file(file_path: Path) -> tree_sitter.Tree:
    """Parse a Rust file and return the tree."""
    content = file_path.read_text()
    parser = _get_parser()
    return parser.parse(bytes(content, "utf8"))


def _node_text(node: tree_sitter.Node, source: bytes) -> str:
    """Extract text from a node as a string."""
    return node.text.decode("utf8") if node.text else ""


def _find_child_by_type(node: tree_sitter.Node, child_type: str) -> Optional[tree_sitter.Node]:
    """Find first child of a given type."""
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _find_children_by_type(node: tree_sitter.Node, child_type: str) -> List[tree_sitter.Node]:
    """Find all children of a given type."""
    return [child for child in node.children if child.type == child_type]


def _is_inside_mod_item(node: tree_sitter.Node, root: tree_sitter.Node, source: bytes) -> bool:
    """Check if a node is nested inside a mod_item (inline module).

    Used to skip test functions and other items inside ``mod tests { ... }``.
    """
    # Walk up the tree by tracking (node, parent, child_index) stack
    # We need to know parent to determine if node is a direct child at each level
    stack: List[tree_sitter.Node] = [root]
    index_stack: List[int] = [0]

    while stack:
        current = stack[-1]

        # Check if we reached the target node
        if current is node:
            # Look at ancestors: if any ancestor (not the node itself) is a mod_item,
            # we're inside a module
            # We need to check if any ancestor other than root is a mod_item
            for anc in stack[1:]:  # skip root in stack
                if anc.type == "mod_item":
                    return True
            return False

        # Find next child to visit
        child_idx = index_stack[-1]
        if child_idx < len(current.children):
            child = current.children[child_idx]
            index_stack[-1] += 1
            stack.append(child)
            index_stack.append(0)
        else:
            stack.pop()
            index_stack.pop()

    return False


def _walk_tree_with_parent(
    root: tree_sitter.Node,
    source: bytes,
    callback: callable,
    skip_mod_items: bool = True,
) -> None:
    """Iteratively walk the tree, calling callback(node, parent, siblings_before) for each node.

    ``siblings_before`` is a list of nodes that appear before this node in the parent's
    children list. This allows callers to look at preceding sibling nodes (e.g., doc
    comments that precede a struct or function).

    Skips content inside ``mod_item`` nodes when skip_mod_items=True (filters out
    items inside inline test modules).
    """
    # Stack entries: (node, parent, child_index, skip_this_subtree, siblings_before)
    # siblings_before is a list of (index, sibling_node) for siblings before the current node
    stack: List[tuple] = [(root, None, 0, False, [])]

    while stack:
        node, parent, child_idx, skip_subtree, siblings_before = stack.pop()

        if skip_subtree:
            continue

        # If we're inside a mod_item, skip function_item and test modules
        if skip_mod_items and node.type == "mod_item":
            # Visit children to find nested mod_items, but mark them as skippable
            for i in range(len(node.children) - 1, -1, -1):
                child = node.children[i]
                stack.append((child, node, 0, True, []))
            continue

        callback(node, parent, siblings_before)

        # Build new siblings_before list for children
        # We need to pass all siblings of the current node's children
        # For each child, siblings_before includes: all previous siblings of the child
        # PLUS the current node (as a "sibling" at the parent level)
        # Actually, simpler: just pass the parent's children as siblings_before to the child
        child_siblings = list(node.children)  # shallow copy

        # Push children in reverse order (so we process them in order)
        for i in range(len(node.children) - 1, -1, -1):
            child = node.children[i]
            # siblings_before for this child = all parent's children before this child
            child_siblings_before = node.children[:i]
            stack.append((child, node, 0, False, child_siblings_before))


def _extract_docstring(node: tree_sitter.Node, source: bytes) -> Optional[str]:
    """Extract doc comments preceding an item."""
    # Look for outer_attributes with doc comments (/// or /**)
    doc_parts = []
    for child in node.children:
        if child.type == "outer_attributes":
            for attr_child in child.children:
                if attr_child.type == "attribute_item":
                    for attr in attr_child.children:
                        if attr.type == "doc_comment":
                            text = _node_text(attr, source)
                            # Strip leading /// or /**
                            text = re.sub(r'^/+ ?', '', text)
                            doc_parts.append(text)
    return "\n".join(doc_parts) if doc_parts else None


def _extract_type(source: bytes, node: tree_sitter.Node) -> str:
    """Extract type from a type node and its children."""
    if not node:
        return ""

    node_type = node.type

    # Handle primitive types
    if node_type == "primitive_type":
        return _node_text(node, source)

    # Handle reference types: &str, &mut T
    if node_type == "reference_type":
        parts = []
        for child in node.children:
            if child.type == "mutable_specifier":
                parts.append("mut")
            else:
                parts.append(_extract_type(source, child))
        return "&" + " ".join(parts)

    # Handle generic types: Result<T, E>
    if node_type == "generic_type":
        for child in node.children:
            if child.type == "type_identifier":
                return _node_text(child, source)
            elif child.type == "generic_arguments":
                args = _extract_type(source, child)
                return f"$<{args}>"
        return _node_text(node, source)

    # Handle tuple types: (i32, String)
    if node_type == "tuple_type":
        types = []
        for child in node.children:
            if child.type not in ("(", ")", ","):
                types.append(_extract_type(source, child))
        return f"({', '.join(types)})"

    # Handle array types: [i32]
    if node_type == "array_type":
        return "[]"

    # Handle self type
    if node_type == "self":
        return "Self"

    # Handle path types: crate::Module::Type
    if node_type == "path_type":
        parts = []
        for child in node.children:
            if child.type == "path_segment":
                for seg_child in child.children:
                    if seg_child.type == "type_identifier":
                        parts.append(_node_text(seg_child, source))
        return "::".join(parts)

    # Handle annotated types
    if node_type == "annotated_type":
        inner = _find_child_by_type(node, "type")
        if inner:
            return _extract_type(source, inner)

    # Default: just get the text
    return _node_text(node, source)


def _extract_params(source: bytes, params_node: tree_sitter.Node) -> str:
    """Extract parameter list from a parameters node."""
    if not params_node:
        return ""

    param_list = []

    for child in params_node.children:
        if child.type == "parameter":
            parts = []

            for param_child in child.children:
                if param_child.type == "identifier":
                    parts.append(_node_text(param_child, source))
                elif param_child.type == "::":
                    # Rust label separator — add colon if last part was an identifier
                    if parts and parts[-1][-1].isidentifier():
                        parts[-1] += ":"
                elif param_child.type == "mutable_specifier":
                    parts[-1] = "mut " + parts[-1] if parts else "mut"
                elif param_child.type == "type":
                    type_str = _extract_type(source, param_child)
                    if type_str:
                        # Ensure colon prefix if last part is identifier-like
                        if parts and parts[-1][-1].isidentifier():
                            parts[-1] += ": "
                        parts.append(type_str)
                elif param_child.type == "function_type":
                    # fn(T) -> T as a parameter type
                    if parts and parts[-1][-1] == ":":
                        parts[-1] += _node_text(param_child, source)
                    else:
                        parts.append(_node_text(param_child, source))
                elif param_child.type == "generic_type":
                    # Bare generic type as parameter (e.g., T in Vec<T>)
                    if parts and parts[-1][-1] == ":":
                        parts[-1] += _node_text(param_child, source)
                    else:
                        parts.append(_node_text(param_child, source))

            if parts:
                param_list.append("".join(parts))
        elif child.type == "self_parameter":
            param_list.append("self")
        elif child.type == "type":
            # Anonymous type node (e.g., T in fn(T) -> T)
            type_str = _extract_type(source, child)
            if type_str:
                param_list.append(type_str)

    return ", ".join(param_list)


def _extract_function(source: bytes, node: tree_sitter.Node, file_path: Path) -> Function:
    """Extract function details from a function_item node."""
    name = ""
    params = ""
    return_type = ""
    docstring = None
    async_flag = False
    decorators = []
    body = ""
    start_line = node.start_point.row + 1
    end_line = node.end_point.row + 1

    for child in node.children:
        child_type = child.type

        if child_type == "identifier":
            name = _node_text(child, source)
        elif child_type == "parameters":
            params = _extract_params(source, child)
        elif child_type == "return_type":
            # return_type node contains: -> token, then the type node
            # The type node may be primitive_type, generic_type, etc. (not "type")
            for rc in child.children:
                if rc.type not in ("->",):
                    return_type = _extract_type(source, rc)
                    break
        elif child_type in ("primitive_type", "type_identifier", "generic_type",
                           "reference_type", "tuple_type", "array_type",
                           "annotated_type", "path_type"):
            # Direct return type child (no return_type wrapper node)
            # Only capture if we haven't found return_type yet
            if not return_type:
                return_type = _extract_type(source, child)
        elif child_type == "attribute_item":
            attr_text = _node_text(child, source)
            if attr_text:
                decorators.append(attr_text.strip())
        elif child_type == "outer_attributes":
            docstring = _extract_docstring(child, source)
        elif child_type == "function_modifiers":
            # Handle async fn (async keyword may be wrapped in function_modifiers node)
            for mod_child in child.children:
                if mod_child.type == "async":
                    async_flag = True
        elif child_type == "async":
            async_flag = True
        elif child_type == "block":
            body = _node_text(child, source)

    # Handle generic type parameters (e.g., fn process_batch<T>)
    type_params_str = ""
    for child in node.children:
        if child.type == "type_parameters":
            type_params_str = _node_text(child, source)
            break

    signature = f"({params})"
    if type_params_str:
        signature = f"{type_params_str} {signature}"
    if return_type:
        signature += f" -> {return_type}"

    return Function(
        name=name,
        signature=signature,
        file=str(file_path),
        line=start_line,
        end_line=end_line,
        docstring=docstring,
        async_flag=async_flag,
        decorators=decorators,
        body=body
    )


def _extract_struct(source: bytes, node: tree_sitter.Node, file_path: Path, siblings_before: list = None) -> DataStructure:
    """Extract struct details from a struct_item node.

    Args:
        siblings_before: List of sibling nodes that appear before this struct_item
                        in its parent's children. Used to find preceding doc comments.
    """
    name = ""
    fields = []
    methods = []
    docstring = None
    start_line = node.start_point.row + 1
    end_line = node.end_point.row + 1

    for child in node.children:
        child_type = child.type

        if child_type == "type_identifier":
            name = _node_text(child, source)
        elif child_type == "field_declaration_list":
            for field_child in child.children:
                if field_child.type == "field_declaration":
                    field_parts = []
                    for fc in field_child.children:
                        if fc.type == "field_identifier":
                            field_parts.append(_node_text(fc, source))
                        elif fc.type == "type":
                            field_parts.append(f": {_extract_type(source, fc)}")
                        elif fc.type == "mutable_specifier":
                            field_parts.insert(0, "mut ")
                    if field_parts:
                        fields.append("".join(field_parts))
        elif child_type == "function_item":
            methods.append(_extract_function(source, child, file_path))
        elif child_type == "outer_attributes":
            docstring = _extract_docstring(child, source)

    # Look for doc comments in preceding siblings if no docstring found yet
    if not docstring and siblings_before:
        doc_lines = []
        for sib in reversed(siblings_before):
            sib_text = _node_text(sib, source).strip()
            if sib.type == "line_comment":
                # Strip leading /// or //!
                comment_text = re.sub(r'^/+/?\s?', '', sib_text).strip()
                doc_lines.append(comment_text)
            elif sib.type == "block_comment":
                comment_text = re.sub(r'^/\*\*\s?', '', sib_text).strip()
                comment_text = re.sub(r'\*/$', '', comment_text).strip()
                doc_lines.append(comment_text)
            elif sib.type in ("empty", "linebreak", "whitespace"):
                continue
            else:
                break
        if doc_lines:
            docstring = "\n".join(reversed(doc_lines))

    return DataStructure(
        name=name,
        type="struct",
        file=str(file_path),
        line=start_line,
        end_line=end_line,
        fields=fields,
        docstring=docstring,
        methods=methods
    )


def _extract_enum(source: bytes, node: tree_sitter.Node, file_path: Path) -> DataStructure:
    """Extract enum details from an enum_item node."""
    name = ""
    variants = []
    docstring = None
    start_line = node.start_point.row + 1
    end_line = node.end_point.row + 1

    def _extract_variant(variant_node: tree_sitter.Node) -> Optional[str]:
        """Extract a single enum variant, returning its string representation."""
        variant_parts = []
        for vc in variant_node.children:
            if vc.type == "identifier":
                variant_parts.append(_node_text(vc, source))
            elif vc.type == "tuple_variant_fields":
                types = []
                for tf in vc.children:
                    if tf.type == "type":
                        types.append(_extract_type(source, tf))
                if types:
                    variant_parts[-1] += f"({', '.join(types)})"
            elif vc.type == "field_declaration_list":
                field_parts = []
                for fc in vc.children:
                    if fc.type == "field_declaration":
                        for f in fc.children:
                            if f.type == "field_identifier":
                                field_parts.append(_node_text(f, source))
                            elif f.type == "type":
                                field_parts[-1] += f": {_extract_type(source, f)}"
                if field_parts:
                    variant_parts[-1] += f" {{ {', '.join(field_parts)} }}"
        return "".join(variant_parts) if variant_parts else None

    for child in node.children:
        child_type = child.type

        if child_type == "type_identifier":
            name = _node_text(child, source)
        elif child_type == "variant":
            v = _extract_variant(child)
            if v:
                variants.append(v)
        elif child_type in ("enum_variant_list", "declaration_list"):
            # Rust tree-sitter uses enum_variant_list for enum variants
            for variant_child in child.children:
                if variant_child.type in ("variant", "enum_variant"):
                    v = _extract_variant(variant_child)
                    if v:
                        variants.append(v)
        elif child_type == "outer_attributes":
            docstring = _extract_docstring(child, source)

    return DataStructure(
        name=name,
        type="enum",
        file=str(file_path),
        line=start_line,
        end_line=end_line,
        fields=variants,
        docstring=docstring
    )


def _extract_impl(source: bytes, node: tree_sitter.Node, file_path: Path) -> List[DataStructure]:
    """Extract impl blocks."""
    results = []

    impl_type = ""
    for child in node.children:
        if child.type == "type_identifier":
            impl_type = _node_text(child, source)
            break
        elif child.type == "generic_type":
            for gc in child.children:
                if gc.type == "type_identifier":
                    impl_type = _node_text(gc, source)
                    break

    if not impl_type:
        return results

    methods = []

    def find_functions(n: tree_sitter.Node) -> None:
        """Recursively find function_item nodes."""
        for child in n.children:
            if child.type == "function_item":
                methods.append(_extract_function(source, child, file_path))
            else:
                find_functions(child)

    for child in node.children:
        if child.type == "declaration_list":
            find_functions(child)

    if methods:
        results.append(DataStructure(
            name=impl_type,
            type="impl",
            file=str(file_path),
            line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            methods=methods
        ))

    return results


def _extract_imports(content: str) -> List[Import]:
    """Extract use statements from Rust source."""
    imports = []

    content = re.sub(r'//.*', '', content)

    pattern = r'\buse\s+([a-zA-Z0-9_:]+)(?:\s*::\s*\{([^}]+)\})?(?:;|$)'

    for match in re.finditer(pattern, content):
        module = match.group(1)
        names_str = match.group(2)

        if names_str:
            names = [n.strip() for n in names_str.split(',')]
        else:
            names = [module.split('::')[-1]]

        imports.append(Import(
            module=module,
            names=names
        ))

    return imports


def extract_from_rust(file_path: Path) -> List[Function]:
    """Extract top-level functions from a Rust source file.

    Excludes functions inside ``mod tests { ... }`` blocks.
    """
    try:
        tree = _parse_rust_file(file_path)
    except Exception:
        return []

    source = file_path.read_bytes()
    functions: List[Function] = []

    collected: set = set()

    def on_node(node: tree_sitter.Node, parent: tree_sitter.Node, siblings_before: list):
        if node.type == "function_item":
            # Skip methods inside impl (they're extracted separately)
            # A function_item inside an impl_item has parent.type == "declaration_list"
            if parent is not None and parent.type == "declaration_list":
                return
            func = _extract_function(source, node, file_path)
            if func.name not in collected:
                functions.append(func)
                collected.add(func.name)

    _walk_tree_with_parent(tree.root_node, source, on_node, skip_mod_items=True)
    return functions


def extract_structs_from_rust(file_path: Path) -> List[DataStructure]:
    """Extract structs from a Rust source file.

    Skips structs inside ``mod_item`` blocks.
    """
    try:
        tree = _parse_rust_file(file_path)
    except Exception:
        return []

    source = file_path.read_bytes()
    structs: List[DataStructure] = []

    collected: set = set()

    def on_node(node: tree_sitter.Node, parent: tree_sitter.Node, siblings_before: list):
        if node.type == "struct_item":
            struct = _extract_struct(source, node, file_path, siblings_before)
            key = (struct.name, struct.line)
            if key not in collected:
                structs.append(struct)
                collected.add(key)

    _walk_tree_with_parent(tree.root_node, source, on_node, skip_mod_items=True)
    return structs


def extract_enums_from_rust(file_path: Path) -> List[DataStructure]:
    """Extract enums from a Rust source file.

    Skips enums inside ``mod_item`` blocks.
    """
    try:
        tree = _parse_rust_file(file_path)
    except Exception:
        return []

    source = file_path.read_bytes()
    enums: List[DataStructure] = []

    collected: set = set()

    def on_node(node: tree_sitter.Node, parent: tree_sitter.Node, siblings_before: list):
        if node.type == "enum_item":
            enum = _extract_enum(source, node, file_path)
            key = (enum.name, enum.line)
            if key not in collected:
                enums.append(enum)
                collected.add(key)

    _walk_tree_with_parent(tree.root_node, source, on_node, skip_mod_items=True)
    return enums


def extract_impls_from_rust(file_path: Path) -> List[DataStructure]:
    """Extract impl blocks from a Rust source file.

    Skips impl blocks inside ``mod_item`` blocks.
    """
    try:
        tree = _parse_rust_file(file_path)
    except Exception:
        return []

    source = file_path.read_bytes()
    impls: List[DataStructure] = []

    collected: set = set()

    def on_node(node: tree_sitter.Node, parent: tree_sitter.Node, siblings_before: list):
        if node.type == "impl_item":
            for impl in _extract_impl(source, node, file_path):
                key = (impl.name, impl.line)
                if key not in collected:
                    impls.append(impl)
                    collected.add(key)

    _walk_tree_with_parent(tree.root_node, source, on_node, skip_mod_items=True)
    return impls


def extract_all_rust(file_path: Path) -> tuple:
    """Extract functions, structs, enums, and impls from a Rust file.

    Returns: (functions, data_structures, imports)
    """
    funcs = extract_from_rust(file_path)
    structs = extract_structs_from_rust(file_path)
    enums = extract_enums_from_rust(file_path)
    impls = extract_impls_from_rust(file_path)

    content = file_path.read_text()
    imports = _extract_imports(content)

    return funcs, structs + enums + impls, imports
