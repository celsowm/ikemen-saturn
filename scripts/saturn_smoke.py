#!/usr/bin/env python3
"""Run an injection smoke test with the external LibSaturn Ymir probe.

This checks execution and panic state; it does not prove CD boot or gameplay parity.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def symbol(nm, elf, name):
    result = subprocess.run([str(nm), '-S', '--defined-only', str(elf)],
                            check=True, text=True, capture_output=True)
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) == 4 and fields[3] in (name, '_' + name):
            return int(fields[0], 16), int(fields[1], 16)
    raise ValueError(f'missing ELF symbol {name}')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--probe', type=Path, required=True)
    p.add_argument('--bios', type=Path, required=True)
    p.add_argument('--nm', type=Path, default=Path('sh2eb-elf-nm'))
    p.add_argument('--build', type=Path, default=ROOT / 'build/saturn')
    p.add_argument('--out', type=Path, required=True, help='new output directory')
    p.add_argument('--frames', type=int, default=600)
    p.add_argument('--pad-script', type=Path, default=ROOT / 'scripts/pads/ikemen_kick.pad')
    args = p.parse_args()
    if args.frames < 2:
        p.error('--frames must be at least 2')
    args.out.mkdir(parents=True, exist_ok=False)
    elf = args.build / 'ikemen_saturn.elf'
    binary = args.build / 'ikemen_saturn.app.bin'
    iso = args.build / 'disc/ikemen_saturn.iso'
    address, size = symbol(args.nm, elf, 'g_sat_last_panic')
    if size != 44:
        raise ValueError(f'unexpected panic record size {size}')
    report = args.out / 'probe.json'
    panic = args.out / 'panic.bin'
    screenshot = args.out / 'fight.png'
    command = [str(args.probe), '--iso', str(iso), '--bios', str(args.bios),
               '--bin', str(binary), '--frames', str(args.frames), '--boot-frames', '90',
               '--ram-cart', '4m', '--pad-script', str(args.pad_script),
               '--dump-mem', f'{address:#x}:{size}:{panic}',
               '--screenshot', f'{args.frames - 1}:{screenshot}', '--out', str(report)]
    with (args.out / 'probe.log').open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    summary = {'passed': False, 'command': command, 'returncode': result.returncode,
               'elf_sha256': sha256(elf), 'binary_sha256': sha256(binary),
               'iso_sha256': sha256(iso), 'pad_sha256': sha256(args.pad_script),
               'scope': 'Ymir direct injection; does not validate disc boot or gameplay parity'}
    try:
        if result.returncode:
            raise ValueError(f'probe exited with {result.returncode}')
        data = json.loads(report.read_text())
        boot = data['boot']
        if not boot['injected'] or data['frames_run'] != args.frames:
            raise ValueError('injection or requested frame count not observed')
        if data['ram_cartridge']['type'] != '4m':
            raise ValueError('4 MiB cartridge not configured')
        if not boot['load_addr'] <= boot['pc_after_run'] < boot['load_addr'] + boot['bin_bytes']:
            raise ValueError('final PC is outside injected binary')
        raw = panic.read_bytes()
        if len(raw) != size:
            raise ValueError('panic dump is truncated')
        if raw[:4] == b'PANC':
            raise ValueError('native panic record present')
        if not screenshot.is_file() or screenshot.stat().st_size == 0:
            raise ValueError('screenshot missing')
        summary.update(passed=True, frames=data['frames_run'],
                       final_pc=boot['pc_after_run'], screenshot=str(screenshot))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        summary['error'] = str(exc)
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
