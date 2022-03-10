#!/usr/bin/python3

# Copyright 2018 Arkady Shtempler.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import subprocess,time,os,sys
import shutil
import json
import gzip

start_time=time.time()
not_supported_logs=[]


## Grep by time ###
try:
    grep=sys.argv[1].strip()
except:
    grep='2018-11-03 00:04:00'
## Log path ##
try:
    log_root_dir=sys.argv[2].strip()
except:
    log_root_dir='/var/log/containers'
# Result directory
try:
    result_directory=sys.argv[3]
except:
    result_directory='Overcloud_Relevant_Logs'


def collect_log_paths(log_root_path):
    logs=[]
    for root, dirs, files in os.walk(log_root_path):
        for name in files:
            if '.log' in name:
                file_abs_path=os.path.join(os.path.abspath(root), name)
                if os.path.getsize(file_abs_path)!=0:
                    to_add = True
                    for item in not_supported_logs:
                        if item in file_abs_path:
                            to_add = False
                    if to_add==True:
                        logs.append(file_abs_path)
    logs=list(set(logs))
    return logs

def empty_file_content(log_file_name):
    f = open(log_file_name, 'w')
    f.write('')
    f.close()

def append_to_file(log_file, msg):
    log_file = open(log_file, 'a')
    log_file.write(msg)

def print_list(lis):
    for l in lis:
        print(str(l).strip())

def print_dic(dic):
    for k in list(dic.keys()):
        print('~'*80)
        print(k,' --> ',dic[k])

def zip_file(file):
    with gzip.open(file+'.zip', 'wb') as f:
        f.write(open(file,'r').read())

def print_in_color(string,color_or_format=None):
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

(command):
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

def get_file_last_modified(file_path):
    return exec_command_line_command('stat -c "%y" '+file_path)['CommandOutput'].split('.')[0]

if __name__ == "__main__":
    # Create result Directory #
    if result_directory in os.listdir('.'):
        shutil.rmtree(result_directory)
    shutil.copytree(log_root_dir,result_directory)
    # Remove not relevant logs #
    logs=collect_log_paths(log_root_dir)
    for log in logs:
        if time.strptime(get_file_last_modified(log),'%Y-%m-%d %H:%M:%S')<time.strptime(grep, '%Y-%m-%d %H:%M:%S'):
            local_path=log.replace(log_root_dir,os.path.abspath(result_directory))
            os.remove(local_path)
        else:
            print('OK --> '+os.path.basename(log) + ' - is relevant!')
    # Zip the result dir #
    com_result=exec_command_line_command('zip -r '+result_directory+'.zip '+result_directory)
    if com_result['ReturnCode']==0:
        shutil.rmtree(result_directory)
        print_in_color('Size of: '+result_directory+'.zip '+'is: '+str(os.path.getsize(result_directory+'.zip')/1024/1024.0 )+'[MB]','bold')
        print('SUCCESS!!!'*5)