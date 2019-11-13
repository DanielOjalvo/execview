#!/usr/bin/env python3

import os
import sys
import isoparser
from argparse import ArgumentParser

from lib import *


__doc__ = "A tool to extract rpm files from a given iso."

def rpm_extract(r, d):
    '''
    Iterate over the iso object, extract and write all files into the output directory.

    @param
    r       an entry in the file hierarchy (may be a file or a directory)
    d       the path that will be used for storing extracted rpms 
    '''
    #debug
    #print(r.name)

    # when encounter a directory
    if r.is_directory:
        # extract all files in subdirectory
        for x in r.children:
            rpm_extract(x, d)
    # when encounter a file
    else:
        # UTF-8 decode for the new filename
        with open(os.path.join(d, r.name.decode('utf-8')), 'wb') as rpm:
            rpm.write(r.content)


def iso_process(file, output_dir):
    '''
    Create and process an iso object on the top of the iso file given. create the output directory if not exist.

    @param
    file            a string that represents path to a file
    output_dir      the path that will be used for storing extracted rpms 
    '''
    # create iso object
    iso = isoparser.parse(file)
    # get the root directory
    root = iso.root

    # check if directory exists 
    if not os.path.exists(output_dir):
        utility.terminal_msg(1, "Output directory not found. Attempt to create one...")
        try:
            # create destination directory if not exist
            os.makedirs(output_dir)
            utility.terminal_msg(2, "Successfully created output directory %s" % os.path.abspath(output_dir))
        except OSError as e:
            utility.terminal_msg(0, "Failed to create output directory from the given path.\n OS Error: {0}".format(e))

    # extract files
    rpm_extract(root, output_dir)


if __name__ == "__main__":
    p = ArgumentParser(description=__doc__)

    p.add_argument("-i", "--iso", metavar="<ISO file>", type=str, required=True,
                   help= "The iso to be examined.")
    p.add_argument("-r", "--rpmdir", metavar="<output directory>", type=str, required=True,
                   help= "The directory where the extraced rpm files will be stored.")

    args = p.parse_args()

    iso_process(args.iso, args.rpmdir)
