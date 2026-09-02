from neon import *
import sys
import os
import re

decls = []


def appendOnce(a: list, what):
    if what not in a:
        a.append(what)


typeStr = re.compile(r"([a-zA-Z][a-zA-Z_0-9]+)<(.*)>")


def convert_type(typ: str) -> str:
    """
    Convert Neon types to equivalent C types.
    """
    type_map = {
        "number": "int",
        "uint": "unsigned int",
        "uchar": "unsigned char",
        "ulong": "unsigned long",
        "string": "const char*",
        "boolean": "bool",
    }
    m = typeStr.split(typ)
    if len(m) > 1:  # volatile<ptr<uint16_t>> -> ['', 'volatile', 'ptr<uint16_t>', '']
        _, type, rest, _ = m
        if type == "ptr":
            inner = convert_type(rest)
            return f"{inner}*"
        elif type == "volatile":
            inner = convert_type(rest)
            return f"volatile {inner}"
        elif type == "struct":
            inner = convert_type(rest)
            return f"struct {inner}"

    if typ in type_map:
        return type_map[typ]

    return typ


def get_array_info(type_str: str):
    """
    Helper to parse Array<Type, Size> strings.
    Returns (base_type_c_string, size_string) if it's an array, else None.
    """
    if type_str.startswith("Array<") and type_str.endswith(">"):
        arr, res = type_str.split("<", 1)
        typeAndSize = res[:-1]
        if "," in typeAndSize:
            base, size = typeAndSize.split(",", 1)
            base = base.strip()
            size = size.strip()
            return convert_type(base), (size if size != "0" else "")
        return convert_type(typeAndSize), ""
    return None


def generate_expr(expr: object | None) -> str:
    if expr is None:
        return ""
    if isinstance(expr, Num):
        return str(expr.value)
    elif isinstance(expr, Str):
        return f'"{expr.value}"'
    elif isinstance(expr, Bool):
        return "true" if expr.value else "false"
    elif isinstance(expr, Var):
        return expr.name
    elif isinstance(expr, MemberAccess):
        return f"{generate_expr(expr.obj)}.{expr.member}"
    elif isinstance(expr, AttributeAccess):
        return f"{generate_expr(expr.obj)}->{expr.attribute}"
    elif isinstance(expr, IndexAccess):
        return f"{generate_expr(expr.obj)}[{generate_expr(expr.index)}]"
    elif isinstance(expr, UnaryOp):
        return f"{expr.op}{generate_expr(expr.operand)}"
    elif isinstance(expr, BinOp):
        left = generate_expr(expr.left)
        right = generate_expr(expr.right)
        return f"({left} {expr.op} {right})"
    elif isinstance(expr, FuncCall):
        args = ", ".join(generate_expr(arg) for arg in expr.args)
        return f"{expr.func_name}({args})"
    elif isinstance(expr, StructLiteral):
        init_parts = []
        for key, val in expr.fields:
            val_str = generate_expr(val)
            part = f".{key} = {val_str}" if key is not None else val_str
            init_parts.append(part)
        return "{" + ", ".join(init_parts) + "}"
    elif isinstance(expr, (PCast, Cast)):
        # Both cast types behave similarly enough for C generation here
        is_ptr = isinstance(expr, PCast)
        cast_type = convert_type(expr.type_name) + ("*" if is_ptr else "")
        return f"({cast_type}) {generate_expr(expr.expr)}"
    elif isinstance(expr, Char):
        return f"{expr.value}"
    elif isinstance(expr, PreprocessorDirective):
        return expr.directive
    elif isinstance(expr, Deref):
        return f"*{generate_expr(expr.expr)}"
    else:
        raise Exception(f"Unknown expression type: {expr}")


def generate_decl_common(
    name: str, type_str: str, attr: str, init_expr: object | None, is_const: bool
) -> str:
    """
    Shared logic for VarDecl and ConstDecl to avoid duplication.
    """
    prefix_parts = []
    if attr == "@static":
        prefix_parts.append("static")
    if is_const:
        prefix_parts.append("const")

    prefix = " ".join(prefix_parts) + (" " if prefix_parts else "")

    array_info = get_array_info(type_str)

    if array_info:
        base_type, size = array_info
        code = f"{prefix}{base_type} {name}[{size}]"
    else:
        code = f"{prefix}{convert_type(type_str)} {name}"

    if init_expr is not None:
        code += " = " + generate_expr(init_expr)

    return code + ";"


def generate_statement(stmt: object) -> str:
    if isinstance(stmt, PreprocessorDirective):
        return stmt.directive
    elif isinstance(stmt, VarDecl):
        return generate_decl_common(
            stmt.name, stmt.var_type, stmt.var_attr, stmt.init_expr, is_const=False
        )
    elif isinstance(stmt, ConstDecl):
        return generate_decl_common(
            stmt.name, stmt.const_type, stmt.const_attr, stmt.init_expr, is_const=True
        )
    elif isinstance(stmt, Assignment):
        return f"{generate_expr(stmt.target)} {stmt.op} {generate_expr(stmt.expr)};"
    elif isinstance(stmt, ReturnStmt):
        return f"return {generate_expr(stmt.expr)};"
    elif isinstance(stmt, ExprStmt):
        return generate_expr(stmt.expr) + (
            ";" if not isinstance(stmt.expr, PreprocessorDirective) else ""
        )
    elif isinstance(stmt, IfStmt):
        return generate_if(stmt)
    elif isinstance(stmt, LoopStmt):
        return generate_loop(stmt)
    elif isinstance(stmt, ForStmt):
        return generate_for(stmt)
    elif isinstance(stmt, SelectorStmt):
        return generate_selector(stmt)
    else:
        raise Exception(f"Unknown statement type: {stmt}")


