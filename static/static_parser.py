#!/usr/bin/env python3

import os
import sys
import shutil
import argparse

import analyze_build_log
from lib import *


def wrapper(args, option = 1):
    '''
    The wrapper to automate the steps from collecting necessary information from user, validating input, 
    processing the data with the rest of the scripts, and parsing extracted information into database.

    @param
    args        command arguments
    option      the extract option: 1 ) take information from command argument
                                    2 ) fixed path lookup under the established directory structure of mount (@ Aug 6th, 2019)
    '''
    if args.clean_output_directory and os.path.exists(args.output_directory) and os.path.isdir(args.output_directory):
        for f in os.listdir(args.output_directory):
            path = os.path.join(args.output_directory, f)
            try:
                if os.path.isfile(path):
                    os.unlink(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
            except OSError as e:
                terminal_msg(1, "Error occurred on cleaning the output directory before executing. \n\t Error message: {}".format(e))

    # check if product and version is not null
    if args.product_name and args.version_number:
        # take information from command args
        if option == 1:
            # examine single file
            if args.file:
                # check if file exists in file system
                if os.path.exists(args.file) and os.path.isfile(args.file):
                    analyze_build_log.examine_file(args.file, args.output_directory, args.clean_output_directory, args.product_name, args.version_number)
                else:
                    # file not exist or not a file
                    terminal_msg(0, "The file provided is not a valid file or does not exist in the file system.")

            # examine directory
            elif args.directory:
                # check if directory exists in file system
                if os.path.exists(args.directory) and os.path.isdir(args.directory):
                    analyze_build_log.examine_directory(args.directory, args.output_directory, args.clean_output_directory, args.product_name, args.version_number)
                else:
                    # directory not exist or not a directory
                    terminal_msg(0, "The directory provided is not a valid path or does not exist in the file system.")
            else:
                # when nothing specified for analyzing
                terminal_msg(0, "Either a file (-f), a directory (-d), or --mount has to be specified for processing.")

        # fixed path lookup under the established directory structure of mount
        elif option == 2:
            # set -c switch
            args.clean_output_directory = True

            # get full path from given product name and version number
            args.directory = args.mount

            analyze_build_log.examine_directory(args.directory, args.output_directory, args.clean_output_directory, args.product_name, args.version_number)
            
        
        # unknown option given
        else:
            raise Exception("Invalid option for wrapper() defined in the program.")

    else:
        terminal_msg(0, "Please provide valid product name and/or version number.")

    
    # final check for remove output dir or not
    if args.wipe_program_output:
        # Improve direction: mark all existed file in output dir before processing and delete only those created by program (not marked)
        created_subdir = ["logs", "rpm_names"]

        for f in os.listdir(args.output_directory):
            path = os.path.join(args.output_directory, f)
            try:
                if os.path.isfile(path):
                    os.unlink(path)
                elif os.path.isdir(path) and os.path.basename(path) in created_subdir:
                    shutil.rmtree(path)
            except OSError as e:
                terminal_msg(1, "Error {} occurred on wiping output directories and their contents.".format(e))




if __name__ == "__main__":
    p = argparse.ArgumentParser()

    p.add_argument("-p", "--product-name", metavar = "<bigip/centos/..>", type = str, required = True,
                    help = "The product name of the build log")
    p.add_argument("-v", "--version-number", metavar = "<x.x.x.x-#.#.#>", type = str, required = True,
                    help = "The version number, including the release number, of the build log")
    
    p.add_argument("-f", "--file", metavar = "<file_name>", type = str,
                    help = "A single build log file to process. When -f is specified, it overwrites -d switch, which means that the program will only process the" + \
                          " single build log given as the parameter of this switch.")
    p.add_argument("-d", "--directory", metavar = "<path>", type = str,
                    help = "A directory of build log files to process.")
    p.add_argument("-o", "--output-directory", metavar = "<path>", type = str, default = "./output/",
                    help = "A directory to place the output when -d is given. <cwd>/output is created if not specified.")
    
    p.add_argument("-c", "--clean-output-directory", action = "store_true",
                    help = "Cleanup the output directory before writing to it.")
    p.add_argument("-w", "--wipe-program-output", action = "store_true",
                    help = "Remove the output directories and files after the whole process finishes.")
    
    p.add_argument("-sd", "--mount", metavar = "<mount path>", type = str,
                    help = "The mount point if running on or mounted with the mount machine or any UNIX box that shares the same source code/ISO directory structure as mount." + \
                          "If specified, user can execute the program by providing only the product name (-p) and version number (-v). The program will look for " + \
                          "the path of the correlated release directory and do the analyze of all build logs under it with -d and -c option enabled.")

    args = p.parse_args()

    # if executed from mount machine
    if args.mount:
        wrapper(args, 2)
    # normal command argument input
    else:
        wrapper(args, 1)

