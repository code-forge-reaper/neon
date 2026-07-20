#!/usr/bin/env python3
from tokenizer import tokenize, KEYWORDS
import sys
import os
from nodes import *

sections = {"code": [], "decls": []}

filesIncluded = {}
PROCEDURE = "func"
PROCEDURE_DEFINITION = "prototype"
IMPORT_FILE = "import"
DECLARE_VARIABLE = "var"
DECLARE_CONSTANT = "const"
DEFINE_MACRO = "define"
DECLARE_ENUM = "enum"
DECLARE_TYPE = "type"

PP_DIRECTIVE = "PP_DIRECTIVE"
ABISTRACT_TYPE_DEF = "abstract"  # this shouldn't be passed as a node, but used to create an abstract type, aka, a type that is defined by some library, but not ourselves
# Control flow


LOOP_FOR = "for"
LOOP_WHILE = "while"

# Conditional logic
CONDITIONAL_IF = "if"
CONDITIONAL_ELSE = "else"
CONDITIONAL_ELSE_IF = "elseif"
CONDITIONAL_IS = "is"

PLATFORM_CONDITIONAL = "platform"

# Functions
RETURN_FROM_PROCEDURE = "return"

# Other
SELECTOR_STATEMENT = "case"


# Booleans
BOOLEAN_TRUE = "true"
BOOLEAN_FALSE = "false"

_KEYWORDS = {
    PROCEDURE,
    PROCEDURE_DEFINITION,
    IMPORT_FILE,
    DECLARE_VARIABLE,
    DECLARE_CONSTANT,
    DEFINE_MACRO,
    DECLARE_ENUM,
    DECLARE_TYPE,
    LOOP_FOR,
    LOOP_WHILE,
    CONDITIONAL_IF,
    CONDITIONAL_ELSE,
    CONDITIONAL_ELSE_IF,
    CONDITIONAL_IS,
    RETURN_FROM_PROCEDURE,
    SELECTOR_STATEMENT,
    BOOLEAN_TRUE,
    BOOLEAN_FALSE,
    ABISTRACT_TYPE_DEF,
    PLATFORM_CONDITIONAL,
}
KEYWORDS.clear()
KEYWORDS.update(_KEYWORDS)
IMPORT_PATHS: list[str] = ["~/.neon", "./"]
if os.getenv("NEON_HOME") is not None:
    IMPORT_PATHS.append(str(os.getenv("NEON_HOME")))

currentPlatform = os.getenv("NEON_PLATFORM") or sys.platform
if os.getenv("NEON_PLATFORM") is not None and sys.platform != currentPlatform:
    print("-----------", file=sys.stderr)
    print("you might not be able to compile to this platform", file=sys.stderr)
    print("be carefull with that", file=sys.stderr)
    print("-----------", file=sys.stderr)

GENERIC_TYPES = {
    "Array",
    "ptr",
    "Cast",
    "struct",
}  # this list is used to bypass type checking, since they are used like: Array<int, 3>, ptr<int>, etc
TYPES = {
    "int",
    "double",
    "string",
    "uint",
    "char",
    "boolean",
    "void",
    "float",
    "ulong",
    "uchar",
}


