#!/usr/bin/env python3

import re
from json import dumps
from os import path
from argparse import ArgumentParser
from subprocess import Popen
from tempfile import TemporaryFile

try:
    from functools import reduce
except:
    pass

try:
    import cxxfilt
    def cppdemangle(s):
        if not s.startswith("_Z"):
            return s
        else:
            try:
                result = cxxfilt.demangle(s, external_only=False)
                return result
            except:
                return s
except:
    def cppdemangle(s):
        #print("running cppdemangle")
        if not s.startswith("_Z"):
            return s
        else:
            result = run_shell_cmd(["c++filt", s])
            return result


class ParserError(Exception):
    def __init__(self, _classCaller, thing, line):
        self._classCaller = _classCaller
        self.thing = thing
        self.line = line

    def __str__(self):
        return "Class: %s: Error: %s\n\t%s" % (self._classCaller, self.thing, self.line)

def run_shell_cmd(x):
    """
    Runs a shell cmd, returns tuple (retcode, stdoutput).
    Obviously runs as a full shell cmd, so avoid using untrusted input
    """
    stdout_tmp = TemporaryFile()
    stdout_str = ""

    cmd_str = x
    if (isinstance(x, list)):
        cmd_str = " ".join(x)

    #print("cmd_str")
    #print(cmd_str)

    p = Popen(cmd_str, stdout = stdout_tmp, shell=True)
    p.wait()

    stdout_tmp.seek(0)

    stdout_str = stdout_tmp.read()
    #print (stdout_str)
    return stdout_str.decode("utf-8")

def zip_mangled_demangled_funcs(l):
    l = list(zip(l, [cppdemangle(x) for x in l]))

    output_list = []
    for x in l:
        output_list.append({"function": x[0], "long_name": x[1].strip()})

    return output_list

class AssemblyInstruction:
    """
    The parsing of an instruction like this
    4424:       ff a3 0c 01 00 00       jmp    *0x10c(%ebx)
    or this
    46c1:       89 e5                   mov    %esp,%ebp
    or this
    46fe:       90                      nop
    """

    def __init__(self, inst):
        #The regular expression to match
        instruction_match = r"^\s*(?P<address>\w*):\s*(?P<opcodes>(?P<ignore>[0-9a-f][0-9a-f] )*)\s*" \
                            r"(?P<instruction>$|(?P<instruction_type>[a-z]*)\s*(?P<arguments>.*$))"
        instruction_re = re.compile(instruction_match)

        self.inst_str = inst
        #print (inst)

        match = instruction_re.match(inst)

        if not match:
            self.address = 0xdeadbeef
            self.opcodes = "unknown"
            self.instruction_type = "unparsed"
            self.arguments = ""
            print("couldn't match" + "*" +inst + "*")
            return

        self.address = int(match.group("address"), base=16)
        self.opcodes = match.group("opcodes").strip()
        if not match.group("instruction_type"):
            self.instruction_type = "NONE"
            if not match.group():
                print(("Instruction No match for *" + inst + "*"))
        else:
            self.instruction_type = match.group("instruction_type")
        self.arguments = match.group("arguments")

        def parse_call_arguments(arguments):
            """
            We're using this to extract some data about the arguments
            arg1, the first argument, maybe a register, literal, etc
            arg2, the second argument, may not exist or same as arg1
            arg1_calc, the equation (as a string), which calculates an offset of arg1's register/value
            arg2_calc, the equation (as a string), which calculates an offset of arg2's register/value
            fn, a function being jumped to
            fn_offset, the offset in memory of the function being jumped to
            """
            fn = None
            fn_offset = None
            section = None
            fn_address = None
            #print(arguments)
            jci_string = r"(?P<fn_address>[0-9a-f]*)\s*<(?P<fn>[^@+-]*)(?P<section>@[^+-]*)?(?P<fn_offset>[+-][^@]*)?>" #jump or call instruction match
            jci_re = re.compile(jci_string)
            jci_parts = jci_re.match(arguments)

            if jci_parts:
                fn_address = jci_parts.group('fn_address') #offset starts at 1
                #print(fn_address)
                fn = jci_parts.group('fn')
                #print(fn)
                if jci_parts.group('section'):
                    section = jci_parts.group('section').replace("@", "")
                    #print(section)
                if jci_parts.group('fn_offset'):
                    fn_offset = jci_parts.group('fn_offset')
                    #print(fn_offset)
            else:
                fn_offset = arguments
                fn = "PTR_ARGS"
                #print ("args: couldn't match *" + arguments + "*")

            return (fn_address, fn, fn_offset, section)
        #print(self.arguments)
        if "call" in self.instruction_type:
            #print (self.arguments)
            #print ( parse_call_arguments(self.arguments))
            self.fn_address, self.fn, self.fn_offset, self.section = parse_call_arguments(self.arguments)

    def print_stats(self):
        #print("\t\t\tAddress: 0x%x: inst: %s args: %s" % (self.address, self.instruction_type, self.arguments))
        print("\t\t\t%s" % self.inst_str)
        print("\t\t\t\t arguments: %s" % self.arguments)
        if self.fn:
            print("\t\t\t\t Call to: %s" % self.fn)
        if self.fn_offset:
            print("\t\t\t\t Offset: %s" % self.fn_offset)
        if self.fn_address:
            print("\t\t\t\t address: %s" % self.fn_address)           #issues: fn_address instead of arg1?

    def inst_data(self):
        """
        Return data on a call instruction
        """
        if "call" not in self.instruction_type:
            raise ParserError("AssemblyInstruction", "instruction", "not a call function")
        return {"fn_name":self.fn,
                "fn_address": self.fn_address,
                "fn_section": self.section,
                "fn_offset": self.fn_offset,
                "call_address": self.address}
            

