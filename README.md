# Execview database builder

A repository for execview database creation.


## Installation

1. Make sure you have access to the Execview database builder repo and clone it.
```
git clone git@github.com:DanielOjalvo/execview.git
```

2. Copy *config_template.conf* and rename it **config.conf** under the same dir (library/), fill in the required fields following the instructions in *config_template.conf*.

### Prerequisite

Postgres database. Database architectures can be built automatically by running the *create_tables.py* script under the root directory of the repo.

### Requirements
Required utilities and versions:
(Regarding versions: These are the ones used during development. Other versions may work, but YMMV)
```
GNU readelf version 2.20.51.0.2-5.47.el6_9.1
GNU objdump version 2.20.51.0.2-5.47.el6_9.1
GNU c++filt version 2.20.51.0.2-5.47.el6_9.1
Psycopg2 version '2.7.4 (dt dec pq3 ext lo64)'
Python3
```

### Quickstart
    1. Create ~/rpm-dir/ in your home directory.
    2. python3 dynamic/iso_parser.py -i example_iso/CentOS-7-x86_64-Minimal-1908.iso -r ~/rpm-dir/
    3. 

### Manual

1. Run the wrapper script dynamic_parser.py under dynamic/ to retrieve and process dynamic dependencies from ISOs.

2. Run the wrapper script static_parser.py under static/ to extract static dependencies from build logs.

3. Run dependency_resolver.py under the root directory of repo to resolve dependencies to executables.

**Note:** The scripts have to be run in the designated order. For detailed usage and options, please refer to them with -h switch.


## Data Sources

### Dynamic dependencies
ISO files which install using rpms (like Centos-flavored Linux versions) are the ISO files that are currently supported.
Executable files in the ELF format are what are supported for examination at this time.

### Static dependencies
This determines static dependencies in cases where the executable statically links another library. Generally speaking,
    the use case is to examine the build logs generated by Makefile output is what's examined with some support for libtools.

## Extra Information and a code tour
```
rpm_dissector/
	__init__.py
		- Empty this is just to make the module importable elsewhere
	README
		- Information on required libraries/tools to have
	create_tables.py
		- A simple script to create a database schema on your favorite postgres server for experimentation
	assemblyparser.py
		- Takes as input the output from running "objdump -d <your executable>"
		- Then outputs information about assembly code such as, who's calling what, etc.
		- Internally, it's a collection of classes referring to different sections of code
		- It starts at AssemblyRaw (the pure text file)
		- AssemblySection (breaks down sections with executable code)
		- AssemblyFunction (breaks down functions in a section)
		- AssemblyInstruction (breaks down functions into assembly code and function calls)
		- Information about the actual instructions is gleaned using regular expressions.
		- Currently, it's only examining call functions, but...
		- There's nothing stopping us from examining other instructions for future uses
	iso_parser.py
		- Not particularly interesting, breaks down an iso to extract rpms that we send somewhere
	rpm_db_print.py
		- A helper file to organize an indefinite number of JSON blobs into one big blob.
		- The collections of JSON blobs can be split up into files of a (roughly) specific size
	rpm_provides_generator.py
		- This was one of the tools used to query the collection of JSON blobs
		- This is done by importing potentially a large number of files then doing hash searches
		- This is slow and hasn't been used in a while
	rpm_binary_usage.py
		- This was a similar tool to rpm_provides_generator
		- It's can be used to search for dependent .so files and what rpms they reside in
		- This is slow and hasn't been used in a while
	rpm_db_search.py
		- This was a similar tool to rpm_provides_generator
		- This is slow and hasn't been used in a while
	rpm_db_map_maker.py
		- Something to do with finding linked objects for executables
	rpm_db_processor.py
		- Yet another JSON db parsing tool...
	rpm_db_builder.py
		- This file actually builds the JSON database which gets uploaded and into Dynamo
		- While processing, this will work in two directory trees, a worker directory tree and an output one
		- The program works by digging into a directory, finding ELF files, and processing them into JSON blobs.
		- At a high level, this program works by creating one process that writes the JSON blobs and worker processes to make them
		- The writer process will create 2 queues (q_output and q_files) and send references to the processes it spawns
		- Each worker process will be given its own directory in the worker directory tree
		- The worker process will then gather data by extracting an rpm into that worker directory and examining the ELF files within it
		- After completing that process, the worker process will place it's output as a dict onto the shared queue.
		- The dict will have a single key which is the rpm.
		- After completing this, the worker process will pull another rpm filename from q_files and repeat until the queue is empty
		- The writer process simply grabs from q_output and prints it into a file using DBPrinter (from rpm_db_print.py)
		- The writer will do this in a loop with an exponential backoff (doubling the amount of time waited) to prevent unnecessary querying.
	exec_db_builder.py
		- Like rpm_db_builder, but is applied to executables in a directory.
	rpm_uploader.py
		- This will take the json files created through rpm_db_builder (and exec_db_builder) and upload them
		- This will do so by breaking down the JSON files (in an expected format) and constructing sql insert calls
		- The insert calls are hidden behind insert_row and return the public key of the row created.
		- The query calls (for existence) are hidden behind insert_row.
		- For insert_row, the value tuple will contain the values to be added.
	rpm_db_function_finder.py
		- Queries through a json db to find where a function is defined when an undefined symbol references it
	rpm_binary_usage.py
		- Similar query function on a json database to find the binaries required by an RPM.
```

## Contributors
The project is mainly contributed by the following developers:
Daniel Ojalvo (@ojalvo)
Illestar Wu (@iwu)