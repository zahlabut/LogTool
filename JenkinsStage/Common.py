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


import os, datetime,subprocess,json,sys,re,requests
import urllib2
import difflib
from urllib2 import urlparse
from string import digits
from requests import Request, Session

def download_file(url, dst_path='.'):
    s = Session()
    req = Request('GET', url)
    prepped = s.prepare_request(req)
    # Merge environment settings into session
    settings = s.merge_environment_settings(prepped.url, {}, None, None, None)
    resp = s.send(prepped, **settings)
    with open(os.path.join(os.path.abspath(dst_path),os.path.basename(url)), 'wb') as f:
        f.write(resp.content)
    return {'Status':resp.status_code,'Content':resp.content}

    # r = requests.get(url,verify=False)
    # with open(os.path.join(os.path.abspath(dst_path),os.path.basename(url)), 'wb') as f:
    #     f.write(r.content)
    # return {'Status':r.status_code}






def empty_file_content(log_file_name):
    f = open(log_file_name, 'w')
    f.write('')
    f.close()
    
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

def exec_command_line_command(command):
    try:
        command_as_list = command.split(' ')
        command_as_list = [item.replace(' ', '') for item in command_as_list if item != '']
        result = subprocess.check_output(command,  shell=True, stderr=subprocess.STDOUT,stdin=True)
        json_output = None
        try:
            json_output = json.loads(result.lower())
        except:
            pass
        return {'ReturnCode': 0, 'CommandOutput': result, 'JsonOutput': json_output}
    except subprocess.CalledProcessError as e:
        if 'wget -r' not in command:
            print_in_color(command,'red')
            print_in_color(e.output, 'red')
        return {'ReturnCode': e.returncode, 'CommandOutput': e.output}

def spec_print(string_list,color=None):
    len_list=[]
    for item in string_list:
        len_list.append(len('### '+item.strip()+' ###'))
    max_len=max(len_list)
    print_in_color('',color)
    print_in_color("#"*max_len,color)
    for item in string_list:
        print_in_color("### "+item.strip()+" "*(max_len-len("### "+item.strip())-4)+" ###",color)
    print_in_color("#"*max_len+'\n',color)

def exit(string):
    print_in_color(string,'red')
    sys.exit(1)

def print_dic(dic):
    for k in list(dic.keys()):
        print('~'*80)
        print(k,' --> ',dic[k])

def check_string_for_spev_chars(string):
    return True if re.match("^[a-zA-Z0-9_]*$", string) else False

def append_to_file(log_file, msg):
    log_file = open(log_file, 'a')
    log_file.write(msg)
    log_file.close()

def check_user_time(start_time):
    match = re.search(r'\d{4}-\d{2}-\d{2}.\d{2}:\d{2}:\d{2}', start_time)  # 2020-04-23 08:52:04
    if match:
        string = match.group()
        string = string[0:10] + ' ' + string[11:]
        date = datetime.datetime.strptime(string, '%Y-%m-%d %H:%M:%S')
        return {'Error': None, 'Line': None, 'Date': str(date)}
    else:
        return {'Error': 'Bad time format!', 'Line': start_time, 'Date':None}
