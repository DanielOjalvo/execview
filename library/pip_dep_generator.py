#!/usr/bin/env python3
'''
test script for collecting module dependencies used 
'''
import re, os, isoparser
import itertools
import tempfile
import subprocess


def exec_cmd(cmd_str):
    stdout_tmp = tempfile.TemporaryFile()
    stderr_tmp = tempfile.TemporaryFile()
    stdout_str = ""
    stderr_str = ""

    p = subprocess.Popen(cmd_str, stdout = stdout_tmp, stderr = stderr_tmp, shell=True)
    p.wait()

    stdout_tmp.seek(0)
    stderr_tmp.seek(0)

    retcode = p.returncode

    stdout_str = stdout_tmp.read()
    stderr_str = stderr_tmp.read()

    return (retcode, stdout_str.decode("utf-8"), stderr_str)


if __name__ == "__main__":
    _, result, _ = exec_cmd("grep 'import' *")

    import_patterns = [":import (.*)\n", ":from (.*) import .*\n"]
    
    pip_dependencies = []

    for pattern in import_patterns:
        found = re.findall(pattern, result)
        if found:
            # strip whitespace, and remove regex cases where string contains .* (not really importing)
            found = [element.strip() for element in found if '.*' not in element and not element.startswith('.')]

            pip_dependencies.extend(found)
    

    # split import modules separated by commas (e.g., import )
    pip_dependencies = list(itertools.chain.from_iterable([module.split(',') if ',' in module else [module] for module in pip_dependencies]))

    # remove duplicate modules
    pip_dependencies = list(dict.fromkeys(pip_dependencies))
    
    print(pip_dependencies)
            