# --- Parser ---
class Parser:
    def __init__(self, tokens: List[Token], code: str, fileDir, filePath) -> None:
        self.tokens = tokens
        self.pos = 0
        self.lines = code.splitlines()  # store code lines for context
        self.dir = fileDir
        self.file_name = filePath

    def current(self) -> Optional[Token]:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def lookahead(self, offset: int = 1) -> Optional[Token]:
        pos = self.pos + offset
        return self.tokens[pos] if pos < len(self.tokens) else None

    def error(self, msg: str, token) -> NoReturn:
        line_text = ""
        if token and token.line - 1 < len(self.lines):
            line_text = self.lines[token.line - 1]
        ParserError(msg, token, line_text)
        exit(1)

    def consume(self, expected_type: Optional[str] = None) -> Token:
        token = self.current()
        if token is None:
            self.error("Unexpected end of input", token)
        if expected_type and token.type != expected_type:
            self.error(
                f"Expected token type '{expected_type}' but got '{token.type}'", token
            )
        self.pos += 1
        return token

    def consume_member_name(self) -> str:
        token = self.current()
        # Accept both regular identifiers and keywords as member names.
        if token is None or (token.type != "ID" and token.type not in KEYWORDS):
            self.error("Expected a member name (identifier or keyword)", token)
        self.pos += 1
        return token.value

    def consume_operator(self, expected: str) -> None:
        token = self.current()
        if not (token and token.type == "OP" and token.value == expected):
            self.error(f"Expected operator '{expected}'", token)
        self.consume("OP")

    def match(self, expected_type: str) -> bool:
        token = self.current()
        if token and token.type == expected_type:
            self.consume()
            return True
        return False

    def parse(self) -> Program:
        decls = []
        code = []

        while self.current() is not None:
            token = self.current()
            if not token:
                break

            if token.type == PP_DIRECTIVE:
                decls.append(self.parse_preprocessor_directive())

            elif token.type == PROCEDURE:
                # Parse the complete function definition
                func_node = self.parse_proc()

                # Automatically create a stub (prototype) for the declaration section
                stub_node = StubDef(
                    name=func_node.name,
                    ret_type=func_node.ret_type,
                    attributes=func_node.attributes,
                    args=func_node.args,
                )
                if func_node.name != "main":
                    decls.append(stub_node)
                code.append(func_node)

            elif token.type == PROCEDURE_DEFINITION:
                decls.append(self.parse_stub())

            elif token.type == IMPORT_FILE:
                # Parse imported file
                imported_items = self.parse_import()
                if imported_items:
                    # Separate imported items into decls and code to maintain correct order
                    # The imported_items list is already decls + code, so we iterate and sort
                    for item in imported_items:
                        if isinstance(item, FunctionDef):
                            code.append(item)
                        else:
                            decls.append(item)

            elif token.type == PLATFORM_CONDITIONAL:
                platformCode = self.parse_platform()
                if platformCode:
                    for item in platformCode:
                        # Assuming platform blocks contain vars or statements.
                        # Since function definition isn't supported inside blocks,
                        # most items here will likely be declarations or global logic
                        if isinstance(item, FunctionDef):
                            code.append(item)
                        else:
                            decls.append(item)

            elif token.type == DECLARE_TYPE:
                decls.append(self.parse_struct())
            elif token.type == DECLARE_ENUM:
                decls.append(self.parse_enum())
            elif token.type == ABISTRACT_TYPE_DEF:
                self.consume(ABISTRACT_TYPE_DEF)
                name = self.consume("ID").value
                TYPES.add(name)
            elif token.type == DEFINE_MACRO:
                decls.append(self.parse_define())
            elif token.type == DECLARE_VARIABLE:
                decls.append(self.parse_var_decl())
            elif token.type == DECLARE_CONSTANT:
                decls.append(self.parse_const_decl())
            else:
                self.error(f"Unexpected token at top level: {token.type}", token)

        # Return combined program with declarations first, then code
        return Program(decls + code)

    def parse_preprocessor_directive(self) -> PreprocessorDirective:
        token = self.consume(PP_DIRECTIVE)
        return PreprocessorDirective(token.value)

    def parse_define(self) -> Define:
        self.consume(DEFINE_MACRO)
        name = self.consume("ID").value
        value = self.parse_expr()
        return Define(name, value)

    def parse_platform(self) -> List[object] | None:
        self.consume(PLATFORM_CONDITIONAL)
        name = self.consume("ID").value

        block = self.parse_block()

        if currentPlatform != name:
            return None
        return block

    # somewhat like python's import
    def parse_import(self) -> List[object] | None:
        self.consume(IMPORT_FILE)
        # Consume the string containing the filename.
        sourceT = self.current()
        token = self.consume("STRING")
        p = token.value + ".neon"
        file_name = os.path.join(self.dir, p)
        file_name = os.path.realpath(file_name)
        exists = False

        for fpath in IMPORT_PATHS:
            fpath = os.path.expanduser(fpath)
            if os.path.isfile(os.path.join(fpath, p)):
                exists = True
                file_name = os.path.join(fpath, p)
                break
        if filesIncluded.get(file_name, None) is not None:
            # print(f"{self.file_name}:{token.line+1}: \"{file_name}\" was imported before by \"{filesIncluded[file_name]["path"]}\"")
            # print(f"{filesIncluded[file_name]["path"]}:{filesIncluded[file_name]["line"]+1}: first time \"{file_name}\" was imported")
            return None

        if not exists:
            self.error(f'there should be a "{p}" in {IMPORT_PATHS}', sourceT)

        code = ""
        try:
            with open(file_name, "r") as f:
                code = f.read()
        except IOError as error:
            self.error(f"Could not open import file '{file_name}': {error}", sourceT)
        tokens = tokenize(code, file_name)
        imported_parser = Parser(tokens, code, os.path.dirname(file_name), file_name)
        imported_ast = imported_parser.parse()
        # Return the list of items in the imported AST to be merged into the current AST.
        filesIncluded[file_name] = {"path": self.file_name, "line": token.line}
        # we could add a #pragma once handler into the language, since it aims to be like C
        # but without all of the boiler plate

        # or we can lean into modules with public and private,
        # and handle them acordingly in the parser level
        return imported_ast.items

    def parse_stub(self) -> StubDef:
        self.consume(PROCEDURE_DEFINITION)
        name = self.consume("ID").value
        attributes = []
        while self.current() and self.current().type == "ATTR":
            attributes.append(self.consume("ATTR").value)

        args = []
        self.consume_operator("(")
        while self.current() and self.current().value != ")":
            args.append(self.parse_arg())
            if self.current() and self.current().value == ",":
                self.consume_operator(",")
        self.consume_operator(")")
        self.consume("arrow")
        ret_type = self.parse_type()

        return StubDef(name=name, attributes=attributes, ret_type=ret_type, args=args)

    def parse_proc(self) -> FunctionDef:
        self.consume(PROCEDURE)
        name = self.consume("ID").value

        # Optional attributes.
        attributes = []
        while self.current() and self.current().type == "ATTR":
            attributes.append(self.consume("ATTR").value)

        # Parse arguments.
        args = []

        self.consume_operator("(")
        while self.current() and self.current().value != ")":
            args.append(self.parse_arg())
            if self.current() and self.current().value == ",":
                self.consume_operator(",")
        self.consume_operator(")")
        if self.current() and self.current().type == "arrow":
            self.consume("arrow")
            ret_type = self.parse_type()
        else:
            ret_type = "void"

        # Parse procedure body.

        self.consume_operator("{")
        body = self.parse_until(stop_type="OP", stop_value="}")
        self.consume_operator("}")
        return FunctionDef(name, ret_type, attributes, args, body)

    def parse_arg(self) -> ArgDef:
        if self.current() and self.current().type == "ELLIPSIS":
            self.consume("ELLIPSIS")
            return ArgDef(name="...", arg_type="...", variadic=True)
        name = self.consume("ID").value
        arg_type = self.parse_type()
        variadic = False
        if self.current() and self.current().type == "ELLIPSIS":
            self.consume("ELLIPSIS")
            variadic = True
        return ArgDef(name, arg_type, variadic)

    def parse_type(self) -> str:
        sourceT = self.current()
        base = self.consume("ID").value
        if base not in GENERIC_TYPES and base not in TYPES:
            self.error(f"Unknown type '{base}'", sourceT)

        if (
            self.current()
            and self.current().type == "OP"
            and self.current().value == "<"
        ):
            self.consume_operator("<")
            generic = self.parse_type()
            if self.current().value == ",":
                self.consume("OP")
                if self.current().type == "NUMBER":
                    genericB = self.consume("NUMBER").value
                else:
                    genericB = self.consume("ID").value
                self.consume_operator(">")
                return f"{base}<{generic},{genericB}>"

            self.consume_operator(">")
            return f"{base}<{generic}>"
        return base

    def parse_statement(self) -> object:
        # print(self.current())

        token = self.current()
        if token.type == RETURN_FROM_PROCEDURE:
            self.consume(RETURN_FROM_PROCEDURE)
            expr = None
            if self.current():
                if self.current().line == token.line and self.current().type in [
                    "ID",
                    "OP",
                    "true",
                    "false",
                    "NUMBER",
                    "STRING",
                ]:  # more or less to allow you to return nothing
                    expr = self.parse_expr()
            return ReturnStmt(expr)
        elif token.type == DECLARE_VARIABLE:
            return self.parse_var_decl()
        elif token.type == DECLARE_CONSTANT:
            return self.parse_const_decl()
        elif token.type == CONDITIONAL_IF:
            return self.parse_if()
        elif token.type == LOOP_WHILE:
            return self.parse_loop()
        elif token.type == LOOP_FOR:
            return self.parse_for()

        if self.current().type == SELECTOR_STATEMENT:
            return self.parse_selector()
        elif self.current().type in {"ID"} or self.current().type == "OP":
            expr = self.parse_expr()
            if (
                self.current()
                and self.current().type == "OP"
                and self.current().value in {"=", "+=", "-=", "*=", "/="}
            ):
                op = self.consume("OP").value
                rhs = self.parse_expr()
                return Assignment(expr, rhs, op)
            else:
                return ExprStmt(expr)
        else:
            expr = self.parse_expr()
            return ExprStmt(expr)

    def parse_const_decl(self) -> ConstDecl:
        self.consume(DECLARE_CONSTANT)
        name = self.consume("ID").value
        init_expr = None
        vattr = None
        if self.current().type == "ATTR":
            vattr = self.consume("ATTR").value
        const_type = self.parse_type()

        if (
            self.current()
            and self.current().type == "OP"
            and self.current().value == "="
        ):
            self.consume_operator("=")
            init_expr = self.parse_expr()
        return ConstDecl(name, const_type, vattr, init_expr)

    def parse_var_decl(self) -> VarDecl:
        self.consume(DECLARE_VARIABLE)
        name = self.consume("ID").value
        init_expr = None
        vattr = None
        if self.current().type == "ATTR":
            vattr = self.consume("ATTR").value
        var_type = self.parse_type()

        if (
            self.current()
            and self.current().type == "OP"
            and self.current().value == "="
        ):
            self.consume_operator("=")
            init_expr = self.parse_expr()
        return VarDecl(name, var_type, vattr, init_expr)

    def parse_selector(self) -> SelectorStmt:
        self.consume(SELECTOR_STATEMENT)
        target = self.consume("ID").value
        self.consume(CONDITIONAL_IS)
        self.consume_operator("{")
        cases = []

        while self.current() and self.current().value not in ["}", "*"]:
            value = self.parse_expr()
            if self.current().type == "arrow":
                self.consume("arrow")
                self.consume_operator("{")
                body = self.parse_until(stop_type="OP", stop_value="}")
                self.consume_operator("}")
                cases.append(CaseStmt(value, body))
            else:  # i do not recomend using fall-through in selector/switch
                cases.append(CaseStmt(value, []))
        defaultBody = []
        if self.current() and self.current().value == "*":
            self.consume_operator(
                "*"
            )  # lets be honest, it is best practice to always have a default in there
            self.consume_operator("{")
            defaultBody = self.parse_until(stop_type="OP", stop_value="}")
            self.consume_operator("}")
        self.consume_operator("}")  # this closes off the selector

        return SelectorStmt(target, cases, defaultBody)

    def parse_if(self, IF=CONDITIONAL_IF) -> IfStmt:
        self.consume(IF)
        condition = self.parse_expr()
        true_body = self.parse_block()
        false_body = []
        if self.current() and self.current().type == CONDITIONAL_ELSE_IF:
            false_body.append(self.parse_if(CONDITIONAL_ELSE_IF))
        elif self.current() and self.current().type == CONDITIONAL_ELSE:
            self.consume(CONDITIONAL_ELSE)
            false_body = self.parse_block()
        return IfStmt(condition, true_body, false_body)

    def parse_loop(self) -> LoopStmt:
        self.consume(LOOP_WHILE)
        condition = self.parse_expr()
        body = self.parse_block()

        return LoopStmt(condition, body)

    def parse_for(self):
        self.consume(LOOP_FOR)

        # 1. Initialization (e.g., var i int = 0)
        init = self.parse_statement()
        self.consume_operator(";")
        # print(self.current(), init)

        # 2. Condition (e.g., i < 10)
        condition = self.parse_expr()
        self.consume_operator(";")

        # 3. Update (e.g., i = i + 1)
        update = self.parse_statement()
        body = self.parse_block()

        return ForStmt(init, condition, update, body)

    def parse_struct(self) -> TypeDef:
        self.consume(DECLARE_TYPE)
        sourceName = self.current()
        name = self.consume("ID").value
        fields = None
        if self.current() and self.current().value == "=":
            fields = []
            self.consume("OP")
            if not (
                self.current()
                and self.current().type == "OP"
                and self.current().value == "{"
            ):
                self.error("Expected '{' after type name", sourceName)
            self.consume_operator("{")
            while self.current() and not (
                self.current().type == "OP" and self.current().value == "}"
            ):
                field_name = self.consume("ID").value
                attrs = []
                while self.current().type == "ATTR":
                    attrs.append(self.consume("ATTR").value)

                field_type = self.parse_type()
                if (
                    self.current()
                    and self.current().type == "OP"
                    and self.current().value == ";"
                ):
                    self.consume("OP")
                fields.append((field_name, field_type, attrs))
            self.consume_operator("}")

        if name in TYPES:
            self.error(f"Type {name} already defined", sourceName)
        else:
            TYPES.add(name)
        return TypeDef(name, fields)

    def parse_enum(self) -> TypeDef:
        self.consume(DECLARE_ENUM)
        sourceT = self.current()
        name = self.consume("ID").value
        self.consume("OP")
        if not (
            self.current()
            and self.current().type == "OP"
            and self.current().value == "{"
        ):
            self.error("Expected '{' after type name", sourceT)
        self.consume_operator("{")
        fields = []
        while self.current() and not (
            self.current().type == "OP" and self.current().value == "}"
        ):
            field_name = self.consume("ID").value
            if self.current().value == "=":
                self.consume_operator("=")
                field_value = self.consume("NUMBER").value
                if (
                    self.current()
                    and self.current().type == "OP"
                    and self.current().value == ","
                ):
                    self.consume("OP")
                fields.append((field_name, field_value))
            else:
                fields.append((field_name, None))
        self.consume_operator("}")
        return EnumDef(name, fields)

    def parse_block(self) -> List[object]:
        self.consume_operator("{")
        block = self.parse_until("OP", "}")
        self.consume_operator("}")
        return block

    def parse_until(self, stop_type: str, stop_value: str) -> List[object]:
        block = []
        while self.current() and not (
            self.current().type == stop_type and self.current().value == stop_value
        ):
            stmt = self.parse_statement()
            block.append(stmt)
            # Consume a semicolon if present.
            if (
                self.current()
                and self.current().type == "OP"
                and self.current().value == ";"
            ):
                self.consume("OP")
        return block

    def parse_expr(self) -> object:
        expr = self.parse_arith()
        while (
            self.current()
            and self.current().type == "OP"
            and self.current().value in {"==", "!=", ">", "<", ">=", "<=", "&&", "||"}
        ):
            op = self.consume("OP").value
            right = self.parse_arith()
            expr = BinOp(expr, op, right)
        return expr

    def parse_arith(self) -> object:
        expr = self.parse_term()
        while (
            self.current()
            and self.current().type == "OP"
            and self.current().value in {"+", "-"}
        ):
            op = self.consume("OP").value
            right = self.parse_term()
            expr = BinOp(expr, op, right)
        return expr

    def parse_term(self) -> object:
        expr = self.parse_factor()
        while (
            self.current()
            and self.current().type == "OP"
            and self.current().value in {"*", "/", "%"}
        ):
            op = self.consume("OP").value
            right = self.parse_factor()
            expr = BinOp(expr, op, right)
        return expr

    def parse_factor(self) -> object:
        token = self.current()

        # Handle unary operators like '&' and '!'
        if token.type == "OP" and token.value in {"&", "!"}:
            op = self.consume("OP")
            operand = self.parse_factor()
            return UnaryOp(op.value, operand)
        if token.type == "NEG_ID":
            self.consume("NEG_ID")
            atom = UnaryOp(
                "-", Var(token.value[1:])
            )  # strip the '-', wrap in unary negation
        elif token.type == "NUMBER":
            self.consume("NUMBER")
            atom = Num(token.value)
        elif token.type == "STRING":
            self.consume("STRING")
            atom = Str(token.value)
        elif token.type == "CHAR":
            self.consume("CHAR")
            atom = Char(token.value)
        elif token.type in (BOOLEAN_TRUE, BOOLEAN_FALSE):
            t = self.consume(token.type)
            atom = Bool(t.value)
        elif token.type == "OP" and token.value == "{":
            atom = self.parse_object_literal()
        elif token.type == "ID":
            id_token = self.consume("ID")
            if (
                id_token.value == "ptr"
                and self.current()
                and self.current().type == "OP"
                and self.current().value == "<"
            ):
                self.consume_operator("<")
                type_id = self.parse_type()
                self.consume_operator(">")
                self.consume_operator("(")
                expr = self.parse_expr()
                self.consume_operator(")")
                atom = PCast(type_id, expr)
            elif (
                id_token.value == "struct"
                and self.current()
                and self.current().type == "OP"
                and self.current().value == "<"
            ):
                self.consume_operator("<")
                type_id = self.parse_type()
                self.consume_operator(">")
                atom = StructVar(type_id)
            elif (
                id_token.value == "Raw"
                and self.current()
                and self.current().type == "OP"
                and self.current().value == "<"
            ):
                self.consume_operator("<")
                expr = self.consume("ID").value
                self.consume_operator(">")
                atom = Deref(expr)
            elif (
                id_token.value == "Cast"
                and self.current()
                and self.current().type == "OP"
                and self.current().value == "<"
            ):
                self.consume_operator("<")
                type_id = self.parse_type()
                self.consume_operator(">")
                if self.current().value == "{":
                    expr = self.parse_expr()
                    atom = Cast(type_id, expr)
                else:
                    self.consume_operator("(")
                    expr = self.parse_expr()
                    self.consume_operator(")")
                    atom = Cast(type_id, expr)
            elif (
                id_token.value == "Array"
                and self.current()
                and self.current().type == "OP"
                and self.current().value == "<"
            ):
                self.consume_operator("<")
                array_type = self.parse_type()
                if not self.consume("OP").value == ",":
                    ParserError('arrays expect a type and size, separated by ","')
                array_size = self.consume()
                if not array_size.type in ["ID", "NUMBER"]:
                    ParserError("arrays expect size to be a variable or a number")
                self.consume_operator(">")
                atom = Array(array_type, array_size.value)
            elif (
                self.current()
                and self.current().type == "OP"
                and self.current().value == "("
            ):
                self.consume_operator("(")
                args = []
                if self.current() and not (
                    self.current().type == "OP" and self.current().value == ")"
                ):
                    args.append(self.parse_expr())
                    while (
                        self.current()
                        and self.current().type == "OP"
                        and self.current().value == ","
                    ):
                        self.consume_operator(",")
                        args.append(self.parse_expr())
                self.consume_operator(")")
                atom = FuncCall(id_token.value, args)
            else:
                atom = Var(id_token.value)
        elif token.type == "OP" and token.value == "(":
            self.consume_operator("(")
            atom = self.parse_expr()
            self.consume_operator(")")
        elif token.type == PP_DIRECTIVE:
            atom = self.parse_preprocessor_directive()

        else:
            self.error(f"Unexpected token '{token.type}'", token)

        # Postfix: member and index access.
        while (
            self.current()
            and self.current().type == "OP"
            and self.current().value in {".", ":", "["}
        ):
            if self.current().value == ".":
                self.consume_operator(".")
                member = self.consume_member_name()
                atom = MemberAccess(atom, member)
            elif self.current().value == ":":
                self.consume_operator(":")
                attribute = self.consume_member_name()
                atom = AttributeAccess(atom, attribute)
            elif self.current().value == "[":
                self.consume_operator("[")
                index_expr = self.parse_expr()
                self.consume_operator("]")
                atom = IndexAccess(atom, index_expr)
        return atom

    def parse_object_literal(self) -> StructLiteral:
        self.consume_operator("{")
        fields = []
        if (
            self.current()
            and self.current().type == "OP"
            and self.current().value == "}"
        ):
            self.consume_operator("}")
            return StructLiteral(fields)
        if (
            self.current().type == "ID"
            and self.lookahead()
            and self.lookahead().type == "OP"
            and self.lookahead().value == ":"
        ):
            while True:
                key = self.consume("ID").value
                self.consume_operator(":")
                value = self.parse_expr()
                fields.append((key, value))
                if (
                    self.current()
                    and self.current().type == "OP"
                    and self.current().value == ","
                ):
                    self.consume_operator(",")
                    continue
                else:
                    break
        else:
            while True:
                expr = self.parse_expr()
                fields.append((None, expr))
                if (
                    self.current()
                    and self.current().type == "OP"
                    and self.current().value == ","
                ):
                    self.consume_operator(",")
                    continue
                else:
                    break
        if not (
            self.current()
            and self.current().type == "OP"
            and self.current().value == "}"
        ):
            self.error("Expected '}' to close struct literal", self.current())
        self.consume_operator("}")
        return StructLiteral(fields)


def main():
    if len(sys.argv) < 2:
        print("Usage: neon.py <input-file>")
        sys.exit(1)
    input_file = sys.argv[1]
    with open(input_file, "r") as f:
        code = f.read()
    tokens = tokenize(code, input_file)
    parser = Parser(tokens, code, os.path.dirname(input_file), input_file)
    ast = parser.parse()
    import pprint

    for item in ast.items:
        pprint.pprint(item, compact=True)
    # pprint.pprint(ast.items)


if __name__ == "__main__":
    main()
