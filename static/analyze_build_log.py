#!/usr/bin/env python3

"""
This tool is defined to root out static dependencies from examining build logs.
The logic will look largely as follows.
---------------------------------
ar examination:

This will examine usage of the ar command and determine the archive file created.
A sample ar command will look something like this.

ar crv obj/libdag.a obj/dag_api.o obj/dag_pci.o

This will create an archive file called libdag.a. We can use this later when resolving dependecies
----------------------------------
gcc/g++ examination:

These commands get get pretty complicated and hard to read.

For example, take this compilation call:
g++ -Wl,-z,combreloc -Wl,--sort-common -Wl,--warn-common -Wl,--warn-once -Wl,--build-id -L/home/f5cm/cm/tmos-tier2/1113241/f5_build/devfs/usr/lib -L/home/f5cm/cm/tmos-tier2/1113241/f5_build/devfs/lib -Wl,-rpath-link=/home/f5cm/cm/tmos-tier2/1113241/f5_build/devfs/usr/lib:/home/f5cm/cm/tmos-tier2/1113241/f5_build/devfs/lib obj/f5-ball.o obj/prgm-pic.o obj/dss-key.o obj/get-slot.o obj/get-led.o obj/spr-reset.o obj/can-cmd.o obj/main.o obj/spr-capture.o obj/spr-power.o -lcand_client -llopd_client -lhal_fwmgr -lf5cppcommon -lerrdefs -lhal -lhalmsg -lcpp -lcrypto -o obj/bladectl

Luckily, we only need to focus on a subset of these options.
-l <library_name>
    This is a direct name of the library we're linking against.
    The extension from this library name will indicate the exact library used.

-l<library_postfix>
    Note the lack of a whitespace character after -l.
    This will give us a postfix of the library we're using, but won't tell us if it's a .a or a .so file.

-static
    This option ensures that when a static library option is available, that will be chosen.
    Otherwise, the dynamic library option will be preferred.

-static-libgcc
-static-libasan
-static-libtsan
-static-libubsan
-static-libstdc++
    These options say to statically link the given library (libgcc, etc)

"""
import os
import re
import sys
import shutil
import pprint
from pathlib import Path
from argparse import ArgumentParser
from json import dump

import extract_rpm_names
import sql_processor
from lib import *

# Grep command that does well getting gcc commands
# grep " gcc " * | grep  " gcc\s*[-'.]" | grep -v checking | less
# grep " g++ " * | grep  " g++\s*[-'.]" | grep -v checking | less

# Grab calls to ar, but stop after hitting a special bash character
# Basic idea being we can handle a line like this
# <blah> ar lib.a b.o c.o; <doing something else>
ar_regex = re.compile("\\s*ar\\s+.*\\s(?P<static_lib>\\S*\\.a) (?P<object_files>[^|&;>#]*)") #revision: explicit escape sequences

gcc_regex = re.compile("gcc ")
gpp_regex = re.compile("g\\+\\+ ") #revision: explicit escape sequences
output_regex = re.compile(" -o\\s+(?P<object_file>\\S+)\\s*") #revision: explicit escape sequences

# Like -lmcpmsg, we need to figure out the exact libmcpmsg.o
lib_implicit_regex = re.compile(" -l(?P<library_postfix>\\S+)\\s*") #revision: explicit escape sequences
# Note the space after -l
# like -l mcpmsg.so, we already have exact binary linked
lib_explicit_regex = re.compile(" -l\\s+(?P<library_name>\\S+)\\s*") #revision: explicit escape sequences

static_regex = re.compile(" -static ")
libgcc_static_regex = re.compile(" -static-libgcc ")
libasan_static_regex = re.compile(" -static-libasan ")
libtsan_static_regex = re.compile(" -static-libtsan ")
libubsan_static_regex = re.compile(" -static-libubsan ")
libstdcpp_static_regex = re.compile(" -static-libstdc\\+\\+ ") #revision: explicit escape sequences
bstatic_regex = re.compile("-Bstatic")
bdynamic_regex = re.compile("-Bdynamic")


