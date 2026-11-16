#!/usr/bin/env python3
"""Explicit, offline test lanes. No production credentials or paid image calls."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
LANES={'core':'core','history':'history','transport':'transport','all':''}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite',choices=LANES,default='core')
    parser.add_argument('--collect',action='store_true',help='List the selected checks without running them')
    args=parser.parse_args()
    cmd=[sys.executable,'-m','pytest','-m',LANES[args.suite],'-q']
    if args.collect:cmd.append('--collect-only')
    result=subprocess.run(cmd,cwd=ROOT)
    if result.returncode:return result.returncode
    if args.suite in ('core','all') and not args.collect:
        node=shutil.which('node')
        if not node:
            print('Python检查通过；前端检查尚未执行，需要Node.js。运行工作台本身不需要Node.js。')
            return 1
        return subprocess.run([node,'--test',*[str(p) for p in sorted((ROOT/'tests_frontend').glob('*.test.cjs'))]],cwd=ROOT).returncode
    if args.suite in ('core','all') and args.collect:
        print('Frontend test files (node --test):',flush=True)
        for path in sorted((ROOT/'tests_frontend').glob('*.test.cjs')):print(path.relative_to(ROOT),flush=True)
    return 0

if __name__=='__main__':sys.exit(main())
