#!/usr/bin/python
import subprocess,time,os,sys
import itertools
import json
import gzip

start_time=time.time()


## Log path ##
try:
    log_root_dir=sys.argv[1].strip()
except:
    log_root_dir='/var/log/containers'
## String for Grep##
try:
    string_for_grep=sys.argv[2].strip()
except:
    string_for_grep='ironic'
## Save output to file ##
try:
    output_greps_file=sys.argv[3].strip()
except:
    output_greps_file='All_Greps.log'

def print_in_color(string,color_or_format=None):
    string=str(string)
    class bcolors:
        HEADER = '\033[95m'
        OKBLUE = '\033[94m'
        OKGREEN = '\033[92m'
        WARNING = '\033[93m'
        FAIL = '\033[91m'
        ENDC = '\033[0m'
        BOLD = '\033[1m'
        UNDERLINE = '\033[4m'
    if color_or_format == 'green':
        print(bcolors.OKGREEN + string + bcolors.ENDC)
    elif color_or_format =='red':
        print(bcolors.FAIL + string + bcolors.ENDC)
    elif color_or_format =='yellow':
        print(bcolors.WARNING + string + bcolors.ENDC)
    elif color_or_format =='blue':
        print(bcolors.OKBLUE + string + bcolors.ENDC)
    elif color_or_format =='bold':
        print(bcolors.BOLD + string + bcolors.ENDC)
    else:
        print(string)

def collect_log_paths(log_root_path):
    logs=[]
    for root, dirs, files in os.walk(log_root_path):
        for name in files:
            if '.log' in name:
                file_abs_path=os.path.join(os.path.abspath(root), name)
                if os.path.getsize(file_abs_path)!=0:
                    logs.append(file_abs_path)
    logs=list(set(logs))
    return logs

def exec_command_line_command(command):
    try:
        command_as_list = command.split(' ')
        command_as_list = [item.replace(' ', '') for item in command_as_list if item != '']
        result = subprocess.check_output(command, shell=True, encoding='UTF-8')
        json_output = None
        try:
            json_output = json.loads(result.lower())
        except:
            pass
        return {'ReturnCode': 0, 'CommandOutput': result, 'JsonOutput': json_output}
    except subprocess.CalledProcessError as e:
        return {'ReturnCode': e.returncode, 'CommandOutput': str(e)}

def empty_file_content(log_file_name):
    f = open(log_file_name, 'w')
    f.write('')
    f.close()

def append_to_file(log_file, msg):
    log_file = open(log_file, 'a')
    log_file.write(msg)

if __name__ == "__main__":
    empty_file_content(output_greps_file)
    logs=collect_log_paths(log_root_dir)
    for log in logs:
        print('--> '+log)
        if log.endswith('.gz'):
            command = "zgrep -in '"+string_for_grep+"' "+log
        else:
            command = "grep -in '"+string_for_grep+"' "+log
        print (command)
        com_result=exec_command_line_command(command)
        if com_result['ReturnCode']==0:
            append_to_file(output_greps_file,'\n'+'#'*20+log+'#'*20+'\n'+com_result['CommandOutput'])
