#!/usr/bin/env python3

"""
rpm_db_builder is a tool that utilizes readelf and other tools to compile
information about the ELF files present in a given directory of rpm packages.
rpm_db_builder will then create a series of json-formatted files containing the
ELF files, symbols present in the symbol table of said ELF file, how they're
defined or not defined, and information about the architecture that the RPM
is compiled for.
"""
from multiprocessing import Process, Queue, active_children, cpu_count
from queue import Empty
from os import mkdir, walk, chdir, path, rmdir, remove, X_OK, access, listdir, getcwd, devnull, write, symlink, unlink, O_RDONLY, O_NONBLOCK, fdopen
from os import open as osopen
from sys import argv, exit
from json import dumps
from subprocess import check_call, Popen, PIPE
from tempfile import TemporaryFile
from time import sleep
from shutil import rmtree
from argparse import ArgumentParser
from errno import ENOENT, EACCES
import re

import assemblyparser
from rpm_db_print import DBPrinter
from lib import *

global worker_dir
global restart
global rpm_dir
global err_file
global process_name
global output_dir
global noclean
global current_directory
global debug_process
global mark_worker_dir_for_removal


err_file = None

try:
    import cxxfilt
    def cppdemangle(s):
        if not s.startswith("_Z"):
            return s
        else:
            try:
                result = cxxfilt.demangle(s, external_only=False)
                return result
            except:
                return s
except:
    def cppdemangle(s):
        #print("running cppdemangle")
        if not s.startswith("_Z"):
            return s
        else:
            _, result, _ = run_shell_cmd(["c++filt", s]) #issues: should raise exception instead? error returned if c++filt not apt installed 
            return result

def contains_arch(s):
    # check if file name contains any of the architecture. 
    return any([x in s for x in (X86_64, I686, NOARCH, PPC)])

def get_arch(s):
    # match the architecture. All exceptions that do not belong to either x86_64, i686, noarch, or ppc is returned as otherarch.  
    for arch in (X86_64, I686, NOARCH, PPC):
        if arch in s:
            return arch

    return OTHERARCH


"""
The goal of this tool is to create a json database organized like this
{ "BIG-IP:14-1-0" :{
    "wdiag-14.1.0-0.0.1206.i686.rpm": {
        "All dependencies": [],
        "All executables": [],
        "architecture": "i686",
        "executables": {},
        "package": "wdiag-14.1.0-0.0.1206.i686.rpm",
        "release": "0.0.1206",
        "version": "14.1.0"
    }
,
    "c-ares-1.10.0-3.el7.centos.x86_64.rpm": {
        "All dependencies": [
            "libc.so.6"
        ],
        "All executables": [
            "libcares.so.2.1.0",
            "libcares.so.2"
        ],
        "architecture": "x86_64",
        "executables": {
            "libcares.so.2": {
                "Symlink Target": "libcares.so.2.1.0",
                "dependencies": [
                    "libc.so.6"
                ],
                "rpath": [],
                "symbols": {
                    "__assert_fail@GLIBC_2.2.5": {
                        "at": "GLIBC_2.2.5",
                        "binding": "GLOBAL",
                        "defined": "NO",
                        "long_name": "__assert_fail",
                        "type": "FUNC"
                    },
                    "__ctype_b_loc@GLIBC_2.3": {
                        "at": "GLIBC_2.3",
                        "binding": "GLOBAL",
                        "defined": "NO",
                        "long_name": "__ctype_b_loc",
                        "type": "FUNC"
                    },
                    "pipecmd_dump": {
                        "at": "",
                        "binding": "GLOBAL",
                        "called_functions": [
                            {
                                "function": "__fprintf_chk",
                                "long_name": "__fprintf_chk"
                            },
                            {
                                "function": "fputs",
                                "long_name": "fputs"
                            },
                            {
                                "function": "_IO_putc",
                                "long_name": "_IO_putc"
                            },
                            {
                                "function": "pipecmd_dump",
                                "long_name": "pipecmd_dump"
                            },
                            {
                                "function": "fwrite",
                                "long_name": "fwrite"
                            }
                        ],
                        "defined": "YES",
                        "long_name": "pipecmd_dump",
                        "type": "FUNC"
                    },

...
"""

