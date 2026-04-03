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
                return f"$<{args}>"  # placeholder for generic
        return _node_text(node, source)
    
    # Handle tuple types: (i32, String)
    if node_type == "tuple_type":
        types = []
        for child in node.children:
            if child.type != "(" and child.type != "," and child.type != ")":
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
            # Each parameter has structure like: identifier: type
            parts = []
            
            for param_child in child.children:
                if param_child.type == "identifier":
                    parts.append(_node_text(param_child, source))
                elif param_child.type == "mutable_specifier":
                    parts[-1] = "mut " + parts[-1] if parts else "mut"
                elif param_child.type == "type":
                    type_str = _extract_type(source, param_child)
                    if type_str:
                        parts.append(f": {type_str}")
            
            if parts:
                param_list.append("".join(parts))
        elif child.type == "self_parameter":
            # Self parameter
            param_list.append("self")
    
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
            # return_type contains a type child
            type_node = _find_child_by_type(child, "type")
            if type_node:
                return_type = _extract_type(source, type_node)
        elif child_type == "attribute_item":
            # Attributes like #[derive(Debug)]
            attr_text = _node_text(child, source)
            if attr_text:
                decorators.append(attr_text.strip())
        elif child_type == "outer_attributes":
            docstring = _extract_docstring(child, source)
        elif child_type == "async":
            async_flag = True
        elif child_type == "block":
            body = _node_text(child, source)
    
    # Build signature
    signature = f"({params})"
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


def _extract_struct(source: bytes, node: tree_sitter.Node, file_path: Path) -> DataStructure:
    """Extract struct details from a struct_item node."""
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
            # Parse struct fields
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
    
    for child in node.children:
        child_type = child.type
        
        if child_type == "type_identifier":
            name = _node_text(child, source)
        elif child_type == "variant":
            # Enum variant - can be simple, tuple, or struct style
            variant_parts = []
            for vc in child.children:
                if vc.type == "identifier":
                    variant_parts.append(_node_text(vc, source))
                elif vc.type == "tuple_variant_fields":
                    # Tuple variant like Enum(Data)
                    types = []
                    for tf in vc.children:
                        if tf.type == "type":
                            types.append(_extract_type(source, tf))
                    if types:
                        variant_parts[-1] += f"({', '.join(types)})"
                elif vc.type == "field_declaration_list":
                    # Struct variant like Enum { field: Type }
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
            
            if variant_parts:
                variants.append("".join(variant_parts))
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
    
    # Find the type being implemented
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
    
    # Collect methods
    methods = []
    for child in node.children:
        if child.type == "function_item":
            methods.append(_extract_function(source, child, file_path))
    
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
    
    # Remove line comments
    content = re.sub(r'//.*', '', content)
    
    # Match use statements
    pattern = r'\buse\s+([a-zA-Z0-9_:]+)(?:\s*::\s*\{([^}]+)\})?(?:;|$)'
    
    for match in re.finditer(pattern, content):
        module = match.group(1)
        names_str = match.group(2)
        
        if names_str:
            # Named imports: use serde::{Serialize, Deserialize}
            names = [n.strip() for n in names_str.split(',')]
        else:
            # Single import
            names = [module.split('::')[-1]]
        
        imports.append(Import(
            module=module,
            names=names
        ))
    
    return imports


def extract_from_rust(file_path: Path) -> List[Function]:
    """Extract functions from a Rust source file."""
    try:
        tree = _parse_rust_file(file_path)
    except Exception:
        return []
    
    source = file_path.read_bytes()
    functions = []
    
    def walk(node: tree_sitter.Node):
        if node.type == "function_item":
            functions.append(_extract_function(source, node, file_path))
        for child in node.children:
            walk(child)
    
    walk(tree.root_node)
    return functions


def extract_structs_from_rust(file_path: Path) -> List[DataStructure]:
    """Extract structs from a Rust source file."""
    try:
        tree = _parse_rust_file(file_path)
    except Exception:
        return []
    
    source = file_path.read_bytes()
    structs = []
    
    def walk(node: tree_sitter.Node):
        if node.type == "struct_item":
            structs.append(_extract_struct(source, node, file_path))
        for child in node.children:
            walk(child)
    
    walk(tree.root_node)
    return structs


def extract_enums_from_rust(file_path: Path) -> List[DataStructure]:
    """Extract enums from a Rust source file."""
    try:
        tree = _parse_rust_file(file_path)
    except Exception:
        return []
    
    source = file_path.read_bytes()
    enums = []
    
    def walk(node: tree_sitter.Node):
        if node.type == "enum_item":
            enums.append(_extract_enum(source, node, file_path))
        for child in node.children:
            walk(child)
    
    walk(tree.root_node)
    return enums


def extract_impls_from_rust(file_path: Path) -> List[DataStructure]:
    """Extract impl blocks from a Rust source file."""
    try:
        tree = _parse_rust_file(file_path)
    except Exception:
        return []
    
    source = file_path.read_bytes()
    impls = []
    
    def walk(node: tree_sitter.Node):
        if node.type == "impl_item":
            impls.extend(_extract_impl(source, node, file_path))
        for child in node.children:
            walk(child)
    
    walk(tree.root_node)
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