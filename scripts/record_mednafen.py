#!/usr/bin/env python3
"""Record an actual Saturn CD boot using an isolated Mednafen profile."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bios', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--region', choices=('na', 'jp', 'eu'), default='na',
                        help='console region; selects the matching BIOS setting')
    parser.add_argument('--build', type=Path, default=ROOT / 'build/saturn')
    parser.add_argument('--mednafen', default=shutil.which('mednafen') or 'mednafen')
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--screenshots', type=int, nargs='*', default=[])
    args = parser.parse_args()
    if args.seconds <= 0 or any(s < 0 for s in args.screenshots):
        parser.error('duration must be positive and screenshot times nonnegative')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    profile = out / 'profile'
    profile.mkdir()
    build = args.build.resolve()
    binary = build / 'ikemen_saturn.app.bin'
    elf = build / 'ikemen_saturn.elf'
    disc = build / 'disc/ikemen_saturn.bin'
    cue = build / 'disc/ikemen_saturn.cue'
    movie = out / 'run.mov'
    command = [args.mednafen, '-sound', '0', '-video.driver', 'softfb',
               '-ss.region_default', args.region,
               '-ss.bios_jp' if args.region == 'jp' else '-ss.bios_na_eu', str(args.bios.resolve()),
               '-ss.cart', 'extram4', '-qtrecord', str(movie)]
    for port in (1, 2):
        command.extend([f'-ss.input.port{port}', 'gamepad'])
        for button in ('up', 'down', 'left', 'right', 'a', 'b', 'c', 'x', 'y', 'z', 'ls', 'rs', 'start'):
            command.extend([f'-ss.input.port{port}.gamepad.{button}', ''])
    command.append(str(cue))
    env = os.environ.copy()
    env['MEDNAFEN_HOME'] = str(profile)
    metadata = {'command': command, 'seconds_requested': args.seconds,
                'scope': 'Actual CD boot; inspect recording for gameplay coverage',
                'sha256': {p.name: digest(p) for p in (elf, binary, disc, cue)}}
    with (out / 'mednafen.log').open('w') as log:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            process.wait(timeout=args.seconds)
        except subprocess.TimeoutExpired:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    metadata['returncode'] = process.returncode
    (out / 'run.json').write_text(json.dumps(metadata, indent=2) + '\n')
    if process.returncode:
        raise RuntimeError(f'Mednafen exited {process.returncode}; see mednafen.log')
    if not movie.is_file() or not movie.stat().st_size:
        raise RuntimeError('Mednafen did not produce a recording')
    (out / 'ffprobe.json').write_bytes(subprocess.check_output(
        ['ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-of', 'json', str(movie)]))
    for second in args.screenshots:
        image = out / f'frame-{second}.png'
        subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(second), '-i', str(movie),
                        '-frames:v', '1', '-vf', 'scale=704:480', str(image)], check=True)
        if not image.is_file() or not image.stat().st_size:
            raise RuntimeError(f'no video frame at {second} seconds')
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()