def is_elf_file(f):
    '''
    Validate binary header to distinguish if the file is an ELF file.

    @param
    f               a string that represents path to a file

    @return
    True / False
    '''
    try:
        # os.open returns a file descriptor; while os.fdopen takes an existed fd and create a Python file object based on it.
        # Python built-in test = open(f, 'r') sets O_RDONLY but not in non-block mode; alternatively, use fcntl to set status flag for test.fileno()
        with fdopen(osopen(f, O_RDONLY|O_NONBLOCK), mode='rb') as test:
        # with open(f, "rb") as test:
            front = test.read(4)
            if front == b'\x7fELF':
                return True
    except IOError as error:
        terminal_msg(1, "exec_file open error: " + str(error))
        log_err("Unable to open file: " + f)

    return False


def log_err(s):
    '''
    Logging mechanism for errors raised.

    @param
    s       an error message string
    '''
    try:
        global err_file
        if err_file == None:
            err_file = open(path.join(worker_dir, process_name + "-err"), 'w')

        if not isinstance(s, str):
            s = str(s)

        s = s+'\n'
        err_file.write(s)

    except NameError:
        pass

def writer_process(cores, container_name, output_file, output_size):
    """
    Create Queue to store processed RPM data
    Create file to store output
    Extract list of RPMs (as strings)
    Create queue
    Create <cores processes>
         Give each process <num RPMS>/<cores> rpm files to process
         and queue to place its results in
    while multiprocessing.active_children() // helpfully joins ended processors
          while queue.empty() == False
              dequeue result from child process
              json dumps to file

    return 0 on success, non-zero on error
    """
    terminal_msg(2, "Examining files under %s directory" % rpm_dir)
    #chdir(rpm_dir)
    file_list = []

    global rpm_repository_path
    rpm_repository_path = path.join(worker_dir, "rpm-repository")

    try:
        mkdir(rpm_repository_path)
    except OSError:
        #Already there, no worries
        pass

    for dirpath, dirs, files_in_dir in walk(rpm_dir):
        #root_dir = path.join(rpm_dir, root)
        #print(root_dir)
        for f in files_in_dir:
            if f.endswith("rpm"):
                #print ("examining file " +  f)

                block_list = ("debug", "devel")
                if debug_process == False and any(s in f for s in block_list):
                        continue
                elif debug_process == True and not any(s in f for s in block_list):
                    continue
                #full_path = path.join(root_dir, f)
                full_path = path.join(dirpath, f)
                file_list.append(path.abspath(full_path))
                #print(full_path)
    """
    We'll trim the number of files that we're examining here.
    Each rpm may have an x86_64 or i686 (or other) version.
    So, what we'll do is keep track of the different architectures available for a given RPM
    and pass that information off to the worker.
    """
    x86_64_rpms = [x.replace(X86_64, SEPARATOR) for x in file_list if D_X86_64 in x]
    i686_rpms = [x.replace(I686, SEPARATOR) for x in file_list if D_I686 in x]
    noarch_rpms = [x.replace(NOARCH, SEPARATOR) for x in file_list if D_NOARCH in x]
    ppc_rpms = [x.replace(PPC, SEPARATOR) for x in file_list if D_PPC in x]
    other_rpms = [x for x in file_list if not contains_arch(x)]
    # Desired result {filename:<f>, x86_64:"Y", i686:{N}, ...}
    file_list_union = set(x86_64_rpms) | set(i686_rpms) | set(noarch_rpms) | set(ppc_rpms) | set(other_rpms)
    file_list_input = []

    if restart:
        restart_set = set()
        # Restarting from a previous failure
        # Everything is already symlinked, we just need to figure out what's left
        # Good thing we kept track in rpm_repository right!?
        for dirpath, dirs, files_in_dir in walk(rpm_repository_path):
            for f in files_in_dir:
                if f.endswith("rpm"):
                    rpm = grab_path_leaf(f).replace(X86_64, SEPARATOR).replace(I686, SEPARATOR).replace(NOARCH, SEPARATOR).replace(PPC, SEPARATOR)
                    restart_set.add(rpm)
        file_list_union = file_list_union.intersection(restart_set)

    for f in file_list_union:

        has_x86_64 = f in x86_64_rpms
        has_i686 = f in i686_rpms
        has_noarch = f in noarch_rpms
        has_ppc = f in ppc_rpms
        has_otherarch = f in other_rpms

        if has_x86_64:
            symlink_src = f.replace(SEPARATOR, X86_64)
        elif has_i686:
            symlink_src = f.replace(SEPARATOR, I686)
        elif has_noarch:
            symlink_src = f.replace(SEPARATOR, NOARCH)
        elif has_ppc:
            symlink_src = f.replace(SEPARATOR, PPC)
        elif has_otherarch:
            symlink_src = f

        if not restart:
            symlink(symlink_src, path.join(rpm_repository_path, grab_path_leaf(symlink_src)))

        entry = {FPATH :grab_path_leaf(f),
                 X86_64: has_x86_64,
                 I686: has_i686,
                 NOARCH: has_noarch,
                 PPC: has_ppc,
                 OTHERARCH : has_otherarch}
        file_list_input.append(entry)

    q_output = Queue()
    q_files = Queue()
    terminal_msg(2, "Processed %d unique rpms" % len(file_list))
    terminal_msg(2, "Entered %d de-duplicated rpms in the queue" % len(file_list_input))
    total_rpm_count = len(file_list_input)

    for x in file_list_input:
        q_files.put(x)

    for x in range(cores):
        p = Process(target = worker_process, args = (q_output, q_files, "Process-%s" % x, worker_dir))
        p.start()

    printer = DBPrinter(output_file, output_dir, output_size, container_name)
    timeout = 3
    rpm_len = len(file_list)
    rpms_processed = 0
    last_count = 0

    while rpms_processed < rpm_len:
        try:
            printer.print_out(q_output.get(block=True, timeout=timeout))
            rpms_processed += 1
            timeout = 3
            write(0, b".")
        except Empty:
            num_active_children = len(active_children())
            if num_active_children == 0:
                #If empty because last child is finished
                #finish writing child
                break
            else:
                #Something's probably just taking a while to process
                #print("Queue empty, but has %d children: continuing" % num_active_children)
                write(0, b".")
                remaining_rpms = (total_rpm_count - rpms_processed)
                if last_count != remaining_rpms:
                    write(0, b"\n")
                    print("Remaining rpm files: %d"  % remaining_rpms)
                    last_count = remaining_rpms
                #print("Current timeout: %d seconds" % timeout)
                sleep(timeout)
                #Exponentially back off on checking while the queue is empty
                timeout *= 2

    printer.close_out()

    if mark_worker_dir_for_removal and (noclean == False):
        try:
            rmtree(worker_dir)
        except Exception as e:
            terminal_msg(1, "Unable to remove worker directory. \n\t Error message: {} {}".format(e.args, e))


