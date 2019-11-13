#/bin/python3

import os
import re
import ast
import argparse
import pprint
from pathlib import Path

def generate_rpm_dict(buildlog_dict, xml_list):
    """
    Construct the dictionary that holds the result and dump it to an output file.

    @param
    rpm_extract_output      file content of a single log file
    xml                     the metadata of the ISO
    """
    
    rpm_dict = {}

    # parse rpms from build logs 
    for logfile, rpm_list in buildlog_dict.items():
        for r in rpm_list:
            # set logfile_name to the name of the log file 
            rpm_dict[r] = {
                # set to false by default (will be updated later when examining xml_list)
                'in_manifest': False,
                'logfile_name': logfile
            }
            
    
    # parse rpms from manifest (metadata.xml)
    for x in xml_list:
        # flag for is_this_entry_parsed?
        flag = False

        for r in rpm_dict.keys():
            # if rpm already exist in the data structure, update in_manifest
            if r == x:
                rpm_dict[x]['in_manifest'] = True
                flag = True
                break

        if not flag:
            # if rpm does not exist in current data structure, add new entry
            rpm_dict[x] = {
                'in_manifest': True,
                # set logfile_name to None
                'logfile_name': None,
            }
    #debug
    #for x, v in rpm_dict.items():
    #    if v['in_manifest'] == True and v['logfile_name'] != None:
    #        print(x)
    
    with open(os.getcwd() + "/output/cmp.out", "w") as f:
        f.write(pprint.pformat(rpm_dict, indent = 4))
        print("Finish writing cmp.out under <cwd>/output directory.")


def prepare_data(xml):
    """
    Preprocess data from extract_rpm_names and metadata.xml.

    @param
    xml                     the metadata of the ISO
    """
    buildlog_extract_output = Path().cwd() / 'result' / 'out'
    #debug
    #print(rpm_extract_output)

    # read file and retrieve the rpm dictionary extracted from build logs
    with open(buildlog_extract_output.resolve()) as f:
        # parse file in dict structure with Abstract Syntax Trees
        buildlog_dict = ast.literal_eval(f.read())


    # regex for process xml
    regex_pkg_start = "<packageList>"
    regex_pkg_end = "</packageList>"
    regex_match_start = re.compile(regex_pkg_start)
    regex_match_end = re.compile(regex_pkg_end)

    # init xml_list (used for storing the rpms extracted from xml file)
    xml_list = []

    flag = False
    with open(str(Path(xml).resolve()), "r") as f:
        # store only entries under the <packageList> tag into xml_list
        for line in f:
            # </packageList> found, stop storing from this line
            if re.search(regex_match_end, line):
                flag = False
            
            # flag is True means between <packageList> and </packageList>
            if flag:
                # purpose: trim the string and store only the rpm name
                # original line struct: <package> architecture/rpm_name </package>
                # (1) trim whitespace families (e.g., \r \n \t ...)
                line_strip = re.sub('\s+', '', line)
                # (2) remove tags (e.g., <package>) 
                line_strip = re.sub('<(.*?)>', '', line_strip)
                # (3) remove architecture (e.g., i686/) 
                line_strip = re.sub('.*\/', '', line_strip)
                
                xml_list.append( line_strip )

            # <packageList> found, start storing from next line
            if re.search(regex_match_start, line):
                flag = True

    #debug
    #print(xml_list)
    #print(len(xml_list))

    generate_rpm_dict(buildlog_dict, xml_list)


if __name__ == "__main__":
    prepare_data("input/metadata.xml")

    parser = argparse.ArgumentParser(description = "Inspect the intersection and divergence between rpms extracted from build logs and what is actually put in the ISO. Please run 'extract_rpm_names -o s' first.")
    
    '''
    #debug: for only dev environment test purpose
    #parser.add_argument("-s", "--source", metavar = "src", type = str, default = "input/metadata.xml",
    #                help = "x")
    
    parser.add_argument("source", metavar = "source_dir", type = str, nargs = 1,
                    help = "The directory contains build logs to analyze.")
  
    parser.add_argument("-i", "--iso", metavar = "*.iso", type = str,
                    help = "Feed ISO as the input")
         
    parser.add_argument("-d", "--destination", metavar = "dest_dir", type = str, default = "./output/",
                    help = "If choose to dump the result to file, the directory where output file will be written. By default <cwd>/output is used.")

    parser.add_argument("-v", "--version", action = 'version', version = '%(prog)s v0.1')
    args = parser.parse_args()

    
    # args parsed as list if using positional argument, only need the first element (if changed to optional argument, use args.source instead)
    src_dir = args.source[0]

    # check if destination directory is explicitly assigned
    if args.destination:
        dest_dir = args.destination
    else:
        dest_dir = "result"

    # create destination directory if not exist
    if os.path.exists(dest_dir):
        pass
    else:
        try:
            os.mkdir(dest_dir)
        except OSError as e:
            print("OS Error: {0}".format(e))
            sys.exit("Exit on error")

    # check the desired output type
    if args.output_type:
        if args.output_type == "s" or args.output_type == "m":
            # start loading build logs
            load_file(src_dir, dest_dir, args.output_type)
        else:
            sys.exit("Invalid option for output type.")
    else:
        print("default option for output type is not working")
        sys.exit("Exit on error")

    '''