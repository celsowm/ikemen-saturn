#include "ikemen_saturn/ikemen_expr.h"

#include <limits.h>

static int push(int32_t* stack, uint8_t* sp, int32_t value) {
    if (!stack || !sp || *sp >= IK_EXPR_STACK_CAPACITY) return 0;
    stack[(*sp)++] = value;
    return 1;
}

static int32_t exp_q16(int32_t x) {
    const int64_t one = 65536;
    if (x < -16 * one) return 0;

    uint8_t reductions = 0u;
    while (x > 8192 || x < -8192) {
        x /= 2;
        ++reductions;
    }

    int64_t term = one;
    int64_t result = one;
    for (int32_t i = 1; i <= 12; ++i) {
        term = (term * x) / (one * i);
        result += term;
    }
    if (result < 0) result = 0;
    while (reductions > 0u) {
        result = (result * result) / one;
        if (result > INT32_MAX) return INT32_MAX;
        --reductions;
    }
    return (int32_t)result;
}

static int unary(int32_t* stack, uint8_t sp, uint8_t op) {
    if (!stack || sp < 1u) return 0;
    switch ((ik_expr_op_t)op) {
        case IK_EXPR_NOT:
            stack[sp - 1u] = stack[sp - 1u] == 0;
            return 1;
        case IK_EXPR_NEG:
            stack[sp - 1u] = -stack[sp - 1u];
            return 1;
        case IK_EXPR_CEIL_Q16: {
            const int32_t value = stack[sp - 1u];
            stack[sp - 1u] = value > 0
                ? (value + 65535) / 65536
                : value / 65536;
            return 1;
        }
        case IK_EXPR_FLOOR_Q16: {
            const int32_t value = stack[sp - 1u];
            int32_t integer = value / 65536;
            if (value < 0 && value % 65536 != 0) --integer;
            stack[sp - 1u] = integer * 65536;
            return 1;
        }
        case IK_EXPR_TRUNC_Q16:
            stack[sp - 1u] /= 65536;
            return 1;
        case IK_EXPR_TRUNC_Q8:
            stack[sp - 1u] /= 256;
            return 1;
        case IK_EXPR_ABS:
            if (stack[sp - 1u] == INT32_MIN) stack[sp - 1u] = INT32_MAX;
            else if (stack[sp - 1u] < 0) stack[sp - 1u] = -stack[sp - 1u];
            return 1;
        case IK_EXPR_EXP_Q16:
            stack[sp - 1u] = exp_q16(stack[sp - 1u]);
            return 1;
        default:
            return 0;
    }
}

static int binary(int32_t* stack, uint8_t* sp, uint8_t op) {
    if (!stack || !sp || *sp < 2u) return 0;
    const int32_t rhs = stack[*sp - 1u];
    const int32_t lhs = stack[*sp - 2u];
    int32_t result = 0;

    if ((ik_expr_op_t)op == IK_EXPR_POW) {
        if (rhs < 0) return 0;
        int64_t power = 1;
        int64_t base = lhs;
        uint32_t exponent = (uint32_t)rhs;
        while (exponent != 0u) {
            if ((exponent & 1u) != 0u) {
                power *= base;
                if (power > INT32_MAX) power = INT32_MAX;
                if (power < INT32_MIN) power = INT32_MIN;
            }
            exponent >>= 1;
            if (exponent != 0u) {
                base *= base;
                if (base > INT32_MAX) base = INT32_MAX;
                if (base < INT32_MIN) base = INT32_MIN;
            }
        }
        stack[*sp - 2u] = (int32_t)power;
        --(*sp);
        return 1;
    }

    if ((ik_expr_op_t)op == IK_EXPR_MUL_Q16 ||
        (ik_expr_op_t)op == IK_EXPR_DIV_Q16) {
        if ((ik_expr_op_t)op == IK_EXPR_DIV_Q16 && rhs == 0) return 0;
        int64_t wide = (ik_expr_op_t)op == IK_EXPR_MUL_Q16
            ? ((int64_t)lhs * rhs) / 65536
            : ((int64_t)lhs * 65536) / rhs;
        if (wide > INT32_MAX) wide = INT32_MAX;
        if (wide < INT32_MIN) wide = INT32_MIN;
        stack[*sp - 2u] = (int32_t)wide;
        --(*sp);
        return 1;
    }

    switch ((ik_expr_op_t)op) {
        case IK_EXPR_EQ: result = lhs == rhs; break;
        case IK_EXPR_NE: result = lhs != rhs; break;
        case IK_EXPR_LT: result = lhs < rhs; break;
        case IK_EXPR_LE: result = lhs <= rhs; break;
        case IK_EXPR_GT: result = lhs > rhs; break;
        case IK_EXPR_GE: result = lhs >= rhs; break;
        case IK_EXPR_AND: result = lhs != 0 && rhs != 0; break;
        case IK_EXPR_OR: result = lhs != 0 || rhs != 0; break;
        case IK_EXPR_ADD: result = lhs + rhs; break;
        case IK_EXPR_SUB: result = lhs - rhs; break;
        case IK_EXPR_MUL: result = lhs * rhs; break;
        case IK_EXPR_DIV:
            if (rhs == 0) return 0;
            result = lhs / rhs;
            break;
        case IK_EXPR_MOD:
            if (rhs == 0) return 0;
            result = lhs % rhs;
            break;
        default:
            return 0;
    }

    stack[*sp - 2u] = result;
    --(*sp);
    return 1;
}

