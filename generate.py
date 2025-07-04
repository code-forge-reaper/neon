#!/usr/bin/env python
from neon import *
import argparse
import sys
import subprocess

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
        "pchar": "char*" # since Array expects a actual type
    }
    if typ in type_map:
        return type_map[typ]
    elif typ.startswith("ptr<") and typ.endswith(">"):
        inner = convert_type(typ[4:-1])
        return f"{inner}*"
    elif typ.startswith("struct<") and typ.endswith(">"):
        inner = convert_type(typ[7:-1])
        return f"struct {inner}"
    else:
        return typ


def generate_expr(expr: object | None) -> str:
    if expr == None : return ""
    """
    Recursively generate C code from an expression node.
    """
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
            part = (
                f".{key} = {generate_expr(val)}"
                if key is not None
                else generate_expr(val)
            )
            init_parts.append(part)
        return "{" + ", ".join(init_parts) + "}"
    elif isinstance(expr, PCast):
        # Convert the cast type by converting the inner type and appending '*'
        cast_type = convert_type(expr.type_name) + "*"
        return f"({cast_type}) {generate_expr(expr.expr)}"
    elif isinstance(expr, Cast):
        # Convert the cast type by converting the inner type
        cast_type = convert_type(expr.type_name)
        return f"({cast_type}) {generate_expr(expr.expr)}"
    elif isinstance(expr, Char):
        return f"{expr.value}"
    elif isinstance(expr, PreprocessorDirective):
        # Output preprocessor directive verbatim
        return expr.directive
    elif isinstance(expr, Deref):
        return f"*{expr.expr}"
    else:
        raise Exception(f"Unknown expression type: {expr}")


def generate_statement(stmt: object) -> str:
    """
    Generate C code for a given statement node.
    """
    if isinstance(stmt, PreprocessorDirective):
        # Output preprocessor directive verbatim
        return stmt.directive
    elif isinstance(stmt, VarDecl):
        if stmt.var_type.startswith("Array<"):
            type, value = stmt.var_type[len("Array<"):-1].split(",")
            code = f"{"static " if stmt.var_attr == "@static" else ""}{convert_type(type.strip())} {stmt.name}[{value.strip() if value != "0" else ""}]"
            if stmt.init_expr is not None:
                code += " = " + generate_expr(stmt.init_expr)
            return code+";"
        else:
            code = f"{"static " if stmt.var_attr == "@static" else ""}{convert_type(stmt.var_type)} {stmt.name}"
            if stmt.init_expr is not None:
                code += " = " + generate_expr(stmt.init_expr)
            return code + ";"
    elif isinstance(stmt, ConstDecl):
        if stmt.const_type.startswith("Array<"):
            type, value = stmt.const_type[len("Array<"):-1].split(",")
            code = f"{"static " if stmt.const_attr == "@static" else ""}const {convert_type(type.strip())} {stmt.name}[{value.strip() if value != "0" else ""}]"
            if stmt.init_expr is not None:
                code += " = " + generate_expr(stmt.init_expr)
            return code+";"
        else:
            code = f"{"static " if stmt.const_attr == "@static" else ""}const {convert_type(stmt.const_type)} {stmt.name}"
            if stmt.init_expr is not None:
                code += " = " + generate_expr(stmt.init_expr)
            return code + ";"
    elif isinstance(stmt, Assignment):
        # Use generate_expr on the target since it might be a complex lvalue.
        return f"{generate_expr(stmt.target)} {stmt.op} {generate_expr(stmt.expr)};"
    elif isinstance(stmt, ReturnStmt):
        return f"return {generate_expr(stmt.expr)};"
    elif isinstance(stmt, ExprStmt):
        if not isinstance(stmt.expr, PreprocessorDirective):
            return generate_expr(stmt.expr) + ";"
        return generate_expr(stmt.expr)

    elif isinstance(stmt, IfStmt):
        return generate_if(stmt)
    elif isinstance(stmt, LoopStmt):
        return generate_loop(stmt)
    elif isinstance(stmt, FromStmt):
        return generate_from(stmt)
    elif isinstance(stmt, SelectorStmt):
        return generate_selector(stmt)
    else:
        raise Exception(f"Unknown statement type: {stmt}")


