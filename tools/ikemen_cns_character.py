"""Compile character-wide CNS movement and collision constants."""
from __future__ import annotations


def compile_character_constants(globals_: dict, *, services: dict) -> dict[str, int]:
    Section = services["Section"]
    LOCALCOORD_X = services["LOCALCOORD_X"]
    integer = services["integer"]
    number = services["number"]
    pair = services["pair"]
    q8 = services["q8"]
    q16 = services["q16"]
    data = globals_.get("data", Section("Data"))
    size = globals_.get("size", Section("Size"))
    vel = globals_.get("velocity", Section("Velocity"))
    movement = globals_.get("movement", Section("Movement"))

    run_fwd = pair(vel.get("run.fwd"))
    run_back = pair(vel.get("run.back"))
    jump_neu = pair(vel.get("jump.neu"))
    jump_back = pair(vel.get("jump.back"), -2.55)[0]
    jump_fwd = pair(vel.get("jump.fwd"), 2.5)[0]
    run_jump_fwd = pair(vel.get("runjump.fwd"), 4.0, -8.1)
    air_jump_neu = pair(vel.get("airjump.neu"), 0.0, -8.1)
    air_jump_back = pair(vel.get("airjump.back"), -2.55)[0]
    air_jump_fwd = pair(vel.get("airjump.fwd"), 2.5)[0]
    ground_recover = pair(vel.get("air.gethit.groundrecover"), -.15, -3.5)
    air_recover_mul = pair(vel.get("air.gethit.airrecover.mul"), .5, .2)
    air_recover_add = pair(vel.get("air.gethit.airrecover.add"), 0, -4.5)
    air_ko_add = pair(vel.get("air.gethit.ko.add"), -2.5, -2.0)
    ground_ko_add = pair(vel.get("ground.gethit.ko.add"), -2.5, -2.0)

    return {
        "life": integer(data.get("life"), 1000),
        "air_juggle": integer(data.get("airjuggle"), 15),
        # HitDef values inherit these [Data] defaults when omitted.
        # They are compiler-only metadata; ik_cns_constants_t stays unchanged.
        "default_spark_no": integer(data.get("sparkno"), 2),
        "default_guard_spark_no": integer(data.get("guard.sparkno"), 40),
        "ground_back": integer(size.get("ground.back"), 15),
        "ground_front": integer(size.get("ground.front"), 16),
        "air_back": integer(size.get("air.back"), 12),
        "air_front": integer(size.get("air.front"), 12),
        "height": integer(size.get("height"), 60),
        "attack_dist": integer(size.get("attack.dist"), 160),
        "head_pos_x": int(pair(size.get("head.pos"), 0, 0)[0]),
        "head_pos_y": int(pair(size.get("head.pos"), 0, 0)[1]),
        "mid_pos_x": int(pair(size.get("mid.pos"), 0, 0)[0]),
        "mid_pos_y": int(pair(size.get("mid.pos"), 0, 0)[1]),
        "walk_fwd_q8": q8(number(vel.get("walk.fwd"), 2.4)),
        "walk_back_q8": q8(number(vel.get("walk.back"), -2.2)),
        "run_fwd_x_q8": q8(run_fwd[0]),
        "run_fwd_y_q8": q8(run_fwd[1]),
        "run_back_x_q8": q8(run_back[0]),
        "run_back_y_q8": q8(run_back[1]),
        "jump_neu_x_q8": q8(jump_neu[0]),
        "jump_neu_y_q8": q8(jump_neu[1]),
        "jump_back_q8": q8(jump_back),
        "jump_fwd_q8": q8(jump_fwd),
        "run_jump_fwd_x_q8": q8(run_jump_fwd[0]),
        "run_jump_fwd_y_q8": q8(run_jump_fwd[1]),
        "air_jump_neu_x_q8": q8(air_jump_neu[0]),
        "air_jump_neu_y_q8": q8(air_jump_neu[1]),
        "air_jump_back_q8": q8(air_jump_back),
        "air_jump_fwd_q8": q8(air_jump_fwd),
        "air_jump_num": integer(movement.get("airjump.num"), 0),
        "air_jump_height": integer(movement.get("airjump.height"), 35),
        "yaccel_q8": q8(
            number(movement.get("yaccel"), .44) * 320.0 / LOCALCOORD_X),
        "yaccel_q16": q16(
            number(movement.get("yaccel"), .44) * 320.0 / LOCALCOORD_X),
        "stand_friction_q16": q16(
            number(movement.get("stand.friction"), .85)),
        "crouch_friction_q16": q16(
            number(movement.get("crouch.friction"), .82)),
        "air_gethit_airrecover_yaccel_q16": q16(
            number(movement.get("air.gethit.airrecover.yaccel"), .35)),
        "stand_friction_q8": q8(number(movement.get("stand.friction"), .85)),
        "crouch_friction_q8": q8(number(movement.get("crouch.friction"), .82)),
        "stand_friction_threshold_q8": q8(
            number(movement.get("stand.friction.threshold"), 2.0)
        ),
        "crouch_friction_threshold_q8": q8(
            number(movement.get("crouch.friction.threshold"), .05)
        ),
        "liedown_time": integer(data.get("liedown.time"), 60),
        "air_gethit_groundlevel_q8": q8(
            number(movement.get("air.gethit.groundlevel"), 25)
        ),
        "air_gethit_trip_groundlevel_q8": q8(
            number(movement.get("air.gethit.trip.groundlevel"), 15)
        ),
        "down_bounce_offset_x_q8": q8(
            pair(movement.get("down.bounce.offset"), 0, 20)[0]
        ),
        "down_bounce_offset_y_q8": q8(
            pair(movement.get("down.bounce.offset"), 0, 20)[1]
        ),
        "down_bounce_yaccel_q8": q8(
            number(movement.get("down.bounce.yaccel"), .4)
        ),
        "down_bounce_groundlevel_q8": q8(
            number(movement.get("down.bounce.groundlevel"), 12)
        ),
        "down_friction_threshold_q8": q8(
            number(movement.get("down.friction.threshold"), .05)
        ),
        "air_gethit_groundrecover_x_q8": q8(ground_recover[0]),
        "air_gethit_groundrecover_y_q8": q8(ground_recover[1]),
        "air_gethit_groundrecover_threshold_q8": q8(
            number(
                movement.get("air.gethit.groundrecover.ground.threshold"),
                -20,
            )
        ),
        "air_gethit_groundrecover_groundlevel_q8": q8(
            number(movement.get("air.gethit.groundrecover.groundlevel"), 10)
        ),
        "air_gethit_airrecover_mul_x_q8": q8(air_recover_mul[0]),
        "air_gethit_airrecover_mul_y_q8": q8(air_recover_mul[1]),
        "air_gethit_airrecover_add_x_q8": q8(air_recover_add[0]),
        "air_gethit_airrecover_add_y_q8": q8(air_recover_add[1]),
        "air_gethit_airrecover_back_q8": q8(
            number(vel.get("air.gethit.airrecover.back"), -1)
        ),
        "air_gethit_airrecover_fwd_q8": q8(
            number(vel.get("air.gethit.airrecover.fwd"), 0)
        ),
        "air_gethit_airrecover_up_q8": q8(
            number(vel.get("air.gethit.airrecover.up"), -2)
        ),
        "air_gethit_airrecover_down_q8": q8(
            number(vel.get("air.gethit.airrecover.down"), 1.5)
        ),
        "air_gethit_airrecover_threshold_q8": q8(
            number(movement.get("air.gethit.airrecover.threshold"), -1)
        ),
        "air_gethit_airrecover_yaccel_q8": q8(
            number(movement.get("air.gethit.airrecover.yaccel"), .35)
        ),
        "air_gethit_ko_add_x_q8": q8(air_ko_add[0]),
        "air_gethit_ko_add_y_q8": q8(air_ko_add[1]),
        "air_gethit_ko_ymin_q8": q8(
            number(vel.get("air.gethit.ko.ymin"), -3.0)
        ),
        "ground_gethit_ko_xmul_q16": q16(
            number(vel.get("ground.gethit.ko.xmul"), .66)
        ),
        "ground_gethit_ko_add_x_q8": q8(ground_ko_add[0]),
        "ground_gethit_ko_add_y_q8": q8(ground_ko_add[1]),
        "ground_gethit_ko_ymin_q8": q8(
            number(vel.get("ground.gethit.ko.ymin"), -6.0)
        ),
    }

