#!/usr/bin/env python3

__doc__ = """
    This script will construct the tables used to organize the database.
    This should only need to be run once, then the tables will be available for future users.
"""
import sys
from argparse import ArgumentParser

from library import *


try:
    import psycopg2
except ImportError:
    utility.terminal_msg(0, "Psycopg2 must be installed to use this script.")


# non-primary keys should be using Integer instead of Serial as we don't either want or need them to auto-increase.
table_array = [("CREATE TABLE public.products ("
                "    {PROD_ID} SERIAL,"
                "    {PROD}    TEXT,"
                "    PRIMARY KEY ({PROD_ID})"
               ");"),
               ("CREATE TABLE public.versions ("
                "    {VERS_ID} SERIAL,"
                "    {PROD_ID} INTEGER CHECK({PROD_ID} > 0),"
                "    {VERS} TEXT,"
                "    PRIMARY KEY ({VERS_ID}),"
                "    FOREIGN KEY ({PROD_ID}) REFERENCES products({PROD_ID}) ON DELETE CASCADE"
                ");"),
               ("CREATE TABLE public.rpms ("
                "    {RPM_ID}    SERIAL,"
                "    {VERS_ID}   INTEGER CHECK({VERS_ID} > 0),"
                "    {RPM}       TEXT,"
                "    {X86_64}    BOOLEAN,"
                "    {I686}      BOOLEAN,"
                "    {PPC}       BOOLEAN,"
                "    {NOARCH}    BOOLEAN,"
                "    {OTHERARCH} BOOLEAN,"
                "    {RELEASE}   TEXT,"
                "    {RPM_V}     TEXT,"
                "    PRIMARY KEY ({RPM_ID}),"
                "    FOREIGN KEY ({VERS_ID}) REFERENCES versions ({VERS_ID}) ON DELETE CASCADE"
                ");"),
               ("CREATE TABLE public.execs ("
                "    {EXEC_ID}        SERIAL,"
                "    {RPM_ID}         INTEGER CHECK({RPM_ID} > 0),"
                "    {EXEC}           TEXT,"
                "    PRIMARY KEY ({EXEC_ID}),"
                "    FOREIGN KEY ({RPM_ID}) REFERENCES rpms ({RPM_ID}) ON DELETE CASCADE"
                ");"),
               ("CREATE TABLE public.aliases ("
                "    {ALIAS_ID}        SERIAL,"
                "    {EXEC_ID}         INTEGER CHECK({EXEC_ID} > 0),"
                "    {ALIAS}           TEXT,"
                "    PRIMARY KEY ({ALIAS_ID}),"
                "    FOREIGN KEY ({EXEC_ID}) REFERENCES execs ({EXEC_ID}) ON DELETE CASCADE"
                ");"),
               ("CREATE TABLE public.rpaths ("
                "    {RPATH_ID}  SERIAL,"
                "    {EXEC_ID}   INTEGER CHECK({EXEC_ID} > 0),"
                "    {RPATH}     TEXT,"
                "    PRIMARY KEY ({RPATH_ID}),"
                "    FOREIGN KEY ({EXEC_ID}) REFERENCES execs ({EXEC_ID}) ON DELETE CASCADE"
                ");"),
               ("CREATE TABLE public.deps ("
                "    {DEP_ID}        SERIAL,"
                "    {EXEC_ID}       INTEGER CHECK({EXEC_ID} > 0),"
                "    {DEP}           TEXT,"
                "    {STATIC}        BOOLEAN,"
                "    PRIMARY KEY ({DEP_ID}),"
                "    FOREIGN KEY ({EXEC_ID}) REFERENCES execs ({EXEC_ID}) ON DELETE CASCADE"
                ");"),
               ("CREATE TABLE public.resolved_deps_execs ("
                "    {DEP_ID}          INTEGER CHECK({DEP_ID} > 0),"
                "    {R_EXEC_ID}       INTEGER CHECK({R_EXEC_ID} > 0),"
                "    FOREIGN KEY ({DEP_ID}) REFERENCES deps ({DEP_ID}),"
                "    FOREIGN KEY ({R_EXEC_ID}) REFERENCES execs ({EXEC_ID})"
                ");"),
               ("CREATE TABLE public.decl_funcs ("
                "    {DECL_ID}    SERIAL,"
                "    {EXEC_ID}    INTEGER CHECK({EXEC_ID} > 0),"
                "    {FUNC}       TEXT,"
                "    PRIMARY KEY ({DECL_ID}),"
                "    FOREIGN KEY ({EXEC_ID}) REFERENCES execs ({EXEC_ID}) ON DELETE CASCADE"
                ");"),
               ("CREATE TABLE public.def_funcs ("
                "    {DEF_ID}     SERIAL,"
                "    {DECL_ID}    INTEGER CHECK({DECL_ID} > 0),"
                "    {BIND}       TEXT,"
                "    PRIMARY KEY ({DEF_ID}),"
                "    FOREIGN KEY ({DECL_ID}) REFERENCES decl_funcs ({DECL_ID}) ON DELETE CASCADE"
               ");"),
               ("CREATE TABLE public.at_versions ("
                "    {AT_ID}        SERIAL,"
                "    {DECL_ID}      INTEGER CHECK({DECL_ID} > 0),"
                "    {AT}           TEXT,"
                "    PRIMARY KEY ({AT_ID}),"
                "    FOREIGN KEY ({DECL_ID}) REFERENCES decl_funcs ({DECL_ID}) ON DELETE CASCADE"
                ");"),
               ("CREATE TABLE public.callee_funcs ("
                "    {CALLEE_ID}    SERIAL,"
                "    {DECL_ID}      INTEGER CHECK({DECL_ID} > 0),"
                "    {C_FUNC}       TEXT,"
                "    PRIMARY KEY ({CALLEE_ID}),"
                "    FOREIGN KEY ({DECL_ID}) REFERENCES decl_funcs ({DECL_ID}) ON DELETE CASCADE"
                ");")]

