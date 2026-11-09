"""Command-line interface for the CNS asset compiler."""
from __future__ import annotations

def main(argv: list[str] | None = None, *, services: dict) -> int:
    argparse = services["argparse"]
    Path = services["Path"]
    parse_cmd = services["parse_cmd"]
    read_mugen_text = services["read_mugen_text"]
    _split_top_level = services["_split_top_level"]
    number = services["number"]
    namespace = services["namespace"]
    globals_dict = namespace.__dict__
    parser = argparse.ArgumentParser()
    parser.add_argument("--cns", required=True, type=Path)
    parser.add_argument("--character-def", type=Path,
                        help="character DEF used to read Info.localcoord")
    parser.add_argument("--constants-cns", type=Path,
                        help="separate [Data]/[Size]/[Velocity]/[Movement] file")
    parser.add_argument("--character-zss", type=Path,
                        help="original ZSS character states (strict subset)")
    parser.add_argument("--hits-zss", type=Path,
                        help="original ZSS hit reactions (strict subset)")
    parser.add_argument(
        "--states", default="all",
        help="comma-separated Statedef numbers, or 'all' (default)",
    )
    parser.add_argument(
        "--states-source", action="append", type=Path, default=[],
        help="additional CNS/ST file referenced by the character DEF",
    )
    parser.add_argument(
        "--command-source", action="append", type=Path, default=[],
        help="CMD file used to resolve command trigger IDs",
    )
    parser.add_argument("--common-zss", type=Path)
    parser.add_argument("--air", type=Path,
                        help="the character's .air file (SelfAnimExist)")
    parser.add_argument("--fightfx-air", type=Path,
                        help="shared fightfx .air file for F-prefixed Explods")
    parser.add_argument("--common-states", default="")
    parser.add_argument(
        "--strict", action="store_true",
        help="fail on unsupported triggers or deferred controllers")
    parser.add_argument("--out-prefix", required=True, type=Path)
    parser.add_argument("--symbol", required=True)
    args = parser.parse_args(argv)

    globals_dict["STRICT_CONVERSION"] = args.strict

    globals_dict["COMMAND_IDS"] = {}
    COMMAND_IDS = globals_dict["COMMAND_IDS"]
    for command_source in args.command_source:
        for command in parse_cmd(command_source).names:
            key = command.casefold()
            if key not in COMMAND_IDS:
                COMMAND_IDS[key] = len(COMMAND_IDS)
    if len(COMMAND_IDS) > 128:
        raise ValueError("CNS command table exceeds the 128-name expression limit")

    globals_dict["LOCALCOORD_X"] = 320.0
    globals_dict["CHARACTER_NAME_HASH"] = 0
    if args.character_def is not None:
        def_text = read_mugen_text(args.character_def)
        section = ""
        for raw in def_text.splitlines():
            line = raw.split(";", 1)[0].strip()
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].strip().casefold()
            elif section == "info" and "=" in line:
                key, value = line.split("=", 1)
                key = key.strip().casefold()
                if key == "name":
                    globals_dict["CHARACTER_NAME_HASH"] = services["character_name_hash"](
                        value.strip().strip('"'))
                elif key == "localcoord":
                    parts = _split_top_level(value)
                    if not parts or number(parts[0]) <= 0:
                        raise ValueError(
                            f"{args.character_def}: invalid localcoord {value!r}")
                    globals_dict["LOCALCOORD_X"] = services["number"](parts[0])

    if args.air is not None:
        globals_dict["SELF_ANIMS"] = services["load_air_actions"](args.air)
    if args.fightfx_air is not None:
        globals_dict["FIGHTFX_ANIMS"] = services["load_air_actions"](
            args.fightfx_air)

    services["configure_runtime_values"](globals_dict)

    selected = services["select_state_numbers"](
        args.states, [args.cns, *args.states_source])

    common_selected = [
        int(value.strip())
        for value in args.common_states.split(",")
        if value.strip()
    ]

    report = services["emit"](
        args.cns,
        selected,
        args.out_prefix,
        args.symbol,
        args.common_zss,
        common_selected,
        args.constants_cns,
        args.character_zss,
        args.hits_zss,
        args.states_source,
    )

    unsupported = {
        row["number"]: row["unsupported_controllers"]
        for row in report["states"]
        if row["unsupported_controllers"]
    }

    print(
        f"[ikemen_cns] {args.symbol}: "
        f"states={len(report['states'])} "
        f"hitdefs={len(report['hitdefs'])} "
        f"playsnds={len(report['playsnds'])} "
        f"controllers={len(report['controllers'])} "
        f"helpers={len(report['helpers'])} "
        f"explods={len(report['explods'])} "
        f"projectiles={len(report['projectiles'])} "
        f"projectile_mods={len(report['projectile_mods'])} "
        f"reversals={len(report['reversals'])} "
        f"hitoverrides={len(report['hitoverrides'])}"
    )

    if unsupported:
        print(f"[ikemen_cns] deferred controllers: {unsupported}")
        if args.strict:
            return 1

    return 0

