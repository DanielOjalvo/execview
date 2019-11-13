#!/usr/bin/env python3

__doc__ = """
This script will upload JSON files created by rpm_db_builder into the database
created with create_tables.py. This should only need to be run once, then the
data will be available in the database for future queries.
"""
import sys
import time
from json import load
from os import listdir, path
from argparse import ArgumentParser

from lib import *

try:
    import psycopg2
except ImportError:
    utility.terminal_msg(0, "Psycopg2 must be installed to use this script.")

"""
The format of the json database looks roughly like the following.

{
    "BIG-IP:v11.5.1": {
        "libattr-2.4.32-1.1.0.0.110.i686.rpm": {
            "All dependencies": [
                "libc.so.6"
            ],
            "All executables": [
                "libattr.so.1.1.0",
                "libattr.so.1"
            ],
            "architecture": "i686",
            "executables": {
                "libattr.so.1": {
                    "Symlink Target": "libattr.so.1.1.0",
                    "dependencies": [
                        "libc.so.6"
                    ],
                    "symbols": {
                        "__cxa_finalize@GLIBC_2.1.3": {
                            "at": "GLIBC_2.1.3",
                            "binding": "WEAK",
                            "defined": "NO",
                            "type": "FUNC"
                        },
                        "__errno_location@GLIBC_2.0": {
                            "at": "GLIBC_2.0",
                            "binding": "GLOBAL",
                            "defined": "NO",
                            "type": "FUNC"
                        },
                        "__rawmemchr@GLIBC_2.1": {
                            "at": "GLIBC_2.1",
                        }
                    }
                }
            }
            <More data>
            "package": "libattr-2.4.32-1.1.0.0.110.i686.rpm",
            "release": "1.1.0.0.110",
            "version": "2.4.32"
        },
    },
},
"""
# SQL format strings
prod_str = ("INSERT INTO products (product) "
            "VALUES (%s) "
            "RETURNING prod_id;")

vers_str = ("INSERT INTO versions (prod_id, version) "
            "VALUES (%s, %s) "
            "RETURNING vers_id;")

rpm_sql_str = ("INSERT INTO rpms "
               "(vers_id, rpm, release, rpm_version, x86_64, i686, ppc, noarch, other_arch) "
               "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
               "RETURNING rpm_id;")

exec_sql_str = ("INSERT INTO execs "
                "(rpm_id, exec) "
                "VALUES (%s, %s) "
                "RETURNING exec_id;")

alias_sql_str = ("INSERT INTO aliases "
                 "(exec_id, alias) "
                "VALUES (%s, %s) "
                "RETURNING alias_id;")

dep_sql_str = ("INSERT INTO deps "
               "(exec_id, dep, static) "
               "VALUES (%s, %s, %s) "
               "RETURNING dep_id;")

rpath_sql_str = ("INSERT INTO rpaths "
               "(exec_id, rpath) "
               "VALUES (%s, %s) "
               "RETURNING rpath_id;")

decl_str = ("INSERT INTO decl_funcs "
            "(exec_id, func) "
            "VALUES (%s, %s) "
            "RETURNING func_id;")

at_version_str = ("INSERT INTO at_versions "
                  "(func_id, at) "
                  "VALUES (%s, %s) "
                  "RETURNING at_id;")

def_str = ("INSERT INTO def_funcs "
           "(func_id, binding) "
           "VALUES (%s, %s) "
           "RETURNING def_func_id;")

callee_str = ("INSERT INTO callee_funcs "
              "(func_id, callee_func) "
              "VALUES (%s, %s) "
              "RETURNING callee_func_id;")

rollback_str = ("DELETE FROM versions "
                "WHERE versions.version = %s;")

def existing_index(curs, table, _id, key, value):
    query_str = "SELECT %s from %s " % (_id, table)
    where_str = "WHERE %s = " % (key)
    full_query_str = query_str + where_str + " %s;"

    curs.execute(full_query_str, (value,))
    ret = curs.fetchone()
    
    if ret:
        return ret[0]
    else:
        return False

def insert_row(curs, sql_str, value_tuple):
    # execute statement
    curs.execute(sql_str, value_tuple)
    output = curs.fetchone()[0]
    
    return output


