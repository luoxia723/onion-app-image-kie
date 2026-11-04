"""OS-held workspace lock; released by the kernel even after an abnormal exit."""
import os
from .config import UserError

class InstanceLock:
    def __init__(self,path):
        self.handle=open(path,'a+b')
        try:
            if os.name=='nt':
                import msvcrt
                self.handle.seek(0)
                if self.handle.read(1)==b'':self.handle.write(b'0');self.handle.flush()
                self.handle.seek(0);msvcrt.locking(self.handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            raise UserError('这个工作台已在运行，请回到已打开的窗口',409)

    def close(self):
        if not self.handle.closed:self.handle.close()