def cleanup_process_dir():
    #Cleanup the current directory where we're working
    try:
        entries = listdir(getcwd())
        for en in entries:
            if path.isdir(en):
                retcode, _, _ = run_shell_cmd(["chmod -R a+wx", en])
                if retcode != 0:
                    log_err("Unable to change permissions on %s" % en)
                retcode, _, _ = run_shell_cmd(["rm -rf", en])
                if retcode != 0:
                    log_err("Unable to remove %s" % en)
                #rmtree(en)
            else:
                remove(en)
    except Exception as e:
        log_err("Unable to cleanup directory")
        log_err(getcwd())
        log_err(str(e.args))
        log_err(e.strerror) #issues: no strerror member?
        log_err("---")
        raise e

def rpm_name_process(rpm_dict):
    """
    expecting a dict like this: {filepath: "/path/to/<rpm>.SEPARATOR.rpm", X86_64:True...}
    """
    rpm_leafname = grab_path_leaf(rpm_dict[FPATH].split(D_SEPARATOR)[0])
    log_err("rpm_leafname is %s" % rpm_leafname)
    rpm_parts = rpm_leafname.split('-')
    #print(rpm_leafname)
    #print(rpm_parts)
    rpm_version_parts = [x for x in rpm_parts if x[0].isdigit() == True]

    if len(rpm_version_parts) != 2:
        log_err(rpm_parts)
        log_err(rpm_version_parts)
        log_err ("Warning: %s has unexpected versioning" % rpm_leafname)

    if len(rpm_version_parts) > 1:
        rpm_version = rpm_version_parts[0]
        rpm_release = rpm_version_parts[1]
    elif len(rpm_version_parts) == 1:
        rpm_version = rpm_version_parts[0]
        rpm_release = rpm_version_parts[0] #Just assume the version and release are the same
    else:
        rpm_version = ""
        rpm_release = ""

    out = {
        "package" : rpm_leafname,
        "version" : rpm_version,
        "release" : rpm_release,
        X86_64 : rpm_dict[X86_64],
        I686 : rpm_dict[I686],
        NOARCH : rpm_dict[NOARCH],
        PPC : rpm_dict[PPC],
        OTHERARCH: rpm_dict[OTHERARCH]
    }

    return out


