from dataclasses import dataclass, field
from typing import List, NoReturn, Optional, Tuple, Union, Set
from tokenizer import Token


class ParserError:
    def __init__(
        self, message: str, token: Optional[Token] = None, line_text: str = ""
    ) -> NoReturn:
        if token:
            pointer = "^" * (len(line_text))
            full_message = (
                f"{token.file}:{token.line}: {line_text}\n{pointer}\n{message}"
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
        if value.startswith("0x"):
            self.value = int(value, 16)
        else:
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
        self.value = value == "true"


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
class ForStmt:
    init: object  # e.g., var i int = 0
    condition: object  # e.g., i < 10
    update: object  # e.g., i = i + 1
    body: List[object]


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
class StructVar:  # like "struct sockaddr_in addr" "var addr struct<sockaddr_in>"
    type_name: str


@dataclass
class Deref:
    expr: str


@dataclass
class Array:
    array_type: str
    array_size: int | None | str