static int ternary(int32_t* stack, uint8_t* sp, uint8_t op) {
    if (!stack || !sp || *sp < 3u ||
        (ik_expr_op_t)op != IK_EXPR_IFELSE) return 0;
    const int32_t condition = stack[*sp - 3u];
    const int32_t when_true = stack[*sp - 2u];
    const int32_t when_false = stack[*sp - 1u];
    stack[*sp - 3u] = condition != 0 ? when_true : when_false;
    *sp -= 2u;
    return 1;
}

int ik_expr_eval(
    const ik_expr_instr_t* code,
    uint16_t count,
    const ik_expr_context_t* context,
    int32_t* out_value
) {
    int32_t stack[IK_EXPR_STACK_CAPACITY];
    uint8_t sp = 0u;

    if (!code || !context || !out_value) return 0;

    for (uint16_t i = 0u; i < count; ++i) {
        const ik_expr_instr_t* ins = &code[i];
        int32_t value = 0;

        switch ((ik_expr_op_t)ins->op) {
            case IK_EXPR_PUSH_CONST:
                if (!push(stack, &sp, ins->value0)) return 0;
                break;

            case IK_EXPR_LOAD_FIELD:
                if (!context->read_field ||
                    !context->read_field(
                        context->user, ins->redirect, ins->field,
                        ins->value0, ins->value1, ins->reserved,
                        &value) ||
                    !push(stack, &sp, value)) {
                    return 0;
                }
                break;

            case IK_EXPR_LOAD_PLAYER_FIELD: {
                if (sp < 1u || !context->read_field) return 0;
                const int32_t player_id = stack[sp - 1u];
                if (player_id < 0 || player_id > 1) {
                    stack[sp - 1u] = 0;
                    break;
                }
                if (!context->read_field(
                        context->user, IK_EXPR_REDIRECT_PLAYER_ID,
                        ins->field, ins->value0, player_id, 0u, &value)) {
                    return 0;
                }
                stack[sp - 1u] = value;
                break;
            }

            case IK_EXPR_LOAD_PLAYER_FIELD_DYNAMIC_INDEX: {
                if (sp < 2u || !context->read_field) return 0;
                const int32_t player_id = stack[sp - 2u];
                const int32_t index = stack[sp - 1u];
                if (player_id < 0 || player_id > 1) {
                    stack[sp - 2u] = 0;
                    --sp;
                    break;
                }
                if (!context->read_field(
                        context->user, IK_EXPR_REDIRECT_PLAYER_ID,
                        ins->field, index, player_id, 0u, &value)) {
                    return 0;
                }
                stack[sp - 2u] = value;
                --sp;
                break;
            }

            case IK_EXPR_LOAD_COMMAND:
                if (!context->read_command ||
                    !context->read_command(
                        context->user, (uint16_t)ins->value0, &value) ||
                    !push(stack, &sp, value)) {
                    return 0;
                }
                break;

            case IK_EXPR_STORE_FIELD:
                if (sp < 1u || !context->write_field ||
                    !context->write_field(
                        context->user, ins->redirect, ins->field,
                        ins->value0, ins->value1, ins->reserved,
                        stack[sp - 1u])) {
                    return 0;
                }
                break;

            case IK_EXPR_SELF_ANIM_EXISTS:
                if (sp < 1u || !context->read_field ||
                    !context->read_field(
                        context->user, IK_EXPR_REDIRECT_SELF,
                        IK_EXPR_FIELD_SELF_ANIM_EXISTS,
                        stack[sp - 1u], 0, 0u, &value)) {
                    return 0;
                }
                stack[sp - 1u] = value != 0;
                break;

            case IK_EXPR_NOT:
            case IK_EXPR_NEG:
                if (!unary(stack, sp, ins->op)) return 0;
                break;

            case IK_EXPR_EQ:
            case IK_EXPR_NE:
            case IK_EXPR_LT:
            case IK_EXPR_LE:
            case IK_EXPR_GT:
            case IK_EXPR_GE:
            case IK_EXPR_AND:
            case IK_EXPR_OR:
            case IK_EXPR_ADD:
            case IK_EXPR_SUB:
            case IK_EXPR_MUL:
            case IK_EXPR_DIV:
            case IK_EXPR_MOD:
            case IK_EXPR_POW:
            case IK_EXPR_MUL_Q16:
            case IK_EXPR_DIV_Q16:
                if (!binary(stack, &sp, ins->op)) return 0;
                break;

            case IK_EXPR_IFELSE:
                if (!ternary(stack, &sp, ins->op)) return 0;
                break;

            case IK_EXPR_CEIL_Q16:
            case IK_EXPR_FLOOR_Q16:
            case IK_EXPR_TRUNC_Q16:
            case IK_EXPR_TRUNC_Q8:
            case IK_EXPR_ABS:
            case IK_EXPR_EXP_Q16:
                if (!unary(stack, sp, ins->op)) return 0;
                break;

            default:
                return 0;
        }
    }

    if (sp != 1u) return 0;
    *out_value = stack[0];
    return 1;
}
