#/usr/bin/python

"""Get monotonic time from the OS using the ctypes module.

Only on Mac OS X is a C module required. Other platforms use a Python-only
implementation.

Copyright 2010, 2011 Gavin Beatty <gavinbeatty@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

__author__ = 'Gavin Beatty <gavinbeatty@gmail.com>'
#@VERSION@
__date__ = '2010-01-18'

__all__ = [
  'timespec', 'get_monotonic_time_impl', 'monotonic_time'
]

import ctypes
import os
import sys
import errno

class timespec(ctypes.Structure):
    _fields_ = [
        ('tv_sec', ctypes.c_long),
        ('tv_nsec', ctypes.c_long)
    ]
    def to_seconds_double(self):
        return self.tv_sec + self.tv_nsec * 1e-9

def monotonic_time(impl=None):
    if impl is None:
        impl = get_monotonic_time_impl()
    return impl()

def get_monotonic_time_impl():
    if sys.platform.startswith("linux"):
        return lambda: monotonic_time_unix(1, impl=get_monotonic_time_impl_unix())
    elif sys.platform.startswith("freebsd"):
        return lambda: monotonic_time_unix(4, impl=get_monotonic_time_impl_unix())
    elif sys.platform.startswith("darwin"):
        return lambda: monotonic_time_darwin(impl=get_monotonic_time_impl_darwin())
    elif sys.platform.startswith("win32"):
        return monotonic_time_win32(impl=get_monotonic_time_impl_win32())
    else:
        raise OSError(errno.ENOSYS, "monotonic_time not supported on your platform.")

def get_monotonic_time_impl_darwin():
    return ctypes.CDLL('libmonotonic_time.dylib', use_errno=True).darwin_clock_gettime_MONOTONIC
def monotonic_time_darwin(impl=None):
    if impl is None:
        impl = get_monotonic_time_impl_darwin()
    t = timespec()
    if impl(ctypes.pointer(t)) != 0:
        errno_ = ctypes.get_errno()
        raise OSError(errno_, os.strerrno(errno_))
    return t

def get_monotonic_time_impl_unix():
    fxn = ctypes.CDLL('librt.so.1', use_errno=True).clock_gettime
    fxn.argtypes = [ctypes.c_int, ctypes.POINTER(timespec)]
    return fxn
def monotonic_time_unix(clock, impl=None):
    if impl is None:
        impl = get_monotonic_time_impl_unix()
    t = timespec()
    if impl(clock, ctypes.pointer(t)) != 0:
        errno_ = ctypes.get_errno()
        raise OSError(errno_, os.strerror(errno_))
    return t

def get_monotonic_time_impl_win32():
    return getattr(ctypes.windll.kernel32, 'GetTickCount64', ctypes.windll.kernel32.GetTickCount)
def monotonic_time_win32(impl=None):
    if impl is None:
        impl = get_monotonic_time_impl_win32()
    ms = impl()
    t = timespec()
    t.tv_sec = ms / 1000
    t.tv_nsec = (ms - (t.tv_sec * 1000)) * 1e6
    return t


if __name__ == "__main__":
    print(monotonic_time().to_seconds_double())