# Collects object and archive files
object_file_regex = re.compile("\\s*\\S*\\.o") #revision: explicit escape sequences
archive_file_regex = re.compile("\\s*\\S+\\.a") #revision: explicit escape sequences
c_file_regex = re.compile("\\s*(?P<c_file>\\S*\\.c)") #revision: explicit escape sequences

# Determines if the gcc or gpp macro just produces a make rule
# These are -M, -MM, -MG, -MP, -MT, -MQ, -MD, -MMD
make_rule_output_regex = re.compile("\\s-M[MGPTDQ][M]?\\s") #revision: explicit escape sequences


def examine(filename):
    """
    examine build log file provided and return the following data structure of the extracted information.

    {
        <executable> :
            {
                libraries: # The libraries/objects linked
                    {
                        <library_name>:
                            {
                                statically_linked: <y|n|unknown>
                                object_path: <where object came from, if known>
                            }
                        <lib2>: {...}
                    }
                buildroot_path: </path/to/library/>
                linkage_preference: <static|dynamic|NA>    # Whether this executable prefer to be linked statically
                install_as : <"destination (new name) from install command">
            }
    }

    @param
    filename        file name of the log file (e.g., "logs/errdefsd x86_64.0.0.1324")
    """
    #Currently, this is expecting one rpm per buildlog file

    # We'll create a list of the executables found
    # Extract the object files created and create a data structure like this

    #revision: finish migrating to the following data structure. TODO: add version/rpm and integrate with extract_rpm_names


    result = {}
    
    # open file, ignore encoding errors
    with open(filename, 'r', errors="ignore") as f:
        previous_line = ""

        # iterate over line by line
        for line in f:
            line = line.strip()
            if line.endswith("\\"):
                # if line ends with a continuation, trim the backslash ('\'), add a whitespace, and append to previous_line
                previous_line = previous_line + line[:-1] + " "
                continue
            else:
                line = previous_line + line
                # reset previous_line
                previous_line = ""

            # search on 'ar' command
            ar_search = ar_regex.search(line.strip())
            if (ar_search):
                full_buildroot_path = Path(ar_search.group("static_lib"))
                object_components = [Path(x) for x in ar_search.group("object_files").split()]

                executable = full_buildroot_path.name
                buildroot_path = str(full_buildroot_path.parent)

                linkage_preference = "static"

                libraries = {}
                for x in object_components:
                    object_name = x.name
                    # .lo files and .la files are created for use with libtools
                    if object_name.endswith(".lo"):
                        object_name = object_name.replace(".lo", ".o")
                    if object_name.endswith(".la"):
                        object_name = object_name.replace(".la", ".a")

                    if not object_name.endswith(".a") and not object_name.endswith(".o"):
                        # A bit of a cheat, but we'll just ignore files that
                        # we know aren't objects or archives
                        # We're typically dealing with a situation like this
                        # ar ruv libback_bdb.a `echo init.lo... cache.lo trans.lo monitor.lo | sed 's/\.lo/.o/g'` version.o
                        continue

                    object_path = str(x.parent)
                    statically_linked = "y"
                    library_name = object_name
                    #revision: always use full name for library now; rpm_source will be moved to the parent of executable layer
                    libraries[library_name] = {
                                                "statically_linked": statically_linked,
                                                "object_path": object_path
                                            }
                if executable in result:
                    print("Viewing an executable twice")
                    print("\t", line)
                    print("\texecutable:", executable)
                    print("\t\tlibraries", libraries)
                    print("\t\tlinkage_preference", linkage_preference)

                result[executable] = {
                                        "libraries": libraries,
                                        #revision: linkage key is deprecated, replaced by its subkey buildroot_path
                                        "buildroot_path": buildroot_path,
                                        "linkage_preference": linkage_preference
                                    }


            elif (gcc_regex.search(line) or gpp_regex.search(line)):
                #print(line)
                if line.startswith("checking "):
                    #Ignore logs like this
                    # checking whether g++ accepts -g... yes
                    continue

                executable_name = "Output not given"
                buildroot_path = ""
                linkage_preference = "dynamic"
                libraries = {}
                #if make_rule_output_regex.search(line):
                    #print("Skipping line with -M* option.")
                    #print(line)
                    #continue
                output_search = output_regex.search(line)
                c_file_search = c_file_regex.search(line)

                if output_search:
                    #We found the output file from this gcc call
                    #print(output_search.group("object_file"))
                    full_buildroot_path = Path(output_search.group("object_file"))
                    executable_name = full_buildroot_path.name
                    buildroot_path = str(full_buildroot_path.parent)

                elif (c_file_search):
                    #We didn't find an object,but we did find a .c file
                    #The usual rule is to change it to .o, so let's do that.
                    full_buildroot_path= Path(c_file_search.group("c_file"))
                    executable_name = full_buildroot_path.name
                    buildroot_path = str(full_buildroot_path.parent)

                if (libgcc_static_regex.search(line)):
                    #libgcc and libstdc++ static library names are definitely correct
                    #libasan, libtsan, and libubsan static libraries aren't used (as far as i can tell)
                    #So, the library name may be incorrect
                    libraries["libgcc.a"] = {
                                            "statically_linked":'y',
                                            "object_path": ""
                                            }

                if (libasan_static_regex.search(line)): #Haven't been seen in the logs
                    libraries["libasan.a"] = {
                                            "statically_linked":'y',
                                            "object_path": ""
                                            }

                if (libtsan_static_regex.search(line)): #Haven't been seen in the logs
                    libraries["libtsan.a"] = {
                                            "statically_linked":'y',
                                            "object_path": ""
                                            }

                if (libubsan_static_regex.search(line)): #Haven't been seen in the logs
                    libraries["libubsan.a"] = {
                                            "statically_linked":'y',
                                            "object_path": ""
                                            }

                if (libstdcpp_static_regex.search(line)):
                    libraries["libstdc++.a"] = {
                                            "statically_linked":'y',
                                            "object_path": ""
                                            }

                if static_regex.search(line):
                    #Check which library (.a or .so) is preferred when linking
                    linkage_preference = "static"
                

                # ld -Bstatic Processing

                # match on '-Bstatic' switch of ld command
                bstatic_match = bstatic_regex.search(line)

                # if match found in line
                if bstatic_match:
                    # get the string index of the end of matched static group
                    bstatic_index = bstatic_match.end()

                    # search if match on '-Bdynamic' switch of ld command
                    bdynamic_match = bdynamic_regex.search(line)
                    # if match found in line
                    if bdynamic_match:
                        # get the string index of the end of matched dynamic group
                        bdynamic_index = bdynamic_match.end()

                        # ^... -Bstatic( -... )-Bdynamic -... $
                        if bstatic_index < bdynamic_index:
                            bstatic_slice = line[bstatic_index:bdynamic_match.start()]
                        # ^... -Bdynamic -... -Bstatic( -... )$
                        else:
                            bstatic_slice = line[bstatic_index:]
                    # ^... -Bstatic( -.... )$
                    else:
                        bstatic_slice = line[bstatic_index:]
                    
                    # split on whitespace to get each switch with its param; retrieve the library name section of only the ones started with -l 
                    # ld -l(library) : the archive or object file specified by namespec to the list of files to link
                    token_list = [switch[2:] for switch in bstatic_slice.split() if switch.startswith('-l')]

                    # store into libraries dictionary
                    for lib in token_list:
                        libraries[lib] = {
                                            "statically_linked": 'y',
                                            "object_path": ""
                                        }
                    
                # regex for searching implicitly referred binaries
                for x in lib_implicit_regex.findall(line):
                    #issues: need fix as the name here may be incorrect
                    #The full name is unknown because we don't know which lib version is used
                    library_name = "lib" + x

                    statically_linked = "unknown"
                    object_path = "unknown"
                    libraries[library_name] = {
                                                "statically_linked": statically_linked,
                                                "object_path": object_path
                                            }
                # regex for searching explicitly specified binaries
                for x in lib_explicit_regex.findall(line):
                    library_full_path = Path(x)
                    library_name = library_full_path.name
                    library_path = str(library_full_path.parent)
                    if library_name.endswith(".a") or (".a." in library_name):
                        statically_linked = "y"
                    else:
                        statically_linked = "n"
                    
                    libraries[library_name] = {
                                                "statically_linked": statically_linked,
                                                "object_path": library_path
                                            }
                # regex for searching archive files
                for x in archive_file_regex.findall(line):
                    library_full_path = Path(x)
                    library_name = library_full_path.name
                    library_path = library_full_path.parent
                    statically_linked = "y"
                    libraries[library_name] = {
                                                "statically_linked": statically_linked,
                                                "object_path": library_path
                                            }

                result[executable_name] = {
                                            "libraries": libraries,
                                            "buildroot_path": buildroot_path,
                                            "linkage_preference": linkage_preference
                                        }

                # if executable name not found, debug
                if (executable_name == "Output not given"):
                    print(filename)
                    print(line)

    # Process UNIX install command in build logs.
    # The extracted information will be stored in the following format:  result[<source executable>]['installed_as']
    # (e.g.), result['tmm-padc64.use']['installed_as'] = ['tmm64.pgo_use']

    # init 'installed_as' to null string
    for _, value in result.items():
        value.update({'installed_as': ""})

    # if both filename (prev and new) always have / in path, use the following regex to get a more precise result.
    # install_regex = re.compile("install -[^d;]*?\s[^;]*?\/([^\/\s]*?)\s[^;]*?([^\/]*?)[\r\n;]")
    install_string_regex = re.compile("install.*?[\\r\\n;]")
    with open(filename, 'r', errors="ignore") as f:
        matched_str_list = install_string_regex.findall(f.read())

    # init dict that will be storing format of {'previous_name': 'new_name', ...}
    install_record = {}

    for matched_str in matched_str_list:
        seg_list = matched_str.rstrip().replace(";", "").split(' ')
        for i in range(-1, -len(seg_list), -1):
            if seg_list[i] != "":
                for j in range(i-1, -len(seg_list), -1):
                    if seg_list[j] != "":
                        # previous_name = seg_list[j] ; installed_name = seg_list[i]
                        install_record[seg_list[j].split('/')[-1]] = seg_list[i].split('/')[-1]

                        # only insert the last pair (real prev:new name pair) per seg_list
                        break
                break

    #debug
    #print(install_record)

    for key, value in result.items():
        if key in install_record.keys():
            value.update({'installed_as': install_record[key]})


    return result

