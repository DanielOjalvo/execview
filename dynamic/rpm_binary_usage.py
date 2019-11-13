#!/usr/bin/env python3
"""
This tool is used to find which .so files an rpm is dependent upon and which
rpm provides that dependency.
"""
from argparse import ArgumentParser
from json import load
from os import listdir, path, getcwd
from sys import stdout
from pprint import pformat

rpm_provider_list = []

def load_json_file(json_file):
    #print(json_file)
    with open(json_file, 'r') as f:
        return load(f)

def grab_json_files(json_dir):
    #print(listdir(json_dir))
    if json_dir == None:
        return []
    return [path.join(json_dir, x) for x in listdir(json_dir) if path.isfile(path.join(json_dir, x))]

        
def search_dict(binary, dir_obj):
    global rpm_provider_list
    prods = list(dir_obj.keys())
    #print(prods)
    for prod in prods:
        rpm_list = dir_obj[prod]
        #print(rpm_list)
        for rpm in rpm_list:
            #print(type(rpm))
            #print (rpm.keys())
            for rpm_dict in list(rpm.keys()):
                rpm_val = rpm[rpm_dict]
                #print(rpm_val)
                if binary in rpm_val["All executables"]:
                    rpm_provider = {"RPM" : rpm_dict, "executable" : binary}
                    rpm_provider_list.append(rpm_provider)
                if binary not in rpm_val["All dependencies"]:
                    continue
                executables = rpm_val['executables']
                for executable in executables:
                    shared_objs = executables[executable]
                    dependencies = shared_objs["dependencies"]
                    if binary not in dependencies:
                        continue
                    else:
                        write_out(pformat({"RPM": rpm_dict, "executable" : executable}) + "\n")


def load_search_and_print(json_dir, binary, fil):
    #print(getcwd())
    #print(json_dir)
    json_files = grab_json_files(json_dir)
    #print(json_files)
    if fil != None:
        json_files.append(fil)
    for f in json_files:
        #print(f)
        d = load_json_file(f)
        search_dict(binary, d)
    write_out("Printing out the sources of the binary")
    for r in rpm_provider_list:
        write_out(pformat(r))


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
    p.add_argument("-b", "--binary", type=str, required=True,
                   help="The binary file to be searched for.")
    p.add_argument("-f", "--file", type=str,
                   help="A particular file to be searched through.")
    p.add_argument("-o", "--output_file", type=str,
                   help="Write output to file.")
    p.add_argument("-n", "--nostdout", action="store_true",
                   help="Don't print to stdout.")
    args = p.parse_args()

    global output_fd
    global nostdout

    nostdout = args.nostdout
    output_fd = None

    initialize_fd(args.output_file)

    if (nostdout and args.output_file == None):
        print("You must output the results somewhere...")

    load_search_and_print(args.json_directory, args.binary, args.file)

    close_fd()