def generate_if(stmt: IfStmt) -> str:
    """
    Generate C code for an if statement, including chained else-if and else blocks.
    """
    code = f"if ({generate_expr(stmt.condition)}) {{\n"
    code += indent_block("\n".join(generate_statement(s) for s in stmt.true_body))
    code += "\n}"
    if stmt.false_body:
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
    """
    Generate C code for a selector statement (like a switch).
    """
    code = f"switch ({stmt.target}) {{\n"
    for case in stmt.cases:
        case_val = generate_expr(case.value)
        code += f"case {case_val}:\n"
        if case.body:
            code += indent_block("\n".join(generate_statement(s) for s in case.body))
            code += "\n    break;\n"
        else:
            # If the case is empty (fallthrough), no break
            pass
    code += "default:\n"
    code += indent_block("\n".join(generate_statement(s) for s in stmt.default))
    code += "\n    break;\n"
    code += "}"
    return code


def generate_loop(loop_stmt: LoopStmt) -> str:
    """
    Generate C code for a while-loop.
    """
    code = f"while ({generate_expr(loop_stmt.condition)}) {{\n"
    code += indent_block("\n".join(generate_statement(s) for s in loop_stmt.body))
    code += "\n}"
    return code

def generate_from(from_stmt: FromStmt) -> str:
    """
    Generate C code for a for-loop.
    """
    code = f"for (int {from_stmt.name} = {from_stmt.start}; {from_stmt.name} <= {from_stmt.end}; {from_stmt.name}+={from_stmt.stepCount}) {{\n"
    code += indent_block("\n".join(generate_statement(s) for s in from_stmt.body))
    code += "\n}"
    return code

def generate_proc(proc: FunctionDef) -> str:
    """
    Generate C code for a procedure (function) definition.
    """
    ret_type = convert_type(proc.ret_type) if proc.ret_type else "void"
    is_extern = any(attr == "@extern" for attr in proc.attributes)
    is_static = any(attr == "@static" for attr in proc.attributes)
    params = []
    for arg in proc.args:
        if arg.variadic:
            params.append("...")
            break
        if arg.arg_type.startswith("Array<"):
            type, value = arg.arg_type[len("Array<"):-1].split(",")
            code = f"{convert_type(type.strip())} {arg.name}[{value.strip() if value.strip()!="0" else ""}]"
            params.append(code)
        else:
            params.append(f"{convert_type(arg.arg_type)} {arg.name}")
    args_str = ", ".join(params)
    if not args_str:
        args_str = "void"
    signature = f"{'extern ' if is_extern else ''}{'static ' if is_static else ""}{ret_type} {proc.name}({args_str})"
    def generateBody():
        b = []
        for stmt in proc.body:
            # dead code removal
            if isinstance(stmt, ReturnStmt): # do not generate more code if we got a return
                b.append(generate_statement(stmt)) # geneate the return itself
                break # exit this loop :)
            b.append(generate_statement(stmt))
        return b
    body = indent_block("\n".join(generateBody()))
    return f"{signature} {{\n{body}\n}}"


def generate_stub(stub: StubDef) -> str:
    """
    Generate C code for a procedure (function) definition.
    """
    ret_type = convert_type(stub.ret_type) if stub.ret_type else "void"
    params = []
    for arg in stub.args:
        if arg.variadic:
            params.append("...")
            break
        params.append(f"{convert_type(arg.arg_type)} {arg.name}")
    args_str = ", ".join(params)
    if not args_str:
        args_str = "void"
    signature = f"{ret_type} {stub.name}({args_str});"
    return f"{signature}"


def generate_include(inc: Include) -> str:
    header = inc.header[1:-1]
    return f'#include "{header}.h"'

def generate_struct(struct: TypeDef) -> str:
    field_lines = []
    if struct.fields:
        for name, typ in struct.fields:
            if typ.startswith("Array<"):
                base_type, length = typ[len("Array<"):-1].split(",")
                base_type = convert_type(base_type.strip())
                length = length.strip()
                length = length if length != "0" else ""  # For `[]` style
                field_lines.append(f"    {base_type} {name}[{length}];")
            else:
                field_lines.append(f"    {convert_type(typ)} {name};")

        return f"typedef struct {{\n" + "\n".join(field_lines) + f"\n}} {struct.name};"
    else:
        return f"typedef struct {struct.name} {struct.name};"

