#!/usr/bin/env python3
from tokenizer import *
import sys
import os
from dataclasses import dataclass, field
from typing import List, NoReturn, Optional, Tuple, Union, Set
filesIncluded = {}
IMPORT_PATHS: list[str] = ["~/.neon", "./"]
if os.getenv("NEON_HOME") is not None:
    IMPORT_PATHS.append(str(os.getenv("NEON_HOME")))

GENERIC_TYPES = {"Array", "ptr", "Cast", "struct"}# this list is used to bypass type checking, since they are used like: Array<int, 3>, ptr<int>, etc
TYPES = {
    "int",
    "string",
    "uint",
    "char",
    "boolean",
    "void",
    "float",
    "ulong",
    "uchar"
}

class ParserError:
    def __init__(
        self, message: str, token: Optional["Token"] = None, line_text: str = ""
    ) -> NoReturn:
        if token:
            pointer = "^" * (len(line_text))
            RED = "\033[91m"
            CYAN = "\033[96m"
            RESET = "\033[0m"


            full_message = (
                f"{RED}Syntax error{RESET} on file {CYAN}{token.file}{RESET}:\n"
                f"{token.line+1}: {line_text}\n{pointer}\n{message}"
            )
        else:
            full_message = f"Syntax error at end of input:\n{message}"

        print(full_message)
        exit(1)


# --- AST Node Definitions ---
@dataclass
class Program:
    items: List[object]


@dataclass
class PreprocessorDirective:
    directive: str


@dataclass
class FunctionDef:
    name: str
    ret_type: str
    attributes: List[str] = field(default_factory=list)
    args: List["ArgDef"] = field(default_factory=list)
    body: List[object] = field(default_factory=list)


@dataclass
class StubDef:
    name: str
    ret_type: str
    attributes: List[str] = field(default_factory=list)
    args: List["ArgDef"] = field(default_factory=list)


@dataclass
class ArgDef:
    name: str
    arg_type: str
    variadic: bool = False


@dataclass
class VarDecl:
    name: str
    var_type: str | None
    var_attr: str | None
    init_expr: Optional[object] = None

@dataclass
class ConstDecl:
    name: str
    const_type: str
    const_attr: str
    init_expr: Optional[object] = None


@dataclass
class Assignment:
    target: object
    expr: object
    op: str = "="


@dataclass
class ReturnStmt:
    expr: object | None


@dataclass
class ExprStmt:
    expr: object


@dataclass
class BinOp:
    left: object
    op: str
    right: object

@dataclass
class SelectorStmt:
    target: str
    cases: List[object]
    default: object
@dataclass
class CaseStmt:
    value: str
    body: List[object]

@dataclass
class UnaryOp:
    op: str
    operand: object


@dataclass
class Num:
    value: Union[int, float]

    def __init__(self, value: str):
        self.value = float(value) if "." in value else int(value)


@dataclass
class Str:
    value: str

    def __init__(self, value: str):
        self.value = value


@dataclass
class Char:
    value: str

    def __init__(self, value: str):
        self.value = value


@dataclass
class Bool:
    value: bool

    def __init__(self, value: str):
        self.value = value == BOOLEAN_TRUE


@dataclass
class Var:
    name: str


@dataclass
class MemberAccess:
    obj: object
    member: str


@dataclass
class AttributeAccess:
    obj: object
    attribute: str


@dataclass
class IndexAccess:
    obj: object
    index: object


@dataclass
class FuncCall:
    func_name: str
    args: List[object]


@dataclass
class Include:
    header: str


@dataclass
class TypeDef:
    name: str
    fields: Optional[List[Tuple[str, str]]]

@dataclass
class EnumDef:
    name: str
    fields: List[Tuple[str, int]]


@dataclass
class IfStmt:
    condition: object
    true_body: List[object]
    false_body: List[object] = field(default_factory=list)


@dataclass
class LoopStmt:
    condition: object
    body: List[object]

@dataclass
class FromStmt:
    start: int
    end: int
    name: str
    body: List[object]
    stepCount: str

@dataclass
class StructLiteral:
    fields: List[Tuple[Optional[str], object]]


@dataclass
class Define:
    name: str
    value: object


# New AST nodes for casting
@dataclass
class Cast:
    type_name: str
    expr: object


@dataclass
class PCast:
    type_name: str
    expr: object

@dataclass
class StructVar: # like "struct sockaddr_in addr" "var addr struct<sockaddr_in>"
    type_name: str

@dataclass
class Deref:
    expr: str