def walk_for_execs():
    execs_out = []
    orphan_leaves = []
    unwanted_file_types = (".js", ".gz", ".lua", ".conf", ".jar", ".tgz", ".tcl")

    for root, dirs, files_in_dir in walk("."):
        for f in files_in_dir:
            full_path = path.join(root, f)
            if path.islink(full_path):
                symlink_path = path.realpath(full_path)
                target = path.basename(symlink_path)
                orphan_file = path.basename(full_path)
                
                if orphan_file.endswith(unwanted_file_types) or target.endswith(unwanted_file_types):
                    continue
                orphan_leaves.append((orphan_file, target))
            else:
                if is_elf_file(full_path):
                    execs_out.append(full_path)
    orphan_leaves = [(orphan, target) for (orphan, target) in orphan_leaves for exec_out in execs_out if target in path.basename(exec_out)]
    return execs_out, orphan_leaves


def grab_path_leaf(x):
    path_list = x.split("/")
    return path_list[-1]

def readelf_grab(x):
    #issues: document output format
    retcode, readelf_output, readelf_err = run_shell_cmd(["readelf -d", x, " | grep 'NEEDED\|RPATH\|RUNPATH'"])
    #print(readelf_output)
    #print(readelf_err)
    if retcode in (0, 1):
        log_err(readelf_output)
        readelf_lines = readelf_output.splitlines()

        needed_match_str = "^.*NEEDED.*\[(?P<needed_so>.*)\].*"
        needed_match = re.compile(needed_match_str)
        rpath_match_str = "^.*PATH.*\[(?P<rpath_so>.*)\].*"
        rpath_match = re.compile(rpath_match_str)

        return ([needed_match.match(x).group("needed_so") for x in readelf_lines if needed_match.match(x)],
                [rpath_match.match(x).group("rpath_so") for x in readelf_lines if rpath_match.match(x)])
    else:
        log_err(readelf_err)
        raise Exception("readelf unexpectedly terminated by signal %d " % -retcode)

