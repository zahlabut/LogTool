#!/usr/bin/python2

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
import itertools
import json
import warnings
warnings.simplefilter("ignore", UserWarning)
import difflib
import datetime
import operator
import collections
from string import digits
import re

def set_default_arg_by_index(index, default):
    try:
        value=sys.argv[index]
        return value.strip()
    except:
        return default

### Parameters ###
fuzzy_match = 0.55
time_grep=set_default_arg_by_index(1,'2018-01-01 00:00:00') # Grep by time
log_root_dir=set_default_arg_by_index(2,'/var/log') # Log path #
string_for_grep=set_default_arg_by_index(3,' ERROR ') # String for Grep
result_file=set_default_arg_by_index(4,'All_Greps.log') # Result file
result_file=os.path.join(os.path.abspath('.'),result_file)
save_raw_data=set_default_arg_by_index(5,'yes') # Save raw data messages
operation_mode=set_default_arg_by_index(6,'None') # Operation mode
to_analyze_osp_logs_only=set_default_arg_by_index(7,'all_logs')#'osp_logs_only'
magic_words=['error','traceback','stderr','failed','critical','fatal',"\|err\|",'trace','http error', 'failure'] # Used to cut huge size lines
# String to ignore for Not Standard Log files
ignore_strings=['completed with no errors','program: Errors behavior:',
                    'No error reported.','--exit-command-arg error','Use errors="ignore" instead of skip.',
                    'Errors:None','errors, 0','errlog_type error ','errorlevel = ','ERROR %(name)s','Total errors: 0',
                '0 errors,','python-traceback2-','"Error": ""','perl-Errno-','libgpg-error-','libcom_err-',
                '= CRITICAL ','"Error": "",','stderr F','fatal_exception_format_errors','failed=0   ']

logs_to_ignore=['/var/lib/containers/storage/overlay'] #These logs won't be analysed

python_exceptions=['StopIteration','StopAsyncIteration','ArithmeticError','FloatingPointError',
                   'OverflowError','ZeroDivisionError','AssertionError','AttributeError','BufferError',
                   'EOFError','ImportError','ModuleNotFoundError','LookupError','IndexError','KeyError',
                   'MemoryError','NameError','UnboundLocalError','OSError','BlockingIOError',
                   'ChildProcessError','ConnectionError','BrokenPipeError','ConnectionAbortedError',
                   'ConnectionRefusedError','ConnectionResetError','FileExistsError','FileNotFoundError',
                   'InterruptedError','IsADirectoryError','NotADirectoryError','PermissionError',
                   'ProcessLookupError','TimeoutError','ReferenceError','RuntimeError','NotImplementedError',
                   'RecursionError','SyntaxError','IndentationError','TabError','SystemError','TypeError',
                   'ValueError','UnicodeError','UnicodeDecodeError','UnicodeEncodeError','UnicodeTranslateError']

# These logs are standard (contains proper debug level + timestamp),
# but sometimes messages that supposed to be logged as ERROR are being logged as INFO for example,
# so that is why LogTool will analyze such logs including "magic_strings" without line limitation
# (Debig lebel is in first 60 characters)
analyze_log_as_not_standard=['heat_api_cfn.log', 'ansible.log', 'overcloud_deployment','install-undercloud']


def remove_digits_from_string(s):
    return str(s).translate(None, digits)

def exec_command_line_command(command):
    try:
        result = subprocess.check_output(command, stdin=True, stderr=subprocess.STDOUT, shell=True)
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

def similar(a, b):
    return difflib.SequenceMatcher(None,remove_digits_from_string(a), remove_digits_from_string(b)).ratio()

