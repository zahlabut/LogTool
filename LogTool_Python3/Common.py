import os
import paramiko
import time
import subprocess
import json
import sys
import re
import urllib.request, urllib.error, urllib.parse
from urllib.parse import urlparse
from urllib.parse import urljoin


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
            return {'Status':True}
        except Exception as e:
            print_in_color(str(e),'red')
            return {'Status':False,'Exception':e}

    def ssh_connect_key(self):
        try:
            self.client = paramiko.SSHClient()
            self.client.load_system_host_keys()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(self.host, username=self.user, key_filename=self.key_path)
            return {'Status':True}
        except Exception as e:
            print_in_color(str(e), 'red')
            return {'Status':False,'Exception':e}

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
        return {'Stdout':self.stdout.read(),'Stderr':self.stderr.read().decode()}

    def scp_upload(self, src_abs_path, dst_abs_path):
        try:
            file_size=os.path.getsize(src_abs_path)
            ftp = self.client.open_sftp()
            t1=time.time()
            ftp.put(src_abs_path,dst_abs_path)
            t2=time.time()
            return {'Status':True,'AverageBW':file_size/(t2-t1),'ExecutionTime':t2-t1}
        except  Exception as e:
            print_in_color(str(e), 'red')
            return {'Status':False,'Exception':e}

    def scp_download(self,remote_abs_path,local_abs_path):
        try:
            ftp=self.client.open_sftp()
            t1 = time.time()
            ftp.get(remote_abs_path, local_abs_path)
            t2 = time.time()
            file_size=os.path.getsize(local_abs_path)
            return {'Status': True,'AverageBW':file_size/(t2-t1),'ExecutionTime':t2-t1}
        except  Exception as e:
            print_in_color(str(e), 'red')
            return {'Status': False, 'Exception': e}

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

def check_time(time_string):
    try:
        t=time.strptime(time_string, '%Y-%m-%d %H:%M:%S')
        return True
    except:
        return False

def download_jenkins_job_logs(node_names_list,url):
    response = urllib.request.urlopen(url)
    html= response.read(url)