def print_executable_library_dependencies(data_dict, file_obj=sys.stdout):
    # This will print the results from examine
    # The indented libraries are what's compiled into the binary
    # We won't print out .o files for now for brevity
    #print("calling print_executable_library_dependencies")
    #print(data_dict)
    whitespace = "\t"

    #issues: buildroot_path (originally under linkage) not printed. confirm if this is the design


    for d, v in data_dict.items(): # d = executables
        # alternatively, do something like the following two print statements
        # print(v['libraries'])
        # print(v['linkage_preference'])
        for key, value in v.items():
            if key == 'buildroot_path':
                print (whitespace + "build root path: " + value, file=file_obj)

            if key == 'linkage_preference':
                print (whitespace + "linkage preferred: " + value, file=file_obj)

            if key == 'installed_as':
                print (whitespace + "renamed to: " + value, file=file_obj)

            if key == 'libraries':
                print (whitespace + "linked libraries: ", file=file_obj)
                for lib, _ in value.items(): #revision: change unused variable to _
                    print (whitespace + whitespace + lib, file=file_obj)


def write_log(build_log_name, output_directory, log_so_list, log_uninserted_list):
    '''
    Logging mechanism for alerts raised.
    '''
    # always overwrite logs for every run (current settings, can be modified)

    # define output directory for logs
    out = Path(output_directory)
    log_output_dir = out / 'logs'

    # create destination directory if not exist
    if not log_output_dir.exists():
        utility.terminal_msg(2, "Creating directory for logs..")
        try:
            log_output_dir.mkdir()
        except OSError as e:
            print("OS Error: {0}".format(e))
            utility.terminal_msg(0, "Failed to create logs directory. Please check if you have enough permission to do so.")

    try:
        # log the list of *.so not parsed into database from rpm_dissector function
        log_so = log_output_dir / (build_log_name + ".so-not-exist.log")
        log_so.open('w').write(pprint.pformat(log_so_list, indent = 4))

        # log the list of dependencies that has not yet been parsed into database since their names have not yet found a match in execs or aliases table.
        log_uninserted = log_output_dir / (build_log_name + ".to-parse.log")
        log_uninserted.open('w').write(pprint.pformat(log_uninserted_list, indent = 4))
    except Exception:
        utility.terminal_msg(1, "Error occurred while writing the logs. Skipping the process..")
    finally:
        utility.terminal_msg(2, "Logging completed.")


