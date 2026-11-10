"""Expression parsing and bytecode compilation for CNS triggers and values."""
from __future__ import annotations

import re

try:
    from .ikemen_cns_expr_parser import _ExprParser
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_expr_parser import _ExprParser
try:
    from .ikemen_cns_expr_normalize import (
        character_name_hash,
        expand_dynamic_self_anim_exist,
        normalize_cns_expr,
    )
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_expr_normalize import (
        character_name_hash,
        expand_dynamic_self_anim_exist,
        normalize_cns_expr,
    )


_RUNTIME_EXPR_FIELDS = {
    "stateno": "IK_EXPR_FIELD_STATE_NO",
    "prevstateno": "IK_EXPR_FIELD_PREV_STATE_NO",
    "time": "IK_EXPR_FIELD_STATE_TIME",
    "gametime": "IK_EXPR_FIELD_GAME_TIME",
    "roundstate": "IK_EXPR_FIELD_ROUND_STATE",
    "matchover": "IK_EXPR_FIELD_MATCH_OVER",
    "win": "IK_EXPR_FIELD_WIN",
    "lose": "IK_EXPR_FIELD_LOSE",
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
    "id": "IK_EXPR_FIELD_ENTITY_ID",
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
    "projcontact": "IK_EXPR_FIELD_PROJ_CONTACT",
    "projhit": "IK_EXPR_FIELD_PROJ_HIT",
    "projguarded": "IK_EXPR_FIELD_PROJ_GUARDED",
    "projcontacttime": "IK_EXPR_FIELD_PROJ_CONTACT_TIME",
    "projhittime": "IK_EXPR_FIELD_PROJ_HIT_TIME",
    "projguardedtime": "IK_EXPR_FIELD_PROJ_GUARDED_TIME",
    "teamside": "IK_EXPR_FIELD_TEAM_SIDE",
    "winko": "IK_EXPR_FIELD_WIN_KO",
    "winperfect": "IK_EXPR_FIELD_WIN_PERFECT",
    "loseko": "IK_EXPR_FIELD_LOSE_KO",
}

_PROJECTILE_QUERY_FIELDS = {
    "projcontact": "IK_EXPR_FIELD_PROJ_CONTACT",
    "projhit": "IK_EXPR_FIELD_PROJ_HIT",
    "projguarded": "IK_EXPR_FIELD_PROJ_GUARDED",
    "projcontacttime": "IK_EXPR_FIELD_PROJ_CONTACT_TIME",
    "projhittime": "IK_EXPR_FIELD_PROJ_HIT_TIME",
    "projguardedtime": "IK_EXPR_FIELD_PROJ_GUARDED_TIME",
}