def to_ranges(iterable):
    iterable = sorted(set(iterable))
    for key, group in itertools.groupby(enumerate(iterable), lambda t: t[1] - t[0]):
        group = list(group)
        yield group[0][1], group[-1][1]

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
                if operation_mode == 'Analyze Gerrit(Zuul) failed gate logs':
                    file_abs_path = os.path.join(os.path.abspath(root), name)
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
    # try:
    #line=line[0:50]
    now = datetime.datetime.now()
    year=str(now.year)
    match = re.search(r'\d{4}-\d{2}-\d{2}.\d{2}:\d{2}:\d{2}', line)#2020-04-23 08:52:04
    if match:
        string=match.group()
        string = string[0:10]+' '+string[11:]
        date=datetime.datetime.strptime(string, '%Y-%m-%d %H:%M:%S')
        return {'Error': None, 'Line': None, 'Date': str(date)}
    match = re.search(r'\d{2}\s(...)\s\d{4}\s\d{2}:\d{2}:\d{2}', line)#27 Apr 2020 11:37:46
    if match:
        date=datetime.datetime.strptime(match.group().replace('T',' '), '%d %b %Y %H:%M:%S')
        return {'Error': None, 'Line': None, 'Date': str(date)}
    match = re.search(r'\d{2}/(...)/\d{4}.\d{2}:\d{2}:\d{2}', line)#30/Apr/2020:00:00:20
    if match:
        date=datetime.datetime.strptime(match.group().replace('T',' '), '%d/%b/%Y:%H:%M:%S')
        return {'Error': None, 'Line': None, 'Date': str(date)}
    match = re.search(r'(...)\s\d{2}\s\d{2}:\d{2}:\d{2}', line) #Oct 29 16:25:47
    if match:
        date=datetime.datetime.strptime(year+' '+match.group().replace('T',' '), '%Y %b %d %H:%M:%S')
        return {'Error': None, 'Line': None, 'Date': str(date)}
    match = re.search(r'(...)-\d{2}\s\d{2}:\d{2}:\d{2}', line) #Oct-29 16:25:51
    if match:
        date=datetime.datetime.strptime(year+' '+match.group().replace('T',' '), '%Y %b-%d %H:%M:%S')
        return {'Error': None, 'Line': None, 'Date': str(date)}
    if len(line)>100:
        line=line[0:100]+'...'
    return {'Error': 'Unknown or missing timestamp in line!', 'Line': line.strip(), 'Date':None}