def examine_directory(directory, output_directory, clean_directory, product, version):
    '''
    Iterate over the directory and call examine() for each build log file.

    @param
    directory           the source directory that contains build logs
    output_directory    directory to place the output
    clean_directory     whether the output directory should be cleaned before writing (True / False)
    product             the exact product name that will be parsed into database
    version             the exact version number that will be parsed into database
    '''

    p = Path(directory)
    o = Path(output_directory)

    # check if the given directory is valid
    if not p.exists() or not p.is_dir():
        utility.terminal_msg(0, "The source directory {0} does not exist.".format(directory))

    if not o.exists():
        utility.terminal_msg(1, "The output directory {0} does not exist.".format(output_directory))
        utility.terminal_msg(2, "Creating output directory..")
        try:
            os.makedirs(o)
        except OSError as e:
            print("OS Error: {0}".format(e))
            utility.terminal_msg(0, "Failed to create output directory with the given path. Please check if you have enough permission to do so.")

    # clean all files within the directory before processing if required
    if clean_directory:
        for f in o.iterdir():
            try:
                if f.is_file():
                    f.unlink()
                elif f.is_dir():
                    shutil.rmtree(f)
            except OSError as e:
                utility.terminal_msg(1, "Error occurred on cleaning the output directory before executing.")
                print(e)

    # define the path to store the result
    result_path = o / 'rpm_names'

    # call extract_rpm_names to extract rpms involved in each log file
    extract_rpm_names.load_file(str(p.resolve()), d=result_path)
    

    # look for the default output directory of extract_rpm_names
    if not result_path.exists():
        utility.terminal_msg(0, "Output directory %s generated from extract_rpm_names cannot be found." % result_path)


    for f in p.iterdir():
        # Expecting filename like tmplugin:i686.0.0.1868

        # If f is not a file, ignore it.
        if not f.is_file():    
            continue

        # find the file with the same name as build log under output_dir/rpm_names
        f_rpm_extract = result_path / (f.name + ".txt")

        # init list
        rpm_list = []

        # read the output from extract_rpm_names into a list
        if f_rpm_extract.exists():
            rpm_list = [r for r in f_rpm_extract.read_text().splitlines()]
        # as a fallback approach, when the output file does not exist, use the build log name.
        else:
            utility.terminal_msg(1, "The correlated rpm extract for this build log does not exist, using build log name as rpm name.")
            rpm_list = [f.name.split(":")[0]]


        output_file = Path(o) / f.name
        if output_file.exists():
            # Assuming we've seen a version compiled to a different architecture. Skipping
            continue
        else:
            res = examine(f)

            log_so_list, log_uninserted_list = sql_processor.parse_data_to_db(res, rpm_list, product, version)

            # log the lists
            write_log(p.name, output_directory, log_so_list, log_uninserted_list)

            # json dump
            #of = output_file.open("w")
            #dump({f.name.replace(":", "-"):res}, of, sort_keys = True, indent = 4, separators = (',', ': '))
            #of.close()

            # print resilt set
            #print_executable_library_dependencies(res, of)
            


