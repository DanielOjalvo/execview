#!/usr/bin/env python3

import re
import os
import sys
import shutil
import pathlib
import argparse

import iso_parser
import rpm_db_builder
import rpm_uploader
from lib import *

def search_iso_under_dir(dir_path):
    # confirm if directory exists in file system
    if os.path.exists(dir_path) and os.path.isdir(dir_path):
        iso_list = []

        # look for *.iso inside the directory.
        for f in os.listdir(dir_path):
            if os.path.isfile(dir_path + "/" + f) and os.path.splitext(f)[-1].lower() == ".iso":
                iso_list.append(f)
                
        
        # if no iso could be found, complain
        if not iso_list:
            terminal_msg(1, "No *.iso can be found under the given path {0}".format(dir_path))

    # when directory not exist
    else:
        terminal_msg(0, "Cannot find the correlated source directory path {0} within the file system.".format(dir_path))
    
    return iso_list


def validate_args_with_metadata(args, metadata_dir):
    '''
    Match and update args with metadata.xml

    === standard matadata format ===
    <productName>BIG-IP</productName>       # product name
    <imageType>release</imageType>
    <version>11.6.1</version>               # version number
    <minVersion>9.1.1</minVersion>
    <requiredEmVersion>2.3.0</requiredEmVersion>
    <releaseNotesUrl>http://tech.f5.com/home/bigip-next/releasenotes/relnotes11_6.html</releaseNotesUrl> 
    <buildNumber>0.0.317</buildNumber>      # release number 
    ..

    '''

    # regex for process xml
    regex_pdt = r"<productName>(.*)<\/productName>"
    regex_vrs = r"<version>(.*)<\/version>"
    regex_rls = r"<buildNumber>(.*)<\/buildNumber>"

    # init temp variables
    metadata_prod = ""
    metadata_vers = ""
    vers_flag = False
    rels_flag = False
    prod_checked = False
    vers_checked = False

    with open(metadata_dir + "/metadata.xml", 'r') as f:
        for line in f:
            regex_pdt_match = re.search(regex_pdt, line)
            regex_vrs_match = re.search(regex_vrs, line)
            regex_rls_match = re.search(regex_rls, line)
            
            # regex matches <version>
            if regex_pdt_match and not prod_checked:
                metadata_prod = regex_pdt_match.group(1)
                if metadata_prod != args.product_name and args.product_name != "":
                    # complain inconsistency
                    terminal_msg(1, "Mismatch on product between ISO file name and metadata extracted. \n" + \
                                            "(Content in <productName> tag from metadata is used on conflict) \n" + \
                                            " > The product name has been updated from %s to %s" % (args.product_name, metadata_prod))
                # if product name was not set, update with info from metadata silently
                elif args.product_name != "":
                    terminal_msg(2, "Product name is consistent with information from metadata.")
                
                # update with metadata info
                args.product_name = metadata_prod
                # mark as checked
                prod_checked = True

            # regex matches <version>, check vers_flag to prevent malformed metadata (in certain case, only consider the first occurence of the tag)
            if regex_vrs_match and not vers_flag:
                metadata_vers = regex_vrs_match.group(1) + "-" + metadata_vers
                vers_flag = True

            # regex matches <buildNumber>, check vers_flag to prevent malformed metadata (in certain case, only consider the first occurence of the tag)
            if regex_rls_match and not rels_flag:
                metadata_vers += regex_rls_match.group(1)
                rels_flag = True

            if vers_flag and rels_flag and not vers_checked:
                if metadata_vers != args.version_number and args.version_number != "":
                    # complain inconsistency
                    terminal_msg(1, "Mismatch on version between ISO file name and metadata extracted. \n" + \
                                            "(Content of tags in format of <version>-<buildNumber> from metadata is used on conflict) \n" + \
                                            " > The version number has been updated from %s to %s" % (args.version_number, metadata_vers))
                # if product name was not set, update with info from metadata silently
                elif args.version_number != "":
                    terminal_msg(2, "Version number is consistent with information from metadata.")
                
                # update with metadata info
                args.version_number = metadata_vers
                # mark as checked
                vers_checked = True
            
    return args