def symbol_grab(x):
    """
    Grab and process the symbols. The expected output from the shell cmd will be
    TYPE:BINDING:SYMBOL
    So, FUNC:GLOBAL:tmconf_mcpmsg_set_metadata
    would be processed into
    {symbol: tmconf_mcpmsg_set_metadat, typ: FUNC, binding: GLOBAL, at: ""}
    Some (GLIBC functions in particular) may look something like this
    FUNC:WEAK:symbol@GLIBC_2.2.5
    the last part goes into the "at" entry
    {symbol: symbol, typ: TYPE, binding: WEAK, at: "GLIBC_2.2.5"}
    """
    cmd_str = "readelf -s --wide %s | awk \' $1 ~ /[0-9]\:$/ {print $4\":\"$5\":\"$7\":\"$8}\'" % x
    retcode, symbols, symbol_err = run_shell_cmd(cmd_str)
    output = {}
    if retcode == 0:
        symbol_list = symbols.split('\n')

        for s in symbol_list:
            s_info = s.split(":")

            if (len(s_info) != 4):
                if s_info:
                    log_err("symbols split into " + ":".join(s_info))
                    log_err("***")
                continue

            typ = s_info[0]
            bind = s_info[1]
            if bind == "LOCAL":
                continue
            #print(s_info[2])
            if s_info[2] == "UND":
                defed = "NO"
            else:
                defed = "YES"
            sym_list = s_info[3].split("@")
            symbol = s_info[3]

            if (typ not in ("FUNC", "IFUNC")):
                log_err("Skipping adding %s, type %s, bind %s, defined? %s" % (symbol, typ, bind, defed))
                continue
            long_name = cppdemangle(sym_list[0])
            at = ""

            if (len(sym_list) >= 2):
                at = sym_list[-1]

            symbol_info = {"type": typ, "binding": bind, "defined": defed, "long_name": long_name.strip(), "at": at}

            output[symbol] = symbol_info
    else:
        log_err(symbol_err)

    return output


def readelf_list_process(executables):
    """
    Run readelf to get the executable dependencies and rpaths for the executable files
    """
    so_dict = {}
    full_exec_set = set()
    full_depend_set = set()
    for x in executables:
        exec_name = grab_path_leaf(x)

        full_exec_set.add(exec_name)

        so_dict.setdefault(exec_name, {"dependencies":[], "symbols" : {}, "rpath" : []})

        dep_list, rpath_list = readelf_grab(x)

        so_dict[exec_name]["dependencies"].extend(dep_list)
        so_dict[exec_name]["rpath"].extend(rpath_list)
        full_depend_set |= set(dep_list)
        so_dict[exec_name]["dependencies"] = list(set(so_dict[exec_name]["dependencies"]))

        symbol_dict = symbol_grab(x)
        so_dict[exec_name]["symbols"].update(symbol_dict)

        log_err("%s has %d dependencies and  %d symbols" % (exec_name, len(dep_list), len(symbol_dict)))

    output = {}
    output["All dependencies"] = list(full_depend_set)
    output["All executables"] = list(full_exec_set)
    output["executables"] = so_dict
    return output

def objdump_process(executables):
    """
    Objdump the executables into a file <executable>-dump
    """
    assembly_objs = {}
    for x in executables:
        _, assembly_code, _ = run_shell_cmd("objdump -d " + x)
        assembly_code = assembly_code
        assembly_obj = assemblyparser.AssemblyRaw(text = assembly_code)
        assembly_objs[path.basename(x)] = assembly_obj.create_json_data()

    return assembly_objs

def run_shell_cmd(x):
    """
    Runs a shell cmd, returns tuple (retcode, stdout, stderr).
    Obviously runs as a full shell cmd, so avoid using untrusted input
    """
    stdout_tmp = TemporaryFile()
    stderr_tmp = TemporaryFile()
    stdout_str = ""
    stderr_str = ""

    cmd_str = x
    if (isinstance(x, list)):
        cmd_str = " ".join(x)

    p = Popen(cmd_str, stdout = stdout_tmp, stderr = stderr_tmp, shell=True)
    p.wait()

    stdout_tmp.seek(0)
    stderr_tmp.seek(0)

    retcode = p.returncode
    #stdoutput, stderrput = p.communicate()

    stdout_str = stdout_tmp.read()
    stderr_str = stderr_tmp.read()

    return (retcode, stdout_str.decode("utf-8"), stderr_str)

