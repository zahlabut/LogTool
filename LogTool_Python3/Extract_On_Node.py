#!/usr/bin/python

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
magic_words=['error','traceback','stderr','failed','critical','fatal',"\|err\|",'trace'] # Used to cut huge size lines
# String to ignore for Not Standard Log files
ignore_strings=['completed with no errors','program: Errors behavior:',
                    'No error reported.','--exit-command-arg error','Use errors="ignore" instead of skip.',
                    'Errors:None','errors, 0','errlog_type error ','errorlevel = ','ERROR %(name)s','Total errors: 0',
                '0 errors,','python-traceback2-','"Error": ""','perl-Errno-','libgpg-error-','libcom_err-',
                '= CRITICAL ']
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


def remove_digits_from_string(s):
    remove_digits = str.maketrans('', '', digits)
    return str(s).translate(remove_digits)

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
    if line.find(']') - line.find('[') == 27:
        try:
            date = line[line.find('[') + 1:line.find(']')]
            date=datetime.datetime.strptime(date.split(' +')[0], "%d/%b/%Y:%H:%M:%S")
            return {'Error': None, 'Date':date.strftime('%Y-%m-%d %H:%M:%S.%f').split('.')[0],'Line':line}
        except Exception as e:
            return {'Error': e, 'Line': line.strip(), 'Date':None}

    # Delta 32 []
    elif line.find(']') - line.find('[') == 32:
        try:
            date = line[line.find('[') + 1:line.find(']')]
            date=datetime.datetime.strptime(date.split(' +')[0], "%a %b %d %H:%M:%S.%f %Y")
            return {'Error': None, 'Date': date.strftime('%Y-%m-%d %H:%M:%S.%f').split('.')[0], 'Line': line}
        except Exception as e:
            return {'Error': e, 'Line': line.strip(),'Date':None}

    else:
        try:
            date=line[0:19].replace('T',' ')
            date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
            return {'Error': None, 'Date': date.strftime('%Y-%m-%d %H:%M:%S').split('.')[0], 'Line': line}
        except Exception as e:
            return {'Error':str(e),'Line':line.strip(),'Date':None}

