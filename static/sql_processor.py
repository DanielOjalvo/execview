#!/usr/bin/env python3
import os
import re
import sys
import psycopg2
import argparse
import configparser

from lib import *

# retrive the connection string
conn_string = utility.get_conn_str()


def safe_execsql(sql, args, multi):
    '''
    Safely execute a SQL statement with exceptions and errors caught and processed.

    @param
    sql     the sql statement
    args    arguments for passing into sql query, MUST BE a tuple.
    multi   true for fetchall()

    @return
    the result set (if fetchall(): list of tuples ; if fetchone(): a tuple)
    '''

    # check if arguments are passed in valid format
    if not isinstance(args, tuple):
        raise Exception("The arguments for sql is not passed with a tuple.")

    # establish connection
    conn = psycopg2.connect(conn_string)

    # init variable
    res = None

    # with connect enables auto-commit. (otherwise do conn.commit() manually)
    with conn:
        with conn.cursor() as cur:
            
            cur.execute(sql, args)
            
            # print real query generated by psycopg2
            print(cur.query)

            if multi:
                try:
                    # may have concerns about the size of returned results. 
                    res = cur.fetchall()
                except psycopg2.ProgrammingError:
                    res = None #Error
            else:
                try:
                    res = cur.fetchone()
                except psycopg2.ProgrammingError:
                    res = None #Error
                    
    # close connection
    conn.close()

    return res


