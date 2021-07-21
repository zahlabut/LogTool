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
import json
import warnings
warnings.simplefilter("ignore", UserWarning)
import datetime
import collections
from string import digits
import re
import shutil
import gzip
def set_default_arg_by_index(index, default):
    try:
        value=sys.argv[index]
        return value.strip()
    except:
        return default

### Parameters ###

range_start=set_default_arg_by_index(1,'2020-04-13 16:26:57')
range_stop=set_default_arg_by_index(2,'2020-04-13 16:27:00')
log_root_dir=set_default_arg_by_index(3,'/home/ashtempl/jopa')
result_file=set_default_arg_by_index(4,'Range.log')
result_dir=set_default_arg_by_index(5,'RangeLogFiles')

result_file=os.path.join(os.path.abspath('.'),result_file)
temp_file='zahlabut.txt'


logs_to_ignore=[]

def exec_command_line_command(command):
    try:
        #result = subprocess.check_output(command, shell=True, encoding='UTF-8')
        result = subprocess.check_output(command, stdin=True, stderr=subprocess.STDOUT, shell=True,encoding='UTF-8')
        json_output = None
        try:
            json_output = json.loads(result.lower())
        except:
            pass
        return {'ReturnCode': 0, 'CommandOutput': result, 'JsonOutput': json_output}
    except subprocess.CalledProcessError as e:
        return {'ReturnCode': e.returncode, 'CommandOutput': e.output}

def get_file_last_line(log, tail_lines='1'):
    command='cat ' + log + ' | tail -' + tail_lines
    if log.endswith('.gz'):
        command=command.replace('cat','zcat')
    try:
        return exec_command_line_command(command)['CommandOutput']
    except Exception as e:
        print (e)
        return ''

def get_file_first_line(log, tail_lines='1'):
    command='cat ' + log + ' | head -' + tail_lines
    if log.endswith('.gz'):
        command=command.replace('cat','zcat')
    try:
        return exec_command_line_command(command)['CommandOutput']
    except Exception as e:
        print (e)
        return ''

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

def collect_log_paths(log_root_path,black_list=logs_to_ignore):
    logs=[]
    if '[' in log_root_path:
        log_root_path=log_root_path.replace('[','').replace(']','').replace(' ','')
        log_root_path=log_root_path.split(',')
    else:
        log_root_path=[log_root_path]
    for path in log_root_path:
        for root, dirs, files in os.walk(path):
            for name in files:
                if '.log' in name or 'var/log/messages' in name:
                    to_add=False
                    file_abs_path=os.path.join(os.path.abspath(root), name)
                    if os.path.getsize(file_abs_path)!=0 and 'LogTool' in file_abs_path:
                        if 'Jenkins_Job_Files' in file_abs_path:
                            to_add = True
                        if 'Zuul_Log_Files' in file_abs_path:
                            to_add=True
                    if os.path.getsize(file_abs_path) != 0 and 'LogTool' not in file_abs_path:
                        to_add = True
                    if to_add==True:
                        logs.append(file_abs_path)
    logs=list(set(logs))
    # Remove all logs that are in black list
    filtered_logs=[]
    for log in logs:
        to_add=True
        for path in black_list:
            if path in log:
                to_add=False
                break
        if to_add==True:
            filtered_logs.append(log)
    if len(filtered_logs)==0:
        sys.exit('Failed - No log files detected in: '+log_root_path)
    return filtered_logs

def empty_file_content(log_file_name):
    f = open(log_file_name, 'w')
    f.write('')
    f.close()

def append_to_file(log_file, msg):
    log_file = open(log_file, 'a')
    log_file.write(msg)