def generate_enum(struct: TypeDef) -> str:
    fields = [
    ]
    #fields = "\n".join(f"    {fn} = {fv}" for fn, fv in struct.fields)
    size = len(struct.fields)
    i = 0
    for fn, fv in struct.fields:
        i += 1
        if fv:
            string = f"    {fn} = {fv}"
        else:
            string = f"    {fn}"
        if i != size:
            string+=","
        fields.append(string)

    return f"enum {struct.name} {{\n{"\n".join(fields)}\n}};"


def generate_define(defn: Define) -> str:
    return f"#define {defn.name} {generate_expr(defn.value)}"


def generate_c(ast: Program) -> str:
    code_sections = []
    for item in ast.items:
        if isinstance(item, PreprocessorDirective):
            # Output preprocessor directive verbatim
            code_sections.append(item.directive)
        elif isinstance(item, Include):
            code_sections.append(generate_include(item))
        elif isinstance(item, TypeDef):
            code_sections.append(generate_struct(item))
        elif isinstance(item, EnumDef):
            code_sections.append(generate_enum(item))
        elif isinstance(item, Define):
            code_sections.append(generate_define(item))
        elif isinstance(item, FunctionDef):
            code_sections.append(generate_proc(item))
        elif isinstance(item, VarDecl):
            code_sections.append(generate_statement(item))
        elif isinstance(item, ConstDecl):
            code_sections.append(generate_statement(item))
        elif isinstance(item, StubDef):
            code_sections.append(generate_stub(item))
        else:
            raise Exception(f"Unknown top-level item: {item}")
    return "\n\n".join(code_sections)


def indent_block(block: str, indent: str = "    ") -> str:
    return "\n".join(
        indent + line if line.strip() else line for line in block.splitlines()
    )

def main() -> None:
    parser_args = argparse.ArgumentParser(description="Neon DSL to C code generator")
    parser_args.add_argument("input_file", help="Path to the Neon DSL source file")
    parser_args.add_argument("-o", "--output", help="Output file", default=None)
    parser_args.add_argument("-x", "--compile", action="store_true", help="Compile the C code using cc")
    parser_args.add_argument("-lf", "--link_flags", help="Comma-separated list of link flags", default="")
    parser_args.add_argument("-cf", "--compile_flags", help="Comma-separated list of compile flags", default="")
    parser_args.add_argument("--dump", action="store_true", help="Dump the types defined")

    args = parser_args.parse_args()

    try:
        with open(args.input_file, "r") as f:
            dsl_code = f.read()
    except Exception as e:
        sys.exit(f"Error reading {args.input_file}: {e}")

    tokens = tokenize(dsl_code, args.input_file)
    neon_parser = Parser(tokens, dsl_code, os.path.dirname(args.input_file), args.input_file)
    ast = neon_parser.parse()
    c_code = generate_c(ast)

    if args.compile:
        output_exe = args.output or "a.out"
        compile_flags = ["-" + flag.strip() for flag in args.compile_flags.split(",") if flag.strip()]
        link_flags = ["-l" + flag.strip() for flag in args.link_flags.split(",") if flag.strip()]

        try:
            # Pipe code to cc using stdin
            result = subprocess.run(
                ["cc","-x", "c", "-", "-o", output_exe, *compile_flags, *link_flags],
                input=c_code.encode(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            if result.returncode != 0:
                sys.stderr.write(result.stderr.decode())
                sys.exit("cc compilation failed.")
            print(f"Compilation successful. Output: {output_exe}")
        except Exception as e:
            sys.exit(f"Error during compilation: {e}")
    elif args.output:
        try:
            with open(args.output, "w") as f:
                f.write("/*code generated by Neon's compiler, do not modify\nas it will be overwritten*/\n" + c_code)
            print(f"C code successfully written to {args.output}")
        except Exception as e:
            sys.exit(f"Error writing to {args.output}: {e}")
    else:
        print(c_code)

    if args.dump:
        for item in TYPES:
            print(item)
if __name__ == "__main__":
    main()
