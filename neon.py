#!/usr/bin/env python3
from nodes import FunctionDef, StubDef


from tokenizer import tokenize, KEYWORDS
import sys
import os
from nodes import *

sections = {"code": [], "decls": []}

filesIncluded = {}
PROCEDURE = "func"
IMPORT_FILE = "import"
DECLARE_VARIABLE = "var"
DECLARE_CONSTANT = "const"
DEFINE_MACRO = "define"
DECLARE_ENUM = "enum"
DECLARE_TYPE = "type"

PP_DIRECTIVE = "PP_DIRECTIVE"
ABSTRACT_TYPE_DEF = (
    "abstract"  # used to register a type provided by an external library
)
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
    ABSTRACT_TYPE_DEF,
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
    print("be careful with that", file=sys.stderr)
    print("-----------", file=sys.stderr)

GENERIC_TYPES = {
    "Array",
    "ptr",
    "volatile",
    "Cast",
    "struct",
}  # these types are allowed to have generic parameters
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
    def __init__(
        self, tokens: List[Token], code: str, file_directory: str, file_path: str
    ) -> None:
        self.tokens = tokens
        self.position = 0
        self.code_lines = code.splitlines()
        self.directory = file_directory
        self.file_name = file_path

    def current_token(self) -> Optional[Token]:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def lookahead_token(self, offset: int = 1) -> Optional[Token]:
        position = self.position + offset
        return self.tokens[position] if position < len(self.tokens) else None

    def error(self, message: str, token: Optional[Token]) -> NoReturn:
        line_text = ""
        if token and token.line - 1 < len(self.code_lines):
            line_text = self.code_lines[token.line - 1]
        raise ParserError(message, token, line_text)

    def consume(self, expected_type: Optional[str] = None) -> Token:
        token = self.current_token()
        if token is None:
            self.error("Unexpected end of input", token)
        if expected_type and token.type != expected_type:
            self.error(
                f"Expected token type '{expected_type}' but got '{token.type}'", token
            )
        self.position += 1
        return token

    def consume_member_name(self) -> str:
        token = self.current_token()
        if token is None or (token.type != "ID" and token.type not in KEYWORDS):
            self.error("Expected a member name (identifier or keyword)", token)
        self.position += 1
        return token.value

    def consume_operator(self, expected: str) -> None:
        token = self.current_token()
        if not (token and token.type == "OP" and token.value == expected):
            self.error(f"Expected operator '{expected}'", token)
        self.consume("OP")

    def match(self, expected_type: str) -> bool:
        token = self.current_token()
        if token and token.type == expected_type:
            self.consume()
            return True
        return False

    def _platform_matches(self, name: str) -> bool:
        """Check whether the given platform name matches the current target platform."""
        if name == currentPlatform:
            return True
        # Normalize common platform names
        if name == "windows" and currentPlatform in ("win32", "cygwin", "msys"):
            return True
        if name == "linux" and currentPlatform.startswith("linux"):
            return True
        if name == "android" and currentPlatform in ("android", "linux"):
            if os.getenv("NEON_PLATFORM") == "android" or currentPlatform == "android":
                return True
        return False

    def _parse_one_toplevel(self) -> List[object]:
        """
        Parse a single top-level construct and return a list of AST nodes.
        This is used by both the main parse loop and platform blocks.
        """
        token = self.current_token()
        if not token:
            return []

        if token.type == PP_DIRECTIVE:
            return [self.parse_preprocessor_directive()]

        elif token.type == PROCEDURE:
            return [*self.parse_proc()]
        elif token.type == IMPORT_FILE:
            imported_items = self.parse_import()
            return imported_items if imported_items else []

        elif token.type == PLATFORM_CONDITIONAL:
            platform_code = self.parse_platform()
            return platform_code if platform_code else []

        elif token.type == DECLARE_TYPE:
            return [self.parse_struct()]

        elif token.type == DECLARE_ENUM:
            return [self.parse_enum()]

        elif token.type == ABSTRACT_TYPE_DEF:
            self.consume(ABSTRACT_TYPE_DEF)
            name = self.consume("ID").value
            TYPES.add(name)
            return []

        elif token.type == DEFINE_MACRO:
            return [self.parse_define()]

        elif token.type == DECLARE_VARIABLE:
            return [self.parse_var_decl()]

        elif token.type == DECLARE_CONSTANT:
            return [self.parse_const_decl()]

        else:
            self.error(f"Unexpected token at top level: {token.type}", token)

    def parse(self) -> Program:
        declarations = []
        code = []

        while self.current_token() is not None:
            items = self._parse_one_toplevel()
            for item in items:
                if isinstance(item, FunctionDef):
                    code.append(item)
                else:
                    declarations.append(item)

        return Program(declarations + code)

    def parse_preprocessor_directive(self) -> PreprocessorDirective:
        token = self.consume(PP_DIRECTIVE)
        return PreprocessorDirective(token.value)

    def parse_define(self) -> Define:
        self.consume(DEFINE_MACRO)
        name = self.consume("ID").value
        value = self.parse_expr()
        return Define(name, value)

    def parse_platform(self) -> Optional[List[object]]:
        """
        Parse a platform filter block.

        Syntax:
            platform <name> { ... }
            platform <name> or <name> or ... { ... }

        The block may contain any top-level items. Only items for a matching
        platform are kept; non-matching blocks are skipped by a simple
        brace-counting scan without building AST nodes.
        """
        self.consume(PLATFORM_CONDITIONAL)

        platforms = [self.consume("ID").value]
        while (
            self.current_token()
            and self.current_token().type == "ID"
            and self.current_token().value == "or"
        ):
            self.consume("ID")  # consume "or"
            platforms.append(self.consume("ID").value)

        if not (
            self.current_token()
            and self.current_token().type == "OP"
            and self.current_token().value == "{"
        ):
            self.error(
                "Expected '{' after platform specifier (platform filters must be blocks)",
                self.current_token(),
            )

        matches = any(self._platform_matches(platform) for platform in platforms)

        if not matches:
            # Skip the block without building AST nodes.
            self.consume_operator("{")
            depth = 1
            while self.current_token() is not None and depth > 0:
                token = self.current_token()
                if token.type == "OP":
                    if token.value == "{":
                        depth += 1
                    elif token.value == "}":
                        depth -= 1
                self.position += 1
            if depth != 0:
                self.error("Unterminated platform block", self.current_token())
            return None

        # Matching platform: parse the block normally.
        self.consume_operator("{")
        items = []
        while self.current_token() and not (
            self.current_token().type == "OP" and self.current_token().value == "}"
        ):
            items.extend(self._parse_one_toplevel())
        self.consume_operator("}")
        return items

    def parse_import(self) -> Optional[List[object]]:
        self.consume(IMPORT_FILE)
        source_token = self.current_token()
        token = self.consume("STRING")
        import_file_relative_path = token.value + ".neon"
        import_file_name = os.path.join(self.directory, import_file_relative_path)
        import_file_name = os.path.realpath(import_file_name)
        file_exists = False

        for import_path in IMPORT_PATHS:
            import_path = os.path.expanduser(import_path)
            candidate = os.path.join(import_path, import_file_relative_path)
            if os.path.isfile(candidate):
                file_exists = True
                import_file_name = candidate
                break

        if filesIncluded.get(import_file_name, None) is not None:
            # Already imported; skip to avoid duplicate definitions.
            return None

        if not file_exists:
            self.error(
                f'Cannot find "{import_file_relative_path}" in {IMPORT_PATHS}',
                source_token,
            )

        code = ""
        try:
            with open(import_file_name, "r") as file_handle:
                code = file_handle.read()
        except IOError as error:
            self.error(
                f"Could not open import file '{import_file_name}': {error}",
                source_token,
            )

        tokens = tokenize(code, import_file_name)
        imported_parser = Parser(
            tokens, code, os.path.dirname(import_file_name), import_file_name
        )
        imported_ast = imported_parser.parse()
        filesIncluded[import_file_name] = {"path": self.file_name, "line": token.line}
        return imported_ast.items

    def parse_proc(self) -> list[StubDef] | tuple[StubDef, FunctionDef]:
        self.consume(PROCEDURE)
        name = self.consume("ID").value
        attributes = []
        args = []

        self.consume_operator("(")
        while self.current_token() and self.current_token().value != ")":
            args.append(self.parse_arg())
            if self.current_token() and self.current_token().value == ",":
                self.consume_operator(",")
        self.consume_operator(")")

        while self.current_token() and self.current_token().type == "ATTR":
            attributes.append(self.consume("ATTR").value)
        VALID = ["->", "{"]
        if self.current_token() and self.current_token().value not in VALID:
            msg = f"Invalid token, expected {" or ".join(VALID)},"
            msg += f"but found: {self.current_token().value}"
            self.error(
                msg,
                self.current_token(),
            )

        if self.current_token() and self.current_token().type == "arrow":
            self.consume("arrow")
            ret_type = self.parse_type()
        else:
            ret_type = "void"
        stub_node = StubDef(
            name=name,
            ret_type=ret_type,
            attributes=attributes,
            args=args,
        )
        if "@declaration" in attributes:  # only declare it
            # print(stub_node)
            return [stub_node]

        self.consume_operator("{")
        body = self.parse_until(stop_type="OP", stop_value="}")
        self.consume_operator("}")
        return stub_node, FunctionDef(name, ret_type, attributes, args, body)

    def parse_arg(self) -> ArgDef:
        if self.current_token() and self.current_token().type == "ELLIPSIS":
            self.consume("ELLIPSIS")
            return ArgDef(name="...", arg_type="...", variadic=True)
        name = self.consume("ID").value
        arg_type = self.parse_type()
        variadic = False
        if self.current_token() and self.current_token().type == "ELLIPSIS":
            self.consume("ELLIPSIS")
            variadic = True
        return ArgDef(name, arg_type, variadic)

    def parse_type(self) -> str:
        source_token = self.current_token()
        base = self.consume("ID").value
        if base not in GENERIC_TYPES and base not in TYPES:
            self.error(f"Unknown type '{base}'", source_token)

        if (
            self.current_token()
            and self.current_token().type == "OP"
            and self.current_token().value == "<"
        ):
            self.consume_operator("<")
            generic = self.parse_type()
            if self.current_token().value == ",":
                self.consume("OP")
                if self.current_token().type == "NUMBER":
                    generic_second = self.consume("NUMBER").value
                else:
                    generic_second = self.consume("ID").value
                self.consume_operator(">")
                return f"{base}<{generic},{generic_second}>"

            self.consume_operator(">")
            return f"{base}<{generic}>"
        return base

    def parse_statement(self) -> object:
        token = self.current_token()
        if token.type == RETURN_FROM_PROCEDURE:
            self.consume(RETURN_FROM_PROCEDURE)
            expr = None
            if self.current_token():
                if (
                    self.current_token().line == token.line
                    and self.current_token().type
                    in [
                        "ID",
                        "OP",
                        "true",
                        "false",
                        "NUMBER",
                        "STRING",
                    ]
                ):
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

        if self.current_token().type == SELECTOR_STATEMENT:
            return self.parse_selector()
        elif self.current_token().type in {"ID"} or self.current_token().type == "OP":
            expr = self.parse_expr()
            if (
                self.current_token()
                and self.current_token().type == "OP"
                and self.current_token().value in {"=", "+=", "-=", "*=", "/="}
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
        value_attribute = None
        if self.current_token().type == "ATTR":
            value_attribute = self.consume("ATTR").value
        const_type = self.parse_type()

        if (
            self.current_token()
            and self.current_token().type == "OP"
            and self.current_token().value == "="
        ):
            self.consume_operator("=")
            init_expr = self.parse_expr()
        return ConstDecl(name, const_type, value_attribute, init_expr)

    def parse_var_decl(self) -> VarDecl:
        self.consume(DECLARE_VARIABLE)
        name = self.consume("ID").value
        init_expr = None
        value_attribute = None
        if self.current_token().type == "ATTR":
            value_attribute = self.consume("ATTR").value
        var_type = self.parse_type()

        if (
            self.current_token()
            and self.current_token().type == "OP"
            and self.current_token().value == "="
        ):
            self.consume_operator("=")
            init_expr = self.parse_expr()
        return VarDecl(name, var_type, value_attribute, init_expr)

    def parse_selector(self) -> SelectorStmt:
        self.consume(SELECTOR_STATEMENT)
        target = self.consume("ID").value
        self.consume(CONDITIONAL_IS)
        self.consume_operator("{")
        cases = []

        while self.current_token() and self.current_token().value not in ["}", "*"]:
            if self.current_token().value == ",":
                self.consume()
                continue
            value = self.parse_expr()
            if self.current_token().type == "arrow":
                self.consume("arrow")
                self.consume_operator("{")
                body = self.parse_until(stop_type="OP", stop_value="}")
                self.consume_operator("}")
                cases.append(CaseStmt(value, body))
            else:
                cases.append(CaseStmt(value, []))
        default_body = []
        if self.current_token() and self.current_token().value == "*":
            self.consume_operator("*")
            self.consume_operator("{")
            default_body = self.parse_until(stop_type="OP", stop_value="}")
            self.consume_operator("}")
        self.consume_operator("}")

        return SelectorStmt(target, cases, default_body)

    def parse_if(self, if_token_type: str = CONDITIONAL_IF) -> IfStmt:
        self.consume(if_token_type)
        condition = self.parse_expr()
        true_body = self.parse_block()
        false_body = []
        if self.current_token() and self.current_token().type == CONDITIONAL_ELSE_IF:
            false_body.append(self.parse_if(CONDITIONAL_ELSE_IF))
        elif self.current_token() and self.current_token().type == CONDITIONAL_ELSE:
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

        initialization = self.parse_statement()
        self.consume_operator(";")

        condition = self.parse_expr()
        self.consume_operator(";")

        update = self.parse_statement()
        body = self.parse_block()

        return ForStmt(initialization, condition, update, body)

    def parse_struct(self) -> TypeDef:
        self.consume(DECLARE_TYPE)
        source_token = self.current_token()
        name = self.consume("ID").value
        fields = None
        if self.current_token() and self.current_token().value == "=":
            fields = []
            self.consume("OP")
            if not (
                self.current_token()
                and self.current_token().type == "OP"
                and self.current_token().value == "{"
            ):
                self.error("Expected '{' after type name", self.current_token())
            self.consume_operator("{")
            while self.current_token() and not (
                self.current_token().type == "OP" and self.current_token().value == "}"
            ):
                field_name = self.consume("ID").value
                attrs = []
                while self.current_token().type == "ATTR":
                    attrs.append(self.consume("ATTR").value)

                field_type = self.parse_type()
                if (
                    self.current_token()
                    and self.current_token().type == "OP"
                    and self.current_token().value == ";"
                ):
                    self.consume("OP")
                fields.append((field_name, field_type, attrs))
            self.consume_operator("}")

        if name in TYPES:
            self.error(f"Type {name} already defined", source_token)
        else:
            TYPES.add(name)
        return TypeDef(name, fields)

    def parse_enum(self) -> TypeDef:
        self.consume(DECLARE_ENUM)
        source_token = self.current_token()
        name = self.consume("ID").value
        self.consume("OP")
        if not (
            self.current_token()
            and self.current_token().type == "OP"
            and self.current_token().value == "{"
        ):
            self.error("Expected '{' after type name", self.current_token())
        self.consume_operator("{")
        fields = []
        while self.current_token() and not (
            self.current_token().type == "OP" and self.current_token().value == "}"
        ):
            field_name = self.consume("ID").value
            if self.current_token().value == "=":
                self.consume_operator("=")
                field_value = self.consume("NUMBER").value
                if (
                    self.current_token()
                    and self.current_token().type == "OP"
                    and self.current_token().value == ","
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
        while self.current_token() and not (
            self.current_token().type == stop_type
            and self.current_token().value == stop_value
        ):
            statement = self.parse_statement()
            block.append(statement)
            if (
                self.current_token()
                and self.current_token().type == "OP"
                and self.current_token().value == ";"
            ):
                self.consume("OP")
        return block

    def parse_expr(self):
        return self.parse_logical_or()

    def parse_binary(self, lower_precedence_parser, operators: set) -> object:
        expr = lower_precedence_parser()
        while (
            self.current_token()
            and self.current_token().type == "OP"
            and self.current_token().value in operators
        ):
            operator = self.consume("OP").value
            expr = BinOp(expr, operator, lower_precedence_parser())
        return expr

    def parse_logical_or(self):
        return self.parse_binary(self.parse_logical_and, {"||"})

    def parse_logical_and(self):
        return self.parse_binary(self.parse_equality, {"&&"})

    def parse_equality(self):
        return self.parse_binary(self.parse_comparison, {"==", "!="})

    def parse_comparison(self):
        return self.parse_binary(self.parse_arith, {"<", "<=", ">", ">="})

    def parse_arith(self):
        return self.parse_binary(self.parse_term, {"+", "-"})

    def parse_term(self):
        return self.parse_binary(self.parse_unary, {"*", "/", "%"})

    def parse_unary(self):
        if (
            self.current_token()
            and self.current_token().type == "OP"
            and self.current_token().value in {"-", "!"}
        ):
            operator = self.consume("OP").value
            return UnaryOp(operator, self.parse_unary())

        return self.parse_factor()

    def parse_factor(self) -> object:
        token = self.current_token()

        if token.type == "OP" and token.value in {"&", "!"}:
            operator = self.consume("OP")
            operand = self.parse_factor()
            return UnaryOp(operator.value, operand)

        if token.type == "NEG_ID":
            self.consume("NEG_ID")
            atom = UnaryOp("-", Var(token.value[1:]))
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
            boolean_token = self.consume(token.type)
            atom = Bool(boolean_token.value)
        elif token.type == "OP" and token.value == "{":
            atom = self.parse_object_literal()
        elif token.type == "ID":
            atom = self._parse_identifier_factor()
        elif token.type == "OP" and token.value == "(":
            self.consume_operator("(")
            atom = self.parse_expr()
            self.consume_operator(")")
        elif token.type == PP_DIRECTIVE:
            atom = self.parse_preprocessor_directive()
        else:
            self.error(f"Unexpected token '{token.type}'", token)

        return self._parse_postfix(atom)

    def _parse_postfix(self, atom: object) -> object:
        """Apply postfix operators like member access, attribute access, and indexing."""
        while (
            self.current_token()
            and self.current_token().type == "OP"
            and self.current_token().value in {".", ":", "["}
        ):
            if self.current_token().value == ".":
                self.consume_operator(".")
                member = self.consume_member_name()
                atom = MemberAccess(atom, member)
            elif self.current_token().value == ":":
                self.consume_operator(":")
                attribute = self.consume_member_name()
                atom = AttributeAccess(atom, attribute)
            elif self.current_token().value == "[":
                self.consume_operator("[")
                index_expr = self.parse_expr()
                self.consume_operator("]")
                atom = IndexAccess(atom, index_expr)
        return atom

    def _parse_identifier_factor(self) -> object:
        id_token = self.consume("ID")
        identifier = id_token.value

        # Handle generic-like constructs: ptr<type>(expr), struct<type>, Raw<...>, Cast<type>...
        if (
            identifier == "ptr"
            and self.current_token()
            and self.current_token().type == "OP"
            and self.current_token().value == "<"
        ):
            self.consume_operator("<")
            type_id = self.parse_type()
            self.consume_operator(">")
            self.consume_operator("(")
            expr = self.parse_expr()
            self.consume_operator(")")
            return PCast(type_id, expr)

        if (
            identifier == "struct"
            and self.current_token()
            and self.current_token().type == "OP"
            and self.current_token().value == "<"
        ):
            self.consume_operator("<")
            type_id = self.parse_type()
            self.consume_operator(">")
            return StructVar(type_id)

        if (
            identifier == "Raw"
            and self.current_token()
            and self.current_token().type == "OP"
            and self.current_token().value == "<"
        ):
            self.consume_operator("<")
            # Parse the inner expression as a variable followed by postfix access.
            base_name = self.consume("ID").value
            base_expr = Var(base_name)
            accessed_expr = self._parse_postfix(base_expr)
            self.consume_operator(">")
            return Deref(accessed_expr)

        if (
            identifier == "Cast"
            and self.current_token()
            and self.current_token().type == "OP"
            and self.current_token().value == "<"
        ):
            self.consume_operator("<")
            type_id = self.parse_type()
            self.consume_operator(">")
            if self.current_token().value == "{":
                expr = self.parse_expr()
                return Cast(type_id, expr)
            else:
                self.consume_operator("(")
                expr = self.parse_expr()
                self.consume_operator(")")
                return Cast(type_id, expr)

        if (
            identifier == "Array"
            and self.current_token()
            and self.current_token().type == "OP"
            and self.current_token().value == "<"
        ):
            self.consume_operator("<")
            array_type = self.parse_type()
            if not self.consume("OP").value == ",":
                raise ParserError(
                    'Arrays expect a type and size, separated by ","',
                    self.current_token(),
                )
            array_size = self.consume()
            if array_size.type not in ["ID", "NUMBER"]:
                raise ParserError(
                    "Arrays expect size to be a variable or a number",
                    self.current_token(),
                )
            self.consume_operator(">")
            return Array(array_type, array_size.value)

        # Function call
        if (
            self.current_token()
            and self.current_token().type == "OP"
            and self.current_token().value == "("
        ):
            self.consume_operator("(")
            args = []
            if self.current_token() and not (
                self.current_token().type == "OP" and self.current_token().value == ")"
            ):
                args.append(self.parse_expr())
                while (
                    self.current_token()
                    and self.current_token().type == "OP"
                    and self.current_token().value == ","
                ):
                    self.consume_operator(",")
                    args.append(self.parse_expr())
            self.consume_operator(")")
            return FuncCall(identifier, args)

        return Var(identifier)

    def parse_object_literal(self) -> StructLiteral:
        self.consume_operator("{")
        fields = []
        if (
            self.current_token()
            and self.current_token().type == "OP"
            and self.current_token().value == "}"
        ):
            self.consume_operator("}")
            return StructLiteral(fields)
        if (
            self.current_token().type == "ID"
            and self.lookahead_token()
            and self.lookahead_token().type == "OP"
            and self.lookahead_token().value == ":"
        ):
            # Named fields
            while True:
                key = self.consume("ID").value
                self.consume_operator(":")
                value = self.parse_expr()
                fields.append((key, value))
                if (
                    self.current_token()
                    and self.current_token().type == "OP"
                    and self.current_token().value == ","
                ):
                    self.consume_operator(",")
                    continue
                else:
                    break
        else:
            # Positional fields
            while True:
                expr = self.parse_expr()
                fields.append((None, expr))
                if (
                    self.current_token()
                    and self.current_token().type == "OP"
                    and self.current_token().value == ","
                ):
                    self.consume_operator(",")
                    continue
                else:
                    break
        if not (
            self.current_token()
            and self.current_token().type == "OP"
            and self.current_token().value == "}"
        ):
            self.error("Expected '}' to close struct literal", self.current_token())
        self.consume_operator("}")
        return StructLiteral(fields)


def main():
    if len(sys.argv) < 2:
        print("Usage: neon.py <input-file>")
        sys.exit(1)
    input_file = sys.argv[1]
    with open(input_file, "r") as file_handle:
        code = file_handle.read()
    tokens = tokenize(code, input_file)
    parser = Parser(tokens, code, os.path.dirname(input_file), input_file)
    ast = parser.parse()
    import pprint

    for item in ast.items:
        pprint.pprint(item, compact=True)


if __name__ == "__main__":
    main()
