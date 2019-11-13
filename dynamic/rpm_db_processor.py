#!/usr/bin/env python3
"""
rpm_db_processor is a utility to create associations between a given shared
object and the rpm it comes from. The usefulness of this tool will be to 
help the search for the rpm and shared object where a particular undefined
function call is coming from,.
"""

from json import loads, dumps
from os import listdir, path
from argparse import ArgumentParser
from .rpm_db_print import DBPrinter

class Organizer:
    def __init__(self, directoryname = None):
        self.organized_data = {}
        self.full_data = {}
        json_files = [path.join(directoryname, x) for x in listdir(directoryname) if x.endswith(".json")]
        for json_file in json_files:
            #print("examining " + json_file)
            self.process_file(json_file)

    def process_file(self, json_file):
        data = None
        raw_text = None
        with open(json_file, 'r') as f:
            raw_text = f.read()
        data = loads(raw_text)
        #The self.organized_data structure will look like...
        #{<arch>: {<so_name> : [rpm(s)], ...}, ...}
        data = data["BIG-IP"] # Extract the data from the container
        self.full_data.update(data)
        if isinstance(data, list):
            data = data[0]
        #print(data.keys())
        #print (dumps(data))
        for rpm in list(data.keys()):
            #print("examining rpm " + rpm)
            arch = data[rpm]["architecture"]
            executables = data[rpm]["All executables"]
            if not executables:
                continue

            self.organized_data.setdefault(arch, {})
            for ex in executables:
                self.organized_data[arch].setdefault(ex, [])
                if rpm not in self.organized_data[arch][ex]:
                    self.organized_data[arch][ex].append(rpm)
                #print ("Found " + str(len(self.organized_data[arch][ex])) + " rpms with " + ex)
        #print ("Self.Organized_Data is " + dumps(self.organized_data))

    def print_organized_data(self):
        print(dumps(self.organized_data, indent=4))


if __name__ == "__main__":
    p = ArgumentParser()

    p.add_argument("-d", "--directory", type=str, required=True,
                   help="The directory to examine.")
    p.add_argument("-f", "--filename", type=str, required=True,
                   help="The directory to examine.")
    args = p.parse_args()

    a = Organizer(args.directory)

    printer = DBPrinter(args.filename, container = False)
    printer.simple_json_print(a.organized_data)
    #a.print_organized_data()