@dataclass
class Array:
    array_type: str
    array_size: int | None | str

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
        if token and token.line < len(self.lines):
            line_text = self.lines[token.line]
        ParserError(msg, token, line_text)
        exit(1)

    def consume(self, expected_type: Optional[str] = None) -> Token:
        token = self.current()
        if token is None:
            self.error("Unexpected end of input", token)
        if expected_type and token.type != expected_type:
            self.error(f"Expected token type '{expected_type}' but got '{token.type}'", token)
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
        items = []
        while self.current() is not None:
            token = self.current()
            if not token:
                break
            if token.type == PP_DIRECTIVE:
                items.append(self.parse_preprocessor_directive())
            elif token.type == PROCEDURE:
                items.append(self.parse_proc())
            elif token.type == PROCEDURE_DEFINITION:
                items.append(self.parse_stub())
            elif token.type == IMPORT_FILE:
                # Instead of adding a nested Program node, we merge imported items.
                imported_items = self.parse_import()
                if imported_items:
                    items.extend(imported_items)
            elif token.type == DECLARE_TYPE:
                items.append(self.parse_struct())
            elif token.type == DECLARE_ENUM:
                items.append(self.parse_enum())
            elif token.type == ABISTRACT_TYPE_DEF:
                # this shouldn't be passed as a node, but used to create an abstract type, aka, a type that is defined by some library, but not ourselves
                self.consume(ABISTRACT_TYPE_DEF)
                name = self.consume("ID").value
                TYPES.add(name)
            elif token.type == DEFINE_MACRO:
                items.append(self.parse_define())
            elif token.type == DECLARE_VARIABLE:
                items.append(self.parse_var_decl())
            elif token.type == DECLARE_CONSTANT:
                items.append(self.parse_const_decl())
            else:
                self.error(f"Unexpected token at top level: {token.type}", token)

        return Program(items)

    def parse_preprocessor_directive(self) -> PreprocessorDirective:
        token = self.consume(PP_DIRECTIVE)
        return PreprocessorDirective(token.value)

    def parse_define(self) -> Define:
        self.consume(DEFINE_MACRO)
        name = self.consume("ID").value
        value = self.parse_expr()
        return Define(name, value)

    # somewhat like python's import
    def parse_import(self) -> List[object] | None:
        self.consume(IMPORT_FILE)
        # Consume the string containing the filename.
        sourceT = self.current()
        token = self.consume("STRING")
        p = token.value+".neon"
        file_name = os.path.join(self.dir,p)
        file_name = os.path.realpath(file_name)
        exists = False

        for fpath in IMPORT_PATHS:
            fpath = os.path.expanduser(fpath)
            if os.path.isfile(os.path.join(fpath, p)):
                exists = True
                file_name = os.path.join(fpath, p)
                break
        if filesIncluded.get(file_name, None) is not None:
            #print(f"{self.file_name}:{token.line+1}: \"{file_name}\" was imported before by \"{filesIncluded[file_name]["path"]}\"")
            #print(f"{filesIncluded[file_name]["path"]}:{filesIncluded[file_name]["line"]+1}: first time \"{file_name}\" was imported")
            return None

        if not exists:
            self.error(f"there should be a \"{p}\" in {IMPORT_PATHS}", sourceT)

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
        filesIncluded[file_name] = {
            "path": self.file_name,
            "line": token.line
        }
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
        ret_type = self.parse_type()

        return StubDef(name=name, attributes = attributes, ret_type=ret_type, args=args)

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
        ret_type = self.parse_type()

        # Parse procedure body.
        body = []
        body = self.parse_block(stop_tokens={END_BLOCK})
        self.consume(END_BLOCK)
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
        token = self.current()
        if token.type == RETURN_FROM_PROCEDURE:
            self.consume(RETURN_FROM_PROCEDURE)
            expr = None
            if self.current() and self.current().type in ["ID", "OP", "true", "false", "NUMBER", "STRING"]: # more or less to allow you to return nothing
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
        elif token.type == LOOP_FROM:
            return self.parse_from()
        if self.current().type==SELECTOR_STATEMENT:
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
        return ConstDecl(name, const_type,vattr, init_expr)

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
        return VarDecl(name, var_type,vattr, init_expr)


    def parse_selector(self) -> SelectorStmt:
        self.consume(SELECTOR_STATEMENT)
        target = self.consume("ID").value
        cases = []
        while self.current() and self.current().type == CONDITIONAL_IS:
            self.consume(CONDITIONAL_IS)
            value = self.parse_expr()
            if self.current().type == CONDITIONAL_THEN:
                self.consume(CONDITIONAL_THEN)
                body = self.parse_block(stop_tokens={END_BLOCK})
                cases.append(CaseStmt(value, body))
                self.consume(END_BLOCK)
            else:# i do not recomend using fall-through in selector/switch
                cases.append(CaseStmt(value, []))


        self.consume(CONDITIONAL_ELSE) # lets be honest, it is best practice to always have a default in there
        defaultBody = self.parse_block(stop_tokens={END_BLOCK})
        self.consume(END_BLOCK)
        self.consume(END_BLOCK) # this closes off the selector

        return SelectorStmt(target, cases, defaultBody)

    def parse_if(self) -> IfStmt|SelectorStmt:
        self.consume(CONDITIONAL_IF)
        condition = self.parse_expr()
        self.consume(CONDITIONAL_THEN)
        true_body = self.parse_block(stop_tokens={CONDITIONAL_ELSE_IF, CONDITIONAL_ELSE, END_BLOCK})
        false_body = []
        if self.current() and self.current().type == CONDITIONAL_ELSE_IF:
            false_body.append(self.parse_if_chain())
        elif self.current() and self.current().type == CONDITIONAL_ELSE:
            self.consume(CONDITIONAL_ELSE)
            false_body = self.parse_block(stop_tokens={END_BLOCK})
        self.consume(END_BLOCK)
        return IfStmt(condition, true_body, false_body)


    def parse_if_chain(self) -> IfStmt:
        self.consume(CONDITIONAL_ELSE_IF)
        condition = self.parse_expr()
        self.consume(CONDITIONAL_THEN)
        true_body = self.parse_block(stop_tokens={CONDITIONAL_ELSE_IF, CONDITIONAL_ELSE, END_BLOCK})
        false_body = []
        if self.current() and self.current().type == CONDITIONAL_ELSE_IF:
            false_body.append(self.parse_if_chain())
        elif self.current() and self.current().type == CONDITIONAL_ELSE:
            self.consume(CONDITIONAL_ELSE)
            false_body = self.parse_block(stop_tokens={END_BLOCK})
        return IfStmt(condition, true_body, false_body)

    def parse_loop(self) -> LoopStmt:
        self.consume(LOOP_WHILE)
        condition = self.parse_expr()
        self.consume(LOOP_DO)
        body = self.parse_block(stop_tokens={END_BLOCK})
        self.consume(END_BLOCK)
        return LoopStmt(condition, body)

    # from <start> to <end> [step <number>] as <name> do ... end
    def parse_from(self):
        self.consume(LOOP_FROM)
        if self.current().type == "NUMBER":
            start = self.consume("NUMBER").value
        else:
            start = self.consume("ID").value

        self.consume(LOOP_TO)
        if self.current().type == "NUMBER":
            end = self.consume("NUMBER").value
        else:
            end = self.consume("ID").value
        stepCount = "1"
        if self.current().value == LOOP_STEP:
            self.consume(LOOP_STEP)
            if self.current().type == "NUMBER":
                stepCount = self.consume("NUMBER").value
            else:
                stepCount = self.consume("ID").value

            if stepCount == "0":
                raise ValueError("step count cannot be 0")

        self.consume(LOOP_AS)
        name = self.consume("ID").value
        self.consume(LOOP_DO)

        body = self.parse_block(stop_tokens={END_BLOCK})
        self.consume(END_BLOCK)
        return FromStmt(start,end, name, body, stepCount)


    def parse_struct(self) -> TypeDef:
        self.consume(DECLARE_TYPE)
        sourceName = self.current()
        name = self.consume("ID").value
        fields = None
        if self.current() and self.current().value == '=':
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
                field_type = self.parse_type()
                if (
                    self.current()
                    and self.current().type == "OP"
                    and self.current().value == ";"
                ):
                    self.consume("OP")
                fields.append((field_name, field_type))
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

    def parse_block(self, stop_tokens: Set[str]) -> List[object]:
        block = []
        while self.current() and self.current().type not in stop_tokens:
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
            and self.current().value in {"==", "!=", ">", "<", ">=", "<=", "&&","||"}
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
            atom = UnaryOp("-", Var(token.value[1:]))  # strip the '-', wrap in unary negation
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
                    ParserError("arrays expect a type and size, separated by \",\"")
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
            atom = (self.parse_preprocessor_directive())

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
    #pprint.pprint(ast.items)


if __name__ == "__main__":
    main()