def parse_data_to_db(data_dict, untrimed_rpm_list, product, version):
    '''
    Parse the result of build log analyzation into database.
    analyze_build_log should only be analyzing build logs from one rpm each time. (or instead, modify data_dict dict to contain rpm/version)
    This script should only be used after rpm_db_builder and rpm_uploader from VulnerabilitytriageEngine are finished; parse_data_to_db does not parse rpm, version, and product.

    @param
    data_dict           output data structure defined in analyze_build_log
    untrimed_rpm_list   the list of rpm packages that are built in the source build log
    product             the product name of the product that the rpm resides in 
    version             the version number of the product that the rpm resides in 
    '''

    rpm_list = []

    # untrimed_rpm structure: <rpm name>.<architecture>.<suffix>
    # rpm_name structure: ...-<rpm version>-<release>
    # e.g., libnet-1.1.6-7.el6.0.0.4.x86_64.rpm
    #   ==>  rpm_name: libnet-1.1.6-7.el6.0.0.4
    #   ==>  rpm_arch: x86_64
    #   ==>  rpm_vers: 1.1.6
    #   ==>  rpm_rels: 7.el6.0.0.4

    for untrimed_rpm in untrimed_rpm_list:
        rpm_list.append( re.sub('\\.[^.]+?\\.rpm', '', untrimed_rpm) )
    '''
    rpm_arch = re.sub('[^.]*\\.', '', re.sub('\\.rpm', '', untrimed_rpm) )
    rpm_vers = re.sub('^.*?([^-]*)-[^-]+$', r'\1', rpm)
    rpm_rels = re.sub('.*-', '', rpm)
    '''

    # 0. check if the rpms in rpm_list exist in database. If not, which means this rpm is not built into ISO, don't do anything
    # init variable
    rpm_id_list = []

    for rpm in rpm_list:
        #DHNO: Add a where statement for the version (and product for completeness)
        sql_query = "SELECT rpms.rpm_id FROM rpms JOIN versions ON rpms.vers_id = versions.vers_id JOIN products ON versions.prod_id = products.prod_id" + \
                    " WHERE rpms.rpm = %s and versions.version = %s and products.product = %s"

        rpm_id = safe_execsql(sql_query, (rpm, version, product), False)

        # rpm_id will be a tuple
        if rpm_id is not None:
            rpm_id_list.append(str(rpm_id[0]))
        

    # if none of any rpm extracted from this build log is inside the database, this data_dict does not need to be processed.
    if len(rpm_id_list) == 0:
        return [], []


    # init log variables

    # the list for logging dynamically linked libraries (*.so) that did not get parsed into the deps table with rpm_dissector function under VulnerabilityTriageEngine project
    # format: [(exec_id, dep), (exec_id2, dep2),...]
    # exec_id:      the ID of the executable that uses this .so file as dep
    # dep:   the dep name (ended with .so)
    log_so_list = []

    # the list for logging library name cannot be found as prefix in both execs and aliases table. They can be inserted as executable in later stages, hence another script could be created to go over this log again and insert them at the end.
    # format: [(exec_id, dep, static), (exec_id2, dep2, static2),...]
    # exec_id:      the ID of the executable that uses this .so file as dep
    # dep:   the dependency name (ended with .so)
    # static:       whether this library is statically linked or not 
    log_uninserted_list = []

    try:
        # go through the dictionary structure
        for key, value in data_dict.items():
            # key = executable_name

            # remove any trailing newline character
            key = key.strip()

            # if installed_as is not null string, this executable has been renamed into another name with the UNIX install command.
            # replace executabe name with the new name. 
            #issues: corner case here for libdag / sbin
            if value['installed_as'] != "" and value['installed_as'] != "sbin":
                key = value['installed_as']

            
            # init variables
            exec_id_list = []
            dep_id_list = []
            
            # 1. process executables
            # if executable is an object file, ignore it.
            if key.endswith('.o'):
                continue

            # else query in execs to retrieve exec_id
            sql_query = "SELECT execs.exec_id, rpms.rpm_id FROM execs JOIN rpms ON execs.rpm_id = rpms.rpm_id JOIN versions ON rpms.vers_id = versions.vers_id JOIN products ON versions.prod_id = products.prod_id " + \
                        "WHERE execs.exec = %s AND versions.version = %s AND products.product = %s AND (rpms.rpm_id = " + \
                            " OR rpms.rpm_id = ".join(rpm_id_list) + \
                        ");"

            # result should be constructed by [(exec_id, rpm_id), (exec_id2, rpm_id2)...]
            execs_exec_id_rpm_id = safe_execsql(sql_query, (key, version, product), True)

            # if result returned 1 or more rows, this means the executable is linked with its rpm(s) already.
            # otherwise, check if the executable name is actually a alias
            if len(execs_exec_id_rpm_id) < 1:
                sql_query = "SELECT aliases.exec_id FROM aliases JOIN execs ON aliases.exec_id = execs.exec_id JOIN rpms ON execs.rpm_id = rpms.rpm_id JOIN versions ON rpms.vers_id = versions.vers_id JOIN products ON versions.prod_id = products.prod_id " + \
                            "WHERE aliases.alias = %s AND versions.version = %s AND products.product = %s AND (rpms.rpm_id = " + \
                                " OR rpms.rpm_id = ".join(rpm_id_list) + \
                            ");"

                aliases_exec_id = safe_execsql(sql_query, (key, version, product), True)
    
                # if either exec_id not found in aliases table or the exectable is not linked with any of its rpm(s), check if it needs to be inserted.
                if len(aliases_exec_id) < 1:
                    # if executable does not end with .a, which is an irregular case, print to console and skip
                    if not key.endswith('.a'):
                        utility.terminal_msg(1, "Executable '%s', which is not an archive file (.a), cannot be found in database." % key)
                        continue

                    # else if executable ends with .a, insert new records for all rpms in rpm_list
                    else:
                        sql_query = "INSERT INTO execs (exec, rpm_id) VALUES (%s, %s) RETURNING exec_id;"
                        for rpm_id in rpm_id_list:
                            exec_id = safe_execsql(sql_query, (key, rpm_id), False)
                            utility.terminal_msg(2, "Inserted new exec_id %d : %s" % (exec_id[0], key))
                            exec_id_list.append(str(exec_id[0]))
            
                else:
                    # store exec_id found into exec_id_list
                    for tup in aliases_exec_id:
                        utility.terminal_msg(2, "Found exec_id %s in aliases" % str(tup[0]))
                        exec_id_list.append(str(tup[0]))

            else:
                # store exec_id found into exec_id_list
                for tup in execs_exec_id_rpm_id:
                    utility.terminal_msg(2, "Found exec_id %s in execs" % str(tup[0]))
                    exec_id_list.append(str(tup[0]))

                #backup rpath
                '''
                # check if the rpm that the executable belonging to exist
                sql_query = "SELECT rpm_id FROM rpms WHERE rpm = %s"

                #debug
                print(sql_query % rpm)
                rpm_id = safe_execsql(sql_query, (rpm, ), False)

                # if rpm_id is None, insert rpm first
                if rpm_id is None:
                    # check if the version that the rpm belonging to exist
                    sql_query = "SELECT vers_id FROM versions WHERE version = %s"

                    #debug
                    print(sql_query % version)
                    vers_id = safe_execsql(sql_query, (version, ), False)

                    # if vers_id is None, insert version first
                    if vers_id is None:
                        sql_query = "INSERT INTO versions (version, prod_id) VALUES (%s, '4') RETURNING vers_id;"
                        vers_id = safe_execsql(sql_query, (version, ), False)

                    # with vers_id, proceed to insert rpm

                    # extract rpm architecture
                    if rpm_arch == "x86_64":
                        x86_64 = True
                        i686 = ppc = noarch = other_arch = False
                    elif rpm_arch == "i686":
                        i686 = True
                        x86_64 = ppc = noarch = other_arch = False
                    elif rpm_arch == "ppc":
                        ppc = True
                        x86_64 = i686 = noarch = other_arch = False
                    elif rpm_arch == "noarch":
                        noarch = True
                        x86_64 = i686 = ppc = other_arch = False
                    else:
                        other_arch = True
                        x86_64 = i686 = ppc = noarch = False
                    
                    sql_query = "INSERT INTO rpms (rpm, vers_id, x86_64, i686, ppc, noarch, other_arch, release, rpm_version)" + \
                                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING rpm_id;"
                    rpm_id = safe_execsql(sql_query, (rpm, vers_id, x86_64, i686, ppc, noarch, other_arch, rpm_rels, rpm_vers), False)
                

                # with rpm_id, proceed to insert executable
                sql_query = "INSERT INTO execs (exec, rpm_id) VALUES (%s, %s) RETURNING exec_id;"
                exec_id = safe_execsql(sql_query, (key, rpm_id), False)
                '''


            # 2. process dependencies
            for lib, data in value["libraries"].items():

                # if dependency is an object file, ignore it.
                if lib.endswith('.o'):
                    continue
                
                # if dependency does not have a suffix, reference to the executable's linkage preference (or actually the statically_linked attrib of library?)
                if "." not in lib:
                    if data['statically_linked'] == 'y':
                        lib = lib + ".a"
                    elif data['statically_linked'] == 'n':
                        lib = lib + ".so"
                    else:  # i.e., data['statically_linked'] == 'unknown'
                        if value["linkage_preference"] == 'static':
                            lib = lib + ".a"
                        elif  value["linkage_preference"] == 'dynamic':
                            lib = lib + ".so"
                        else:
                            utility.terminal_msg(1, "Dependency %s has unknown linkage preference and no proper suffix. (Assumed to be dynamically linked in this case)" % lib)
                        
                            # fallback to default. If no evidence provided for whether a library is statically or dynamically linked, assume it is dynamically linked.
                            data["statically_linked"] = 'n'
                            lib = lib + ".so"


                # query aliases table with prefix mode to see if the dependency name already exist as alias name in alias table, and extract the list of real executable name correlated
                sql_query = "SELECT aliases.alias FROM aliases JOIN execs ON aliases.exec_id = execs.exec_id JOIN rpms ON execs.rpm_id = rpms.rpm_id JOIN versions ON rpms.vers_id = versions.vers_id JOIN products ON versions.prod_id = products.prod_id " + \
                            "WHERE aliases.alias ilike %s AND versions.version = %s AND products.product = %s;"
                
                match_in_aliases_list = safe_execsql(sql_query, (lib + "%%", version, product), True)
                
                # when no result found
                if not match_in_aliases_list:
                    match_in_aliases = None
                # otherwise found the one with shortest length (most similar to the name before replacement)
                else:
                    match_in_aliases = min((x[0] for x in match_in_aliases_list), key = len)
                
                if match_in_aliases is not None:
                    # extra safe check: lib should always be contained in match_in_aliases[0], as it is queried for the same prefix
                    if lib in match_in_aliases:
                        # replace for its real executable name
                        lib = match_in_aliases
                    else:
                        utility.terminal_msg(1, "Prefix search found alias name %s for dependency %s" % (match_in_aliases, lib))
                        
                        # still replace to the matched name (behaviour can be modified)
                        lib = match_in_aliases

                # when no executable name in aliases table matches this dependency name
                else:
                    # query execs table with prefix mode to see if the dependency already exist as an executable in execs table 
                    sql_query = "SELECT execs.exec FROM execs JOIN rpms ON execs.rpm_id = rpms.rpm_id JOIN versions ON rpms.vers_id = versions.vers_id JOIN products ON versions.prod_id = products.prod_id " + \
                                "WHERE execs.exec ilike %s AND versions.version = %s AND products.product = %s;"
                    
                    match_in_execs_list = safe_execsql(sql_query, (lib + '%%', version, product), True)
                
                    # when no result found
                    if not match_in_execs_list:
                        match_in_execs = None
                    # otherwise found the one with shortest length (most similar to the name before replacement)
                    else:
                        match_in_execs = min((x[0] for x in match_in_execs_list), key = len)
                    
                    if match_in_execs is not None:
                        # extra safe check: lib should always be contained in match_in_execs[0], as it is queried for the same prefix
                        if lib in match_in_execs:
                            # replace for its real executable name
                            lib = match_in_execs
                        else:
                            utility.terminal_msg(1, "Prefix search found executable name %s for dependency %s" % (match_in_execs, lib))

                            # still replace to the matched name (behaviour can be modified)
                            lib = match_in_execs
                        

                    # while this dependency (library) name can be found as prefix in neither execs nor aliases table
                    else:
                        utility.terminal_msg(1, "Dependency %s cannot be found in both execs and aliases table from database." % lib)
                        # log to an external file in format of (exec_id, dependency, static)
                        for exec_id in exec_id_list: 
                            log_uninserted_list.extend([(exec_id, lib, data["statically_linked"])])
                        # pause
                        #input()

                        # skip this dependency (will be revisited later from log file through another script)
                        continue
                

                # craft query to check if library exist in table
                sql_query = "SELECT deps.dep_id FROM deps JOIN execs ON deps.exec_id = execs.exec_id JOIN rpms ON execs.rpm_id = rpms.rpm_id " + \
                            "WHERE deps.dep = %s AND (execs.exec_id = " + \
                                " OR execs.exec_id = ".join(exec_id_list) + \
                                " ) AND (rpms.rpm_id = " + \
                                    " OR rpms.rpm_id = ".join(rpm_id_list) + \
                            ");"

                #dep_id_list will be a list of tuples e.g., [('01',), ('02'),]
                dep_id_list = safe_execsql(sql_query, (lib, ), True)

                # replace unknown by referring linkage_preference of executable
                if data["statically_linked"] == 'unknown':
                    if value["linkage_preference"] == 'static':
                        data["statically_linked"] = 'y'
                    elif value["linkage_preference"] == 'dynamic':
                        data["statically_linked"] = 'n'
                    else:
                        utility.terminal_msg(1, "Unknown linkage preference for dependency %s. (Assumed to be dynamically linked in this case)" % lib)
                        # pause
                        #input()
                        # fallback to default. If no evidence provided for whether a library is statically or dynamically linked, assume it is dynamically linked.
                        data["statically_linked"] = 'n'
                
                # if dep_id not found, insert new records of libraries
                if len(dep_id_list) < 1:
                    # *.so should be all parsed by rpm_db_builder script. If exceptions found, log it.
                    if ".so" in lib:
                        utility.terminal_msg(1, "Dynamic dependency %s did not exist in database." % lib)
                        # error-handle: log issue to file in format of [(exec_id, dependency)]
                        for exec_id in exec_id_list: 
                            log_so_list.extend([(exec_id, lib)])
                        # skip this dependency
                        continue

                    else:
                        #issues: static should not go with dependency. (executable decide how it would like to link the libraries, so we should have a new linkage table storing <exec_id, dep_id, static>)
                        sql_query = "INSERT INTO deps (exec_id, dep, static) VALUES (%s, %s, %s) RETURNING dep_id;" 
                        
                        #issues: storing both deps' definition (id -> name) and which executables have it in deps table breaks the Normalization Form.

                        for exec_id in exec_id_list:
                            #debug
                            #print(sql_query % (exec_id, lib, isStatic))
                            dep_id = safe_execsql(sql_query, (exec_id, lib, data["statically_linked"]), False)

                            #debug
                            #print("************************ Insert new dependency ************************")
                            utility.terminal_msg(2, "New dependency %s has been inserted to database with ID of %s." % (lib, dep_id))
    
    # Overall Exception handler for database access                   
    except (Exception, KeyboardInterrupt) as e:
        utility.terminal_msg(1, "Exception/Interrupt {} caught during database processing static dependencies. Rolling back all changes with version {}".format(e, version))
        
        sql_query = "DELETE FROM versions WHERE versions = %s;"

        try:
            safe_execsql(sql_query, (version,), False)
            utility.terminal_msg(2, "Database rollback complete. Program terminated.")
            sys.exit(0)
        except (Exception, KeyboardInterrupt) as e2:
            utility.terminal_msg(0, "Failed to rollback database change. Version {} within database may be corrupted. \n\t Error message: {}".format(version, e2))
                        
    return log_so_list, log_uninserted_list
        

if __name__ == "__main__":
    # designed to be called by other modules. use __main__ only for testing purpose.

    ddict = {'exec' :
                    {
                        'libraries':
                                    {
                                        'liba.so':
                                                {
                                                    'statically_linked': 'y',
                                                    'object_path': 'unknown'
                                                },
                                        'libb.a':
                                                {
                                                    'statically_linked': 'n',
                                                    'object_path': 'unknown'
                                                }
                                    },
                        'buildroot_path': '/path/to/library/',
                        'linkage_preference': 'static'
                    }
    }

    #parse_data_to_db(ddict, 'rpm_name', '15.0.0.1')
    #safe_execquery("SELECT dep_id FROM deps WHERE dep = '%s';", ('a', 'b'))