def wrapper(args, option = 1):
    '''
    The wrapper to automate the steps from collecting necessary information from user and iso file, validating input, 
    processing the data with the rest of the scripts, and parsing extracted information into database.

    @param
    args        command arguments
    option      the extract option: 1 ) take information from command argument
                                    2 ) fixed path lookup under the established directory structure of mount (@ Aug 6th, 2019)
    '''
    
    # can do directory form validating (e.g., allow only / or \\)
    # directory formatting (unify format, remove trailing slashes)
    args.output_directory = utility.dir_formatting(args.output_directory)
    if args.directory:
        args.directory = utility.dir_formatting(args.directory)
    
    # define output directory paths for each procedure
    rpm_output_dir = args.output_directory + "/rpms"
    build_worker_dir = args.output_directory + "/worker"
    build_output_dir = args.output_directory + "/json"

    # if clean-output-directory enabled
    if args.clean_output_directory and os.path.exists(args.output_directory) and os.path.isdir(args.output_directory):
        for f in os.listdir(args.output_directory):
            path = os.path.join(args.output_directory, f)
            try:
                if os.path.isfile(path):
                    os.unlink(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
            except OSError as e:
                terminal_msg(1, "Error occurred on cleaning the output directory before executing.\n\t Error message: {}".format(e))

    if option == 1:
        if args.directory:
            # retrieve list of isos that needs to be processed.
            iso_list = search_iso_under_dir(args.directory)

            for iso in iso_list:
                # init iso_args first
                iso_args = None

                # inherit properties from args
                iso_args = args
                iso_args.iso = args.directory + "/" + iso

                # update product and version in args to real name 
                iso_args = real_name_lookup(iso_args, option)

                # append prod/vers extracted from iso filename to the output directories to make them unique. (These may be different from metdata if filename tampered, but an alert will raise) 
                iso_rpm_output_dir = rpm_output_dir + "-" + iso_args.product_name + "-" + iso_args.version_number
                iso_build_worker_dir = build_worker_dir + "-" + iso_args.product_name + "-" + iso_args.version_number
                iso_build_output_dir = build_output_dir + "-" + iso_args.product_name + "-" + iso_args.version_number

                # extract iso
                iso_parser.iso_process(iso_args.iso, iso_rpm_output_dir)

                # validate product/version with information provided in metadata
                iso_args = validate_args_with_metadata(iso_args, iso_rpm_output_dir)
                
                # build data structure
                rpm_db_builder.run(iso_rpm_output_dir, iso_build_worker_dir, iso_build_output_dir, iso_args.product_name, iso_args.version_number, iso_args.processes)

                # insert into database 
                rpm_uploader.upload(iso_build_output_dir)

        elif args.iso:
            # update product and version in args to real name 
            args = real_name_lookup(args, option)

            # check if iso exists in file system and its suffix
            if os.path.exists(args.iso) and os.path.isfile(args.iso) and os.path.splitext(args.iso)[-1].lower() == ".iso":
                # extract iso
                iso_parser.iso_process(args.iso, rpm_output_dir)

                # validate product/version with information provided in metadata
                args = validate_args_with_metadata(args, rpm_output_dir)
                
                # build data structure
                rpm_db_builder.run(rpm_output_dir, build_worker_dir, build_output_dir, args.product_name, args.version_number, args.processes)

                # insert into database 
                rpm_uploader.upload(build_output_dir)

            else:
                terminal_msg(0, "An invalid path or file has been assigned for ISO.")

        else:
            terminal_msg(0, "When -m is not set, an ISO file or a source directory must be provided.")

    elif option == 2:
        # update product and version in args to real name 
        args = real_name_lookup(args, option)

        # check if product and version is not null
        if args.product_name and args.version_number:
            #import pdb; pdb.set_trace()
            # init
            args.iso = ""

            # get iso file
            args.iso = get_mount_path(args.mount, args.product_name, args.version_number)

            if args.iso:
                # extract iso
                iso_parser.iso_process(args.iso, rpm_output_dir)

                # validate product/version with information provided in metadata
                args = validate_args_with_metadata(args, rpm_output_dir)
                
                # build data structure
                rpm_db_builder.run(rpm_output_dir, build_worker_dir, build_output_dir, args.product_name, args.version_number, args.processes)

                # insert into database 
                rpm_uploader.upload(build_output_dir)
            
            else:
                terminal_msg(2, "{} {} skipped due to no iso found under the correlated mount path.".format(args.product_name, args.version_number))
            
        else:
            terminal_msg(0, "Please provide valid product name and/or version number for searching in mount file system.")

    else:
        raise Exception("Invalid option for wrapper() defined in the program.")


    # final check for remove output dir or not
    if args.wipe_program_output:
        # Improve direction: mark all existed file in output dir before processing and delete only those created by program (not marked)
        created_subdir = ["rpms", "worker", "json"]

        for f in os.listdir(args.output_directory):
            path = os.path.join(args.output_directory, f)
            try:
                if os.path.isfile(path):
                    os.unlink(path)
                elif os.path.isdir(path) and os.path.basename(path) in created_subdir:
                    shutil.rmtree(path)
            except OSError as e:
                terminal_msg(1, "Error occurred on wiping output directories and their contents.")
                print(e)
    
    # return updated args (for parser.py usage)
    return args


if __name__ == "__main__":
    ''' #debug: iso name test
    a = argparse.ArgumentParser()
    a.iso=#"BIGIP-13.1.0.0.0.1868.iso"#"BIG-IQ-7.0.0-0.0.1854.iso"#"BIG-IQ-4.4.0.0.0.5858.iso"#"Hotfix-BIG-IQ-4.4.0-2.0.5880-HF2.iso"#"BIG-IQ-4.5.0.0.0.7028.iso"#"BIGIP-11.5.0.0.0.221.iso"#"Hotfix-BIGIP-11.4.1-685.0-HF9.iso"#"BIGIP-11.0.0.128.0.iso"
    k = real_name_lookup(a, 1)
    print(k.product_name)
    print(k.version_number)
    '''
    p = argparse.ArgumentParser()
    
    # Workflow:
    # iso_parser -> rpm_db_builder -> rpm_uploader

    # output-directory / rpms / (results from iso_parser)
    #                  / workers / (worker dir, for resuming rpm_db_builder)
    #                  / json / (results from rpm_db_builder)

    p.add_argument("-i", "--iso", metavar="<ISO file>", type=str,
                    help = "The iso to be examined.")
    p.add_argument("-d", "--directory", metavar="<path>", type=str,
                    help = "The source directory that contains multiple isos for batch examination. If this switch is enabled, param of -i will not be examined.")

    p.add_argument("-pc", "--processes", metavar="<amount>", type=int, default=5,
                    help = "The number of processes to spawn that can be utilized to examine rpm files. " + \
                        "(default 10, suggested threshold x where x <= how many GBs of RAM available)")
    p.add_argument("-o", "--output-directory", metavar = "<path>", type = str, default = "./output/",
                    help = "A directory to place the output. <cwd>/output is created if not specified.")

    p.add_argument("-m", "--mount", metavar = "<mount path>", type = str,
                    help = "The mount point if running on or mounted with the mount machine or any UNIX box that shares the same source code/ISO directory structure as mount." + \
                           "If specified, user can execute the program by providing only the product name (-p) and version number (-v). The program will look for " + \
                           "isos under the path of the correlated release directory and analyze it with -i option.")
    p.add_argument("-p", "--product-name", metavar = "<bigip/bigiq/..>", type = str,
                    help = "The name of the product to examine. MUST be specified when -m switch is set.")
    p.add_argument("-v", "--version-number", metavar = "<x.x.x.x-#.#.#>", type = str,
                    help = "The version number, including the release number, of the product to examine. MUST be specified when -m switch is set.")
                   
    p.add_argument("-c", "--clean-output-directory", action = "store_true",
                   help = "Cleanup the output directory before writing to it.")
    p.add_argument("-w", "--wipe-program-output", action = "store_true",
                   help = "Remove the output directories and files after the whole process finishes.")

    args = p.parse_args()

    # if executed from mount machine
    if args.mount:
        wrapper(args, 2)
    # normal command argument input
    else:
        wrapper(args, 1)
