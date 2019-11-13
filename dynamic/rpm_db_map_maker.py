#!/usr/bin/env python3

from argparse import ArgumentParser
from pprint import pprint
from json import load
from os import path, listdir
from sys import stdout
from .rpm_db_print import DBPrinter

class rpm_map:
    def __init__(self, full_dict, organized_dict = None):
        self.full_dict = full_dict
        self.organized_dict = organized_dict
        self.mapping = []

    def rpm_gen(self):
        for rpm, data in self.full_dict.items():
            arch = data["architecture"]
            executables = data["executables"]
            out = []

            for (_exec, exec_data) in executables.items():
                _exec_map = exec_map(arch, rpm, _exec, exec_data)
                exec_map_generator = _exec_map.exec_gen()
                for output in exec_map_generator:
                    out.append(output)

            yield out

    def rpm_dep_gen(self):
        if not self.organized_dict:
            raise AttributeError("No organized data to work with")

        for rpm, data in self.full_dict.items():
            arch = data["architecture"]
            executables = data["executables"]
            for _exec in executables:
                deps = executables[_exec]["dependencies"]
                arch_deps = self.organized_dict[arch]
                qualified_deps = []
                for dep in deps:
                    try:
                        rpm_names = arch_deps[dep]
                    except:
                        rpm_names = ["UNKNOWN"]
                    for rpm_name in rpm_names:
                        qualified_deps.append(":".join([arch, rpm_name, dep]))
                yield ((":".join([arch, rpm, _exec]), qualified_deps))

class exec_map:
    def __init__(self, arch, rpm_name, _exec, exec_obj):
        self.arch = arch
        self.my_rpm = rpm_name
        self.my_exec = _exec
        self.my_exec_obj = exec_obj

    def exec_gen(self):
        _func_map = func_map(self.arch, self.my_rpm, self.my_exec, self.my_exec_obj["symbols"])
        func_map_generator = _func_map.func_gen()

        for func_output in func_map_generator:
            yield func_output

def make_node(arch, rpm, exec_name, func):
    return ":".join((arch, rpm, exec_name, func))


class func_map:
    def __init__(self, arch, rpm, _exec, all_funcs):
        self.arch = arch
        self.rpm = rpm
        self.exec_name = _exec
        self.all_funcs = all_funcs
        self.defed_funcs = [func for func in self.all_funcs if self.all_funcs[func]["defined"] == "YES"]

    def func_gen(self):
        for func in self.defed_funcs:
            node = make_node(self.arch, self.rpm, self.exec_name, func)

            try:
                called_funcs = self.all_funcs[func]["called_functions"]
            except KeyError:
                yield (node, [])
                continue

            func_calls = []

            for x in called_funcs:
                #give our best guess for where the called_func is located
                try:
                    #print(x)
                    #print(self.all_funcs[x])
                    best_opt = x
                    opt_obj = self.all_funcs[x]
                except:
                    opts = [y for y in list(self.all_funcs.keys()) if y.startswith(x)]
                    try:
                        best_opt = opts.pop() #Not necessarily the best option...
                    except:
                        called_node = make_node(self.arch, "UNKNOWN", "UNKNOWN", x)
                        func_calls.append(called_node)
                        continue
                    opt_obj = self.all_funcs[best_opt]

                if opt_obj["defined"] == "YES":
                    called_node = make_node(self.arch, self.rpm, self.exec_name, best_opt)
                    func_calls.append(called_node)
                else:
                    for rpm_name, exec_name in opt_obj.items():
                        if rpm_name in ("binding", "called_functions", "type", "at", "defined"):
                            continue
                        else:
                            called_node = make_node(self.arch, rpm_name, exec_name, best_opt)
                            func_calls.append(called_node)
            yield (node, func_calls)

def print_map(x):
    for y in x:
        #import pdb; pdb.set_trace()
        if  type(y) == type({}):
            for key in y:
                print (key)
                for val in y[key]:
                    print(("         " + val))
        else:
            print((str(y)))

if __name__ == "__main__":
    p = ArgumentParser()

    p.add_argument("-o", "--output", type=str,
                   help="The json file name prefix to use.")
    p.add_argument("-i", "--input", type=str,
                  help="The json file to read in.")
    p.add_argument("-d", "--directory", type=str,
                   help="The json file to read in.")
    p.add_argument("-e", "--exec_mappings", type=str, default = "",
                   help="A json file matching dependencies to rpms")
    args = p.parse_args()

    print("loading")
    if args.directory:
        raw_data = {}
        json_files = [path.join(args.directory, x) for x in listdir(args.directory) if x.endswith(".json")]
        print(("loading full db with %d files" % len(json_files)))
        for json_file in json_files:
            stdout.write(".")
            stdout.flush()
            #print(json_file)
            with open(json_file, "r") as f:
                data = load(f)
                raw_data.update(data["BIG-IP"])
        print("")
        print("done loading full db")
    else:
        with open(args.input, "r") as inpt:
            raw_data = load(inpt)
    print("done loading")

    print("loading organized DB")
    with open(args.exec_mappings, "r") as inpt:
        organized_data = load(inpt)
    print ("done loading organized DB")
    rpm_obj = rpm_map(raw_data, organized_data)
    rpm_gen = rpm_obj.rpm_gen()

    printer = DBPrinter(args.output, output_filesize = 10**7, container = False)
    for rpm in rpm_gen:
        stdout.write(".")
        stdout.flush()
        data = ""
        for x in rpm:
            func_str = x[0] + "\n"
            if x[1]:
                calls_list = x[1]
                for y in calls_list:
                    func_str += "    " + y + "\n"
            printer.simple_print(func_str)
    print("\ncompleted happily!")

    printer.close_out()