def generate_if(stmt: IfStmt) -> str:
    code = f"if ({generate_expr(stmt.condition)}) {{\n"
    code += indent_block("\n".join(generate_statement(s) for s in stmt.true_body))
    code += "\n}"

    if stmt.false_body:
        # Optimization: generic else-if handling
        if len(stmt.false_body) == 1 and isinstance(stmt.false_body[0], IfStmt):
            code += " else " + generate_if(stmt.false_body[0])
        else:
            code += " else {\n"
            code += indent_block(
                "\n".join(generate_statement(s) for s in stmt.false_body)
            )
            code += "\n}"
    return code


def generate_selector(stmt: SelectorStmt) -> str:
    code = f"switch ({stmt.target}) {{\n"
    for case in stmt.cases:
        case_val = generate_expr(case.value)
        code += f"case {case_val}:\n"
        if case.body:
            code += indent_block("\n".join(generate_statement(s) for s in case.body))
            code += "\n    break;\n"

    code += "default:\n"
    code += indent_block("\n".join(generate_statement(s) for s in stmt.default))
    code += "\n    break;\n"
    code += "}"
    return code


def generate_loop(loop_stmt: LoopStmt) -> str:
    code = f"while ({generate_expr(loop_stmt.condition)}) {{\n"
    code += indent_block("\n".join(generate_statement(s) for s in loop_stmt.body))
    code += "\n}"
    return code


def generate_for(for_stmt: ForStmt) -> str:
    init = generate_statement(for_stmt.init).rstrip(";")
    cond = generate_expr(for_stmt.condition)
    upd = generate_statement(for_stmt.update).rstrip(";")

    code = f"for ({init}; {cond}; {upd}) {{\n"
    code += indent_block("\n".join(generate_statement(s) for s in for_stmt.body))
    code += "\n}"
    return code


def generate_signature(
    name: str,
    ret_type: str,
    args: list,
    attributes: list = None,
    is_definition: bool = True,
) -> str:
    """
    Centralized function signature generation for both Definitions and Stubs.
    """
    attributes = attributes or []
    ret_type_str = convert_type(ret_type) if ret_type else "void"
    is_extern = "@extern" in attributes
    is_static = "@static" in attributes

    params = []
    for arg in args:
        if arg.variadic:
            params.append("...")
            break

        array_info = get_array_info(arg.arg_type)
        if array_info:
            base, size = array_info
            params.append(f"{base} {arg.name}[{size}]")
        else:
            params.append(f"{convert_type(arg.arg_type)} {arg.name}")

    args_str = ", ".join(params) if params else "void"

    prefix = ""
    if is_extern:
        prefix += "extern "
    if is_static:
        prefix += "static "

    signature = f"{prefix}{ret_type_str} {name}({args_str})"
    return signature


def generate_proc(proc: FunctionDef) -> str:
    signature = generate_signature(proc.name, proc.ret_type, proc.args, proc.attributes)

    body_stmts = []
    for stmt in proc.body:
        body_stmts.append(generate_statement(stmt))
        if isinstance(stmt, ReturnStmt):
            break

    body = indent_block("\n".join(body_stmts))

    # Add prototype to global decls if it's not main
    # if proc.name != "main":
    #    appendOnce(decls, signature + ";")

    return f"{signature} {{\n{body}\n}}"


def generate_stub(stub: StubDef) -> str:
    # Stubs usually don't have 'static' in the prototype if they are meant for headers/forward decls,
    # but we pass attributes just in case.
    return (
        generate_signature(stub.name, stub.ret_type, stub.args, stub.attributes) + ";"
    )


def generate_include(inc: Include) -> str:
    header = inc.header[1:-1]
    return f'#include "{header}.h"'


def generate_struct(struct: TypeDef) -> str:
    if not struct.fields:
        return f"typedef struct {struct.name} {struct.name};"

    field_lines = []
    for name, typ, attrs in struct.fields:
        at = " ".join(attr[1:] for attr in attrs) if attrs else ""
        if at:
            at = " " + at  # Pad if exists

        array_info = get_array_info(typ)
        if array_info:
            base, size = array_info
            field_lines.append(f"    {at}{base} {name}[{size}];")
        else:
            field_lines.append(f"    {at}{convert_type(typ)} {name};")

    return f"typedef struct {{\n" + "\n".join(field_lines) + f"\n}} {struct.name};"


def generate_enum(struct: TypeDef) -> str:
    fields = []
    for i, (fn, fv) in enumerate(struct.fields):
        string = f"    {fn} = {fv}" if fv else f"    {fn}"
        if i != len(struct.fields) - 1:
            string += ","
        fields.append(string)

    return f"enum {struct.name} {{\n" + "\n".join(fields) + "\n};"


def generate_define(defn: Define) -> str:
    return f"#define {defn.name} {generate_expr(defn.value)}"


def generate_h(ast: Program) -> str:
    c = []
    for item in ast.items:
        if isinstance(item, StubDef):
            c.append(generate_stub(item))
    return "\n\n".join(c)


def generate_c(ast: Program) -> str:
    code_sections = []
    dispatch = {
        PreprocessorDirective: lambda item: item.directive,
        Include: generate_include,
        TypeDef: generate_struct,
        EnumDef: generate_enum,
        Define: generate_define,
        FunctionDef: generate_proc,
        VarDecl: generate_statement,
        ConstDecl: generate_statement,
        StubDef: generate_stub,
    }

    for item in ast.items:
        handler = dispatch.get(type(item))
        if handler:
            code_sections.append(handler(item))
        else:
            raise Exception(f"Unknown top-level item: {item}")

    return "\n\n".join(code_sections)


def indent_block(block: str, indent: str = "    ") -> str:
    return "\n".join(
        indent + line if line.strip() else line for line in block.splitlines()
    )