def analyze_log(log, string, time_grep, last_line_date):
    grep_file='zahlabut.txt'
    strings=[]
    third_lines=[]
    LogDataDic={'Log':log, 'AnalyzedBlocks':[],'TotalNumberOfErrors':0}
    time_grep=time.strptime(time_grep, '%Y-%m-%d %H:%M:%S')
    last_line_date=time.strptime(last_line_date, '%Y-%m-%d %H:%M:%S')
    existing_messages = []
    # Let's check if log has standard DEBUG level
    is_standard_log=False
    last_ten_lines=get_file_last_line(log,'10')
    last_ten_lines=[line[0:100] for line in last_ten_lines.splitlines()]
    for level in ['ERROR','CRITICAL','FATAL','TRACE','|ERR|','DEBUG','INFO','WARN']:
        if level in str(last_ten_lines):
            is_standard_log=True
            break
    # Sorry, but this block will change the "is_standard_log" to False,
    # once by default log is listed in "analyze_log_as_not_standard"
    for item in analyze_log_as_not_standard:
        if item in log:
            is_standard_log=False
            break
    if os.path.exists(grep_file):
        os.remove(grep_file)
    command = ''
    if string=='WARN':
        basic_strings=['WARNING',string]
        strings=basic_strings
    if 'ERROR' in string:
        basic_strings=[' ERROR',' CRITICAL',' FATAL',' TRACE','|ERR|','Traceback ',' STDERR', ' FAILED']
        strings=basic_strings
    if is_standard_log==False:
        strings = python_exceptions+[' ' + item for item in magic_words]
        for item in strings:
            command+="grep -B2 -A7 -in '"+item+"' " + log + " >> "+grep_file+";echo -e '--' >> "+grep_file+';'
    if is_standard_log==True:
        for item in strings+python_exceptions:
            command+="grep -B2 -A7 -in '"+item+"' " +log+ " >> "+grep_file+";echo -e '--' >> "+grep_file+';'
    if log.endswith('.gz'):
        command.replace('grep','zgrep')
    exec_command_line_command(command)
    if os.path.exists(grep_file) and os.path.getsize(grep_file)!=0:
        temp_data = open(grep_file, 'r').read()
        if '--\n' in temp_data:
            list_of_blocks = temp_data.split('--\n')
        else:
            list_of_blocks = [temp_data]
    else:  # zahlabut.txt is empty
        list_of_blocks=[]
    list_of_blocks=[block for block in list_of_blocks if len(block)>=1] #Ignore empty blocks
    # Try to get block date
    last_parsed_date=last_line_date
    for block in list_of_blocks:
        block_date=get_line_date(block)
        if block_date['Error']==None:
            date=time.strptime(block_date['Date'], '%Y-%m-%d %H:%M:%S')
        else:
            print_in_color('Failed to get block date\n: '+block_date['Line'],'yellow')
            print('Last known parsed date was: '+str(last_parsed_date))
            date=last_parsed_date
            block="*** LogTool --> this block is missing timestamp, therefore could be irrelevant to your" \
                  " time range! ***\n"+block
        if date>time_grep:
            # Create list of third lines, do not analyze the same blocks again and again
            block_lines=block.splitlines()
            if len(block_lines)>=3:
                third_line=block_lines[2]
                if len(third_line) > 1000:
                    third_line = third_line[0:1000]
                third_line=remove_digits_from_string(third_line)
            else:
                third_line=block_lines[0]
                if len(third_line) > 1000:
                    third_line = third_line[0:1000]
                third_line=remove_digits_from_string(third_line)
            # Block is relevant only when the debug level or python standard exeption is in the first 60 characters in THIRD LINE (no digits in it)
            relevant_block=False
            if is_standard_log==True:
                cut_line = third_line[0:60].lower()
                legal_debug_strings = strings
                legal_debug_strings.append('warn')
                for item in legal_debug_strings+python_exceptions:
                    if item.lower() in cut_line.lower():
                        relevant_block=True
                        break
            if is_standard_log==False:
                relevant_block=True
            if relevant_block==True:
                LogDataDic['TotalNumberOfErrors'] += 1
                if third_line not in third_lines:
                    third_lines.append(third_line)
                    block=cut_huge_block(block)
                    if block!=None:
                        block_lines=block.splitlines()
                    else:
                        block_lines=[]
                else:
                    continue
                # Check fuzzy match and count matches #
                to_add = True
                is_trace = False
                if 'Traceback (most recent call last)' in str(block_lines):
                    is_trace = True
                block_size = len(block_lines)
                for key in existing_messages:
                    if similar(key[1], str(block_lines)) >=fuzzy_match:
                        to_add = False
                        messages_index = existing_messages.index(key)
                        counter = existing_messages[messages_index][0]
                        message = existing_messages[messages_index][1]
                        existing_messages[messages_index] = [counter + 1, message, is_trace, block_size]
                        break
                if to_add == True and block_lines!=[]:
                    if to_add == True and block_lines != []:
                        existing_messages.append([1, block_lines, is_trace, block_size])
    for i in existing_messages:
        dic = {}
        dic['UniqueCounter'] = i[0]
        dic['BlockLines'] = i[1]
        dic['IsTracebackBlock'] = i[2]
        dic['AnalyzedBlockLinesSize'] = i[3]
        unique_date=get_line_date(str(dic['BlockLines']))
        if unique_date['Error']==None:
            unique_block_date=unique_date['Date']
        else:
            unique_block_date='No timestamp in block, last  "parsed date" was used!'
        dic['BlockDate']=unique_block_date
        dic['Log']=log
        LogDataDic['AnalyzedBlocks'].append(dic)
    if os.path.exists(grep_file):
        os.remove(grep_file)
    return LogDataDic

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
        for k in l.keys():
            append_to_file(fil,str(k)+' --> '+str(l[k])+'\n')

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

def get_file_line_index(fil,line):
    return exec_command_line_command("grep -n '"+line+"' "+fil)['CommandOutput'].split(':')[0]

def unique_list(lis):
    return list(collections.OrderedDict.fromkeys(lis).keys())

#This function is used for Non Standard logs only
def ignore_block(block, ignore_strings=ignore_strings, indicator_line=2):
    block_lines=block.splitlines()
    if len(block_lines)<3:
        return False
    for string in ignore_strings:
        if string.lower() in block_lines[indicator_line].lower():
            return True
    return False

def find_all_string_matches_in_line(line, string):
    line,string=line.lower(),string.lower()
    if string=='\|err\|':
        return [(i.start(), i.start() + len(string)-2) for i in re.finditer(string.lower(), line.lower())]
    else:
        return [(i.start(),i.start()+len(string)) for i in re.finditer(string.lower(), line.lower())]

def create_underline(line, list_of_strings):
    underline=''
    line = str(line).lower()
    lis_line=[' ' if char!='\t' else '\t' for char in line]
    strings=[string.lower() for string in list_of_strings]
    for string in strings:
        matches=find_all_string_matches_in_line(line,string)
        for match in matches:
            for start in range(match[0],match[1]):
                lis_line[start]='^'
    underline=''
    for c in lis_line:
        underline+=c
    return underline

