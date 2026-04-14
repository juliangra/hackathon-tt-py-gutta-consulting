"""Parse TypeScript source files using tree-sitter.

Provides AST access and method extraction for the translator pipeline.

Compliance note: tree-sitter and tree-sitter-typescript are MIT-licensed AST
parsing libraries, allowed under Rule 5. The C extension has no node/js runtime
dependency (Rule 6 compliant). Full audit: docs/COMPLIANCE.md
"""
from __future__ import annotations

import tree_sitter_typescript as ts_lang
from tree_sitter import Language, Parser, Node


_TS_LANGUAGE = Language(ts_lang.language_typescript())


def parse_typescript(source: str) -> Node:
    """Parse TypeScript source and return the root AST node."""
    parser = Parser(_TS_LANGUAGE)
    tree = parser.parse(source.encode("utf-8"))
    return tree.root_node


def get_text(node: Node) -> str:
    """Get the source text of an AST node."""
    return node.text.decode("utf-8")


def find_class(root: Node, name: str) -> Node | None:
    """Find a class declaration by name."""
    for child in root.children:
        if child.type == "export_statement":
            for c in child.children:
                if c.type == "class_declaration":
                    name_node = c.child_by_field_name("name")
                    if name_node and get_text(name_node) == name:
                        return c
        if child.type == "class_declaration":
            name_node = child.child_by_field_name("name")
            if name_node and get_text(name_node) == name:
                return child
    return None


def find_methods(class_node: Node) -> dict[str, Node]:
    """Extract all method definitions from a class body."""
    methods: dict[str, Node] = {}
    body = class_node.child_by_field_name("body")
    if not body:
        return methods
    for child in body.children:
        if child.type == "method_definition":
            name_node = child.child_by_field_name("name")
            if name_node:
                methods[get_text(name_node)] = child
        elif child.type == "public_field_definition":
            name_node = child.child_by_field_name("name")
            if name_node:
                methods[get_text(name_node)] = child
    return methods


def find_method_body(method_node: Node) -> Node | None:
    """Get the body (block statement) of a method."""
    return method_node.child_by_field_name("body")
