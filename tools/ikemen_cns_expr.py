"""Expression parsing and bytecode compilation for CNS triggers and values."""
from __future__ import annotations

import math
import re

# MUGEN expression parser for CNS parameters.
# Supports arithmetic, comparisons, logical operators, ifelse(), var(), sysvar(), fvar(), const(), GetHitVar().
_EXPR_TOK_RE = re.compile(
    r"\s*(?:"
    r"(?P<num>(?:\d+(?:\.\d*)?|\.\d+))|"
    r"(?P<ident>[A-Za-z_][A-Za-z0-9_.]*)|"
    r"(?P<op>\+\+|\*\*|==|!=|>=|<=|&&|\|\||[!()+\-*/%=<>,])"
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


_RUNTIME_EXPR_FIELDS = {
    "stateno": "IK_EXPR_FIELD_STATE_NO",
    "prevstateno": "IK_EXPR_FIELD_PREV_STATE_NO",
    "time": "IK_EXPR_FIELD_STATE_TIME",
    "gametime": "IK_EXPR_FIELD_GAME_TIME",
    "roundstate": "IK_EXPR_FIELD_ROUND_STATE",
    "roundno": "IK_EXPR_FIELD_ROUND_NUMBER",
    "stageauthorhash": "IK_EXPR_FIELD_STAGE_AUTHOR_HASH",
    "power": "IK_EXPR_FIELD_POWER",
    "life": "IK_EXPR_FIELD_LIFE",
    "lifemax": "IK_EXPR_FIELD_LIFE_MAX",
    "ctrl": "IK_EXPR_FIELD_CTRL",
    "movecontact": "IK_EXPR_FIELD_MOVE_CONTACT",
    "movehit": "IK_EXPR_FIELD_MOVE_HIT",
    "moveguarded": "IK_EXPR_FIELD_MOVE_GUARDED",
    "movereversed": "IK_EXPR_FIELD_MOVE_REVERSED",
    "statetype": "IK_EXPR_FIELD_STATE_TYPE",
    "movetype": "IK_EXPR_FIELD_MOVE_TYPE",
    "p2statetype": "IK_EXPR_FIELD_STATE_TYPE",
    "p2movetype": "IK_EXPR_FIELD_MOVE_TYPE",
    "frontedgedist": "IK_EXPR_FIELD_FRONT_EDGE_DIST",
    "frontedgebodydist": "IK_EXPR_FIELD_FRONT_EDGE_BODY_DIST",
    "backedgedist": "IK_EXPR_FIELD_BACK_EDGE_DIST",
    "anim": "IK_EXPR_FIELD_ANIM_NO",
    "facing": "IK_EXPR_FIELD_FACING",
    "backedgebodydist": "IK_EXPR_FIELD_BACK_EDGE_BODY_DIST",
    "animelem": "IK_EXPR_FIELD_ANIM_ELEM",
    "animtime": "IK_EXPR_FIELD_ANIM_TIME",
    "hitpausetime": "IK_EXPR_FIELD_HIT_PAUSE_TIME",
    "hitshakeover": "IK_EXPR_FIELD_HIT_SHAKE_OVER",
    "hitfall": "IK_EXPR_FIELD_GET_HIT_FALL",
    "canrecover": "IK_EXPR_FIELD_CAN_RECOVER",
    "hitover": "IK_EXPR_FIELD_HIT_OVER",
    "hitcount": "IK_EXPR_FIELD_HIT_COUNT",
    "uniqhitcount": "IK_EXPR_FIELD_UNIQ_HIT_COUNT",
    "inguarddist": "IK_EXPR_FIELD_IN_GUARD_DIST",
    "random": "IK_EXPR_FIELD_RANDOM",
    "numenemy": "IK_EXPR_FIELD_NUM_ENEMIES",
    "numproj": "IK_EXPR_FIELD_NUM_PROJECTILES",
    "numprojectile": "IK_EXPR_FIELD_NUM_PROJECTILES",
    "numprojectiles": "IK_EXPR_FIELD_NUM_PROJECTILES",
    "teamside": "IK_EXPR_FIELD_TEAM_SIDE",
    "winko": "IK_EXPR_FIELD_WIN_KO",
    "winperfect": "IK_EXPR_FIELD_WIN_PERFECT",
    "loseko": "IK_EXPR_FIELD_LOSE_KO",
}


def character_name_hash(name: str) -> int:
    value = 2166136261
    for byte in name.casefold().encode("utf-8"):
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value & 0x7fffffff


class _ExprCompiler(_ExprParser):
    """Compile the integer/runtime CNS expression subset to postfix bytecode."""

    def __init__(self, text: str, q16: bool = False):
        super().__init__(text)
        self.q16 = q16

    def _load_runtime_field(
        self,
        field: str,
        index: int = 0,
        redirect: str = "IK_EXPR_REDIRECT_SELF",
        redirect_id: int = 0,
        redirect_index: int = 0,
    ) -> list[dict]:
        code = self._load(field, index)
        if redirect != "IK_EXPR_REDIRECT_SELF":
            for instruction in code:
                if instruction.get("op") == "IK_EXPR_LOAD_FIELD":
                    instruction["redirect"] = redirect
                    if redirect == "IK_EXPR_REDIRECT_HELPER":
                        instruction["value1"] = redirect_id
                        instruction["redirect_index"] = redirect_index
        if not self.q16 or field == "IK_EXPR_FIELD_FVAR_Q16":
            if not self.q16 and field.endswith("_Q8"):
                return code + [{"op": "IK_EXPR_TRUNC_Q8"}]
            return code
        if field == "IK_EXPR_FIELD_HITDEF_ATTR":
            return code + [
                {"op": "IK_EXPR_PUSH_CONST", "value0": 65536},
                {"op": "IK_EXPR_MUL"},
            ]
        factor = (256 if field.endswith("_Q8") else 65536)
        return code + [
            {"op": "IK_EXPR_PUSH_CONST", "value0": factor},
            {"op": "IK_EXPR_MUL"},
        ]

    def parse(self) -> list[dict]:
        code = self._or()
        if self._peek() is not None:
            raise ValueError(f"unexpected token in expression: {self._peek()!r}")
        return code

    def _or(self) -> list[dict]:
        code = self._and()
        while self._peek() and self._peek()[1] == "||":
            self._take()
            code += self._and()
            code.append({"op": "IK_EXPR_OR"})
        return code

    def _and(self) -> list[dict]:
        code = self._equality()
        while self._peek() and self._peek()[1] == "&&":
            self._take()
            code += self._equality()
            code.append({"op": "IK_EXPR_AND"})
        return code

    def _equality(self) -> list[dict]:
        code = self._rel()
        while self._peek() and self._peek()[1] in ("=", "==", "!="):
            op = self._take()[1]
            code += self._rel()
            code.append({"op": "IK_EXPR_NE" if op == "!=" else "IK_EXPR_EQ"})
        return code

    def _rel(self) -> list[dict]:
        code = self._add()
        while self._peek() and self._peek()[1] in (">", "<", ">=", "<="):
            op = self._take()[1]
            code += self._add()
            code.append({"op": {
                ">": "IK_EXPR_GT", "<": "IK_EXPR_LT",
                ">=": "IK_EXPR_GE", "<=": "IK_EXPR_LE",
            }[op]})
        return code

    def _add(self) -> list[dict]:
        code = self._mul()
        while self._peek() and self._peek()[1] in ("+", "-"):
            op = self._take()[1]
            code += self._mul()
            code.append({"op": "IK_EXPR_ADD" if op == "+" else "IK_EXPR_SUB"})
        return code

    def _mul(self) -> list[dict]:
        code = self._power()
        while self._peek() and self._peek()[1] in ("*", "/", "%"):
            op = self._take()[1]
            code += self._power()
            code.append({"op": {
                "*": "IK_EXPR_MUL_Q16" if self.q16 else "IK_EXPR_MUL",
                "/": "IK_EXPR_DIV_Q16" if self.q16 else "IK_EXPR_DIV",
                "%": "IK_EXPR_MOD",
            }[op]})
        return code

    def _power(self) -> list[dict]:
        code = self._unary()
        if self._peek() and self._peek()[1] == "**":
            self._take()
            code += self._power()
            code.append({"op": "IK_EXPR_POW"})
        return code

    def _unary(self) -> list[dict]:
        if self._peek() and self._peek()[1] in ("-", "+", "!"):
            op = self._take()[1]
            code = self._unary()
            if op == "-":
                code.append({"op": "IK_EXPR_NEG"})
            elif op == "!":
                code.append({"op": "IK_EXPR_NOT"})
            return code
        return self._primary()

    @staticmethod
    def _load(field: str, index: int = 0) -> list[dict]:
        return [{"op": "IK_EXPR_LOAD_FIELD", "field": field,
                 "value0": index}]

    def _args(self) -> list[list[dict]]:
        args: list[list[dict]] = []
        if self._peek() and self._peek()[1] == ")":
            return args
        args.append(self._or())
        while self._peek() and self._peek()[1] == ",":
            self._take()
            args.append(self._or())
        return args

    @staticmethod
    def _constant_arg(code: list[dict], function: str) -> int:
        if len(code) != 1 or code[0].get("op") != "IK_EXPR_PUSH_CONST":
            raise ValueError(f"{function}() index must be a constant integer")
        return int(code[0]["value0"])

    def _integer_arg(self, code: list[dict], function: str) -> int:
        value = self._constant_arg(code, function)
        if self.q16:
            if value % 65536:
                raise ValueError(f"{function}() argument must be an integer")
            value //= 65536
        return value

    def _primary(self) -> list[dict]:
        tok = self._peek()
        if tok is None:
            raise ValueError("unexpected end of expression")
        if tok == ("op", "("):
            self._take()
            code = self._or()
            if self._peek() != ("op", ")"):
                raise ValueError("missing closing parenthesis")
            self._take()
            return code
        if tok[0] == "num":
            self._take()
            value = float(tok[1])
            if not self.q16 and int(value) != value:
                raise ValueError("runtime CNS expression requires integer constants")
            scaled = int(round(value * 65536)) if self.q16 else int(value)
            return [{"op": "IK_EXPR_PUSH_CONST", "value0": scaled}]
        if tok[0] != "ident":
            raise ValueError(f"unexpected token in expression: {tok!r}")

        name = self._take()[1]
        lower = name.lower()
        if lower == "ishelper" and self._peek() != ("op", "("):
            scale = 65536 if self.q16 else 1
            return (
                self._load_runtime_field("IK_EXPR_FIELD_ENTITY_TYPE") +
                [{"op": "IK_EXPR_PUSH_CONST", "value0": 2 * scale},
                 {"op": "IK_EXPR_EQ"}]
            )
        redirects = {
            "p2": "IK_EXPR_REDIRECT_P2",
            "enemy": "IK_EXPR_REDIRECT_P2",
            "enemynear": "IK_EXPR_REDIRECT_P2",
            "target": "IK_EXPR_REDIRECT_TARGET",
            "parent": "IK_EXPR_REDIRECT_PARENT",
            "root": "IK_EXPR_REDIRECT_ROOT",
        }
        if lower in redirects and self._peek() == ("op", ","):
            self._take()
            if self._peek() is None or self._peek()[0] != "ident":
                raise ValueError(f"missing redirected field after {name},")
            field_name = self._take()[1]
            field_lower = field_name.lower()
            redirect = redirects[lower]
            if field_lower == "const":
                if self._peek() != ("op", "("):
                    raise ValueError(f"{name},Const requires a constant name")
                self._take()
                const_name = self._peek()
                if const_name is None or const_name[0] != "ident":
                    raise ValueError(f"{name},Const requires a constant name")
                const_name = self._take()[1].casefold()
                if self._peek() != ("op", ")"):
                    raise ValueError(f"{name},Const takes one constant name")
                self._take()
                const_indexes = {
                    "size.head.pos.x": 1,
                    "size.head.pos.y": 2,
                    "size.mid.pos.x": 3,
                    "size.mid.pos.y": 4,
                }
                if const_name not in const_indexes:
                    raise ValueError(
                        f"unsupported redirected Const() value {const_name!r}")
                return self._load_runtime_field(
                    "IK_EXPR_FIELD_CHAR_CONSTANT",
                    const_indexes[const_name], redirect)
            if field_lower == "gethitvar":
                if self._peek() != ("op", "("):
                    raise ValueError(
                        f"{name},GetHitVar requires a field argument")
                self._take()
                argument = self._peek()
                if argument is None or argument[0] != "ident":
                    raise ValueError(
                        f"{name},GetHitVar requires a supported field name")
                hit_field = self._take()[1].casefold()
                if self._peek() != ("op", ")"):
                    raise ValueError(
                        f"{name},GetHitVar takes exactly one field name")
                self._take()
                fields = {
                    "animtype": "IK_EXPR_FIELD_GET_HIT_ANIM_TYPE",
                    "hitcount": "IK_EXPR_FIELD_GET_HIT_HIT_COUNT",
                    "groundtype": "IK_EXPR_FIELD_GET_HIT_GROUND_TYPE",
                    "slidetime": "IK_EXPR_FIELD_GET_HIT_SLIDE_TIME",
                    "ctrltime": "IK_EXPR_FIELD_GET_HIT_CTRL_TIME",
                    "xvel": "IK_EXPR_FIELD_GET_HIT_XVEL_Q8",
                    "yvel": "IK_EXPR_FIELD_GET_HIT_YVEL_Q8",
                    "yaccel": "IK_EXPR_FIELD_GET_HIT_YACCEL_Q16",
                    "fall": "IK_EXPR_FIELD_GET_HIT_FALL",
                    "fall.xvel": "IK_EXPR_FIELD_GET_HIT_FALL_XVEL_Q8",
                    "fall.yvel": "IK_EXPR_FIELD_GET_HIT_FALL_YVEL_Q8",
                    "fall.recover": "IK_EXPR_FIELD_GET_HIT_FALL_RECOVER",
                    "isbound": "IK_EXPR_FIELD_GET_HIT_IS_BOUND",
                    "chainid": "IK_EXPR_FIELD_GET_HIT_CHAIN_ID",
                }
                if hit_field not in fields:
                    raise ValueError(
                        f"unsupported GetHitVar field {hit_field!r}")
                return self._load_runtime_field(fields[hit_field], redirect=redirect)
            if self._peek() == ("op", "("):
                self._take()
                args = self._args()
                if self._peek() != ("op", ")"):
                    raise ValueError(
                        f"missing closing parenthesis in {name},{field_name}()")
                self._take()
                if field_lower in ("var", "sysvar", "fvar") and len(args) == 1:
                    index = self._constant_arg(args[0], field_name)
                    if self.q16:
                        if index % 65536:
                            raise ValueError(
                                f"{field_name}() index must be an integer constant")
                        index //= 65536
                    max_count = 60 if field_lower == "var" else 40
                    if index < 0 or index >= max_count:
                        raise ValueError(
                            f"{field_name}({index}) is outside the supported "
                            f"range 0..{max_count - 1}")
                    runtime_field = {
                        "var": "IK_EXPR_FIELD_VAR",
                        "sysvar": "IK_EXPR_FIELD_SYSVAR",
                        "fvar": "IK_EXPR_FIELD_FVAR_Q16",
                    }[field_lower]
                    return self._load_runtime_field(
                        runtime_field, index, redirect)
                if field_lower == "numtarget" and len(args) == 1:
                    target_id = self._constant_arg(args[0], field_name)
                    if self.q16:
                        if target_id % 65536:
                            raise ValueError(
                                "NumTarget() id must be an integer constant")
                        target_id //= 65536
                    return self._load_runtime_field(
                        "IK_EXPR_FIELD_NUM_TARGETS", target_id, redirect)
                if field_lower == "numhelper" and len(args) == 1:
                    helper_id = self._integer_arg(args[0], field_name)
                    if helper_id < 0 or helper_id > 2147483647:
                        raise ValueError(
                            "NumHelper() id is outside the signed 32-bit range")
                    return self._load_runtime_field(
                        "IK_EXPR_FIELD_NUM_HELPERS", helper_id, redirect)
                if field_lower == "animelemtime" and len(args) == 1:
                    elem = self._integer_arg(args[0], field_name)
                    if elem < 1 or elem > 65535:
                        raise ValueError(
                            "AnimElemTime() index must be in the range 1..65535")
                    return self._load_runtime_field(
                        "IK_EXPR_FIELD_ANIM_ELEM_TIME", elem, redirect)
                raise ValueError(
                    f"unsupported redirected function {name},{field_name}()")
            if field_lower in _RUNTIME_EXPR_FIELDS:
                return self._load_runtime_field(
                    _RUNTIME_EXPR_FIELDS[field_lower], redirect=redirect)
            if field_lower in ("pos", "vel"):
                axis = self._take()[1].lower()
                if axis not in ("x", "y"):
                    raise ValueError(
                        f"unsupported {name},{field_name} axis {axis!r}")
                field = {
                    ("pos", "x"): "IK_EXPR_FIELD_POS_X_Q8",
                    ("pos", "y"): "IK_EXPR_FIELD_POS_Y_Q8",
                    ("vel", "x"): "IK_EXPR_FIELD_VEL_X_Q8",
                    ("vel", "y"): "IK_EXPR_FIELD_VEL_Y_Q8",
                }[(field_lower, axis)]
                return self._load_runtime_field(field, redirect=redirect)
            if field_lower == "p2dist":
                axis = self._take()[1].lower()
                if axis not in ("x", "y"):
                    raise ValueError(
                        f"unsupported {name},P2Dist axis {axis!r}")
                field = (
                    "IK_EXPR_FIELD_P2_DIST_X_Q8" if axis == "x" else
                    "IK_EXPR_FIELD_P2_DIST_Y_Q8"
                )
                return self._load_runtime_field(field, redirect=redirect)
            raise ValueError(
                f"unsupported redirected symbol in runtime expression: "
                f"{name},{field_name}")
        if lower == "helper" and self._peek() == ("op", "("):
            self._take()
            args = self._args()
            if self._peek() != ("op", ")") or len(args) != 1:
                raise ValueError("Helper() redirection requires one constant id")
            self._take()
            helper_id = self._integer_arg(args[0], name)
            if helper_id < 0 or helper_id > 2147483647:
                raise ValueError("Helper() id is outside the signed 32-bit range")
            if self._peek() != ("op", ","):
                raise ValueError("Helper() requires a redirected field")
            self._take()
            field = self._peek()
            if field is None or field[0] != "ident":
                raise ValueError("Helper() requires a redirected field")
            field_name = self._take()[1]
            field_lower = field_name.casefold()
            redirect = "IK_EXPR_REDIRECT_HELPER"
            if field_lower in _RUNTIME_EXPR_FIELDS:
                return self._load_runtime_field(
                    _RUNTIME_EXPR_FIELDS[field_lower],
                    redirect=redirect, redirect_id=helper_id)
            if field_lower in ("pos", "vel"):
                axis = self._take()[1].lower()
                if axis not in ("x", "y"):
                    raise ValueError(
                        f"unsupported Helper() {field_name} axis {axis!r}")
                mapped = {
                    ("pos", "x"): "IK_EXPR_FIELD_POS_X_Q8",
                    ("pos", "y"): "IK_EXPR_FIELD_POS_Y_Q8",
                    ("vel", "x"): "IK_EXPR_FIELD_VEL_X_Q8",
                    ("vel", "y"): "IK_EXPR_FIELD_VEL_Y_Q8",
                }[(field_lower, axis)]
                return self._load_runtime_field(
                    mapped, redirect=redirect, redirect_id=helper_id)
            if field_lower in ("var", "sysvar", "fvar") and \
                    self._peek() == ("op", "("):
                self._take()
                args = self._args()
                if self._peek() != ("op", ")") or len(args) != 1:
                    raise ValueError(
                        f"Helper(),{field_name}() takes one constant index")
                self._take()
                index = self._integer_arg(args[0], field_name)
                max_count = 60 if field_lower == "var" else 40
                if index < 0 or index >= max_count:
                    raise ValueError(
                        f"{field_name}({index}) is outside 0..{max_count - 1}")
                field = {
                    "var": "IK_EXPR_FIELD_VAR",
                    "sysvar": "IK_EXPR_FIELD_SYSVAR",
                    "fvar": "IK_EXPR_FIELD_FVAR_Q16",
                }[field_lower]
                return self._load_runtime_field(
                    field, index, redirect, helper_id)
            raise ValueError(
                f"unsupported Helper() field in runtime expression: "
                f"{field_name}")
        if lower == "gethitvar" and self._peek() == ("op", "("):
            self._take()
            argument = self._peek()
            if argument is None or argument[0] != "ident":
                raise ValueError("GetHitVar() requires a supported field name")
            field_name = self._take()[1].casefold()
            if self._peek() != ("op", ")"):
                raise ValueError("GetHitVar() takes exactly one field name")
            self._take()
            fields = {
                "animtype": "IK_EXPR_FIELD_GET_HIT_ANIM_TYPE",
                "hitcount": "IK_EXPR_FIELD_GET_HIT_HIT_COUNT",
                "groundtype": "IK_EXPR_FIELD_GET_HIT_GROUND_TYPE",
                "slidetime": "IK_EXPR_FIELD_GET_HIT_SLIDE_TIME",
                "ctrltime": "IK_EXPR_FIELD_GET_HIT_CTRL_TIME",
                "xvel": "IK_EXPR_FIELD_GET_HIT_XVEL_Q8",
                "yvel": "IK_EXPR_FIELD_GET_HIT_YVEL_Q8",
                "yaccel": "IK_EXPR_FIELD_GET_HIT_YACCEL_Q16",
                "fall": "IK_EXPR_FIELD_GET_HIT_FALL",
                "fall.xvel": "IK_EXPR_FIELD_GET_HIT_FALL_XVEL_Q8",
                "fall.yvel": "IK_EXPR_FIELD_GET_HIT_FALL_YVEL_Q8",
                "fall.recover": "IK_EXPR_FIELD_GET_HIT_FALL_RECOVER",
                "isbound": "IK_EXPR_FIELD_GET_HIT_IS_BOUND",
                "chainid": "IK_EXPR_FIELD_GET_HIT_CHAIN_ID",
            }
            if field_name not in fields:
                raise ValueError(
                    f"unsupported GetHitVar field {field_name!r}")
            return self._load_runtime_field(fields[field_name])

        if lower == "hitdefattr" and self._peek() == ("op", "("):
            self._take()
            state_arg = self._peek()
            if state_arg is None or state_arg[0] != "ident":
                raise ValueError("HitDefAttr() requires a state class")
            self._take()
            if self._peek() != ("op", ","):
                raise ValueError("HitDefAttr() requires attack attributes")
            self._take()
            state_mask = 0
            for token in state_arg[1].upper():
                state_mask |= {"S": 1, "C": 2, "A": 4}.get(token, 0)
            if not state_mask:
                raise ValueError(
                    f"HitDefAttr() has unsupported state class {state_arg[1]!r}")
            attr_bits = {
                "NA": 1 << 0, "SA": 1 << 1, "HA": 1 << 2,
                "NP": 1 << 3, "SP": 1 << 4, "HP": 1 << 5,
                "NT": 1 << 6, "ST": 1 << 7, "HT": 1 << 8,
            }
            attr_mask = 0
            while True:
                attr_token = self._peek()
                if attr_token is None or attr_token[0] != "ident":
                    raise ValueError("HitDefAttr() requires attack attributes")
                attr_name = self._take()[1].upper()
                if attr_name in {"AA", "AP", "AT"}:
                    groups = {"AA": "NA SA HA", "AP": "NP SP HP",
                              "AT": "NT ST HT"}[attr_name]
                    attr_mask |= sum(attr_bits[name] for name in groups.split())
                elif attr_name in attr_bits:
                    attr_mask |= attr_bits[attr_name]
                else:
                    raise ValueError(
                        f"HitDefAttr() has unsupported attack {attr_name!r}")
                if self._peek() != ("op", ","):
                    break
                self._take()
            if self._peek() != ("op", ")"):
                raise ValueError(f"missing closing parenthesis in {name}()")
            self._take()
            packed = (state_mask << 16) | attr_mask
            code = self._load_runtime_field(
                "IK_EXPR_FIELD_HITDEF_ATTR", packed)
            return code

        if self._peek() == ("op", "("):
            self._take()
            args = self._args()
            if self._peek() != ("op", ")"):
                raise ValueError(f"missing closing parenthesis in {name}()")
            self._take()
            if lower == "animelemtime" and len(args) == 1:
                index = self._integer_arg(args[0], name)
                if index < 1 or index > 65535:
                    raise ValueError(
                        f"{name}() index must be in the range 1..65535")
                return self._load_runtime_field(
                    "IK_EXPR_FIELD_ANIM_ELEM_TIME", index)
            if lower == "animelemno" and len(args) == 1:
                if self._integer_arg(args[0], name) != 0:
                    raise ValueError("AnimElemNo currently supports only argument 0")
                return self._load_runtime_field("IK_EXPR_FIELD_ANIM_ELEM")
            if lower == "numtarget" and len(args) == 1:
                target_id = self._integer_arg(args[0], name)
                return self._load_runtime_field(
                    "IK_EXPR_FIELD_NUM_TARGETS", target_id)
            if lower == "abs" and len(args) == 1:
                return args[0] + [{"op": "IK_EXPR_ABS"}]
            if lower == "ishelper" and len(args) == 1:
                helper_id = self._integer_arg(args[0], name)
                scale = 65536 if self.q16 else 1
                return (
                    self._load_runtime_field("IK_EXPR_FIELD_ENTITY_TYPE") +
                    [{"op": "IK_EXPR_PUSH_CONST", "value0": 2 * scale},
                     {"op": "IK_EXPR_EQ"}] +
                    self._load_runtime_field("IK_EXPR_FIELD_ENTITY_ID") +
                    [{"op": "IK_EXPR_PUSH_CONST",
                      "value0": helper_id * scale},
                     {"op": "IK_EXPR_EQ"}, {"op": "IK_EXPR_AND"}]
                )
            if lower == "ceil" and len(args) == 1:
                code = args[0]
                if any(ins.get("field") == "IK_EXPR_FIELD_FVAR_Q16"
                       for ins in code):
                    return code + [{"op": "IK_EXPR_CEIL_Q16"}]
                return code
            if lower == "floor" and len(args) == 1:
                if self.q16:
                    return args[0] + [{"op": "IK_EXPR_FLOOR_Q16"}]
                return args[0]
            if lower == "command" and len(args) == 1:
                command_id = self._integer_arg(args[0], name)
                if command_id < 0 or command_id >= 128:
                    raise ValueError("command() id is outside 0..127")
                code = [{"op": "IK_EXPR_LOAD_COMMAND", "value0": command_id}]
                if self.q16:
                    code.extend([
                        {"op": "IK_EXPR_PUSH_CONST", "value0": 65536},
                        {"op": "IK_EXPR_MUL"},
                    ])
                return code
            if lower == "numhelper" and len(args) == 1:
                helper_id = self._integer_arg(args[0], name)
                if helper_id < 0 or helper_id > 2147483647:
                    raise ValueError(
                        "NumHelper() id is outside the signed 32-bit range")
                return self._load_runtime_field(
                    "IK_EXPR_FIELD_NUM_HELPERS", helper_id)
            if lower == "numexplod" and len(args) <= 1:
                explod_id = (
                    self._integer_arg(args[0], name)
                    if args else -2147483648)
                if explod_id < -2147483648 or explod_id > 2147483647:
                    raise ValueError(
                        "NumExplod() id is outside the signed 32-bit range")
                return self._load_runtime_field(
                    "IK_EXPR_FIELD_NUM_EXPLODS", explod_id)
            if lower in ("var", "sysvar", "fvar") and len(args) == 1:
                index = self._constant_arg(args[0], name)
                if self.q16:
                    if index % 65536:
                        raise ValueError(
                            f"{name}() index must be an integer constant")
                    index //= 65536
                max_count = 60 if lower == "var" else 40
                if index < 0 or index >= max_count:
                    raise ValueError(
                        f"{name}({index}) is outside the supported range 0..{max_count - 1}")
                field = {
                    "var": "IK_EXPR_FIELD_VAR",
                    "sysvar": "IK_EXPR_FIELD_SYSVAR",
                    "fvar": "IK_EXPR_FIELD_FVAR_Q16",
                }[lower]
                return self._load_runtime_field(field, index)
            if lower == "ifelse" and len(args) == 3:
                condition, when_true, when_false = args
                return (condition + when_true + when_false +
                        [{"op": "IK_EXPR_IFELSE"}])
            raise ValueError(f"unsupported function in runtime expression: {name}")

        if lower in ("true", "false"):
            return [{"op": "IK_EXPR_PUSH_CONST", "value0": int(lower == "true")}]
        if lower == "screenpos":
            axis = self._take()[1].lower()
            if axis != "y":
                raise ValueError(
                    "ScreenPos X is unsupported without horizontal camera projection")
            # The fight runtime has a fixed vertical camera, so screen-space Y
            # is the entity's world-space Y in this engine.
            return self._load_runtime_field("IK_EXPR_FIELD_POS_Y_Q8")
        if lower == "screenposy":
            return self._load_runtime_field("IK_EXPR_FIELD_POS_Y_Q8")
        if lower == "numtarget":
            return self._load_runtime_field("IK_EXPR_FIELD_NUM_TARGETS", -1)
        if lower in ("p2statetype", "p2movetype"):
            return self._load_runtime_field(
                _RUNTIME_EXPR_FIELDS[lower],
                redirect="IK_EXPR_REDIRECT_P2",
            )
        if lower in _RUNTIME_EXPR_FIELDS:
            return self._load_runtime_field(_RUNTIME_EXPR_FIELDS[lower])
        if lower == "p2stateno":
            return self._load_runtime_field(
                "IK_EXPR_FIELD_STATE_NO",
                redirect="IK_EXPR_REDIRECT_P2",
            )
        if lower == "p2namehash":
            return self._load_runtime_field(
                "IK_EXPR_FIELD_CHARACTER_NAME_HASH",
                redirect="IK_EXPR_REDIRECT_P2",
            )
        if lower == "namehash":
            return self._load_runtime_field(
                "IK_EXPR_FIELD_CHARACTER_NAME_HASH")
        if lower in ("pos", "vel"):
            axis = self._take()[1].lower()
            if axis not in ("x", "y"):
                raise ValueError(f"unsupported {name} axis {axis!r}")
            field = {
                ("pos", "x"): "IK_EXPR_FIELD_POS_X_Q8",
                ("pos", "y"): "IK_EXPR_FIELD_POS_Y_Q8",
                ("vel", "x"): "IK_EXPR_FIELD_VEL_X_Q8",
                ("vel", "y"): "IK_EXPR_FIELD_VEL_Y_Q8",
            }[(lower, axis)]
            return self._load_runtime_field(field)
        if lower == "p2dist":
            axis = self._take()[1].lower()
            if axis not in ("x", "y"):
                raise ValueError(f"unsupported P2Dist axis {axis!r}")
            return self._load_runtime_field(
                "IK_EXPR_FIELD_P2_DIST_X_Q8" if axis == "x" else
                "IK_EXPR_FIELD_P2_DIST_Y_Q8"
            )
        if lower == "p2bodydist":
            axis = self._take()[1].lower()
            if axis == "x":
                return self._load_runtime_field(
                    "IK_EXPR_FIELD_BODY_DIST_X",
                    redirect="IK_EXPR_REDIRECT_P2",
                )
            if axis == "y":
                return self._load_runtime_field("IK_EXPR_FIELD_P2_DIST_Y_Q8")
            raise ValueError(f"unsupported P2BodyDist axis {axis!r}")
        raise ValueError(f"unsupported symbol in runtime expression: {name}")


def _normalize_logical_operators(text: str) -> str:
    """Normalize MUGEN's single-character logical operators."""
    output: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if quote is not None:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in ('"', "'"):
            quote = char
            output.append(char)
            index += 1
            continue
        if char == "|":
            output.append("||")
            index += 2 if text[index:index + 2] == "||" else 1
            continue
        if char == "&":
            output.append("&&")
            index += 2 if text[index:index + 2] == "&&" else 1
            continue
        output.append(char)
        index += 1
    return "".join(output)


def compile_cns_expr(
    text: str,
    q16: bool = False,
    *,
    command_ids: dict[str, int] | None = None,
    localcoord_x: float = 320.0,
    const_values: dict[str, float] | None = None,
    self_anims: set[int] | None = None,
) -> list[dict]:
    def expand_state_range(match: re.Match[str]) -> str:
        field, operator, low, high = match.groups()
        field = field.lower()
        if operator == "=":
            return f"(({field}>={low}) && ({field}<={high}))"
        return f"(({field}<{low}) || ({field}>{high}))"

    def expand_interval(match: re.Match[str]) -> str:
        field, operator, opening, low, high, closing = match.groups()
        low_op = ">=" if opening == "[" else ">"
        high_op = "<=" if closing == "]" else "<"
        if operator in ("=", "=="):
            return (
                f"(({field}{low_op}{low}) && "
                f"({field}{high_op}{high}))"
            )
        outside_low_op = "<" if opening == "[" else "<="
        outside_high_op = ">" if closing == "]" else ">="
        return (
            f"(({field}{outside_low_op}{low}) || "
            f"({field}{outside_high_op}{high}))"
        )

    normalized = _normalize_logical_operators(text)
    normalized = re.sub(
        r"\bstagevar\s*\(\s*info\.author\s*\)\s*(==|!=|=)\s*"
        r"\"([^\"]*)\"",
        lambda match: (
            f"stageauthorhash {match.group(1)} "
            f"{character_name_hash(match.group(2))}"
        ),
        normalized,
        flags=re.I,
    )
    def expand_time_mod(match: re.Match[str]) -> str:
        divisor = int(match.group(2))
        if divisor <= 0:
            raise ValueError("TimeMod divisor must be a positive integer")
        return f"((time % {divisor}) {match.group(1)} {match.group(3)})"

    normalized = re.sub(
        r"\btimemod\s*(==|!=|=)\s*(\d+)\s*,\s*(-?\d+)",
        expand_time_mod,
        normalized,
        flags=re.I,
    )
    def character_name(match: re.Match[str]) -> str:
        field, operator, name = match.groups()
        return f"{field}hash {operator} {character_name_hash(name)}"

    normalized = re.sub(
        r"\b(p2name|name)\s*(==|!=|=)\s*\"([^\"]+)\"",
        character_name,
        normalized,
        flags=re.I,
    )
    if self_anims is not None:
        normalized = expand_dynamic_self_anim_exist(normalized, self_anims)
    normalized = re.sub(
        r"\bconst\s*\(\s*([a-z][a-z0-9_.]*)\s*\)",
        lambda match: str((const_values or {})[match.group(1).casefold()])
        if match.group(1).casefold() in (const_values or {}) else match.group(0),
        normalized,
        flags=re.I,
    )
    normalized = re.sub(r"\balive\b", "(life > 0)", normalized, flags=re.I)
    def const_720p(match: re.Match[str]) -> str:
        value = float(match.group(1)) * localcoord_x / 1280.0
        if not q16 and int(value) != value:
            raise ValueError(
                f"Const720p({match.group(1)}) is fractional in "
                f"localcoord.x={localcoord_x:g}; expression needs Q16 context")
        return str(int(value) if int(value) == value else value)

    normalized = re.sub(
        r"\bconst720p\s*\(\s*(-?\d+(?:\.\d+)?)\s*\)",
        const_720p,
        normalized,
        flags=re.I,
    )
    def command_name(match: re.Match[str]) -> str:
        name = match.group(2)
        command_id = (command_ids or {}).get(name.casefold())
        if command_id is None:
            raise ValueError(
                f"command {name!r} has no matching --command-source entry")
        return f"command({command_id}) {match.group(1)} 1"

    normalized = re.sub(
        r"\bcommand\s*(=|!=|==)\s*\"([^\"]+)\"",
        command_name,
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\bfloor\s*\(\s*(\d+)\s*\*\s*ifelse\s*\(\s*"
        r"(.+?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*"
        r"(-?\d+(?:\.\d+)?)\s*\)\s*\)",
        lambda match: f"IfElse({match.group(2)},"
        f"{int(math.floor(int(match.group(1)) * float(match.group(3))))},"
        f"{int(math.floor(int(match.group(1)) * float(match.group(4))))})",
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\bceil\s*\(\s*(\d+(?:\.\d+)?)\s*\*\s*"
        r"(parent|root|p2)\s*,\s*fvar\s*\(\s*(\d+)\s*\)"
        r"\s*\*\s*(\d+)\s*\)",
        lambda match: (
            f"Ceil({match.group(2)},FVar({match.group(3)})*"
            f"{int(round(float(match.group(1)) * int(match.group(4))))})"
        ),
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\banimelemno\s*\(\s*0\s*\)\s*(!=|=)\s*"
        r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]",
        lambda match: (
            f"((animelem >= {match.group(2)}) && "
            f"(animelem <= {match.group(3)}))"
            if match.group(1) == "=" else
            f"((animelem < {match.group(2)}) || "
            f"(animelem > {match.group(3)}))"
        ),
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\banimelem\s*=\s*(\d+)\s*,\s*=\s*"
        r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]",
        lambda match: (
            f"((animelemtime({match.group(1)}) >= {match.group(2)}) && "
            f"(animelemtime({match.group(1)}) <= {match.group(3)}))"
        ),
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\banimelem\s*=\s*(\d+)\s*,\s*(-?\d+)\b",
        lambda match: (
            f"animelemtime({match.group(1)}) = {match.group(2)}"
        ),
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\b((?:(?:p2|enemy|enemynear|parent|root)\s*,\s*)?"
        r"(?:stateno|p2stateno|prevstateno|anim))\s*(==|!=|=)\s*"
        r"([\[(])\s*(-?\d+)\s*,\s*(-?\d+)\s*([\])])",
        expand_interval,
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\b(time|gametime)\s*(==|!=|=)\s*([\[(])\s*"
        r"(-?\d+)\s*,\s*(-?\d+)\s*([\])])",
        expand_interval,
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\b(p2bodydist\s+x)\s*(==|!=|=)\s*([\[(])\s*"
        r"(-?\d+)\s*,\s*(-?\d+)\s*([\])])",
        expand_interval,
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\b((?:(?:parent|root|p2)\s*,\s*)?"
        r"(?:var|sysvar|fvar)\s*\(\s*\d+\s*\))"
        r"\s*(!=|=)\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]",
        lambda match: (
            f"(({match.group(1)} >= {match.group(3)}) && "
            f"({match.group(1)} <= {match.group(4)}))"
            if match.group(2) == "=" else
            f"(({match.group(1)} < {match.group(3)}) || "
            f"({match.group(1)} > {match.group(4)}))"
        ),
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\b(gethitvar\s*\(\s*[a-z][a-z0-9_.]*\s*\))"
        r"\s*(!=|=)\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]",
        lambda match: (
            f"(({match.group(1)} >= {match.group(3)}) && "
            f"({match.group(1)} <= {match.group(4)}))"
            if match.group(2) == "=" else
            f"(({match.group(1)} < {match.group(3)}) || "
            f"({match.group(1)} > {match.group(4)}))"
        ),
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\b(random(?:\s*%\s*\d+)?)\s*(!=|=)\s*"
        r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]",
        lambda match: (
            f"(({match.group(1)} >= {match.group(3)}) && "
            f"({match.group(1)} <= {match.group(4)}))"
            if match.group(2) == "=" else
            f"(({match.group(1)} < {match.group(3)}) || "
            f"({match.group(1)} > {match.group(4)}))"
        ),
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\b([a-z][a-z0-9_]*)\s*(!=|=)\s*"
        r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]",
        lambda match: (
            f"(({match.group(1)} >= {match.group(3)}) && "
            f"({match.group(1)} <= {match.group(4)}))"
            if match.group(2) == "=" else
            f"(({match.group(1)} < {match.group(3)}) || "
            f"({match.group(1)} > {match.group(4)}))"
        ),
        normalized,
        flags=re.I,
    )
    state_types = {"u": 0, "s": 1, "c": 2, "a": 3, "l": 4}
    move_types = {"u": 0, "i": 1, "a": 2, "h": 3}
    for field in ("p2statetype", "statetype"):
        normalized = re.sub(
            rf"\b{field}\s*(=|!=)\s*([UCALS])\b",
            lambda match: f"{field}{match.group(1)}"
            f"{state_types[match.group(2).lower()]}",
            normalized,
            flags=re.I,
        )
    for field in ("p2movetype", "movetype"):
        normalized = re.sub(
            rf"\b{field}\s*(=|!=)\s*([UIAH])\b",
            lambda match: f"{field}{match.group(1)}"
            f"{move_types[match.group(2).lower()]}",
            normalized,
            flags=re.I,
        )
    normalized = re.sub(
        r"\banimelem\s*=\s*(\d+)\s*,\s*(<=|<|>=|>|=)\s*(-?\d+)",
        lambda match: (
            f"animelemtime({match.group(1)}) "
            f"{match.group(2)} {match.group(3)}"
        ),
        normalized,
        flags=re.I,
    )
    code = _ExprCompiler(normalized, q16=q16).parse()
    if len(code) > 255:
        raise ValueError("runtime CNS expression exceeds 255 instructions")
    return code

def expand_dynamic_self_anim_exist(
    text: str, self_anims: set[int] | None
) -> str:
    """Fold dynamic SelfAnimExist expressions against this character's AIR.

    The runtime only has the current animation number, not the source AIR
    action table. Expand the two common arithmetic forms into exact boolean
    expressions so missing actions remain false at runtime.
    """
    if self_anims is None:
        return text

    def terms_for_values(values: set[int], field: str) -> str:
        if not values:
            return "0"
        ordered = sorted(values)
        ranges: list[tuple[int, int]] = []
        start = previous = ordered[0]
        for value in ordered[1:]:
            if value == previous + 1:
                previous = value
                continue
            ranges.append((start, previous))
            start = previous = value
        ranges.append((start, previous))
        checks = [
            f"({field}>={low})" if low == high else
            f"(({field}>={low}) && ({field}<={high}))"
            for low, high in ranges
        ]
        return "(" + " || ".join(checks) + ")"

    def replace(match: re.Match[str]) -> str:
        negated, expression = match.groups()
        expression = re.sub(r"\s+", "", expression).casefold()
        fixed_action = re.fullmatch(r"\d+", expression)
        if fixed_action:
            result = "1" if int(expression) in self_anims else "0"
        elif expression in {"anim", "anim+0"}:
            result = terms_for_values(self_anims, "anim")
        else:
            anim_offset = re.fullmatch(r"anim([+-])(\d+)", expression)
            hit_offset = re.fullmatch(
                r"(\d+)\+gethitvar\(animtype\)", expression)
            if anim_offset:
                sign, amount = anim_offset.groups()
                offset = int(amount) * (1 if sign == "+" else -1)
                result = terms_for_values(
                    {action - offset for action in self_anims}, "anim")
            elif hit_offset:
                base = int(hit_offset.group(1))
                values = sorted(
                    hit_type for hit_type in range(0, 16)
                    if base + hit_type in self_anims)
                if len(values) > 8:
                    raise ValueError(
                        "SelfAnimExist dynamic animtype has too many cases")
                result = "(" + " || ".join(
                    f"(gethitvar(animtype)={value})" for value in values
                ) + ")" if values else "0"
            else:
                raise ValueError(
                    f"unsupported dynamic SelfAnimExist({expression})")
        return f"!({result})" if negated else result

    return re.sub(
        r"(!?)\s*SelfAnimExist\s*\(\s*([^()]+)\s*\)",
        replace,
        text,
        flags=re.I,
    )
