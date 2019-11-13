#!/usr/bin/env python3
"""
A collection of constant strings for column names, architectures, etc.
"""
# rpm_db_builder constants
SEPARATOR = "*****"
D_SEPARATOR = ".*****."
FPATH = "filepath"
D_X86_64 = ".x86_64."
D_I686 = ".i686."
D_NOARCH = ".noarch."
D_PPC = ".ppc."


# Database constants
## Product table columns
PRODUCTS = "products"
PROD_ID = "prod_id"
PROD = "product"
## Version table columns
VERSIONS = "versions"
VERS_ID = "vers_id"
VERS = "version"
## RPM table columns / rpm_db_builder constants
RPMS = "rpms"
RPM_ID = "rpm_id"
RPM = "rpm"
RELEASE = "release"
RPM_V = "rpm_version"
X86_64 = "x86_64"
I686 = "i686"
NOARCH = "noarch"
PPC = "ppc"
OTHERARCH = "other_arch"
## Exec table columns
EXECS = "execs"
EXEC_ID = "exec_id"
EXEC = "exec"
## Alias table columns
ALIASES = "aliases"
ALIAS_ID = "alias_id"
ALIAS = "alias"
## Rpath table columns
RPATHS = "rpaths"
RPATH_ID = "rpath_id"
RPATH = "rpath"
## Dependency table columns
DEPENDENCIES = "deps"
DEP_ID = "dep_id"
DEP = "dep"
STATIC = "static"
## Resolved dependency join table columns
R_DEPS_EXECS = "resolved_deps_execs"
DEP_ID = "dep_id"
R_EXEC_ID = "r_exec_id"
## Function table columns
DECL_FUNCS = "decl_funcs"
DECL_ID = "func_id"
FUNC = "func"
## Defined function table columns
DEF_FUNCS = "def_funcs"
DEF_ID = "def_func_id"
BIND = "binding"
## At table columns
AT_VERSIONS = "at_versions"
AT_ID = "at_id"
AT = "at"
## Callee table columns
CALLEE_FUNCS = "callee_funcs"
CALLEE_ID = "callee_func_id"
C_FUNC = "callee_func"
