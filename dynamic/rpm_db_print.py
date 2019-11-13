#!/usr/bin/env python3

from json import dumps
from os import path

class DBPrinter:
    def __init__(self, base_filename, base_dir = "", output_filesize = 10, container_name = "BIG-IP", container = True):
        self.fp = None
        self.filecount = 0
        self.base_filename = base_filename
        if base_dir:
            self.base_filename = path.join(base_dir, base_filename)
        self.filesize = output_filesize
        self.charcount = 0
        self.container_start = "{ \"" + container_name + "\" :{"
        self.container_end = "}}"
        self.last_dump = None
        self.container = container

    def initialize_file(self):
        if not self.fp:
            filename = self.base_filename + "-" + str(self.filecount) + ".json"
            self.fp = open(filename, "w")
            if self.container:
                self.fp.write(self.container_start)

    def print_out(self, output_dict):
        self.initialize_file()
        if not isinstance(output_dict, dict):
            raise Exception("The output_dict passed for DBPrinter.print_out() is a {0} object. (expected dictionary).".format(type(output_dict)))

        strdump = dumps(obj = output_dict, sort_keys = True, indent = 4, separators = (',', ': '))[1:-1]
        self.charcount += len(strdump)
        if self.last_dump == None and strdump:
            self.last_dump = strdump
        else:
            if strdump:
                self.fp.write(strdump)
                self.fp.write(",")

        if self.charcount > self.filesize:
            self.fp.write(self.last_dump)
            self.fp.write(self.container_end)
            self.fp.close()
            self.fp = None
            self.charcount = 0
            self.filecount += 1
            self.last_dump = None

    def simple_print(self, data):
        strdump = str(data)
        self.initialize_file()

        self.charcount += len(strdump)

        if self.last_dump == None:
            self.last_dump = strdump
        else:
            self.fp.write(strdump)

        if self.charcount > self.filesize:
            self.fp.write(self.last_dump)
            self.fp.close()
            self.fp = None
            self.charcount = 0
            self.filecount += 1
            self.last_dump = None


    def print_stdout(self, output_dict):
        strdump = dumps(obj = output_dict, sort_keys = True, indent = 4, separators = (',', ': '))[1:-1]
        print (strdump)

    def simple_json_print(self, mydict):
        self.initialize_file()
        strdump = dumps(obj = mydict, sort_keys = True, indent = 4, separators = (',', ': '))
        self.fp.write(strdump)
        self.close_out()


    def close_out(self):
        if self.fp:
            if self.last_dump:
                self.fp.write(self.last_dump)
            if self.container:
                self.fp.write(self.container_end)
            self.fp.close()