class _ExprCompiler(_ExprParser):
    """Compile the integer/runtime CNS expression subset to postfix bytecode."""

    def __init__(
        self, text: str, q16: bool = False, localcoord_x: float = 320.0
    ):
        super().__init__(text)
        self.q16 = q16
        self.localcoord_x = localcoord_x

    def _load_runtime_field(
        self,
        field: str,
        index: int = 0,
        redirect: str = "IK_EXPR_REDIRECT_SELF",
        redirect_id: int | None = None,
        redirect_index: int = 0,
    ) -> list[dict]:
        code = self._load(field, index)
        if redirect != "IK_EXPR_REDIRECT_SELF":
            for instruction in code:
                if instruction.get("op") == "IK_EXPR_LOAD_FIELD":
                    instruction["redirect"] = redirect
                    if redirect in {
                        "IK_EXPR_REDIRECT_HELPER",
                        "IK_EXPR_REDIRECT_TARGET",
                    }:
                        instruction["value1"] = (
                            redirect_id if redirect_id is not None else
                            -1 if redirect == "IK_EXPR_REDIRECT_TARGET" else 0
                        )
                        instruction["redirect_index"] = redirect_index
        if not self.q16 or field in {
            "IK_EXPR_FIELD_FVAR_Q16",
            "IK_EXPR_FIELD_SYSFVAR_Q16",
            "IK_EXPR_FIELD_STAGE_AUTHOR_MATCH",
            "IK_EXPR_FIELD_CHARACTER_NAME_HASH",
            "IK_EXPR_FIELD_CHARACTER_AUTHOR_HASH",
        }:
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

    def _root_dist(self, axis: str) -> list[dict]:
        if axis not in ("x", "y"):
            raise ValueError(f"unsupported RootDist axis {axis!r}")
        field = (
            "IK_EXPR_FIELD_POS_X_Q8" if axis == "x" else
            "IK_EXPR_FIELD_POS_Y_Q8"
        )
        code = (
            self._load_runtime_field(
                field, redirect="IK_EXPR_REDIRECT_ROOT") +
            self._load_runtime_field(field) +
            [{"op": "IK_EXPR_SUB"}]
        )
        if axis == "x":
            code = (
                self._load_runtime_field("IK_EXPR_FIELD_FACING") + code +
                [{"op": "IK_EXPR_MUL_Q16" if self.q16 else "IK_EXPR_MUL"}]
            )
        return code

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
            if self._peek() == ("op", "["):
                self._take()
                lower = self._rel()
                if self._peek() != ("op", ","):
                    raise ValueError("range comparison requires two bounds")
                self._take()
                upper = self._rel()
                if self._peek() != ("op", "]"):
                    raise ValueError("range comparison is missing closing ]")
                self._take()
                if op == "!=":
                    code = (
                        code + lower + [{"op": "IK_EXPR_LT"}] +
                        code + upper + [{"op": "IK_EXPR_GT"},
                                        {"op": "IK_EXPR_OR"}]
                    )
                else:
                    code = (
                        code + lower + [{"op": "IK_EXPR_GE"}] +
                        code + upper + [{"op": "IK_EXPR_LE"},
                                        {"op": "IK_EXPR_AND"}]
                    )
                continue
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

    def _args(self, *, integer_literals: bool = False) -> list[list[dict]]:
        args: list[list[dict]] = []
        if self._peek() and self._peek()[1] == ")":
            return args

        def argument() -> list[dict]:
            if integer_literals:
                start = self.i
                sign = 1
                if self._peek() and self._peek()[1] in ("+", "-"):
                    sign = -1 if self._take()[1] == "-" else 1
                token = self._peek()
                if token and token[0] == "num" and re.fullmatch(
                    r"\d+(?:\.0+)?", token[1]
                ):
                    self._take()
                    if self._peek() is None or self._peek()[1] in (",", ")"):
                        return [{
                            "op": "IK_EXPR_PUSH_CONST",
                            "value0": sign * int(token[1].split(".", 1)[0]),
                            "integer_literal": True,
                        }]
                self.i = start
            return self._or()

        args.append(argument())
        while self._peek() and self._peek()[1] == ",":
            self._take()
            args.append(argument())
        return args

    @staticmethod
    def _constant_arg(code: list[dict], function: str) -> int:
        if len(code) != 1 or code[0].get("op") != "IK_EXPR_PUSH_CONST":
            raise ValueError(f"{function}() index must be a constant integer")
        return int(code[0]["value0"])

    def _integer_arg(self, code: list[dict], function: str) -> int:
        value = self._constant_arg(code, function)
        if code[0].get("integer_literal"):
            return value
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
            if not -(1 << 31) <= scaled <= (1 << 31) - 1:
                raise ValueError(
                    f"runtime CNS expression constant is out of range: {tok[1]}"
                )
            return [{"op": "IK_EXPR_PUSH_CONST", "value0": scaled}]
        if tok[0] != "ident":
            raise ValueError(f"unexpected token in expression: {tok!r}")

        name = self._take()[1]
        lower = name.lower()
        name_hash_functions = {
            "nameis": (
                "IK_EXPR_FIELD_CHARACTER_NAME_HASH",
                "IK_EXPR_REDIRECT_SELF"),
            "p1nameis": (
                "IK_EXPR_FIELD_CHARACTER_NAME_HASH",
                "IK_EXPR_REDIRECT_SELF"),
            "p2nameis": (
                "IK_EXPR_FIELD_CHARACTER_NAME_HASH",
                "IK_EXPR_REDIRECT_P2"),
            "enemynameis": (
                "IK_EXPR_FIELD_CHARACTER_NAME_HASH",
                "IK_EXPR_REDIRECT_P2"),
            "enemynearnameis": (
                "IK_EXPR_FIELD_CHARACTER_NAME_HASH",
                "IK_EXPR_REDIRECT_P2"),
            "targetnameis": (
                "IK_EXPR_FIELD_CHARACTER_NAME_HASH",
                "IK_EXPR_REDIRECT_TARGET"),
            "parentnameis": (
                "IK_EXPR_FIELD_CHARACTER_NAME_HASH",
                "IK_EXPR_REDIRECT_PARENT"),
            "rootnameis": (
                "IK_EXPR_FIELD_CHARACTER_NAME_HASH",
                "IK_EXPR_REDIRECT_ROOT"),
            "authornameis": (
                "IK_EXPR_FIELD_CHARACTER_AUTHOR_HASH",
                "IK_EXPR_REDIRECT_SELF"),
            "p1authornameis": (
                "IK_EXPR_FIELD_CHARACTER_AUTHOR_HASH",
                "IK_EXPR_REDIRECT_SELF"),
            "p2authornameis": (
                "IK_EXPR_FIELD_CHARACTER_AUTHOR_HASH",
                "IK_EXPR_REDIRECT_P2"),
            "enemyauthornameis": (
                "IK_EXPR_FIELD_CHARACTER_AUTHOR_HASH",
                "IK_EXPR_REDIRECT_P2"),
            "enemynearauthornameis": (
                "IK_EXPR_FIELD_CHARACTER_AUTHOR_HASH",
                "IK_EXPR_REDIRECT_P2"),
            "targetauthornameis": (
                "IK_EXPR_FIELD_CHARACTER_AUTHOR_HASH",
                "IK_EXPR_REDIRECT_TARGET"),
            "parentauthornameis": (
                "IK_EXPR_FIELD_CHARACTER_AUTHOR_HASH",
                "IK_EXPR_REDIRECT_PARENT"),
            "rootauthornameis": (
                "IK_EXPR_FIELD_CHARACTER_AUTHOR_HASH",
                "IK_EXPR_REDIRECT_ROOT"),
        }
        if lower in name_hash_functions:
            if self._peek() != ("op", "("):
                raise ValueError(f"{name} requires one hash argument")
            self._take()
            args = self._args(integer_literals=True)
            if len(args) != 1 or self._peek() != ("op", ")"):
                raise ValueError(f"{name} requires one hash argument")
            self._take()
            expected_hash = self._integer_arg(args[0], name)
            if not 0 <= expected_hash <= 0x7fffffff:
                raise ValueError(f"{name} hash is outside the supported range")
            field, redirect = name_hash_functions[lower]
            code = self._load_runtime_field(field, redirect=redirect)
            code += [
                {"op": "IK_EXPR_PUSH_CONST", "value0": expected_hash},
                {"op": "IK_EXPR_EQ"},
            ]
            if self.q16:
                code += [
                    {"op": "IK_EXPR_PUSH_CONST", "value0": 65536},
                    {"op": "IK_EXPR_MUL"},
                ]
            return code
        if lower == "numpartner":
            # This runtime has two fighter slots on opposing teams, so a
            # fighter has no same-side partners. Match NumPartner's value in
            # that supported 1P-versus-2P mode without adding a fictitious
            # runtime player field.
            return [{
                "op": "IK_EXPR_PUSH_CONST",
                "value0": 0,
            }]
        projectile_query = re.fullmatch(
            r"(projcontacttime|projhittime|projguardedtime|"
            r"projcontact|projhit|projguarded)(\d+)", lower)
        if projectile_query:
            field_name, projectile_id = projectile_query.groups()
            if int(projectile_id) > 2147483647:
                raise ValueError(
                    f"{name} ID is outside the signed 32-bit range")
            return self._load_runtime_field(
                _PROJECTILE_QUERY_FIELDS[field_name], int(projectile_id))
        if lower == "playerid" and self._peek() == ("op", "("):
            self._take()
            args = self._args()
            if self._peek() != ("op", ")") or len(args) != 1:
                raise ValueError("PlayerID() redirection requires one player ID")
            self._take()
            if self._peek() != ("op", ","):
                raise ValueError("PlayerID() requires a redirected field")
            self._take()
            field_token = self._peek()
            if field_token is None or field_token[0] != "ident":
                raise ValueError("PlayerID() requires a redirected field")
            field_name = self._take()[1]
            field_lower = field_name.casefold()
            if field_lower == "ishelper":
                # PlayerID addresses one of the runtime's two fighter slots;
                # neither slot can be a helper.
                return [{"op": "IK_EXPR_PUSH_CONST", "value0": 0}]
            if field_lower == "teamside":
                player_code = list(args[0])
                if self.q16 or any(ins.get("field") in {
                        "IK_EXPR_FIELD_FVAR_Q16",
                        "IK_EXPR_FIELD_SYSFVAR_Q16",
                } for ins in player_code):
                    player_code.extend([
                        {"op": "IK_EXPR_FLOOR_Q16"},
                        {"op": "IK_EXPR_TRUNC_Q16"},
                    ])
                field_code = self._load_runtime_field(
                    "IK_EXPR_FIELD_TEAM_SIDE")
                field_code[0]["op"] = "IK_EXPR_LOAD_PLAYER_FIELD"
                return player_code + field_code
            if field_lower == "numexplod" and \
                    self._peek() == ("op", "("):
                self._take()
                explod_args = self._args(integer_literals=True)
                if self._peek() != ("op", ")") or len(explod_args) > 1:
                    raise ValueError(
                        "PlayerID(),NumExplod() takes at most one ID")
                self._take()
                explod_id = (
                    self._integer_arg(explod_args[0], field_name)
                    if explod_args else -2147483648)
                if explod_id < -2147483648 or explod_id > 2147483647:
                    raise ValueError(
                        "NumExplod() ID is outside the signed 32-bit range")
                player_code = list(args[0])
                if self.q16 or any(ins.get("field") in {
                        "IK_EXPR_FIELD_FVAR_Q16",
                        "IK_EXPR_FIELD_SYSFVAR_Q16",
                } for ins in player_code):
                    player_code.extend([
                        {"op": "IK_EXPR_FLOOR_Q16"},
                        {"op": "IK_EXPR_TRUNC_Q16"},
                    ])
                field_code = self._load_runtime_field(
                    "IK_EXPR_FIELD_NUM_EXPLODS", explod_id)
                for instruction in field_code:
                    if instruction.get("op") == "IK_EXPR_LOAD_FIELD":
                        instruction["op"] = "IK_EXPR_LOAD_PLAYER_FIELD"
                return player_code + field_code
            if field_lower not in {"var", "sysvar", "fvar", "sysfvar"} or \
                    self._peek() != ("op", "("):
                raise ValueError(
                    f"unsupported PlayerID() field {field_name!r}")
            self._take()
            index_args = self._args()
            if self._peek() != ("op", ")") or len(index_args) != 1:
                raise ValueError(
                    f"PlayerID(),{field_name}() requires one index")
            self._take()
            max_count = {
                "var": 60, "fvar": 40, "sysvar": 5, "sysfvar": 5,
            }[field_lower]
            runtime_field = {
                "var": "IK_EXPR_FIELD_VAR",
                "sysvar": "IK_EXPR_FIELD_SYSVAR",
                "fvar": "IK_EXPR_FIELD_FVAR_Q16",
                "sysfvar": "IK_EXPR_FIELD_SYSFVAR_Q16",
            }[field_lower]
            player_code = list(args[0])
            if self.q16 or any(ins.get("field") in {
                    "IK_EXPR_FIELD_FVAR_Q16",
                    "IK_EXPR_FIELD_SYSFVAR_Q16",
            } for ins in player_code):
                player_code.extend([
                    {"op": "IK_EXPR_FLOOR_Q16"},
                    {"op": "IK_EXPR_TRUNC_Q16"},
                ])
            index_code = list(index_args[0])
            is_constant_index = (
                len(index_code) == 1 and
                index_code[0].get("op") == "IK_EXPR_PUSH_CONST")
            if is_constant_index:
                index = self._integer_arg(index_code, field_name)
                if index < 0 or index >= max_count:
                    raise ValueError(
                        f"PlayerID(),{field_name}({index}) is outside "
                        f"0..{max_count - 1}")
                field_code = self._load_runtime_field(runtime_field, index)
                for instruction in field_code:
                    if instruction.get("op") == "IK_EXPR_LOAD_FIELD":
                        instruction["op"] = "IK_EXPR_LOAD_PLAYER_FIELD"
                return player_code + field_code
            if self.q16:
                index_code.append({"op": "IK_EXPR_TRUNC_Q16"})
            return player_code + index_code + [{
                "op": "IK_EXPR_LOAD_PLAYER_FIELD_DYNAMIC_INDEX",
                "field": runtime_field,
            }]
        if lower == "ishelper" and self._peek() == ("op", "("):
            self._take()
            sign = -1 if self._peek() == ("op", "-") else 1
            if sign < 0:
                self._take()
            token = self._peek()
            if token is None or token[0] != "num" or not re.fullmatch(
                    r"\d+", token[1]):
                raise ValueError("IsHelper() requires an integer ID")
            helper_id = sign * int(self._take()[1])
            if self._peek() != ("op", ")"):
                raise ValueError("IsHelper() requires one integer ID")
            self._take()
            return (
                self._load_runtime_field("IK_EXPR_FIELD_ENTITY_TYPE") +
                [{"op": "IK_EXPR_PUSH_CONST", "value0": 2},
                 {"op": "IK_EXPR_EQ"}] +
                self._load("IK_EXPR_FIELD_ENTITY_ID") +
                [{"op": "IK_EXPR_PUSH_CONST", "value0": helper_id},
                 {"op": "IK_EXPR_EQ"}, {"op": "IK_EXPR_AND"}]
            )
        if lower.startswith("rawcmp_") and self._peek() == ("op", "("):
            parts = lower.split("_")
            if len(parts) < 3:
                raise ValueError(f"unsupported integer comparison {name!r}")
            field_name, operator = "_".join(parts[1:-1]), parts[-1]
            operators = {
                "eq": "IK_EXPR_EQ", "ne": "IK_EXPR_NE",
                "lt": "IK_EXPR_LT", "le": "IK_EXPR_LE",
                "gt": "IK_EXPR_GT", "ge": "IK_EXPR_GE",
            }
            fields = {
                "anim": ("IK_EXPR_FIELD_ANIM_NO", "IK_EXPR_REDIRECT_SELF"),
                "stateno": ("IK_EXPR_FIELD_STATE_NO", "IK_EXPR_REDIRECT_SELF"),
                "prevstateno": (
                    "IK_EXPR_FIELD_PREV_STATE_NO", "IK_EXPR_REDIRECT_SELF"),
                "root_prevstateno": (
                    "IK_EXPR_FIELD_PREV_STATE_NO", "IK_EXPR_REDIRECT_ROOT"),
                "p2stateno": (
                    "IK_EXPR_FIELD_STATE_NO", "IK_EXPR_REDIRECT_P2"),
                "entityid": (
                    "IK_EXPR_FIELD_ENTITY_ID", "IK_EXPR_REDIRECT_SELF"),
                "enemy_stateno": (
                    "IK_EXPR_FIELD_STATE_NO", "IK_EXPR_REDIRECT_P2"),
                "enemynear_stateno": (
                    "IK_EXPR_FIELD_STATE_NO", "IK_EXPR_REDIRECT_P2"),
                "p2_stateno": (
                    "IK_EXPR_FIELD_STATE_NO", "IK_EXPR_REDIRECT_P2"),
                "parent_stateno": (
                    "IK_EXPR_FIELD_STATE_NO", "IK_EXPR_REDIRECT_PARENT"),
                "root_stateno": (
                    "IK_EXPR_FIELD_STATE_NO", "IK_EXPR_REDIRECT_ROOT"),
                "target_stateno": (
                    "IK_EXPR_FIELD_STATE_NO", "IK_EXPR_REDIRECT_TARGET"),
                "enemy_anim": (
                    "IK_EXPR_FIELD_ANIM_NO", "IK_EXPR_REDIRECT_P2"),
                "enemynear_anim": (
                    "IK_EXPR_FIELD_ANIM_NO", "IK_EXPR_REDIRECT_P2"),
                "parent_anim": (
                    "IK_EXPR_FIELD_ANIM_NO", "IK_EXPR_REDIRECT_PARENT"),
                "root_anim": (
                    "IK_EXPR_FIELD_ANIM_NO", "IK_EXPR_REDIRECT_ROOT"),
                "target_anim": (
                    "IK_EXPR_FIELD_ANIM_NO", "IK_EXPR_REDIRECT_TARGET"),
            }
            if operator not in operators:
                raise ValueError(f"unsupported integer comparison {operator!r}")
            if field_name not in fields:
                raise ValueError(f"unsupported integer field {field_name!r}")
            self._take()
            sign = -1 if self._peek() == ("op", "-") else 1
            if sign < 0:
                self._take()
            token = self._peek()
            if token is None or token[0] != "num" or not re.fullmatch(
                    r"\d+", token[1]):
                raise ValueError("integer comparisons require integer constants")
            action = sign * int(self._take()[1])
            if self._peek() != ("op", ")"):
                raise ValueError(
                    "integer comparisons require one integer constant")
            self._take()
            field, redirect = fields[field_name]
            return ([{"op": "IK_EXPR_LOAD_FIELD", "field": field,
                      "redirect": redirect}] +
                    [{"op": "IK_EXPR_PUSH_CONST", "value0": action},
                     {"op": operators[operator]}])
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
                    "size.ground.back": 5,
                    "size.ground.front": 6,
                    "size.air.back": 7,
                    "size.air.front": 8,
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
                    "airtype": "IK_EXPR_FIELD_GET_HIT_AIR_TYPE",
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
                integer_fields = set(_PROJECTILE_QUERY_FIELDS) | {
                    "var", "sysvar", "fvar", "sysfvar", "numtarget",
                    "numhelper", "numexplod", "animelemtime", "animelemno",
                }
                args = self._args(
                    integer_literals=field_lower in integer_fields)
                if self._peek() != ("op", ")"):
                    raise ValueError(
                        f"missing closing parenthesis in {name},{field_name}()")
                self._take()
                if field_lower in _PROJECTILE_QUERY_FIELDS and len(args) <= 1:
                    projectile_id = (
                        self._integer_arg(args[0], field_name)
                        if args else -1)
                    if projectile_id < -1 or projectile_id > 2147483647:
                        raise ValueError(
                            f"{field_name}() ID is outside the signed 32-bit range")
                    return self._load_runtime_field(
                        _PROJECTILE_QUERY_FIELDS[field_lower],
                        projectile_id, redirect)
                if field_lower in ("var", "sysvar", "fvar", "sysfvar") and len(args) == 1:
                    index = self._integer_arg(args[0], field_name)
                    max_count = {
                        "var": 60, "fvar": 40,
                        "sysvar": 5, "sysfvar": 5,
                    }[field_lower]
                    if index < 0 or index >= max_count:
                        raise ValueError(
                            f"{field_name}({index}) is outside the supported "
                            f"range 0..{max_count - 1}")
                    runtime_field = {
                        "var": "IK_EXPR_FIELD_VAR",
                        "sysvar": "IK_EXPR_FIELD_SYSVAR",
                        "fvar": "IK_EXPR_FIELD_FVAR_Q16",
                        "sysfvar": "IK_EXPR_FIELD_SYSFVAR_Q16",
                    }[field_lower]
                    return self._load_runtime_field(
                        runtime_field, index, redirect)
                if field_lower == "numtarget" and len(args) == 1:
                    target_id = self._integer_arg(args[0], field_name)
                    return self._load_runtime_field(
                        "IK_EXPR_FIELD_NUM_TARGETS", target_id, redirect)
                if field_lower == "numhelper" and len(args) == 1:
                    helper_id = self._integer_arg(args[0], field_name)
                    if helper_id < 0 or helper_id > 2147483647:
                        raise ValueError(
                            "NumHelper() id is outside the signed 32-bit range")
                    return self._load_runtime_field(
                        "IK_EXPR_FIELD_NUM_HELPERS", helper_id, redirect)
                if field_lower == "numexplod" and len(args) <= 1:
                    explod_id = (
                        self._integer_arg(args[0], field_name)
                        if args else -2147483648)
                    if explod_id < -2147483648 or explod_id > 2147483647:
                        raise ValueError(
                            "NumExplod() id is outside the signed 32-bit range")
                    return self._load_runtime_field(
                        "IK_EXPR_FIELD_NUM_EXPLODS", explod_id, redirect)
                if field_lower == "animelemtime" and len(args) == 1:
                    elem = self._integer_arg(args[0], field_name)
                    if elem < 1 or elem > 65535:
                        raise ValueError(
                            "AnimElemTime() index must be in the range 1..65535")
                    return self._load_runtime_field(
                        "IK_EXPR_FIELD_ANIM_ELEM_TIME", elem, redirect)
                if field_lower == "animelemno" and len(args) == 1:
                    if self._integer_arg(args[0], field_name) != 0:
                        raise ValueError(
                            "AnimElemNo currently supports only argument 0")
                    return self._load_runtime_field(
                        "IK_EXPR_FIELD_ANIM_ELEM", redirect=redirect)
                raise ValueError(
                    f"unsupported redirected function {name},{field_name}()")
            if field_lower in _RUNTIME_EXPR_FIELDS:
                return self._load_runtime_field(
                    _RUNTIME_EXPR_FIELDS[field_lower],
                    -1 if field_lower in _PROJECTILE_QUERY_FIELDS else 0,
                    redirect=redirect)
            if field_lower == "namehash":
                return self._load_runtime_field(
                    "IK_EXPR_FIELD_CHARACTER_NAME_HASH", redirect=redirect)
            if field_lower == "authornamehash":
                return self._load_runtime_field(
                    "IK_EXPR_FIELD_CHARACTER_AUTHOR_HASH", redirect=redirect)
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
        if lower == "target" and self._peek() == ("op", "("):
            self._take()
            args = self._args(integer_literals=True)
            if self._peek() != ("op", ")") or len(args) not in (1, 2):
                raise ValueError(
                    "Target redirection requires an ID and optional index")
            self._take()
            target_id = self._integer_arg(args[0], "Target")
            target_index = (
                self._integer_arg(args[1], "Target") if len(args) == 2 else 0
            )
            if target_id < -1 or target_index < 0 or target_index > 255:
                raise ValueError("Target redirection ID or index is out of range")
            if self._peek() != ("op", ","):
                raise ValueError("Target redirection requires a field")
            self._take()
            field_name = self._peek()
            if field_name is None or field_name[0] != "ident" or \
                    field_name[1].casefold() != "const":
                raise ValueError("Target redirection supports Const() fields")
            self._take()
            if self._peek() != ("op", "("):
                raise ValueError("Target,Const requires a constant name")
            self._take()
            const_name = self._peek()
            if const_name is None or const_name[0] != "ident":
                raise ValueError("Target,Const requires a constant name")
            self._take()
            if self._peek() != ("op", ")"):
                raise ValueError("Target,Const takes one constant name")
            self._take()
            const_indexes = {
                "size.head.pos.x": 1,
                "size.head.pos.y": 2,
                "size.mid.pos.x": 3,
                "size.mid.pos.y": 4,
                "size.ground.back": 5,
                "size.ground.front": 6,
                "size.air.back": 7,
                "size.air.front": 8,
            }
            constant_index = const_indexes.get(const_name[1].casefold())
            if constant_index is None:
                raise ValueError(
                    f"unsupported redirected Const() value {const_name[1]!r}")
            return self._load_runtime_field(
                "IK_EXPR_FIELD_CHAR_CONSTANT", constant_index,
                "IK_EXPR_REDIRECT_TARGET", target_id, target_index)
        if lower == "helper" and self._peek() == ("op", "("):
            self._take()
            args = self._args(integer_literals=True)
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
            if field_lower == "animelemtime" and \
                    self._peek() == ("op", "("):
                self._take()
                args = self._args(integer_literals=True)
                if self._peek() != ("op", ")") or len(args) != 1:
                    raise ValueError(
                        "Helper(),AnimElemTime() requires one element")
                self._take()
                elem = self._integer_arg(args[0], field_name)
                if elem < 1 or elem > 65535:
                    raise ValueError(
                        "AnimElemTime() index must be in the range 1..65535")
                return self._load_runtime_field(
                    "IK_EXPR_FIELD_ANIM_ELEM_TIME", elem,
                    redirect=redirect, redirect_id=helper_id)
            if field_lower == "animelemno" and \
                    self._peek() == ("op", "("):
                self._take()
                args = self._args(integer_literals=True)
                if self._peek() != ("op", ")") or len(args) != 1:
                    raise ValueError(
                        "Helper(),AnimElemNo() requires one argument")
                self._take()
                if self._integer_arg(args[0], field_name) != 0:
                    raise ValueError(
                        "AnimElemNo currently supports only argument 0")
                return self._load_runtime_field(
                    "IK_EXPR_FIELD_ANIM_ELEM", redirect=redirect,
                    redirect_id=helper_id)
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
            if field_lower in ("var", "sysvar", "fvar", "sysfvar") and \
                    self._peek() == ("op", "("):
                self._take()
                args = self._args(integer_literals=True)
                if self._peek() != ("op", ")") or len(args) != 1:
                    raise ValueError(
                        f"Helper(),{field_name}() takes one constant index")
                self._take()
                index = self._integer_arg(args[0], field_name)
                max_count = {
                    "var": 60, "fvar": 40,
                    "sysvar": 5, "sysfvar": 5,
                }[field_lower]
                if index < 0 or index >= max_count:
                    raise ValueError(
                        f"{field_name}({index}) is outside 0..{max_count - 1}")
                field = {
                    "var": "IK_EXPR_FIELD_VAR",
                    "sysvar": "IK_EXPR_FIELD_SYSVAR",
                    "fvar": "IK_EXPR_FIELD_FVAR_Q16",
                    "sysfvar": "IK_EXPR_FIELD_SYSFVAR_Q16",
                }[field_lower]
                return self._load_runtime_field(
                    field, index, redirect, helper_id)
            if field_lower == "numexplod" and \
                    self._peek() == ("op", "("):
                self._take()
                args = self._args(integer_literals=True)
                if self._peek() != ("op", ")") or len(args) > 1:
                    raise ValueError(
                        "Helper(),NumExplod() takes at most one ID")
                self._take()
                explod_id = (
                    self._integer_arg(args[0], field_name)
                    if args else -2147483648)
                if explod_id < -2147483648 or explod_id > 2147483647:
                    raise ValueError(
                        "NumExplod() id is outside the signed 32-bit range")
                return self._load_runtime_field(
                    "IK_EXPR_FIELD_NUM_EXPLODS", explod_id,
                    redirect, helper_id)
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
                "airtype": "IK_EXPR_FIELD_GET_HIT_AIR_TYPE",
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
            integer_argument_functions = set(_PROJECTILE_QUERY_FIELDS) | {
                "animelemtime", "animelemno", "animexist", "selfanimexist",
                "numexplod", "numhelper", "numtarget", "stageauthoris",
            } | set(name_hash_functions)
            args = self._args(
                integer_literals=lower in integer_argument_functions)
            if self._peek() != ("op", ")"):
                raise ValueError(f"missing closing parenthesis in {name}()")
            self._take()
            if lower in _PROJECTILE_QUERY_FIELDS and len(args) <= 1:
                projectile_id = (
                    self._integer_arg(args[0], name) if args else -1)
                if projectile_id < -1 or projectile_id > 2147483647:
                    raise ValueError(
                        f"{name}() ID is outside the signed 32-bit range")
                return self._load_runtime_field(
                    _PROJECTILE_QUERY_FIELDS[lower], projectile_id)
            if lower == "animelemtime" and len(args) == 1:
                index = self._integer_arg(args[0], name)
                if index < 1 or index > 65535:
                    raise ValueError(
                        f"{name}() index must be in the range 1..65535")
                return self._load_runtime_field(
                    "IK_EXPR_FIELD_ANIM_ELEM_TIME", index)
            if lower in {"selfanimexist", "animexist"} and len(args) == 1:
                code = args[0]
                if self.q16 and not code[0].get("integer_literal"):
                    code = code + [{"op": "IK_EXPR_TRUNC_Q16"}]
                code = code + [{"op": "IK_EXPR_SELF_ANIM_EXISTS"}]
                if self.q16:
                    code.extend([
                        {"op": "IK_EXPR_PUSH_CONST", "value0": 65536},
                        {"op": "IK_EXPR_MUL"},
                    ])
                return code
            if lower == "animelemno" and len(args) == 1:
                if self._integer_arg(args[0], name) != 0:
                    raise ValueError("AnimElemNo currently supports only argument 0")
                return self._load_runtime_field("IK_EXPR_FIELD_ANIM_ELEM")
            if lower == "numtarget" and len(args) == 1:
                target_id = self._integer_arg(args[0], name)
                return self._load_runtime_field(
                    "IK_EXPR_FIELD_NUM_TARGETS", target_id)
            if lower == "const240p" and len(args) == 1:
                scale = self.localcoord_x / 320.0
                if scale == 1.0:
                    return args[0]
                if not self.q16 and int(scale) != scale:
                    raise ValueError(
                        "Const240p() is fractional in integer expression")
                factor = int(round(scale * 65536)) if self.q16 else int(scale)
                return args[0] + [
                    {"op": "IK_EXPR_PUSH_CONST", "value0": factor},
                    {"op": "IK_EXPR_MUL_Q16" if self.q16 else "IK_EXPR_MUL"},
                ]
            if lower == "abs" and len(args) == 1:
                return args[0] + [{"op": "IK_EXPR_ABS"}]
            if lower == "exp" and len(args) == 1:
                if not self.q16:
                    raise ValueError("Exp() requires a fixed-point expression")
                return args[0] + [{"op": "IK_EXPR_EXP_Q16"}]
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
                if any(ins.get("field") in {
                           "IK_EXPR_FIELD_FVAR_Q16",
                           "IK_EXPR_FIELD_SYSFVAR_Q16",
                       }
                       for ins in code):
                    return code + [{"op": "IK_EXPR_CEIL_Q16"}]
                return code
            if lower == "floor" and len(args) == 1:
                if self.q16:
                    return args[0] + [{"op": "IK_EXPR_FLOOR_Q16"}]
                return args[0]
            if lower == "command" and len(args) == 1:
                command_id = self._integer_arg(args[0], name)
                if command_id < 0 or command_id >= 192:
                    raise ValueError("command() id is outside 0..191")
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
            if lower in ("var", "sysvar", "fvar", "sysfvar") and len(args) == 1:
                index = self._integer_arg(args[0], name)
                max_count = {
                    "var": 60, "fvar": 40,
                    "sysvar": 5, "sysfvar": 5,
                }[lower]
                if index < 0 or index >= max_count:
                    raise ValueError(
                        f"{name}({index}) is outside the supported range 0..{max_count - 1}")
                field = {
                    "var": "IK_EXPR_FIELD_VAR",
                    "sysvar": "IK_EXPR_FIELD_SYSVAR",
                    "fvar": "IK_EXPR_FIELD_FVAR_Q16",
                    "sysfvar": "IK_EXPR_FIELD_SYSFVAR_Q16",
                }[lower]
                if self._peek() == ("op", ":="):
                    if lower in ("fvar", "sysfvar"):
                        raise ValueError(
                            f"assignment to {name}() is unsupported")
                    self._take()
                    value_code = self._or()
                    return value_code + [{
                        "op": "IK_EXPR_STORE_FIELD",
                        "field": field,
                        "redirect": "IK_EXPR_REDIRECT_SELF",
                        "redirect_index": int(self.q16),
                        "value0": index,
                    }]
                return self._load_runtime_field(field, index)
            if lower == "ifelse" and len(args) == 3:
                condition, when_true, when_false = args
                return (condition + when_true + when_false +
                        [{"op": "IK_EXPR_IFELSE"}])
            if lower == "playeridexist" and len(args) == 1:
                # The Saturn fight runtime has exactly two player slots, with
                # player IDs 0 and 1. Other MUGEN player IDs do not exist in
                # this 1P-versus-2P runtime.
                player_id = args[0]
                scale = 65536 if self.q16 else 1
                return (
                    player_id +
                    [{"op": "IK_EXPR_PUSH_CONST", "value0": 0},
                     {"op": "IK_EXPR_GE"}] +
                    player_id +
                    [{"op": "IK_EXPR_PUSH_CONST", "value0": 2 * scale},
                     {"op": "IK_EXPR_LT"},
                     {"op": "IK_EXPR_AND"}]
                )
            if lower == "stageauthoris" and len(args) == 1:
                author_hash = self._integer_arg(args[0], name)
                if author_hash < 0 or author_hash > 0x7fffffff:
                    raise ValueError("StageVar author hash is out of range")
                return self._load_runtime_field(
                    "IK_EXPR_FIELD_STAGE_AUTHOR_MATCH", author_hash)
            raise ValueError(f"unsupported function in runtime expression: {name}")

        if lower in ("true", "false"):
            return [{"op": "IK_EXPR_PUSH_CONST", "value0": int(lower == "true")}]
        if lower in ("camerapos", "campos"):
            axis = self._take()[1].lower()
            if axis != "x":
                raise ValueError(
                    f"CameraPos {axis.upper()} is unsupported without vertical camera tracking")
            return self._load_runtime_field(
                "IK_EXPR_FIELD_CAMERA_POS_X_Q8")
        if lower == "screenpos":
            axis = self._take()[1].lower()
            if axis == "x":
                scale = 65536 if self.q16 else 1
                return (
                    self._load_runtime_field("IK_EXPR_FIELD_POS_X_Q8") +
                    self._load_runtime_field(
                        "IK_EXPR_FIELD_CAMERA_POS_X_Q8") +
                    [{"op": "IK_EXPR_SUB"},
                     {"op": "IK_EXPR_PUSH_CONST",
                      "value0": 160 * scale},
                     {"op": "IK_EXPR_SUB"}]
                )
            if axis != "y":
                raise ValueError(f"unsupported ScreenPos axis {axis!r}")
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
            return self._load_runtime_field(
                _RUNTIME_EXPR_FIELDS[lower],
                -1 if lower in _PROJECTILE_QUERY_FIELDS else 0)
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
        if lower == "p2authornamehash":
            return self._load_runtime_field(
                "IK_EXPR_FIELD_CHARACTER_AUTHOR_HASH",
                redirect="IK_EXPR_REDIRECT_P2",
            )
        if lower == "p1namehash":
            return self._load_runtime_field(
                "IK_EXPR_FIELD_CHARACTER_NAME_HASH")
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
        if lower == "rootdist":
            return self._root_dist(self._take()[1].lower())
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


def compile_cns_expr(
    text: str,
    q16: bool = False,
    *,
    command_ids: dict[str, int] | None = None,
    localcoord_x: float = 320.0,
    const_values: dict[str, float] | None = None,
    self_anims: set[int] | None = None,
    character_author: str | None = None,
) -> list[dict]:
    normalized = normalize_cns_expr(
        text,
        q16,
        command_ids=command_ids,
        localcoord_x=localcoord_x,
        const_values=const_values,
        self_anims=self_anims,
        character_author=character_author,
    )
    code = _ExprCompiler(
        normalized, q16=q16, localcoord_x=localcoord_x).parse()
    if len(code) > 255:
        raise ValueError("runtime CNS expression exceeds 255 instructions")
    return code
