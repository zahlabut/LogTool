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

import os, time, subprocess, json, sys, re, difflib, datetime, shutil, requests
import urllib.request, urllib.error, urllib.parse
from urllib.parse import urlparse
from urllib.parse import urljoin
from string import digits

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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

class MyOutput():
    def __init__(self, logfile):
        self.stdout = sys.stdout
        self.log = open(logfile, 'w')
  
    def write(self, text):
        self.stdout.write(text)
        self.log.write(text)
        #self.log.flush()
  
    def close(self):
        self.stdout.close()
        self.log.close()

def check_ping(ip):
    try:
        if subprocess.check_output(["ping", "-c", "1", ip]):
            return True
    except Exception as e:
        print('Ping to '+ip+' failed with '+str(e))
        return False

class SSH():
    def __init__(self, host, user, password='', key_path=''):
        self.host=host
        self.user=user
        self.password=password
        self.key_path=key_path

    def ssh_connect_password(self):
        try:
            self.client = paramiko.SSHClient()
            self.client.load_system_host_keys()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(self.host, username=self.user, password=self.password)
            return {'Status':True,'Host':self.host}
        except Exception as e:
            print_in_color(str(e),'red')
            return {'Status':False,'Exception':e,'Host':self.host}

    def ssh_connect_key(self):
        try:
            self.client = paramiko.SSHClient()
            self.client.load_system_host_keys()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(self.host, username=self.user, key_filename=self.key_path)
            return {'Status':True,'Host':self.host}
        except Exception as e:
            print_in_color(str(e), 'red')
            return {'Status':False,'Exception':e,'Host':self.host}

    def ssh_command(self, command):
        stdin,stdout,stderr=self.client.exec_command(command)
        #stdin.close()
        self.output=''
        self.stderr=''
        for line in stdout.read().decode().splitlines():
            self.output+=line+'\n'
        for line in stderr.read().decode().splitlines():
            self.stderr+=line+'\n'
        result= {'Stdout':self.output, 'Stderr':self.stderr}
        if len(result['Stderr'])!=0 and 'warning' in str(result['Stderr']).lower():
            print_in_color(result['Stderr'],'yellow')
        else:
            print_in_color(result['Stderr'], 'red')
        return result

    def ssh_command_only(self, command):
        self.stdin,self.stdout,self.stderr=self.client.exec_command(command)
        return {'Stdout':self.stdout.read().decode(),'Stderr':self.stderr.read().decode(),'Host':self.host}

    def scp_upload(self, src_abs_path, dst_abs_path):
        try:
            file_size=os.path.getsize(src_abs_path)
            ftp = self.client.open_sftp()
            t1=time.time()
            ftp.put(src_abs_path,dst_abs_path)
            t2=time.time()
            return {'Status':True,'AverageBW':file_size/(t2-t1),'ExecutionTime':str(round(t2-t1,2))+'[sec]','Host':self.host}
        except  Exception as e:
            print_in_color(str(e), 'red')
            return {'Status':False,'Exception':e,'Host':self.host}

    def scp_download(self,remote_abs_path,local_abs_path):
        try:
            ftp=self.client.open_sftp()
            t1 = time.time()
            ftp.get(remote_abs_path, local_abs_path)
            t2 = time.time()
            file_size=os.path.getsize(local_abs_path)
            return {'Status': True,'AverageBW':file_size/(t2-t1),'ExecutionTime':str(round(t2-t1,2))+'[sec]','Host':self.host}
        except  Exception as e:
            print_in_color(str(e), 'red')
            return {'Status': False, 'Exception': e,'Host':self.host}

    def ssh_close(self):
        self.client.close()

def exec_command_line_command(command):
    try:
        command_as_list = command.split(' ')
        command_as_list = [item.replace(' ', '') for item in command_as_list if item != '']
        result = subprocess.check_output(command, shell=True, encoding='UTF-8', stderr=subprocess.STDOUT, stdin=True)
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

def choose_option_from_list(list_object, msg):
    print('')
    try:
        if (len(list_object)==0):
            print("Nothing to choose :( ")
            print("Execution will stop!")
            time.sleep(5)
            exit("Connot continue execution!!!")
            sys.exit(1)
        print(msg)
        counter=1
        for item in list_object:
            print(str(counter)+') - '+item)
            counter=counter+1
        choosed_option=input("Choose your option:")
        if choosed_option=='Demo':
            return [True, 'Demo']
        while (int(choosed_option)<0 or int(choosed_option)> len(list_object)):
            print("No such option - ", choosed_option)
            choosed_option=input("Choose your option:")
        print_in_color("Option is: '"+list_object[int(choosed_option)-1]+"'"+'\n','bold')
        return [True,list_object[int(choosed_option)-1]]
    except Exception as e:
        print('*** No such option!!!***', e)
        return[False, str(e)]

