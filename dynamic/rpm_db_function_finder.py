#!/usr/bin/env python3
"""
rpm_db_function_finder is a utility to connect the undefined functions in an
executable to the executable and rpm where it is defined.
"""

from .rpm_db_processor import Organizer
from argparse import ArgumentParser
from json import dumps, load
from .rpm_db_print import DBPrinter
from os import listdir, path
from sys import stdout

class Memo:
    def __init__(self):
        self.memo = {}

    def find_memo(self, arch, dep, func):
        try:
            out = self.memo[(arch, dep, func)]
        except:
            return None
        else:
            return out

    def add_memo(self, arch, _exec, func, rpm):
        key_tuple = (arch, _exec, func)
        self.memo.setdefault(key_tuple, [])
        self.memo[key_tuple].append({rpm: _exec})

class FunctionFinder:
    def __init__(self, full_db, organized_db):
        self.orphan_functions = []
        self.memo = Memo()
        self.full_db = full_db
        self.organized_db = organized_db

    def FF_generator(self):
        for rpm_key in self.full_db:
            rpm = self.full_db[rpm_key]
            arch = rpm["architecture"]
            rpm_execs = rpm["executables"]
            #if ("noarch" in rpm_key):
                #print ("skipping analysis of " + rpm_key)
                #continue
            for executable in rpm_execs:
                try:
                    dependencies = rpm_execs[executable]["dependencies"]
                except:
                    print(executable)
                    #print(rpm_execs)
                    print((list(rpm_execs[executable].keys())))
                    #import pdb; pdb.set_trace()
                    raise
                symbs = rpm_execs[executable]["symbols"]
                undef_funcs = [x for x in symbs if symbs[x]["defined"] == "NO"]
                undef_func_mapper = FunctionFinder.undef_func_mapper(self, undef_funcs, dependencies, arch, rpm_key, executable)
                undef_func_gen = undef_func_mapper.undef_func_gen()
                for undef_func_data in undef_func_gen:
                    self.full_db[rpm_key]["executables"][executable]["symbols"].update(undef_func_data)
            yield {rpm_key: self.full_db[rpm_key]}

    class undef_func_mapper:
        def __init__(self, container, undef_funcs, dependencies, arch, rpm_key, executable):
            self.container = container
            self.undef_funcs = undef_funcs
            self.dependencies = dependencies
            self.arch = arch
            self.rpm_key = rpm_key
            self.executable = executable
            self.rpm_key_printed = False

        def undef_func_gen(self):
            for undef_func in self.undef_funcs:
                symbol_data = self.container.full_db[self.rpm_key]["executables"][self.executable]["symbols"][undef_func]

                weak_exact_symbol_option = [] # used for defined weak dependencies with exact name of undef_func
                global_symbol_option = [] #Used for global dependencies with slightly mismatched names
                weak_fuzzy_symbol_option = [] # used for defined weak dependencies with a variant name of undef_func
                local_symbol_option = [] #used for defined local dependencies
                undef_symbol_option = [] #Used when an undefined reference is seen in a dependency

                found = False

                for dep in self.dependencies:
                    x = self.container.memo.find_memo(self.arch, dep, undef_func)
                    if x != None:
                        #print("using memo for " + str(x))
                        for y in x:
                            symbol_data.update(y)
                            found = True
                        break

                if (found == True):
                    yield {undef_func: symbol_data}
                    continue

                for dep in self.dependencies:
                    try:
                        rpm_options = self.container.organized_db[self.arch][dep]
                    except KeyError:
                        #Occasionally a dependency mismatch occurs, make a best effort
                        extra_options = [x for x in self.container.organized_db[self.arch] if x.startswith(dep)]
                        self.dependencies.extend(extra_options)
                        continue

                    for rpm_option in rpm_options:
                        #There's a few possibilities for what the symbol will actually look like in a binary
                        # no_at is the default symbol name if nothing else is available: func
                        # at is the symbol name and a version for the symbol: func@version
                        # double_at is the symbol name and a version for the symbol: func@@version

                        symb_options = {"no_at":"", "at":"", "double_at":""}

                        func_split = undef_func.split("@")
                        if len(func_split) > 1:
                            no_at = func_split[0]
                            func_at = func_split[-1]
                            at_variant = func_split[0] + "@" + func_at
                            double_at_variant = func_split[0] + "@@" + func_at
                        else:
                            no_at = undef_func
                            at_variant = ""
                            double_at_variant = ""

                        try:
                            symb = self.container.full_db[rpm_option]["executables"][dep]["symbols"][no_at]
                            symb_options["no_at"] = (no_at, symb)
                        except KeyError as e:
                            pass

                        try:
                            if at_variant:
                                symb = self.container.full_db[rpm_option]["executables"][dep]["symbols"][at_variant]
                                symb_options["at"] = (at_variant, symb)
                        except KeyError as e:
                            pass

                        try:
                            if double_at_variant:
                                symb = self.container.full_db[rpm_option]["executables"][dep]["symbols"][double_at_variant]
                                symb_options["double_at"] = (double_at_variant, symb)
                        except KeyError as e:
                            pass

                        possible_symbs = [x for x in symb_options if symb_options[x]]

                        for x in possible_symbs:
                            name, obj = symb_options[x]
                            ext = {rpm_option:dep}
                            if name == undef_func:
                                if obj["defined"] == "YES":
                                    binding = obj["binding"]
                                    if binding == "GLOBAL":
                                        # A defined global variable is guaranteed to be the one used
                                        # No more searching required
                                        symbol_data.update(ext)
                                        found = True
                                        self.container.memo.add_memo(self.arch, dep, undef_func, rpm_option)
                                        break
                                    elif binding == "WEAK":
                                        weak_exact_symbol_option.append(ext)
                                    elif binding == "LOCAL":
                                        local_symbol_option.append(ext)
                                    else:
                                        print(binding)
                                        #import pdb; pdb.set_trace(ext)
                                else:
                                    undef_symbol_option.append(ext)
                            else:
                                if obj["defined"] == "YES":
                                    binding = obj["binding"]
                                    if binding == "GLOBAL":
                                        self.container.memo.add_memo(self.arch, dep, undef_func, rpm_option)
                                        global_symbol_option.append(ext)
                                    elif binding == "WEAK":
                                        weak_fuzzy_symbol_option.append(ext)
                                    elif binding == "LOCAL":
                                        local_symbol_option.append(ext)
                                    else:
                                        print(binding)
                                        #import pdb; pdb.set_trace(ext)
                                else:
                                    undef_symbol_option.append(ext)
                        if (found == True):
                            yield {undef_func: symbol_data}
                            break
                    else:
                        # We broke out of the for loop without a definite answer
                        # We'll use our best guess
                        if (weak_exact_symbol_option):
                            for opt in weak_exact_symbol_option:
                                symbol_data.update(opt)
                        elif (global_symbol_option):
                            for opt in global_symbol_option:
                                symbol_data.update(opt)
                        elif (weak_fuzzy_symbol_option):
                            for opt in weak_fuzzy_symbol_option:
                                symbol_data.update(opt)
                        elif (local_symbol_option):
                            for opt in local_symbol_option:
                                symbol_data.update(opt)
                        elif (undef_symbol_option):
                            for opt in undef_symbol_option:
                                symbol_data.update(opt)
                        else:
                            #Weird enough that we should take a look at it
                            if self.rpm_key_printed == False:
                                ##import pdb; pdb.set_trace()
                                print((self.rpm_key))
                                self.rpm_key_printed = True
                            print(("    " + undef_func))
                yield {undef_func: symbol_data}

