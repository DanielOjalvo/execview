#!/usr/bin/env python3
'''
script for importing resources from library/ 
'''

import os
import sys
import inspect

# use inspect instead of __file__ variable since the later does not reflect the real value in some python implementations
_current = os.path.dirname( os.path.abspath( inspect.getfile( inspect.currentframe() ) ) )

# shared_lib = os.path.join(os.path.dirname(_current), "library")
_parent = os.path.dirname(_current)

if os.path.exists(_parent):
    sys.path.append(_parent)
else:
    raise Exception("lib.py failed to locate the directory of shared library under {0}.".format(_parent))

try:
    from library import *
except ImportError:
    raise Exception("lib.py failed to locate the resources inside shared library.")


if __name__ == "__main__":
    # only for testing purpose
    utility.terminal_msg(1, "test")
    print(get_conn_str())
    print(DEP_ID)
