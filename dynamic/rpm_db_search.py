#!/usr/bin/env python3
"""
This tool is used to find the RPM and executable a symbol is defined in and,
optionally, where it is linked in.
"""
from argparse import ArgumentParser
from json import load
from os import listdir, path, getcwd
from sys import stdout


def load_json_file(json_file):
    #print(json_file)
    with open(json_file, 'r') as f:
        return load(f)

def grab_json_files(json_dir):
    #print(listdir(json_dir))
    if json_dir == None:
        return []
    return [path.join(json_dir, x) for x in listdir(json_dir) if path.isfile(path.join(json_dir, x))]

        
def search_dict(substr, dir_obj, include_refs):
    prods = list(dir_obj.keys())
    #print(prods)
    for prod in prods:
        rpm_dict = dir_obj[prod]
        #print(rpm_list)
        for rpm in list(rpm_dict.keys()):
            #print(type(rpm))
            #print (rpm.keys())
            rpm_val = rpm_dict[rpm] 

            #print(rpm_val)
            executables = rpm_val['executables']
            for executable in list(executables.keys()):
                shared_obj = executables[executable]
                symbols = shared_obj["symbols"]
                for symbol in list(symbols.keys()):
                    symbol_dict = symbols[symbol]
                    if (substr in symbol):
                        if (match_whole_string and substr != symbol):
                            continue
                        if not include_refs and symbol_dict["defined"] == "NO":
                            continue
                        write_out(rpm + ":\n")
                        write_out("    " + executable + ":\n")
                        write_out(symbol)
                        if "at" in list(symbol_dict.keys()):
                            write_out("@" + symbol_dict["at"])
                        write_out('\n')
                        write_out("      binding: " + symbol_dict["binding"] + "\n")
                        if include_refs:
                            write_out("      defined: " + symbol_dict["defined"])
                            write_out('\n')
                        write_out('\n')
                        stdout.flush()

def load_search_and_print(json_dir, substr, fil, include_refs):
    #print(getcwd())
    #print(json_dir)
    json_files = grab_json_files(json_dir)
    #print(json_files)
    if fil != None:
        json_files.append(fil)
    for f in json_files:
        #print(f)
        d = load_json_file(f)
        search_dict(substr, d, include_refs)

def initialize_fd(s):
    global output_fd
    if s:
        output_fd = open(s, "w")

def close_fd():
    global output_fd
    if output_fd:
        output_fd.close()

def write_out(s):
    if nostdout == False:
        stdout.write(s)
    if output_fd:
        output_fd.write(s)

if __name__ == "__main__":
    p = ArgumentParser(description=__doc__)

    p.add_argument("-j", "--json_directory", type=str,
                   help="The root directory where JSON files will be found.")
    p.add_argument("-s", "--string", type=str, required=True,
                   help="The substring to be searched for.")
    p.add_argument("-c", "--complete_string", action="store_true",
                   help="Only match if the symbol is the substring.")
    p.add_argument("-f", "--file", type=str,
                   help="A particular file to be searched through.")
    p.add_argument("-i", "--include_refs", action="store_true",
                   help="Include binaries that reference symbols, but don't define them.")
    p.add_argument("-o", "--output_file", type=str,
                   help="Write output to file.")
    p.add_argument("-n", "--nostdout", action="store_true",
                   help="Don't print to stdout.")
    args = p.parse_args()

    global output_fd
    global nostdout
    global match_whole_string

    nostdout = args.nostdout
    match_whole_string = args.complete_string
    output_fd = None

    initialize_fd(args.output_file)

    if nostdout and args.output_file == None:
        print("You must output the results somewhere...")

    load_search_and_print(args.json_directory, args.string, args.file, args.include_refs)

    close_fd()
