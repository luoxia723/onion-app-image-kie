#!/bin/zsh
cd "${0:A:h}"
ONION_LAUNCH_PYTHON=''
for onion_candidate in python3.13 python3.12 python3.14 python3.11 python3.10 python3 .venv/bin/python; do
  if command -v "$onion_candidate" >/dev/null 2>&1 && "$onion_candidate" -c 'import sys;sys.exit(not ((3,10)<=sys.version_info[:2]<=(3,14)))' >/dev/null 2>&1; then
    ONION_LAUNCH_PYTHON="$onion_candidate"
    break
  fi
done
if [[ -z "$ONION_LAUNCH_PYTHON" ]]; then
  print '请先安装64位 Python 3.10–3.14，建议3.12或3.13：https://www.python.org/downloads/'
  read '?按回车关闭…'
  exit 1
fi
"$ONION_LAUNCH_PYTHON" bootstrap.py "$@"
onion_exit=$?
if [[ $onion_exit != 0 ]]; then read '?按回车关闭…'; fi
exit $onion_exit