def exit(string):
    print_in_color(string,'red')
    sys.exit(1)

def print_dic(dic):
    for k in list(dic.keys()):
        print('~'*80)
        print(k,' --> ',dic[k])

def check_string_for_spev_chars(string):
    return True if re.match("^[a-zA-Z0-9_]*$", string) else False

def download_jenkins_job_logs(node_names_list,url):
    response = urllib.request.urlopen(url)
    html= response.read(url)

def unique_list_by_fuzzy(lis,fuzzy):
    unique_messages=[]
    for item in lis:
        to_add = True
        for key in unique_messages:
            if similar(key, str(item)) >= fuzzy:
                to_add = False
                break
        if to_add == True:
            unique_messages.append(str(item))
    return unique_messages

def remove_digits_from_string(s):
    return str(s).translate(None, digits)

def similar(a, b):
    return difflib.SequenceMatcher(None,remove_digits_from_string(a), remove_digits_from_string(b)).ratio()

def remove_digits_from_string(s):
    remove_digits = str.maketrans('', '', digits)
    return str(s).translate(remove_digits)

def choose_time(user_time, host):
    start_time_options = ['10 Minutes ago', '30 Minutes ago', 'One Hour ago', 'Three Hours ago', 'Ten Hours ago',
                          'One Day ago', 'Custom']
    start_time_option = choose_option_from_list(start_time_options, 'Please choose your "since time": ')
    if start_time_option[1] == 'Custom':
        print_in_color('Current date on '+host+' is: ' + user_time, 'blue')
        print_in_color('Use the same date format as in previous output', 'blue')
        start_time = input('And enter your "since time" to extract log messages: ')
        check_time = check_user_time(start_time)
        if check_time['Error'] != None:
            print_in_color(check_time,'yellow')
            print('Please retry:')
            start_time=choose_time(user_time, host)
    if start_time_option[1] == '10 Minutes ago':
        start_time = datetime.datetime.strptime(user_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(minutes=10)
    if start_time_option[1] == '30 Minutes ago':
        start_time = datetime.datetime.strptime(user_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(minutes=30)
    if start_time_option[1] == 'One Hour ago':
        start_time = datetime.datetime.strptime(user_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(hours=1)
    if start_time_option[1] == 'Three Hours ago':
        start_time = datetime.datetime.strptime(user_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(hours=3)
    if start_time_option[1] == 'Ten Hours ago':
        start_time = datetime.datetime.strptime(user_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(hours=10)
    if start_time_option[1] == 'One Day ago':
        start_time = datetime.datetime.strptime(user_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(hours=24)
    if start_time_option[1] == 'Two Days ago':
        start_time = datetime.datetime.strptime(user_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(hours=48)
    return str(start_time)

def check_user_time(start_time):
    match = re.search(r'\d{4}-\d{2}-\d{2}.\d{2}:\d{2}:\d{2}', start_time)  # 2020-04-23 08:52:04
    if match:
        string = match.group()
        string = string[0:10] + ' ' + string[11:]
        date = datetime.datetime.strptime(string, '%Y-%m-%d %H:%M:%S')
        return {'Error': None, 'Line': None, 'Date': str(date)}
    else:
        return {'Error': 'Bad time format!', 'Line': start_time, 'Date':None}


def create_dir(dir_dst_path):
    if os.path.isdir(dir_dst_path):
        shutil.rmtree(dir_dst_path)
    os.mkdir(dir_dst_path)


def download_file(url, dst_path='.',extension='.log'):
    try:
        r = requests.get(url,verify=False)
        if os.path.basename(url)!='':
            file_path = os.path.join(os.path.abspath(dst_path), os.path.basename(url))
            with open(file_path, 'wb') as f:
                f.write(r.content)
        else:
            url=url.strip('/')+extension
            file_path=os.path.join(os.path.abspath(dst_path),os.path.basename(url))
            with open(file_path, 'wb') as f:
                f.write(r.content)
        return {'Status':r.status_code,'Content':r.content,'FilePath':file_path}
    except Exception as e:
        print_in_color('Failed to download: \n'+url+'\n'+str(e),'yellow')
        return {'Status': None, 'Content':None, 'FilePath':None}
