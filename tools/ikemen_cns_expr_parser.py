"""Tokenization and constant evaluation for CNS expressions."""
from __future__ import annotations

import re

_EXPR_TOK_RE = re.compile(
    r"\s*(?:"
    r"(?P<num>(?:\d+(?:\.\d*)?|\.\d+))|"
    r"(?P<ident>[A-Za-z_][A-Za-z0-9_.]*)|"
    r"(?P<op>\+\+|\*\*|==|!=|>=|<=|&&|\|\||[!()+\-*/%=<>,\[\]])"
    r")"
)


class _ExprParser:
    def __init__(self, text: str):
        self.text = text
        self.tokens: list[tuple[str, str]] = []
        self.i = 0
        self._tokenize()

    def _tokenize(self):
        pos = 0
        while pos < len(self.text):
            m = _EXPR_TOK_RE.match(self.text, pos)
            if not m:
                raise ValueError(f"unexpected expression token at {pos}: {self.text[pos:]!r}")
            kind = m.lastgroup
            value = m.group(kind)
            if kind == "num":
                self.tokens.append(("num", value))
            elif kind == "ident":
                self.tokens.append(("ident", value))
            elif kind == "op":
                self.tokens.append(("op", value))
            pos = m.end()

    def _peek(self) -> tuple[str, str] | None:
        if self.i < len(self.tokens):
            return self.tokens[self.i]
        return None

    def _take(self):
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def parse(self) -> float:
        result = self._or()
        if self._peek() is not None:
            tok = self._peek()
            raise ValueError(f"unexpected token in expression: {tok!r}")
        return result

    def _or(self) -> float:
        left = self._and()
        while self._peek() and self._peek()[1] in ("||",):
            self._take()
            right = self._and()
            # MUGEN || returns first truthy value, or last value
            left = right if right != 0 else left
        return left

    def _and(self) -> float:
        left = self._equality()
        while self._peek() and self._peek()[1] in ("&&",):
            self._take()
            right = self._equality()
            left = right if left != 0 and right != 0 else 0
        return left

    def _equality(self) -> float:
        left = self._rel()
        while self._peek() and self._peek()[1] in ("==", "!=", "="):
            op = self._take()[1]
            right = self._rel()
            if op in ("=", "=="):
                left = 1.0 if left == right else 0.0
            else:
                left = 1.0 if left != right else 0.0
        return left

    def _rel(self) -> float:
        left = self._add()
        while self._peek() and self._peek()[1] in (">", "<", ">=", "<="):
            op = self._take()[1]
            right = self._add()
            if op == ">":
                left = 1.0 if left > right else 0.0
            elif op == "<":
                left = 1.0 if left < right else 0.0
            elif op == ">=":
                left = 1.0 if left >= right else 0.0
            elif op == "<=":
                left = 1.0 if left <= right else 0.0
        return left

    def _add(self) -> float:
        left = self._mul()
        while self._peek() and self._peek()[1] in ("+", "-"):
            op = self._take()[1]
            right = self._mul()
            if op == "+":
                left = left + right
            else:
                left = left - right
        return left

    def _mul(self) -> float:
        left = self._power()
        while self._peek() and self._peek()[1] in ("*", "/", "%"):
            op = self._take()[1]
            right = self._power()
            if op == "*":
                left = left * right
            elif op == "/":
                left = left / right if right != 0 else 0
            else:
                left = left % right if right != 0 else 0
        return left

    def _power(self) -> float:
        left = self._unary()
        if self._peek() and self._peek()[1] == "**":
            self._take()
            right = self._power()
            left = left ** right
        return left

    def _unary(self) -> float:
        if self._peek() and self._peek()[1] == "-":
            self._take()
            return -self._primary()
        if self._peek() and self._peek()[1] == "+":
            self._take()
            return self._primary()
        return self._primary()

    def _primary(self) -> float:
        tok = self._peek()
        if tok is None:
            raise ValueError("unexpected end of expression")
        if tok[0] == "num":
            self._take()
            return float(tok[1])
        if tok[0] == "ident":
            name = self._take()[1]
            # Check for function call
            if self._peek() == ("op", "("):
                self._take()  # consume (
                args = self._parse_args()
                if self._peek() == ("op", ")"):
                    self._take()  # consume )
                else:
                    raise ValueError(f"missing closing paren in {name}()")
                return self._call_function(name, args)
            raise ValueError(f"unsupported symbol in expression: {name}")
        if tok == ("op", "("):
            self._take()
            val = self._or()
            if self._peek() == ("op", ")"):
                self._take()
            else:
                raise ValueError("missing closing parenthesis")
            return val
        raise ValueError(f"unexpected token in expression: {tok!r}")

    def _parse_args(self) -> list[float]:
        args = []
        if self._peek() == ("op", ")"):
            return args
        args.append(self._or())
        while self._peek() and self._peek()[1] == ",":
            self._take()
            args.append(self._or())
        return args

    def _call_function(self, name: str, args: list[float]) -> float:
        nl = name.lower()
        if nl == "ifelse":
            if len(args) != 3:
                raise ValueError(f"ifelse expects 3 args, got {len(args)}")
            return args[1] if args[0] != 0 else args[2]
        raise ValueError(f"unsupported function in expression: {name}")