def escape_ansi(line):
    ansi_escape =re.compile(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')
    return ansi_escape.sub('', line)

def cut_huge_block(block, limit_line_size=150, number_of_characters_after_match=120,number_of_characters_before_match=50):
    block_lines=block.splitlines()
    # Check if not Jumbo block
    if len(block_lines)>5000:
        new_block='LogTool --> this block is a Jumbo block and its size is: '+str(len(block_lines))+' lines!\n'
        for line in block_lines[0:20]:
            new_block+=line+'\n'
        for line in block_lines[-20:-1]:
            new_block += line + '\n'
        block=new_block
    # Normilize block
    block_lines=block.splitlines()
    block_lines=[escape_ansi(line) for line in block_lines]
    new_block=''
    matches = []
    for line in block_lines:
        for string in magic_words+python_exceptions:
            match_indexes=find_all_string_matches_in_line(line.lower(),string.lower())
            if match_indexes!=[]:
                for item in match_indexes:
                    if item[0]>number_of_characters_before_match:
                        if item[1]+number_of_characters_after_match<len(line):
                            match_line=line[item[0]-number_of_characters_before_match:item[0]]+line[item[0]:item[1]+number_of_characters_after_match]+'...'
                        else:
                            match_line=line[item[0]-number_of_characters_before_match:item[0]]+line[item[0]:]
                    else:
                        if item[1]+number_of_characters_after_match<len(line):
                            match_line=line[0:item[0]]+line[item[0]:item[1]+number_of_characters_after_match]+'...'
                        else:
                            match_line=line[0:item[0]]+line[item[0]:]
                    matches.append(match_line)
        if len(line) < limit_line_size:
            new_block += line+'\n'
        else:
            new_block += line[0:limit_line_size] + '...<--LogTool-LINE IS TOO LONG!\n'
    if matches!=[]:
        new_block += "\nLogTool --> "+"POTENTIAL BLOCK'S ISSUES: \n"
        if len(matches)>100:
            unique_matches = unique_list_by_fuzzy(matches, 0.2) #To reduce execution time
        else:
            unique_matches = unique_list_by_fuzzy(matches, fuzzy_match)
        for item in unique_matches:
            new_block+=item+'\n'
            new_block+=create_underline(item,magic_words+python_exceptions)+'\n'
    if matches==[]: #Nothing was found, so it's not relevant block
        new_block=None
    # Drop if not relevant block using "ignore_block"
    if ignore_block(block,ignore_strings)==True:
        new_block=None
    # If block is too long, cut it
    if new_block!=None:
        block_lines = new_block.splitlines()
        length_new_block=len(block_lines)
        if length_new_block>40:
            new_small_block=''
            for line in block_lines[0:5]:
                new_small_block+=line+'\n'
            new_small_block+='...\n...\n...\nLogTool --> THIS BLOCK IS TOO LONG!\n'
            if "LogTool --> POTENTIAL BLOCK'S ISSUES:" in new_block:
                new_small_block+=new_block[new_block.find("LogTool --> POTENTIAL BLOCK'S ISSUES:"):]
            else:
                new_small_block+='...\n'*3
                for line in block_lines[-5:-1]:
                    new_small_block += line + '\n'
            new_block=new_small_block
    return new_block

# Extract WARN or ERROR messages from log and return unique messages #
def extract_log_unique_greped_lines(log, string_for_grep):
    temp_grep_result_file = 'zahlabut.txt'
    unique_messages = []
    if os.path.exists(temp_grep_result_file):
        os.remove(temp_grep_result_file)
    commands=["grep -in -A7 -B2 '" + string_for_grep.lower() + "' " + log+" >> "+temp_grep_result_file]
    if 'error' in string_for_grep.lower():
        commands.append("grep -in -A7 -B2 traceback " + log+" >> "+temp_grep_result_file+"; echo -e '--' >> "+temp_grep_result_file)
        commands.append('grep -in -E ^stderr: -A7 -B2 '+log+' >> '+temp_grep_result_file+"; echo -e '--' >> "+temp_grep_result_file)
        commands.append('grep -n -A7 -B2 STDERR ' + log + ' >> '+temp_grep_result_file+"; echo -e '--' >> "+temp_grep_result_file)
        commands.append('grep -in -A7 -B2 failed ' + log + ' >> '+temp_grep_result_file+"; echo -e '--' >> "+temp_grep_result_file)
        commands.append("grep -in -A7 -B2 fatal " + log + ' >> ' + temp_grep_result_file+"; echo -e '--' >> "+temp_grep_result_file)
        commands.append('grep -in -A7 -B2 critical ' + log + ' >> ' + temp_grep_result_file+"; echo -e '--' >> "+temp_grep_result_file)
        commands.append('grep -in -A7 -B2 |ERR| ' + log + ' >> ' + temp_grep_result_file+"; echo -e '--' >> "+temp_grep_result_file)
        for string in python_exceptions:
            commands.append(
                'grep -n -A7 -B2 '+string+' ' + log + ' >> ' + temp_grep_result_file + "; echo -e '--' >> " + temp_grep_result_file)
    if '/var/log/messages' in log:
        if 'error' in string_for_grep.lower():
            string_for_grep='level=error'
        if 'warn' in string_for_grep.lower():
            string_for_grep = 'level=warn'
        commands = ["grep -n '" + string_for_grep + "' " + log + " > "+temp_grep_result_file]
    if 'consoleFull' in log:
        string_for_grep=string_for_grep+'\|background:red\|fatal:'
        commands = ["grep -n -A7 -B2 '" + string_for_grep.replace(' ','') + "' " + log + " > "+temp_grep_result_file]
    commands=[command.replace('grep','zgrep') if log.endswith('.gz') else command for command in commands]
    command=''
    for com in commands:
        command+=com+';'
    exec_command_line_command(command)
    # Read temp_grep_result_file txt and create list of blocks
    if os.path.exists(temp_grep_result_file) and os.path.getsize(temp_grep_result_file)!=0:
        temp_data=open(temp_grep_result_file,'r').read()
        if '--\n' in temp_data:
            list_of_blocks=temp_data.split('--\n')
        else:
            list_of_blocks = [temp_data]
    else: #zahlabut.txt is empty
        return {'UniqueMessages': unique_messages, 'AnalyzedBlocks': len(unique_messages), 'Log': log}
    # Pass through all blocks and normilize the size (huge blocks oredering) and filter it out if not relevant block is detected
    list_of_blocks=[cut_huge_block(block)+'\n' for block in list_of_blocks if cut_huge_block(block)!=None]
    # Fill out "relevant_blocks" by filtering out all "ignore strings" and by "third_line" if such a line was already handled before
    relevant_blocks = []
    third_lines = []
    for block in list_of_blocks:
        block_lines=block.splitlines()
        if len(block_lines)>=6:# Do nothing if len of blocks is less than 4
            third_line=block_lines[2:5]
            third_line=remove_digits_from_string(third_line)
            if third_line not in third_lines:
                third_lines.append(third_line)
                relevant_blocks.append(block)
    # Run fuzzy match
    number_of_blocks=len(relevant_blocks)
    for block in relevant_blocks:
        to_add=True
        for key in unique_messages:
            if similar(key, block) >= fuzzy_match:
                to_add = False
                break
        if to_add == True:
            unique_messages.append(block)
    if os.path.exists(temp_grep_result_file):
        os.remove(temp_grep_result_file)
    return {'UniqueMessages':unique_messages,'AnalyzedBlocks':len(unique_messages),'Log':log}

def sort_list_by_index(lis, index):
    return (sorted(lis, key=lambda x: x[index]))

if __name__ == "__main__":
    not_standard_logs=[]
    analyzed_logs_result=[]
    not_standard_logs_unique_messages=[] #Use it for all NOT STANDARD log files, add to this list {log_path:[list of all unique messages]}
    empty_file_content(result_file)
    start_time=time.time()
    logs=collect_log_paths(log_root_dir)
    for log in logs:
        print_in_color(log,'bold')
        # Skip log file if bigger than 1GB, save this information into not standard logs section
        log_size = os.path.getsize(log)
        if log_size > 1024 * 1024 * 1024:  # 1GB
            print_in_color(log + ' size is too big, skipped!!!', 'yellow')
            append_to_file(result_file,'~'*100+'\nWARNING the size of:'+log+' is: '
                           + str(log_size /(1024.0*1024.0*1024.0)) + ' [GB] LogTool is hardcoded to support log files up to 1GB, this log was skipped!\n')
            continue
        Log_Analyze_Info = {}
        Log_Analyze_Info['Log']=log
        Log_Analyze_Info['IsSingleLine']=is_single_line_file(log)
        # Try to check if there is a known timestamp in last 100 lines
        last_line=get_file_last_line(log,'100')
        is_known_time_format=False
        for line in last_line.splitlines():
            last_line_date=get_line_date(line)
            if last_line_date['Error']==None:
                is_known_time_format=True
                break
        Log_Analyze_Info['ParseLogTime']=last_line_date
        if is_known_time_format==True:
            if time.strptime(last_line_date['Date'], '%Y-%m-%d %H:%M:%S') >= time.strptime(time_grep, '%Y-%m-%d %H:%M:%S'):
                log_result=analyze_log(Log_Analyze_Info['Log'],string_for_grep,time_grep,last_line_date['Date'])
                analyzed_logs_result.append(log_result)
        else:
            if to_analyze_osp_logs_only=='all_logs':
                if 'WARNING' in string_for_grep:
                    string_for_grep='WARN'
                if 'ERROR' in string_for_grep:
                    string_for_grep=' ERROR'
                not_standard_logs_unique_messages.append(extract_log_unique_greped_lines(log, string_for_grep))


    ### Add basic description about the results into result file ###
    info='############################################# Usage Instruction ############################################\n'\
         "This LogTool result file have some logical structure and its content is divided into the several sections.\n" \
         "On the bottom of this file you will be able to find the 'Table of Content'\n"\
         "that is simply pointing you into the start line of each section inside this file.\n\n"\
         "There are two kinds of sections:\n"\
         '1) Statistics - Number of Errors/Warnings...\n'\
         "   In this section you will find log's path and the number of exported Errors/Warnings\n"\
         '   blocks sorted in increasing order, so most "suspicious"(high number of Errors/Warnings) logs\n'\
         '   could be found in the bottom of this section.\n\n'\
         '2) Exported unique messages...\n'\
         '   This section contains all exported unique Errors/Warnings blocks (sequence of log lines)\n'\
         "   sorted by blocks' timestamps\n"\
         '   Basing on your understanding from the previous Statistics section,\n'\
         '   you will need to check/expert exported Error/Warning blocks for each "suspicious" log file.\n'\
         '   In order to do that, copy log path string and search for this string inside this file. \n'\
         "   By doing that you will be able to pass through all exported blocks for each certain log file.\n"\
         "   Press 'n' in case when file is opened with VI/VIM text editor, pass through all blocks and try \n" \
         "   to figure out which one of them could be the 'Root Cause' you are searching for.\n"\
         "   Note:\n" \
         "   You can always 'jump' directly into the beginning of this section, using section start line number\n"\
         "   provided in 'Table of Content' and to scroll down till you find the potential 'Root Cause' and it's OK\n"\
         "   when you have let say tens of exported blocks, but when there are much more blocks, the efficient way\n"\
         "   would be trying to understand basing on 'Statistics' sections which logs are most 'suspicious' and then\n"\
         "   trying to dig out using 'searching' method explained here.\n\n"\
         'There are two kinds of log files: "Standard" and "Not Standard":\n' \
         'Standard logs - DEBUG level string + TIMESTAMP, both of them have been detected in log line, example line:\n'\
         '  "2020-04-25 07:10:30.697 27 DEBUG ceilometer.publisher.gnocchi..." \n'\
         'Not Standard - all the rest, example line does not include TIMESTAMP:\n'\
         '  "Debug: Evicting cache entry for environment "production"...\n'\
         "Note: this is the reason for having four sections in total inside LogTool result file.\n"
    append_to_file(result_file,info)

    ### Fill statistics section for Standard OSP logs###
    print_in_color('\nAggregating statistics for Standard OSP logs','bold')
    statistics_dic={item['Log']:item['TotalNumberOfErrors'] for item in analyzed_logs_result if item['TotalNumberOfErrors']>1}
    statistics_dic = sorted(list(statistics_dic.items()), key=operator.itemgetter(1))
    statistics_list=[{item[0]:item[1]} for item in statistics_dic]
    total_number_of_all_logs_errors=sum([item['TotalNumberOfErrors'] for item in analyzed_logs_result if item['TotalNumberOfErrors']!=0])
    statistics_list.insert(0,{'Total_Number_Of_'+str(string_for_grep).replace(' ','')+'s':total_number_of_all_logs_errors})
    print_list(statistics_list)
    write_list_of_dict_to_file(result_file,statistics_list,
                               '\n\n\n'+'#'*20+' Statistics - Number of Errors/Warnings per Standard OSP log since: '+time_grep+' '+'#'*20+'\n')


    ### Fill statistics section for Not Standard OSP logs###
    print_in_color('\nAggregating statistics for Not Standard OSP logs','bold')
    statistics_list = [[item['Log'],item['AnalyzedBlocks']] for item in not_standard_logs_unique_messages if item['AnalyzedBlocks']!=0]
    statistics_list = sort_list_by_index(statistics_list, 1)
    total_number_of_errors=sum([i[1] for i in statistics_list])
    statistics_list.insert(0,['Total_Number_Of_'+string_for_grep.replace(' ','')+'s',total_number_of_errors])
    print_list(statistics_list)
    append_to_file(result_file,'\n\n\n'+'#'*20+' Statistics - Number of Errors/Warnings per Not Standard OSP log since ever '+'#'*20)
    write_list_to_file(result_file,statistics_list,False)



    ### Fill Statistics - Unique(Fuzzy Matching) section ###
    #print_in_color('\nArrange Statistics - Unique(Fuzzy Matching) per log file ','bold')
    append_to_file(result_file,'\n\n\n'+'#'*20+' Exported unique messages, per STANDARD OSP log file since: '+time_grep+'#'*20+'\n')
    common_list_of_all_blocks=[]
    for item in analyzed_logs_result:
        for block in item['AnalyzedBlocks']:
            common_list_of_all_blocks.append(block)
    for block in sorted(common_list_of_all_blocks,key=lambda i: i['BlockDate']):
        append_to_file(result_file, '\n'+'-'*30+' LogPath: ' + block['Log']+' '+'-'*30+' \n')
        append_to_file(result_file, 'IsTracebackBlock:' + str(block['IsTracebackBlock'])+'\n')
        append_to_file(result_file, 'UniqueCounter:' + str(block['UniqueCounter'])+'\n')
        append_to_file(result_file, 'AnalyzedBlockLinesSize:' + str(block['AnalyzedBlockLinesSize']) + '\n')
        append_to_file(result_file, 'BlockDate:' + str(block['BlockDate']) + '\n')
        append_to_file(result_file, 'Log:' + str(block['Log']) + '\n')
        for line in block['BlockLines']:
            append_to_file(result_file, line + '\n')


    ### Exported Unique messages per NOT STANDARD log file, since ever  ###
    append_to_file(result_file,'\n\n\n'+'#'*20+' Exported unique messages per NOT STANDARD log file, since ever '+'#'*20+'\n')
    for dir in not_standard_logs_unique_messages:
        if len(dir['UniqueMessages'])>0:
            append_to_file(result_file,'\n'+'~'*40+' '+dir['Log']+' '+'~'*40+'\n')
            write_list_to_file(result_file,dir['UniqueMessages'])

    ### Fill statistics section - Table of Content: line+index ###
    section_indexes=[]
    messages=[
        #'Raw Data - extracted Errors/Warnings from standard OSP logs since: '+time_grep,
        # 'Skipped logs - no debug level string (Error, Info, Debug...) has been detected',
        'Statistics - Number of Errors/Warnings per Standard OSP log since: '+time_grep,
        'Statistics - Number of Errors/Warnings per Not Standard OSP log since ever',
        'Exported unique messages, per STANDARD OSP log file since: '+time_grep,
        'Exported unique messages per NOT STANDARD log file, since ever',
        #'Statistics - Unique(Fuzzy Matching for all messages in total for standard OSP logs'
        ]
    for msg in messages:
        section_indexes.append({msg:"SectionStartLine: "+get_file_line_index(result_file,msg)})
    write_list_of_dict_to_file(result_file,section_indexes,'\n\n\n'+'#'*20+' Table of content (Section name --> Line number)'+'#'*20+'\n')
    #exec_command_line_command('gzip '+result_file)
    print('Execution time:'+str(time.time()-start_time))
    if total_number_of_all_logs_errors+total_number_of_errors>0:
        print('Total_Number_Of_Errors:'+str(total_number_of_all_logs_errors+total_number_of_errors))
    print('SUCCESS!!!')