class AssemblyFunction:
    """
    A class representing a unit of AssemblyInstructions
    00004424 <error@plt>:
        4424:       ff a3 0c 01 00 00       jmp    *0x10c(%ebx)
        442a:       68 00 02 00 00          push   $0x200
        442f:       e9 e0 fb ff ff          jmp    4014 <_init+0x30>
    """
    def __init__(self, first_instruction):
        #We begin this class by parsing the first part of the stanza
        # 00004014 <__errno_location@plt-0x10>:
        parts = first_instruction.split()
        self.received_instruction = first_instruction
        try:
            self.function_name = "".join([x for x in parts[1] if x not in ("<", ">", ":")])
            #print(1, self.function_name)
            self.function_name = self.function_name.split("@", 1)[0]
            #print(2, self.function_name)
            if self.function_name.find("-0x") != -1:
                self.function_name = self.function_name[:self.function_name.find("-0x")] #Remove offsets

            #print(3, self.function_name)
            if self.function_name.find("+0x") != -1:
                self.function_name = self.function_name[:self.function_name.find("+0x")]

            #print(4, self.function_name)
            self.assemblyInstructions = []
            self.callInstructions = set()
            
            self.long_name = cppdemangle(self.function_name)
        except Exception as e:
            print(first_instruction)
            print(parts)
            raise e
            

    def add_instruction(self, s):
        new_inst = AssemblyInstruction(s)
        self.stanzaEnd = new_inst.address
        if "call" in new_inst.instruction_type and new_inst.fn != "PTR_ARGS":
            self.callInstructions.add(new_inst.fn)

        self.assemblyInstructions.append(new_inst)

    def grab_call_instructions(self, fn = None):
        return [x for x in self.assemblyInstructions
                if "call" in x.instruction_type
                and x.fn != None
                and self.function_name not in x.fn]

    def print_stats(self, limit=0):
        print(("\t\tFunction name: %s" % self.function_name))
        #if self.at:
        #    print("\t\tAt %s" % self.at)

        call_instructions = self.grab_call_instructions()

        print(("\t\tNumber call instructions: %d" % len(call_instructions)))

        count = 0
        for x in call_instructions:
            if limit != 0 and count > limit:
                break
            x.print_stats()
            count += 1

