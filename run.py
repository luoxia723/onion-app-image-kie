#!/usr/bin/env python3
import sys
if sys.version_info < (3,10):
    print('请先安装 Python 3.10 或更高版本，再双击启动。')
    sys.exit(1)
try:
    import PIL, cv2, numpy
except ImportError:
    print('缺少运行依赖。请先在本目录运行：python -m pip install -r requirements.txt')
    sys.exit(1)
from local_app.server import main
sys.exit(main())