def merge_data(readelf_list, objdump_list):
    so_list = list(objdump_list.keys())
    
    all_execs = [x for x in so_list if x in readelf_list["All executables"]]

    for so in all_execs:
        defined_funcs = objdump_list[so]["defined_functions"]
        readelf_symbol_dict = readelf_list["executables"][so]["symbols"]
        shared_defined_funcs = [x for x in defined_funcs if x in readelf_symbol_dict]
        extra_funcs = [x for x in defined_funcs if x not in readelf_symbol_dict]

        for symbol in shared_defined_funcs:
            readelf_symbol_dict[symbol].update({"called_functions": defined_funcs[symbol]["called_functions"]})

        for symbol in extra_funcs:
            readelf_symbol_dict.update({symbol : {
                    "defined": "YES",
                    "binding": "LOCAL",
                    "at" : "",
                    "long_name": symbol,
                    "called_functions": defined_funcs[symbol]["called_functions"]}})

    return readelf_list

def rehome_orphans(output, orphans):
    executables = output["executables"]
    for symlink, target in orphans:
        try:
            symlink_data = executables[target]
        except KeyError:
            #print("Unable to rehome " + symlink + " targeted to " + target)
            continue
        output["All executables"].append(symlink)
        symlink_data["Symlink Target"] = target
        new_symlink_dict = {symlink: symlink_data}
        output["executables"].update(new_symlink_dict)

    return output

def process_executables(executables):
    readelf_list = readelf_list_process(executables)
    objdump_list = objdump_process(executables)
    #output.update(readelf_list)
    #output.update(objdump_list)
    output = merge_data(readelf_list, objdump_list)
    return output

def process_rpm(rpm_dict):
    output = rpm_name_process(rpm_dict)
    #print("output has %d items" % (len(output)))

    executables, orphans = walk_for_execs()

    executable_information = process_executables(executables)
    output.update(executable_information)
    output = rehome_orphans(output, orphans)
    return output

def worker_process(q_output, q_files, name, worker_dir):
    """
    Ensure name is unique.
    mkdir name/
    for f in file_list:
        <check applicable architectures>
            if f[X86_64]: file_path = f[FPATH].replace(SEPARATOR, x86_64)
        cp filepath name/
        rpm2cpio <rpm file> |
        find executable files
        run readelf
        parse output
        place in q.
    """
    global current_directory
    chdir(current_directory)

    full_worker_dir = path.join(worker_dir, name)
    global process_name
    process_name = name

    log_err("start dirs")
    log_err(getcwd())
    log_err(worker_dir)
    log_err(name)
    log_err(full_worker_dir)
    log_err("end dirs")
    try:
        mkdir(full_worker_dir)
    except OSError:
        #already there, no worries
        pass

    chdir(full_worker_dir)
    #print(full_worker_dir)
    devnull_f = open(devnull, "w") #To not redirect stdout/stderr

    while (q_files.empty() == False):
        try:
            x = q_files.get(block = True, timeout = 2)
        except Empty:
            return

        #Received a dict here
        filename = x[FPATH] #contains SEPARATOR
        if x[X86_64]:
            filename = filename.replace(SEPARATOR, X86_64)
        elif x[I686]:
            filename = filename.replace(SEPARATOR, I686)
        elif x[NOARCH]:
            filename = filename.replace(SEPARATOR, NOARCH)
        elif x[PPC]:
            filename = filename.replace(SEPARATOR, PPC)
        else:
            #do nothing since we didn't change rpm name
            pass
        #print(filepath)
        with open ("tmpfile", 'w') as tmp:
            log_err("PROCESSING: %s" % str(x))
            try:
                #check_call(["cp", x, "."])
                p = Popen(["rpm2cpio", path.join("../rpm-repository", filename)], stdout=tmp)
                p.wait()
            except Exception as e:
                log_err("tmpfilecreate exception")
                log_err(x)
                log_err(e)
                log_err("%s errored out on rpm2cpio" % process_name)
                terminal_msg(0, "%s errored out on rpm2cpio" % process_name)
                

        try:
            check_call(["cpio -idm --no-preserve-owner < tmpfile"], shell=True,
                       stdout=devnull_f, stderr=devnull_f)
        except Exception as e:
            log_err("unpacking error")
            log_err(x)
            log_err(e)
            log_err ("%s errored out on unpacking" % process_name)
            terminal_msg(0, "%s errored out on unpacking" % process_name)
            

        processed_data = process_rpm(x)
        q_output.put({processed_data["package"] : processed_data})
        cleanup_process_dir()
        unlink(path.join("../rpm-repository", filename))

    log_err(name + " has completed!")
    err_file.close()
    devnull_f.close()

