#!/usr/bin/env python3

import os
import sys
import configparser
import time

"""
common utility library for Vulnerability Triage Engine parser
"""

def read_config():
    '''
    Read the config and establish connection to database.
    '''
    try:
        # config file (by default searching under the sme directory of this script, replace the path if necessary)
        CONFIG_FILE = os.path.dirname(os.path.abspath(__file__)) + "/config.conf"

        config = configparser.ConfigParser(allow_no_value = True)
        config.read(CONFIG_FILE)
        return config

    except configparser.Error:
        terminal_msg(0, "Failure on loading config file. Please check if a proper config file exists.")

    return {}
    
def get_database_url():
    config = read_config()
    DBURL = "NO_DB"

    try:
        DBURL = config['database']['db_url']
    except KeyError:
        terminal_msg(0, "Failed to retrieve the URL of database.")
    return DBURL

def get_database_name():
    config = read_config()
    DBURL = "NO_NAME"

    try:
        DBURL = config['database']['db_name']
    except KeyError:
        terminal_msg(0, "Failed to retrieve the URL of database.")
    return DBURL

def get_conn_str():
    config = read_config()

    try:
        DBURL = config['database']['db_url']
    except KeyError:
        terminal_msg(0, "Failed to retrieve the URL of database.")

    try:
        DBNAME = config['database']['db_name']
    except KeyError:
        terminal_msg(0, "Failed to retrieve database name.")

    try:
        DBUSER = config['database']['db_user']
    except KeyError:
        terminal_msg(0, "Failed to retrieve database user.")

    try:
        DBPWD = config['database']['db_pwd']
    except KeyError:
        terminal_msg(0, "Failed to retrieve database password.")
        
    try:
        DBSCHEMA = config['database']['db_schema']
    except KeyError:
        terminal_msg(0, "Failed to retrieve database schema.")
        
    conn_string = "host='%s' dbname='%s' user='%s' password='%s' options='-c search_path=%s'" % (DBURL, DBNAME, DBUSER, DBPWD, DBSCHEMA)

    return conn_string


def dir_formatting(path):
    '''
    trim the trailing slashes to prevent unexpected interpretion of directory structure
    '''
    while path.endswith('/'):
        path = path[:-1]
    return path


def is_valid_path(path, base_dir):
    '''
    Safe check for whether a directory traversal attempt has been made to ineract with files that does not fall under the base directory.
    '''
    return os.path.realpath(path).startswith(os.path.realpath(base_dir))


def revert_db(prod, vers):
    pass

def set_success_flag(**kwargs):
    filename = os.path.dirname(os.path.abspath(__file__)) + "/../flag_" + time.strftime("%Y-%m-%d-%H-%M-%S", time.gmtime())


def terminal_msg(severity, message):
    '''
    Formats message before displaying to user. Only use this function when it is a user-side / user-caused error.
    For checks of developer-side errors (e.g., misuse of function), raise Exception instead.

    @param
    severity    0 (fatal), 1 (alert), 2 (message)
    message
    '''
    # apply optional logging for fatal (0) and alert (1)
    log = os.path.dirname(os.path.abspath(__file__)) + "/../logs"

    
    if severity == 0:
        print("\n Fatal: " + message)
        sys.exit(-1)
    elif severity == 1:
        print("\n Alert: " + message)
    elif severity == 2:
        print("\n Message: " + message)
    else:
        raise Exception("Invalid severity for terminal_msg(). The severity level must be an integer between 0 to 2.")