def get_line_date(line):
    try:
        # line=line[0:50]
        now = datetime.datetime.now()
        year = str(now.year)
        match = re.search(r'\d{4}-\d{2}-\d{2}.\d{2}:\d{2}:\d{2}', line)  # 2020-04-23 08:52:04
        if match:
            string = match.group()
            string = string[0:10] + ' ' + string[11:]
            date = datetime.datetime.strptime(string, '%Y-%m-%d %H:%M:%S')
            return {'Error': None, 'Line': None, 'Date': str(date)}
        match = re.search(r'\d{4}/\d{2}/\d{2}.\d{2}:\d{2}:\d{2}', line)  # 2020/04/23 08:52:04
        if match:
            date = datetime.datetime.strptime(match.group(), '%Y/%m/%d %H:%M:%S')
            return {'Error': None, 'Line': None, 'Date': str(date)}
        match = re.search(r'\d{2}\s(...)\s\d{4}\s\d{2}:\d{2}:\d{2}', line)  # 27 Apr 2020 11:37:46
        if match:
            date = datetime.datetime.strptime(match.group().replace('T', ' '), '%d %b %Y %H:%M:%S')
            return {'Error': None, 'Line': None, 'Date': str(date)}
        match = re.search(r'\d{2}/(...)/\d{4}.\d{2}:\d{2}:\d{2}', line)  # 30/Apr/2020:00:00:20
        if match:
            date = datetime.datetime.strptime(match.group().replace('T', ' '), '%d/%b/%Y:%H:%M:%S')
            return {'Error': None, 'Line': None, 'Date': str(date)}
        match = re.search(r'(...)\s\d{2}\s\d{2}:\d{2}:\d{2}', line)  # Oct 29 16:25:47
        if match:
            date = datetime.datetime.strptime(year + ' ' + match.group().replace('T', ' '), '%Y %b %d %H:%M:%S')
            return {'Error': None, 'Line': None, 'Date': str(date)}
        match = re.search(r'(...)-\d{2}\s\d{2}:\d{2}:\d{2}', line)  # Oct-15 13:30:46
        if match:
            date = datetime.datetime.strptime(year + match.group(), '%Y%b-%d %H:%M:%S')
            return {'Error': None, 'Line': None, 'Date': str(date)}
        match = re.search(r'(...)\s\s\d{1}\s\d{2}:\d{2}:\d{2}', line)  # Jul  6 22:19:00
        if match:
            date = datetime.datetime.strptime(year + match.group(), '%Y%b  %d %H:%M:%S')
            return {'Error': None, 'Line': None, 'Date': str(date)}
        if len(line) > 100:
            line = line[0:100] + '...'
        return {'Error': 'Unknown or missing timestamp in line!', 'Line': line.strip(), 'Date': None}
    except Exception as e:
        return {'Error': str(e), 'Line': line.strip(), 'Date': None}

def print_list(lis):
    for l in lis:
        if l!='':
            print(str(l).strip())

def print_dic(dic):
    for k in list(dic.keys()):
        print('~'*80)
        print(k,' --> ',dic[k])

def write_list_of_dict_to_file(fil, lis,msg_start='',msg_delimeter=''):
    append_to_file(fil,msg_start)
    for l in lis:
        append_to_file(fil,msg_delimeter)
        for k in list(l.keys()):
            append_to_file(fil,str(k)+' --> '+str(str(l[k]))+'\n')

def write_list_to_file(fil, list, add_new_line=True):
    for item in list:
        if add_new_line==True:
            append_to_file(fil, '\n'+str(item)+'\n')
        else:
            append_to_file(fil, '\n'+str(item))

def is_single_line_file(log):
    if log.endswith('.gz'):
        result=exec_command_line_command('zcat ' + log + ' | wc -l')['CommandOutput'].strip()
    else:
        result = exec_command_line_command('cat ' + log + ' | wc -l')['CommandOutput'].strip()
    if result=='1':
        return True
    else:
        return False

def get_file_line_index(fil,line):
    return exec_command_line_command("grep -n '"+line+"' "+fil)['CommandOutput'].split(':')[0]

def unique_list(lis):
    return list(collections.OrderedDict.fromkeys(lis).keys())

def get_file_line_index(fil,line):
    return exec_command_line_command("grep -n '"+line+"' "+fil)['CommandOutput'].split(':')[0]

def remove_digits_from_string(s):
    remove_digits = str.maketrans('', '', digits)
    return str(s).translate(remove_digits)