def examine_file(build_log, output_directory, clean_directory, product, version):
    '''
    Call examine() for processing a single build log file.

    @param
    build_log           build log to analyze
    output_directory    directory to place the output
    product             the exact product name that will be parsed into database
    version             the exact version number that will be parsed into database
    '''
    p = Path(build_log)
    o = Path(output_directory)

    # check if the given build log is a valid file
    if not p.exists() or not p.is_file():
        utility.terminal_msg(0, "The source build log {0} does not exist or not a valid file.".format(build_log))

    if not o.exists():
        utility.terminal_msg(1, "The output directory {0} does not exist.".format(output_directory))
        utility.terminal_msg(2, "Creating output directory..")
        try:
            os.makedirs(o)
        except OSError as e:
            print("OS Error: {0}".format(e))
            utility.terminal_msg(0, "Failed to create logs directory. Please check if you have enough permission to do so.")

    # clean all files within the directory before processing if required
    if clean_directory:
        for f in o.iterdir():
            try:
                if f.is_file():
                    f.unlink()
                elif f.is_dir():
                    shutil.rmtree(f)
            except OSError as e:
                utility.terminal_msg(1, "Error occurred on cleaning the output directory before executing.")
                print(e)

    # define the path to store the result
    result_path = o / 'rpm_names'

    # call extract_rpm_names to extract rpms involved in the log file
    extract_rpm_names.load_file(str(p.resolve()), f=True, d=result_path)

    # find the file with the same name as build log under output_dir/rpm_names
    f_rpm_extract = result_path / (p.name + ".txt")

    #debug
    #print(f_rpm_extract.resolve())

    # init list
    rpm_list = []

    # read the output from extract_rpm_names into a list
    if f_rpm_extract.exists():
        rpm_list = [r for r in f_rpm_extract.read_text().splitlines()]
    # as a fallback approach, when the output file does not exist, use the build log name.
    else:
        utility.terminal_msg(1, "The correlated rpm extract for this build log does not exist, using build log name as rpm name.")
        rpm_list = [p.name.split(":")[0]]

    # do the examine for this log file
    res = examine(p)

    # parse into database
    log_so_list, log_uninserted_list = sql_processor.parse_data_to_db(res, rpm_list, product, version)

    # log the lists
    write_log(p.name, output_directory, log_so_list, log_uninserted_list)

    # print result set
    #print_executable_library_dependencies(res)



if __name__ == "__main__":
    pass

    '''
    p = ArgumentParser()

    p.add_argument("-d", "--directory", type=str,
                   help= "A directory of build log files to examine.")
    p.add_argument("-o", "--output_directory", type=str, default="./output/",
                   help="A directory to place the output, if none is given <cwd>/output is created.")
    p.add_argument("-c", "--clean_output_directory", action="store_true",
                   help="Cleanup the output directory before writing to it.")
    p.add_argument("-f", "--filename", type=str,
                   help="The build log file to examine.")
    args = p.parse_args()


    if args.filename:
        #revision: since we would like to use extract_rpm_names to tell what rpm is actually involved instead of using build log names directly, it's better to write another function to prepare the params
        examine_file(args.filename)


    if args.directory:
        #revision: not necessary for examine_directory to return anything.
        examine_directory(args.directory, args.output_directory, args.clean_output_directory)
    '''