class AssemblySection:
    """
    A class representing a collection of AssemblyInstructions
    00004424 <error@plt>:
        4424:       ff a3 0c 01 00 00       jmp    *0x10c(%ebx)
        442a:       68 00 02 00 00          push   $0x200
        442f:       e9 e0 fb ff ff          jmp    4014 <_init+0x30>

    000044e4 <setsockopt@plt>:
        44e4:       ff a3 3c 01 00 00       jmp    *0x13c(%ebx)
        44ea:       68 60 02 00 00          push   $0x260
        44ef:       e9 20 fb ff ff          jmp    4014 <_init+0x30>
    """
    def __init__(self, name, instructionList):
        def stanza_start(s):
            stanza_start_str = "^[0-9a-f]* <"
            stanza_re = re.compile(stanza_start_str)
            return stanza_re.match(s)

        self.function_dict = {}
        #print("instruction list is:")
        #print(instructionList)

        def process_instruction_list(stanza_list, next_instruction):
            if not next_instruction:
                #print("returning")
                return stanza_list
            elif stanza_start(next_instruction):
                #Make a new AssemblyFunction and add this to the end of the list
                #print("examining a stanza start")
                #print(next_instruction)
                if stanza_list:
                    func_name = stanza_list.pop(0)
                    self.function_dict[func_name] = stanza_list.pop()
                stanza_list = []
                next_func = AssemblyFunction(next_instruction)
                stanza_list.append(next_func.function_name)
                stanza_list.append(next_func)
            else:
                try:
                    #print("adding a new instruction")
                    stanza_list[-1].add_instruction(next_instruction)
                    #print(stanza_list)
                except Exception as e:
                    print (stanza_list)
                    print (next_instruction)
                    raise e
            return stanza_list

        self.section_name = name
        reduce(process_instruction_list, instructionList, [])

    def merge_section(self, new_section):
        #A function to merge two sections if they are only different in their offsets
        self.function_dict.update(new_section.function_dict)
        
    def print_stats(self, limit=0):
        print("\tAssemblySection: %s " % self.section_name)
        print("\tNumber of AssemblyFunctions: %d " % len(self.function_dict))
        count = 0
        for stanza in list(self.function_dict.values()):
            if limit != 0 and count > limit:
                break
            stanza.print_stats(limit = 2*limit)
            count += 1

    def get_functions(self):
        return list(self.function_dict.keys())

    def get_calls(self, fn = None):
        if fn == "PTR_ARGS":
            return None
        elif fn:
            function = self.function_dict[fn]
            return function.callInstructions
        else:
            all_funcs = set()
            for fn in list(self.function_dict.keys()):
                all_funcs |= self.function_dict[fn].callInstructions
            return all_funcs