def upload(filedir):
    conn = psycopg2.connect(utility.get_conn_str())

    json_files = [path.join(filedir, x) for x in listdir(filedir) if x.endswith(".json")]

    for filename in json_files:
        terminal_msg(2, "Examining %s" % filename)
        time_import_start = time.time()
        with open(filename, "r") as f:
            json_data = load(f)
        time_import_end = time.time()
        terminal_msg(2, "File import time: {}".format(time_import_end - time_import_start))

        time_upload_start = time.time()
        for x in json_data:
            # Expecting a version string like <prod>:<vers>
            split = x.split(":")
            product = split[0]
            version = split[1]
            json_data = json_data[x]
            break
        with conn:
            with conn.cursor() as curs:
                try:
                    #debug
                    #print("inserting product cur id %d" % prod_id)
                    prod_id = existing_index(curs, "products", "prod_id", "product", product)
                    if prod_id == False:
                        prod_id = insert_row(curs, prod_str, (product,))

                    vers_id = existing_index(curs, "versions", "vers_id", "version", version)
                    if vers_id == False:
                        vers_id = insert_row(curs, vers_str, (prod_id, version))

                    for rpm in json_data:
                        try:
                            package = json_data[rpm]["package"]
                            release = json_data[rpm]["release"]
                            version = json_data[rpm]["version"]
                            x86_64 = json_data[rpm]["x86_64"]
                            i686 = json_data[rpm]["i686"]
                            ppc = json_data[rpm]["ppc"]
                            noarch = json_data[rpm]["noarch"]
                            otherarch = json_data[rpm]["other_arch"]
                            #print("inserting rpm")
                            rpm_id = insert_row(curs, rpm_sql_str, (vers_id, rpm, release, version, x86_64, i686, ppc, noarch, otherarch))

                            execs = json_data[rpm]["executables"]

                            alias_table = [] # aliases [{target_exec:blah, exec_:blah}...]
                            exist_dict = {} # [{<exec_name>: exec_id}]

                            for exe in execs:
                                #print("inserting exec")
                                try:
                                    target_exec = execs[exe]["Symlink Target"]
                                    if target_exec != "" and target_exec != exe:
                                        # Make alias table pairing the executable
                                        # and the executable it symlinks to.
                                        alias_table.append({"target_exec": target_exec, "exec": exe})
                                        continue
                                except:
                                    pass

                                exec_id = insert_row(curs, exec_sql_str, (rpm_id, exe))

                                exist_dict[exe] = exec_id; #Add real exec to existing_dict
                                
                                dep_list = execs[exe]["dependencies"]
                                for dep in dep_list:
                                    #print ("inserting dep")
                                    dep_id = insert_row(curs, dep_sql_str, (exec_id, dep, False))
                                #print("deps inserted")
                                rpath_list = execs[exe]["rpath"]
                                for rpath in rpath_list:
                                    #print ("inserting rpath")
                                    if rpath:
                                        rpath_id = insert_row(curs, rpath_sql_str, (exec_id, rpath))
                                #print ("rpaths inserted")
                                symbol_list = execs[exe]["symbols"]

                            # getting around extra callees
                                callee_funcs = set()

                                for symbol in symbol_list:
                                    symbol_data = symbol_list[symbol]
                                    #print ("inserting symbol")
                                    sym_id = insert_row(curs, decl_str, (exec_id, symbol))
                                    try:
                                        #print ("inserting at")
                                        at = symbol_data["at"]
                                        if at:
                                            insert_row(curs, at_version_str, (sym_id, at))
                                    except:
                                        pass

                                    binding = symbol_data["binding"]
                                    defined = symbol_data["defined"]
                                    #print ("inserting definition")

                                    if defined == "YES":
                                        #print("inserted definition now")
                                        def_func_id = insert_row(curs, def_str, (sym_id, binding))
                                        #print("inserted definition %d" % def_func_id)

                                    try:
                                        #print("got here")
                                        called_funcs = symbol_data["called_functions"]
                                        for x in called_funcs:
                                            callee = x["function"]
                                            if callee == symbol:
                                                #Don't record self-references
                                                continue
                                            callee_id = insert_row(curs, callee_str, (sym_id, callee))
                                    except:
                                        pass
                            
                            alias_passes = 0
                            while alias_table and alias_passes <= len(alias_table):
                                alias_candidate = alias_table.pop()
                                try:
                                    alias_exec_id = exist_dict[alias_candidate["target_exec"]]
                                    insert_row(curs, alias_sql_str, (alias_exec_id, alias_candidate["exec"]))
                                    exist_dict[alias_candidate["exec"]] = alias_exec_id
                                    #Reset the number of times we've looked through alias_table
                                    #Why? We might have added the right exec into the table
                                    alias_passes = 0
                                except KeyError:
                                    alias_passes += 1
                                    alias_table.insert(0, alias_candidate)
                                    #Try again, we're working with a chain of aliases it seems
                                    #print("passed through loop")
                            
                        except Exception as e:
                            terminal_msg(1, "Exception {} occurred during processing json data".format(e))
                            raise e

                # Overall Exception handler for database access
                except (Exception, KeyboardInterrupt) as e:
                    utility.terminal_msg(1, "Exception/Interrupt {} caught during database processing static dependencies. Rolling back all changes with version {}".format(e, version))
                    try:
                        # rollback database changes
                        curs.execute(rollback_str, (version,))
                        utility.terminal_msg(2, "Database rollback complete. Program terminated.")
                        sys.exit(0)
                    except (Exception, KeyboardInterrupt) as e2:
                        terminal_msg(0, "Failed to rollback database change. Version {} within database may be corrupted. \n\t Error message: {}".format(version, e2))

        time_upload_end = time.time()
        terminal_msg(2, "Time upload: {}".format(time_upload_end - time_upload_start))

    conn.close()

if __name__ == "__main__":
    p = ArgumentParser(description=__doc__)

    p.add_argument("-j", "--json_directory", type=str, required=True,
                   help="The root directory JSON RPMDB files will be found.")

    args = p.parse_args()

    upload(args.json_directory)