if __name__ == "__main__":
    detected_relevant_logs=[]
    skipped_logs=[]
    if __name__ == "__main__":
        empty_file_content(result_file)
        empty_file_content(temp_file)
        os.makedirs(result_dir,exist_ok=True)
        start_time=time.time()
        logs=collect_log_paths(log_root_dir)
        statistics_list=[]
        for log in logs:
            log_stat_info={'Log':log,'NumberOfLines':0}
            print_in_color(log,'bold')
            # Try to check if there is a known timestamp in last 100 lines
            first_line=get_file_first_line(log,'100')
            last_line=get_file_last_line(log,'100')
            is_known_time_format=False
            # Get first line date
            for line in first_line.splitlines():
                first_line_date=get_line_date(line)
                if first_line_date['Error']==None:
                    is_known_time_format=True
                    break
            # Get last line date
            for line in reversed(last_line.splitlines()):
                last_line_date=get_line_date(line)
                if last_line_date['Error']==None:
                    break
            # Check if log is relevant, basing on time start range
            if is_known_time_format==True:
                if first_line_date['Date'] is None:
                    print_in_color('LogTool was not able to detect "first_line_date"', 'yellow')
                    skipped_logs.append(log)
                    continue
                if last_line_date['Date'] is None:
                    print_in_color('LogTool was not able to detect "last_line_date"', 'yellow')
                    skipped_logs.append(log)
                    continue
                first_line_time=time.strptime(first_line_date['Date'], '%Y-%m-%d %H:%M:%S')
                last_line_time=time.strptime(last_line_date['Date'], '%Y-%m-%d %H:%M:%S')
                range_start_time=time.strptime(range_start, '%Y-%m-%d %H:%M:%S')
                range_stop_time=time.strptime(range_stop,'%Y-%m-%d %H:%M:%S')
                if first_line_time<=range_start_time<=last_line_time:
                    log_to_save = result_dir+log
                    os.makedirs(os.path.dirname(log_to_save), exist_ok=True)
                    log_file_to_save=open(log_to_save,'w')
                    start_found=None
                    detected_relevant_logs.append(log)
                    append_to_file(temp_file,'\n\n\n### '+log+' ###\n')
                    known_lines=[]
                    if log.endswith('.gz'):
                        try:
                            with open(log, 'r') as f:
                                for line in f:
                                    line_date=get_line_date(line)
                                    char_line = remove_digits_from_string(line)
                                    if line_date['Error']==None:
                                       if time.strptime(range_start,'%Y-%m-%d %H:%M:%S')<=time.strptime(line_date['Date'],'%Y-%m-%d %H:%M:%S')<=time.strptime(range_stop,'%Y-%m-%d %H:%M:%S'):
                                            start_found=True
                                            log_file_to_save.write(line)
                                            if char_line not in known_lines:
                                                known_lines.append(char_line)
                                                append_to_file(temp_file,line)
                                       if time.strptime(line_date['Date'],'%Y-%m-%d %H:%M:%S')>time.strptime(range_stop,'%Y-%m-%d %H:%M:%S'):
                                            break
                                    if line_date['Error']!=None and start_found==True:
                                        log_file_to_save.write(line)
                                        if char_line not in known_lines:
                                            known_lines.append(char_line)
                                            append_to_file(temp_file, line)
                        except Exception as e:
                            print_in_color(e,'yellow')
                    else:
                        with open(log, 'r') as f:
                            for line in f:
                                line_date=get_line_date(line)
                                char_line = remove_digits_from_string(line)
                                if line_date['Error']==None:
                                   if time.strptime(range_start,'%Y-%m-%d %H:%M:%S')<=time.strptime(line_date['Date'],'%Y-%m-%d %H:%M:%S')<=time.strptime(range_stop,'%Y-%m-%d %H:%M:%S'):
                                        start_found=True
                                        log_file_to_save.write(line)
                                        if char_line not in known_lines:
                                            known_lines.append(char_line)
                                            append_to_file(temp_file,line)
                                   if time.strptime(line_date['Date'],'%Y-%m-%d %H:%M:%S')>time.strptime(range_stop,'%Y-%m-%d %H:%M:%S'):
                                        break
                                if line_date['Error']!=None and start_found==True:
                                    log_file_to_save.write(line)
                                    if char_line not in known_lines:
                                        known_lines.append(char_line)
                                        append_to_file(temp_file, line)
                    # Save statistics and close file
                    log_stat_info['NumberOfLines']=len(known_lines)
                    statistics_list.append(log_stat_info)
                    log_file_to_save.close()


    not_relevant_lines=['### '+item['Log']+' ###' for item in statistics_list if item['NumberOfLines']==0]
    statistics_list=[item for item in statistics_list if item['NumberOfLines']!=0]
    print_list(statistics_list)
    append_to_file(result_file,'### Statistics: Number of lines per file:')
    write_list_to_file(result_file,statistics_list,False)
    for line in open(temp_file, 'r').readlines():
        if line.strip() not in not_relevant_lines:
            append_to_file(result_file,line)
    os.remove(temp_file)
    exec_command_line_command('gzip '+result_file)
    shutil.make_archive(result_dir, 'zip', result_dir)
    print_in_color('Skipped logs (LogTool was not able to detect timestamps in its content), are:', 'yellow')
    print_list(skipped_logs)
    print('Execution time:'+str(time.time()-start_time))
    print('SUCCESS!!!')