if __name__ == "__main__":
    print_stdout = DBPrinter.print_stdout

    p = ArgumentParser()

    p.add_argument("-d", "--directory", type=str, required=True,
                   help="The directory to examine.")
    p.add_argument("-o", "--organized_db", type=str,
                   help="The json file of organized data to work with.")
    p.add_argument("-f", "--file", type=str,
                   help="The json file to put the result in.")
    args = p.parse_args()

    if args.organized_db:
        print ("loading organized data")
        directoryname = args.directory
        full_db = {}
        with open(args.organized_db, "r") as org_db:
            organized_data = load(org_db)
        json_files = [path.join(directoryname, x) for x in listdir(directoryname) if x.endswith(".json")]
        print(("loading full db with %d files" % len(json_files)))
        for json_file in json_files:
            stdout.write(".")
            stdout.flush()
            with open(json_file, "r") as f:
                data = load(f)
                full_db.update(data["BIG-IP"])
        print()
        print("done loading full db")
    else:
        a = Organizer(args.directory)
        full_db = a.full_data
        organized_data = a.organized_data

    ff = FunctionFinder(full_db, organized_data)

    #a.print_organized_data()

    printer = DBPrinter(args.file, output_filesize = 10**7)

    ff_generator = ff.FF_generator()
    print("printing out ff_generator data")
    for data in ff_generator:
        #stdout.write(".")
        #stdout.flush()
        printer.print_out(data)

    printer.close_out()