class AssemblyRaw:
    """
    A class representing the raw disassembly file to be parsed into an AssemblySection

    liberrdefs.so:     file format elf32-i386


    Disassembly of section .init:

    00003fe4 <_init>:
        3fe4:       55                      push   %ebp
        3fe5:       89 e5                   mov    %esp,%ebp
        3fe7:       53                      push   %ebx
        3fe8:       83 ec 04                sub    $0x4,%esp
        3feb:       e8 00 00 00 00          call   3ff0 <_init+0xc>
        3ff0:       5b                      pop    %ebx
        3ff1:       81 c3 4c ae 01 00       add    $0x1ae4c,%ebx
        3ff7:       8b 93 e4 ff ff ff       mov    -0x1c(%ebx),%edx
        3ffd:       85 d2                   test   %edx,%edx
        3fff:       74 05                   je     4006 <_init+0x22>
        4001:       e8 1e 01 00 00          call   4124 <__gmon_start__@plt>
        4006:       e8 b5 06 00 00          call   46c0 <shmget@plt+0xac>
        400b:       e8 60 bf 00 00          call   ff70 <gettid+0x30>
        4010:       58                      pop    %eax
        4011:       5b                      pop    %ebx
        4012:       c9                      leave  
        4013:       c3                      ret    

    """

    def __init__(self, filename = None, text = None):
        self.raw_text = None
        if filename:
            with open(filename, 'r') as disassembly_file:
                self.raw_text = disassembly_file.read()
        elif text:
            self.raw_text = text

        if not self.raw_text:
            raise ParserError("AssemblyRaw", "raw_text", "No raw text")
        else:
            self.disassembly_name = None
            self.file_format = None
            self.sections = {}

            cur_section = None
            instruction_list = []

            for line in self.raw_text.splitlines():
                if not line:
                    continue
                elif "..." in line:
                    continue
                elif "file format" in line:
                    if (self.disassembly_name or self.file_format):
                        raise ParserError(type(self).__name__, "file format", line)
                    else:
                        # Expecting this format
                        # liberrdefs.so:     file format elf32-i386
                        match_string = r"(?P<so_name>.*):\s*file format\s*(?P<file_format>.*)"
                        match = re.match(match_string, line)
                        self.disassembly_name = path.basename(match.group('so_name'))
                        self.file_format = match.group('file_format')
                elif "Disassembly of section " in line:
                    if cur_section:
                        #looks like we hit the end of a section, create a
                        #SectionCollection Object and add it to the list
                        new_section = AssemblySection(cur_section, instruction_list)
                        section_name = new_section.section_name
                        if section_name in self.sections:
                            print(("Adding pre-existing section", section_name))
                        self.sections[section_name] = new_section

                    #Expecting line like this:
                    #"Disassembly of section .plt:"
                    cur_section = line.split().pop().replace(":", "")
                    instruction_list = []
                else:
                    instruction_list.append(line)
            if cur_section:
                #Create the assembly collection for the last section
                new_section = AssemblySection(cur_section, instruction_list)
                section_name = new_section.section_name
                try:
                    self.sections[section_name].merge_section(new_section)
                    print("added pre-existing section")
                except:
                    #More likely
                    self.sections[section_name] = new_section
        #Now generate defined functions
        self.defined_functions = {}

        #now to get the called functions
        for section in list(self.sections.keys()):
            if ".plt" in section:
                #.plt is for functions that aren't defined (more-or-less)
                continue
            section_obj = self.sections[section]
            func_names = section_obj.get_functions()
            for name in func_names:
                self.defined_functions[name] = {"called_functions" : 
                                                zip_mangled_demangled_funcs(list(section_obj.get_calls(name)))}

    def print_stats(self, limit=0):
        print(("AssemblyRaw of file: %s" % self.disassembly_name))
        print(("File format: %s" % self.file_format))
        print(("Number of sections: %d" % len(self.sections)))
        count = 0
        for section in self.sections:
            if limit != 0 and count > limit:
                break
            section.print_stats(limit = 2*limit)
            count += 1
  
    def create_json_data(self):
        out_dict = {"defined_functions" : self.defined_functions}
        return out_dict


if __name__ == "__main__":
    p = ArgumentParser()

    p.add_argument("-f", "--file", type=str, required=True,
                   help="This disassembly file to examine")
    p.add_argument("-d", "--demangle", action="store_true",
                   help="Demangle C++-mangled symbols")
    p.add_argument("-s", "--print_stats", action="store_true",
                   help="Print Statistics on the assembly")
    p.add_argument("-j", "--print_json", action="store_true",
                   help="Print create JSON data from the executable.")
    args = p.parse_args()

    demangle = args.demangle

    a = AssemblyRaw(args.file)


    print("Completed our assembly file parsing!")
    if args.print_stats:
        a.print_stats()

    if args.print_json:
        json_data = a.create_json_data()
        print(dumps(json_data, indent=4))