def main():
    # putting the column names into the array of formatted create statement strings (table_array)
    f_array = [
        x.format(
            PROD_ID=PROD_ID, PROD=PROD,
            VERS_ID=VERS_ID, VERS=VERS,
            RPM_ID=RPM_ID, RPM=RPM, RELEASE=RELEASE, RPM_V=RPM_V,
            X86_64=X86_64, I686=I686, PPC=PPC, NOARCH=NOARCH, OTHERARCH=OTHERARCH,
            EXEC_ID=EXEC_ID, EXEC=EXEC,
            RPATH_ID=RPATH_ID, RPATH=RPATH,
            DEP_ID=DEP_ID, DEP=DEP, STATIC=STATIC, 
            R_EXEC_ID=R_EXEC_ID,
            DECL_ID=DECL_ID, FUNC=FUNC,
            DEF_ID=DEF_ID, BIND=BIND,
            AT_ID=AT_ID, AT=AT,
            CALLEE_ID=CALLEE_ID, C_FUNC=C_FUNC,
            ALIAS_ID=ALIAS_ID, ALIAS=ALIAS
        ) for x in table_array
    ]

    # Define our connection string
    conn_string = get_conn_str()

    # print the connection string we will use to connect
    terminal_msg(2, "Connecting to database\n\t-> %s" % (conn_string))

    
    # get a connection, if a connect cannot be made an exception will be raised here
    conn = psycopg2.connect(conn_string)
    terminal_msg(2, "Connected!\n")

    for table in f_array:
        try:
            with conn.cursor() as cursor:
                cursor.execute(table)
        except psycopg2.ProgrammingError as e:
            raise e
        conn.commit()
    conn.close()

if __name__ == "__main__":

    p = ArgumentParser(description=__doc__)

    main()