#!/bin/env python3
"""
A tool to extract and build a json database using only executable files.
"""
from rpm_db_print import DBPrinter
from rpm_db_builder import process_executables, is_elf_file
from pathlib import Path
from argparse import ArgumentParser

X86_64 = "x86_64"
I686 = "i686"
NOARCH = "noarch"
PPC = "ppc"
OTHERARCH = "other_arch"


def create_executable_db(container_name, exec_directory, output_directory, size, rpm_name, output_file):
    out = {"package" : rpm_name,
           "version" : "x.x.x",
           "release" : "x.x.x",
           X86_64 : True,
           I686 : True,
           NOARCH : True,
           PPC : True,
           OTHERARCH: True}
    printer = DBPrinter(output_file, output_directory, size, container_name)
    exec_p = Path(exec_directory)
    exec_list = [str(x) for x in exec_p.iterdir() if x.is_file() and is_elf_file(str(x))]
    output = process_executables(exec_list)
    out.update(output)
    package_dict = {rpm_name:out}
    printer.print_out(package_dict)
    printer.close_out()


if __name__ == "__main__":
    p = ArgumentParser(description=__doc__)

    p.add_argument("-e", "--exec_directory", type=str, required=True,
                   help="A flat directory containing the executables in question.")
    p.add_argument("-o", "--output_directory", type=str,
                   help="The directory where output files are written.")
    p.add_argument("-l", "--size", type=int, default=10,
                   help="The rough maximum size of the output files in megabytes. 0 means print only to one file.")
    p.add_argument("-p", "--product", type=str, default="BIG-IP",
                   help="The product being examined.")
    p.add_argument("-s", "--software_version", type=str, default="test",
                   help="The software version of the product.")
    p.add_argument("-r", "--rpm_name", type=str, default="test",
                   help="The related rpm for the collection of executables.")

    args = p.parse_args()

    exec_directory = args.exec_directory
    output_directory = args.output_directory
    size = args.size * (2**20)
    product = args.product
    version = args.software_version
    rpm_name = args.rpm_name
    output_file = "-".join([product, version, rpm_name])
    
    container_name = "%s:%s" % (product, version)

    create_executable_db(container_name, exec_directory, output_directory, size, rpm_name, output_file)