def analyze_log(log, string, time_grep, file_to_save,last_line_date):
    grep_file='zahlabut.txt'
    strings=[]
    third_lines=[]
    LogDataDic={'Log':log, 'AnalyzedBlocks':[],'TotalNumberOfErrors':0}
    time_grep=time.strptime(time_grep, '%Y-%m-%d %H:%M:%S')
    last_line_date=time.strptime(last_line_date, '%Y-%m-%d %H:%M:%S')
    existing_messages = []
    if os.path.exists(grep_file):
        os.remove(grep_file)
    command = ''
    if string=='WARN':
        basic_strings=['WARNING',string]
        strings=basic_strings
    if 'ERROR' in string:
        basic_strings=[' ERROR',' CRITICAL',' FATAL',' TRACE','|ERR|',' FAILED', ' STDERR',' traceback']
        strings=basic_strings+python_exceptions
    for item in strings:
        command+="grep -B2 -A7 -i '"+item+"' " + log + " >> "+grep_file+";echo -e '--' >> "+grep_file+';'
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
        block_lines=block.splitlines()
        parsed_date=False
        for line in block_lines:
            block_date=get_line_date(line)
            if block_date['Error']==None:
                date=time.strptime(block_date['Date'], '%Y-%m-%d %H:%M:%S')
                last_parsed_date=date
                parsed_date=True
                break
        if parsed_date==False:
            print_in_color('Failed to parse date on line: '+str(block_date),'yellow')
            print('Last known parsed date was: '+str(last_parsed_date))
            date=last_parsed_date
            block_lines.insert(0,"*** LogTool --> this block is missing timestamp, therefore could be irrelevant to your time range! ***")
        if date < time_grep:
            continue
        # Create list of third lines, do not analyze the same blocks again and again
        if len(block_lines)>=3:
            third_line=remove_digits_from_string(block_lines[2])
        else:
            third_line=remove_digits_from_string(block_lines[0])
        # Block is relevant only when the debug level is in the first 60 characters in THIRD LINE (no digits in it)
        cut_line = third_line[0:60].lower()
        temp_list=[cut_line.find(item.lower()) for item in strings if cut_line.find(item.lower())>0]
        if sum(temp_list)==0:
            continue
        LogDataDic['TotalNumberOfErrors'] += 1
        if third_line not in third_lines:
            third_lines.append(third_line)
            block=cut_huge_block(block)
            if block!=None:
                block_lines=block.splitlines()
        else:
            continue
        # Check fuzzy match and count matches #
        to_add = True
        is_trace = False
        if 'Traceback (most recent call last)' in str(block_lines):
            is_trace = True
        block_size = len(block_lines)
        for key in existing_messages:
            if similar(key[1], str(block_lines)) >= fuzzy_match:
                to_add = False
                messages_index = existing_messages.index(key)
                counter = existing_messages[messages_index][0]
                message = existing_messages[messages_index][1]
                existing_messages[messages_index] = [counter + 1, message, is_trace, block_size]
                break
        if to_add == True:
            existing_messages.append([1, block_lines, is_trace, block_size])
    for i in existing_messages:
        dic = {}
        dic['UniqueCounter'] = i[0]
        dic['BlockLines'] = i[1]
        dic['IsTracebackBlock'] = i[2]
        dic['BlockLinesSize'] = i[3]
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
        if len(line) < limit_line_size:
            new_block += line + '\n'
        else:
            new_block+=line[0:limit_line_size]+'...<--LogTool-LINE IS TOO LONG!\n'
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
    if matches!=[]:
        new_block += "LogTool --> "+"POTENTIAL BLOCK'S ISSUES: \n"
        if len(matches)>100:
            unique_matches = unique_list_by_fuzzy(matches, 0.2) #To reduce execution time
        else:
            unique_matches = unique_list_by_fuzzy(matches, fuzzy_match)
        for item in unique_matches:
            new_block+=item+'\n'
            new_block+=create_underline(item,magic_words+python_exceptions)+'\n'

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
        commands.append('grep -in -A7 -B2 fatal ' + log + ' >> ' + temp_grep_result_file+"; echo -e '--' >> "+temp_grep_result_file)
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
        if len(block_lines)>=3:# Do nothing if len of blocks is less than 3
            third_line=block_lines[2]
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
    if __name__ == "__main__":
        empty_file_content(result_file)
        #append_to_file(result_file,'\n\n\n'+'#'*20+' Raw Data - extracted Errors/Warnings from standard OSP logs since: '+time_grep+' '+'#'*20)
        start_time=time.time()
        logs=collect_log_paths(log_root_dir)
        for log in logs:
            # Skip log file if bigger than 1GB, save this information into not standard logs section
            log_size = os.path.getsize(log)
            if log_size > 1024 * 1024 * 1024:  # 1GB
                print_in_color(log + ' size is too big, skipped!!!', 'yellow')
                append_to_file(result_file,'~'*100+'\nWARNING the size of:'+log+' is: '
                               + str(log_size /(1024.0*1024.0*1024.0)) + ' [GB] LogTool is hardcoded to support log files up to 1GB, this log was skipped!\n')
                continue
            print_in_color('--> '+log, 'bold')
            Log_Analyze_Info = {}
            Log_Analyze_Info['Log']=log
            Log_Analyze_Info['IsSingleLine']=is_single_line_file(log)
            # Get the time of last line, if fails will be added to ignored logs
            last_line=get_file_last_line(log)
            last_line_date=get_line_date(last_line)
            Log_Analyze_Info['ParseLogTime']=last_line_date
            if last_line_date['Error'] != None:
                if 'WARNING' in string_for_grep:
                    string_for_grep='WARN'
                if 'ERROR' in string_for_grep:
                    string_for_grep=' ERROR'
                if to_analyze_osp_logs_only=='all_logs':
                    not_standard_logs_unique_messages.append(extract_log_unique_greped_lines(log, string_for_grep))
            else:
                if time.strptime(last_line_date['Date'], '%Y-%m-%d %H:%M:%S') > time.strptime(time_grep, '%Y-%m-%d %H:%M:%S'):
                    log_result=analyze_log(Log_Analyze_Info['Log'],string_for_grep,time_grep,result_file,last_line_date['Date'])
                    analyzed_logs_result.append(log_result)

    ### Fill statistics section for Standard OSP logs###
    print_in_color('\nAggregating statistics for Standard OSP logs','bold')
    statistics_dic={item['Log']:item['TotalNumberOfErrors'] for item in analyzed_logs_result if item['TotalNumberOfErrors']!=0}
    statistics_dic = sorted(list(statistics_dic.items()), key=operator.itemgetter(1))
    statistics_list=[{item[0]:item[1]} for item in statistics_dic]
    total_number_of_all_logs_errors=sum([item['TotalNumberOfErrors'] for item in analyzed_logs_result if item['TotalNumberOfErrors']!=0])
    if 'error' in string_for_grep.lower():
        statistics_list.insert(0,{'Total_Number_Of_Errors':total_number_of_all_logs_errors})
    if 'warn' in string_for_grep.lower():
        statistics_list.insert(0,{'Total_Number_Of_Warnings':total_number_of_all_logs_errors})
    print_list(statistics_list)
    write_list_of_dict_to_file(result_file,statistics_list,
                               '\n\n\n'+'#'*20+' Statistics - Number of Errors/Warnings per Standard OSP log since: '+time_grep+' '+'#'*20+'\n')


    ### Fill statistics section for Not Standard OSP logs###
    print_in_color('\nAggregating statistics for Not Standard OSP logs','bold')
    statistics_list = [[item['Log'],item['AnalyzedBlocks']] for item in not_standard_logs_unique_messages if item['AnalyzedBlocks']!=0]
    statistics_list = sort_list_by_index(statistics_list, 1)
    total_number_of_errors=sum([i[1] for i in statistics_list])
    if 'error' in string_for_grep.lower():
        statistics_list.insert(0,['Total_Number_Of_Errors',total_number_of_errors])
    if 'warn' in string_for_grep.lower():
        statistics_list.insert(0,['Total_Number_Of_Warnings',total_number_of_errors])
    print_list(statistics_list)
    append_to_file(result_file,'\n\n\n'+'#'*20+' Statistics - Number of Errors/Warnings per Not Standard OSP log since ever '+'#'*20)
    write_list_to_file(result_file,statistics_list,False)


    ### Fill Statistics - Unique(Fuzzy Matching) section ###
    #print_in_color('\nArrange Statistics - Unique(Fuzzy Matching) per log file ','bold')
    append_to_file(result_file,'\n\n\n'+'#'*20+' Statistics - Unique messages, per STANDARD OSP log file since: '+time_grep+'#'*20+'\n')
    for item in analyzed_logs_result:
        #print 'LogPath --> '+item['Log']
        for block in item['AnalyzedBlocks']:
            append_to_file(result_file, '\n'+'-'*30+' LogPath: ' + item['Log']+' '+'-'*30+' \n')
            append_to_file(result_file, 'IsTracebackBlock:' + str(block['IsTracebackBlock'])+'\n')
            append_to_file(result_file, 'UniqueCounter:' + str(block['UniqueCounter'])+'\n')
            append_to_file(result_file, 'BlockLinesSize:' + str(block['BlockLinesSize']) + '\n')
            if block['BlockLinesSize']<30:
                for line in block['BlockLines']:
                    append_to_file(result_file,line+'\n')
            else:
                for line in block['BlockLines'][0:10]:
                    append_to_file(result_file, line + '\n')
                append_to_file(result_file,'...\n---< BLOCK IS TOO LONG >---\n...\n')
                for line in block['BlockLines'][-10:-1]:
                    append_to_file(result_file, line + '\n')
            #append_to_file(result_file, '~' * 100 + '\n')

    ### Statistics - Unique messages per NOT STANDARD log file, since ever  ###
    append_to_file(result_file,'\n\n\n'+'#'*20+' Statistics - Unique messages per NOT STANDARD log file, since ever '+'#'*20+'\n')
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
        'Statistics - Unique messages, per STANDARD OSP log file since: '+time_grep,
        'Statistics - Unique messages per NOT STANDARD log file, since ever',
        #'Statistics - Unique(Fuzzy Matching for all messages in total for standard OSP logs'
        ]
    for msg in messages:
        section_indexes.append({msg:get_file_line_index(result_file,msg)})
    write_list_of_dict_to_file(result_file,section_indexes,'\n\n\n'+'#'*20+' Table of content (Section name --> Line number)'+'#'*20+'\n')
    exec_command_line_command('gzip '+result_file)
    print('Execution time:'+str(time.time()-start_time))
    print('SUCCESS!!!')