#!/usr/bin/env python3

import os
import sys
import re
import argparse
import pprint
from pathlib import Path

from lib import *

# dictionary used for storing data structure before dumping to file when 's' (single file) output type is selected.
final_dict = {}


def load_file(src_path, **kwargs):
    '''
    Inspect a single file or iterate over build log files under the designated source directory, open, and read.

    @param
    src_path                        path of the source directory / file
    dest_path   kwargs key: 'd'     path of the output directory (by default "./result/")
    output      kwargs key: 'o'     the output type (by default "m"; if isFile is True, output is always "m")
    isFile      kwargs key: 'f'     is the source a file? (default: False = directory; True = file)
    '''
    # default init for the params
    dest_path = "./result/"
    output = "m"
    isFile = False

    # parse keyword arguments
    for key, val in kwargs.items():
        if key == 'd':
            dest_path = str(val)

        if key == 'o':
            # check the validity of output type
            if val != "s" and val != "m":
                raise Exception("Invalid output type option selected for extract_rpm_names.load_file().")
            else:
                output = val

        if key == 'f':
            # allow a range of patterns for lazy parameter parsing
            if val in [True, 1, 'true', 'True', 't', 'T', '1']:
                isFile = True
            elif val in [False, 0, 'false', 'False', 'f', 'F', '0']: 
                isFile = False
            else:
                raise Exception("Invalid param isFile for extract_rpm_names.load_file(). (expecting boolean type)")

    # create destination directory if not exist
    if not os.path.exists(dest_path):
        try:
            os.mkdir(dest_path)
        except OSError as e:
            utility.terminal_msg(0, "extract_rpm_names failed to create output directories for storing rpm names. \n\t OS Error: {0}".format(e))

    #debug
    #print("Selected directory: %s" % src_path)

    # if the src_path is pointing to a single file
    if isFile:
        #debug
        #print("# Load file: " + str(path.name))
        
        path = Path(src_path)

        # open and read file
        f = open(str(path.resolve()), "r", errors="ignore")
        content = f.read()
        res = parse_file(content)
        f.close()

        # if there is only one single build log to analyze, always use "m" option. (print into an output file that shares the same name with build log)
        # current build logs have no file extension / suffix, hence path.name is used (return final path component); otherwise, use path.stem to remove suffix
        print_multi(res, dest_path, str(path.name))

    # if the src_path is pointing to a directory
    else:
        for path in filter(lambda p: p.is_file(), Path(src_path).iterdir()):
            #debug
            #print("# Load file: " + str(path.name))
            
            # open and read file
            f = open(str(path.resolve()), "r", errors="ignore")
            content = f.read()

            # process file
            res = parse_file(content)

            # close file
            f.close()

            if output == "s":
                # construct dictionary: {'build_log_name' : ['rpm_name1', 'rpm_name2'...]}
                # current build logs have no file extension / suffix, hence path.name is used (return final path component)
                final_dict[str(path.name)] = list(res)

                #debug
                #print ("\nCurrent structure of dict: \n")
                #print(final_dict)

            elif output == "m":
                # print to multi files
                # current build logs have no file extension / suffix, hence path.name is used (return final path component)
                print_multi(res, dest_path, str(path.name))
        
        if output == "s":
            print_single(dest_path)


def parse_file(content):
    '''
    Determine rpms built in a log file.

    @param
    content     file content of a single log file

    @return
    A filtered list of rpm names
    '''
    
    # exempt rpms that does not need to take into consideration.
    exempt_list = ["debug", "devel"]

    # regex for extracting valid rpm packages (e.g., Wrote: /home/f5cm/cm/bigip13.1.1/1035825/f5_build/RPMS/i686/device-mapper-event-devel-1.02.77-9.el6_4.3.0.0.4.i686.rpm)
    # Note that ^ and $ is not used at the moment as newline sequences are not recognized by re (different platform/OS has different line break implementation TODO: Inspection on UNIX platform)
    regex_str = "Wrote:.*.rpm"
    regex_match = re.compile(regex_str)
    

    rpm_draft_list = regex_match.findall(content)

    # initialize the list that will store final result
    final = []
    
    # filter the exempt keywords and trim strings that are not part of rpm names in the matches (remove  all .../)
    # if string after : within rpm names should be omitted, use re.sub(':.*', '', re.sub('.*\/', '', s))
    for s in rpm_draft_list:
        if not any([exempt in s for exempt in exempt_list]):
            final.append(re.sub('.*\\/', '', s))
    
    #debug
    #print("\n * final list *")
    #print(final)

    return final


def print_single(dest):
    '''
    Store rpms extracted from all build logs in the following dictionary structure. Create a file 'out' under destination directory and dump the result.

    {
        'build_log_name' : ['rpm_name1', 'rpm_name2'...]
    }

    @param
    dest        path of the output directory

    @global
    final_dict  the dictionary that stores the build log name as key and the correlated list of rpm names as value 
    '''
    with open(str(Path(dest).resolve()) + "/out.txt", "w") as f:
        f.write(pprint.pformat(final_dict, indent = 4))

    # console log
    utility.terminal_msg(2, "extract_rpm_names finish writing to 'out.txt'")


def print_multi(result, dest, filename):
    '''
    Print rpms extracted from each build log into a file with the same filename of the build log in the destination directory.

    @param
    result      the list of rpms extracted
    dest        path of the output directory
    filename    the name of the file that the result will be written into
    '''
    # attach suffix
    filename += ".txt"

    with open(str(Path(dest).resolve()) + "/" + filename, "w") as f:
        for entry in result:
            f.write("%s\n" % entry)

    # console log
    utility.terminal_msg(2, "extract_rpm_names finish writing file " + filename)



if __name__ == "__main__":

    parser = argparse.ArgumentParser(description = "Extract RPM names from ISO build logs.")
    
    parser.add_argument("source", metavar = "source_dir", type = str, nargs = 1,
                    help = "The directory contains build logs to analyze.")
    
    parser.add_argument("-f", "--file", action="store_true",
                    help = "If the source is a file instead of a directory, the -f switch must be specified.")

    parser.add_argument("-o", "--output-type", metavar = "s/m", type = str, default = "s",
                    help = "How the result should be outputed. (s: print all results to a single file with list structure (default);" + \
                            "m: create files under the destination directory with the same name of the build logs; q: generate queries and parse into database [not yet implemented])")
         
    parser.add_argument("-d", "--destination", metavar = "dest_dir", type = str, default = "./result/",
                    help = "If choose to dump the result to file, the directory where output file will be written. By default <cwd>/result is used.")

    parser.add_argument("-v", "--version", action = 'version', version = '%(prog)s v0.4')
    args = parser.parse_args()

    
    # args parsed as list if using positional argument, only need the first element (if changed to optional argument, use args.source instead)
    src_dir = args.source[0]

    args_str = {}

    # check if destination directory is explicitly assigned
    if args.destination:
        args_str['d'] = args.destination

    if args.output_type:
        args_str['o'] = args.output_type

    if args.file:
        args_str['f'] = args.file

    load_file(src_dir, **args_str)

    


    
