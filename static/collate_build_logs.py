from argparse import ArgumentParser
from pathlib import Path
from pprint import pprint

def collate_output(directory):
    p = Path(directory)
    if not p.exists() or not p.is_dir():
        print("Directory:", directory, "does not exist")
        return None

    holder = {}
    for f in p.iterdir():
        if not f.is_file():
            continue
        with f.open("r") as input_file:
            object_name = ""
            preferred_linkage = ""
            object_components = []
            for line in input_file:
                if not line.startswith("\t"):
                    object_name = line.strip()
                    if not line.endswith(".o"):
                        #Ignore .o files since they may be repeated (main.o for example)
                        holder[object_name] = {"preferred linkage": preferred_linkage,
                                               "object_components": object_components,
                                               "rpm_name":f.name}
                elif "linkage preferred:" in line:
                    preferred_linkage = line.split()[:-1]
                elif "linked libraries" in line:
                    continue
                else:
                    #This is a component that we've identified
                    #Add it to the list, but do a little processing
                    object_component = line.strip()
                    object_components.append(object_component)
    return holder

def process_output(data, output_file):
    o = Path(output_file)
    o.open("w")
    for name, value in data.items():
        if not name:
            pprint(name)
            pprint(value)
        linkage_preference = value["preferred linkage"]
        rpm_name = value["rpm_name"]
        print("\t", rpm_name)
        for obj in value["object_components"]:
            if obj.endswith(".o"):
                #We're going to ignore object files
                continue
            home_rpm = "unknown"
            if (obj.endswith(".a") or obj.endswith(".so")):
                try:
                    home_rpm = data[obj]["rpm_name"]
                except:
                    pass
            elif(obj.startswith("lib")):
                #We have a library, but don't know the linkage type
                #Let's guess based on the stated linkage preference
                if "dynamic" in linkage_preference:
                    preferred = ".so"
                    preferred2 = ".a"
                else:
                    preferred = ".a"
                    preferred2 = ".so"

                try:
                    #print("object is", obj+preferred)
                    home_rpm = data[obj+preferred]["rpm_name"]
                except:
                    try:
                        #print("object is", obj+preferred2)
                        home_rpm = data[obj+preferred2]["rpm_name"]
                    except:
                        pass
            print("\t", obj)
            print("\t\t", home_rpm)
                    
if __name__ == "__main__":
    p = ArgumentParser()

    p.add_argument("-d", "--directory", type=str,
                   help= "A directory of build log files to examine.")
    p.add_argument("-f", "--output_file", type=str, default="./collated_output",
                   help="A directory to place the output, if none is given <cwd>/output is created.")
    p.add_argument("-k", "--print_keys", action="store_true",
                   help="Print the object keys to stdout.")
    args = p.parse_args()

    result = collate_output(args.directory)
    if args.print_keys:
        pprint(list(result.keys()))
    else:
        process_output(result, args.output_file)