def run(rpm_directory, worker_directory, output_directory, product, software_version, process_count):
    global worker_dir
    global restart
    global rpm_dir
    global output_dir
    global noclean
    global current_directory
    global debug_process
    global mark_worker_dir_for_removal

    worker_dir = worker_directory
    restart = False
    output_file = software_version
    rpm_dir = rpm_directory
    output_dir = output_directory
    output_size = 10 * (2 ** 20)
    noclean = True
    current_directory = getcwd()
    debug_process = False
    mark_worker_dir_for_removal = True

    cores = process_count
    container_name = "%s:%s" % (product, software_version)

    # create directory if not exist
    if not path.exists(worker_directory):
        try:
            mkdir(worker_directory)
        except OSError as e:
            terminal_msg(0, "Failed to create worker directory for rpm_db_builder. OS Error: {0}".format(e))
            
    if not path.exists(output_directory):
        try:
            mkdir(output_directory)
        except OSError as e:
            terminal_msg(0, "Failed to create output directory for rpm_db_builder. OS Error: {0}".format(e))

    writer_process (cores, container_name, output_file, output_size)


if __name__ == "__main__":
    p = ArgumentParser(description=__doc__)

    p.add_argument("-r", "--rpm_directory", type=str, required=True,
                   help="The root directory where RPM files will be found in subdirectories.")
    p.add_argument("-p", "--processes", type=int, default=10,
                   help="The number of processes that can be utilized to examine rpm files.")
    p.add_argument("-w", "--worker_directory", type=str,
                   help="The directory where RPM files will be unpacked for processing.")
    p.add_argument("-d", "--output_directory", type=str,
                   help="The directory where output files are written.")
    p.add_argument("-s", "--size", type=int, default=10,
                   help="The rough maximum size of the output files in megabytes. 0 means print only to one file.")
    p.add_argument("-n", "--noclean", action="store_true",
                   help="Don't delete the directories where worker processes were unpacking rpm files or the directory created if one isn't given")
    p.add_argument("-v", "--debug-process", action="store_true",
                   help="Unpack and process only debuginfo rpms for processing. Warning: takes a while longer....")
    p.add_argument("-b", "--product", type=str, default="BIG-IP",
                   help="The product being examined.")
    p.add_argument("-o", "--software_version", type=str, default="test",
                   help="The software version of the product.")
    p.add_argument("-e", "--restart", action="store_true",
                   help="If restarting after error, gather rpm files to process from this directory. -o, -w and -d need to be specified as well.")
    args = p.parse_args()

    current_directory = getcwd()
    rpm_dir = args.rpm_directory
    cores = args.processes
    output_file = args.software_version
    mark_worker_dir_for_removal = args.noclean
    restart = False

    product = args.product
    version = args.software_version
    container_name = "%s:%s" % (product, version)

    if args.restart:
        if (args.software_version == "test") or (not args.worker_directory) or (not args.output_directory):
            terminal_msg(0, "If restarting from previous failure, the software_version, worker_directory, and output_directory must be specified")
        else:
            restart = True

    if args.worker_directory:
        worker_dir = args.worker_directory
        mark_worker_dir_for_removal = False
    else:
        worker_dir = output_file + "-worker-dir"
        try:
            mkdir(worker_dir)
        except OSError:
            pass

    if args.output_directory:
        output_dir = args.output_directory
    else:
        output_dir = output_file + "-output-dir"
        try:
            mkdir(output_dir)
        except OSError:
            pass

    output_size = args.size * (2**20)
    debug_process = args.debug_process

    noclean = args.noclean

    writer_process (cores, container_name, output_file, output_size)

    terminal_msg(2, "Completed happily!")
