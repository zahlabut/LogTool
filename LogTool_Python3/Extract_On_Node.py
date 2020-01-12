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
import gzip
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
log_root_dir=set_default_arg_by_index(2,'/var/log/containers') # Log path #
string_for_grep=set_default_arg_by_index(3,' ERROR ') # String for Grep
result_file=set_default_arg_by_index(4,'All_Greps.log') # Result file
result_file=os.path.join(os.path.abspath('.'),result_file)
save_raw_data=set_default_arg_by_index(5,'yes') # Save raw data messages
operation_mode=set_default_arg_by_index(6,'None') # Operation mode
magic_words=['error','traceback','stderr','failed','critical','fatal'] # Used to cut huge size lines
# String to ignore for Not Standard Log files
ignore_strings=['completed with no errors','program: Errors behavior:',
                    'No error reported.','--exit-command-arg error','Use errors="ignore" instead of skip.',
                    'Errors:None','errors, 0','errlog_type error ','errorlevel = ','ERROR %(name)s','Total errors: 0',
                '0 errors,']


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

def collect_log_paths(log_root_path):
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
    if len(logs)==0:
        sys.exit('Failed - No log files detected in: '+log_root_path)
    return logs

def empty_file_content(log_file_name):
    f = open(log_file_name, 'w')
    f.write('')
    f.close()

def append_to_file(log_file, msg):
    log_file = open(log_file, 'a')
    log_file.write(msg)

def get_line_date(line):
    line=line[0:50] # Use first 50 characters to get line timestamp
    # Check that debug level exists in log last line
    valid_debug_levels=['INFO','WARN','DEBUG','ERROR','CRITICAL','FATAL','TRACE','OFF']
    return_error=True
    for level in valid_debug_levels:
        if level in line:
            return_error=False
            break
    if return_error==True:
        return {'Error': 'No valid debug level found in log last line!', 'Line': line.strip(), 'Date': None}

    # Delta 27 []
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

def analyze_log(log, string, time_grep, file_to_save = 'Exported.txt'):
    grep_file='zahlabut.txt'
    strings=[]
    LogDataDic={'Log':log, 'AnalyzedBlocks':[],'TotalNumberOfErrors':0}
    time_grep=time.strptime(time_grep, '%Y-%m-%d %H:%M:%S')
    existing_messages = []
    if os.path.exists(grep_file):
        os.remove(grep_file)
    command = "grep -n '" + string + "' " + log + " >> "+grep_file
    if string=='WARN':
        strings=['WARNING',string]
    if string ==' ERROR':
        command=''
        strings=[' ERROR',' CRITICAL',' FATAL',' TRACE']
        for item in strings:
            command+="grep -n '" +item+ "' " + log + " >> "+grep_file+';'
    if log.endswith('.gz'):
        command.replace('grep','zgrep')
    exec_command_line_command(command)
    if os.path.exists(grep_file) and os.path.getsize(grep_file)!=0:
        lines=open(grep_file,'r').readlines()
        filtered_lines = []
        for line in lines:
            for string in strings:
                if string in line[0:60]:
                    filtered_lines.append(line)
        lines=filtered_lines
        lines_dic={}
        for line in lines:
            lines_dic[line.split(':')[0]]=line[line.find(':')+1:].strip() #{index1:line1,....indexN:lineN}
        indexes=[int(line.split(':')[0]) for line in lines]# [1,2,3,....15,26]
        blocks=list(to_ranges(indexes)) #[(1,2)...(4,80)]
        for block in blocks:
            if block[0]==block[1]:# Single line
                block_lines=[lines_dic[str(block[0])]]
            elif block[1]-block[0]>100:
                block_lines=[]
                for indx in range(block[0],block[0]+15):
                    block_lines.append(lines_dic[str(indx)])
                block_lines.append('.../n'*3)
                block_lines.append('LogTool --> This block is too long!')
                block_lines.append('.../n' * 3)
                for indx in range(block[1]-15,block[1]+1):
                    block_lines.append(lines_dic[str(indx)])
            else:
                block_lines=[lines_dic[str(indx)] for indx in range(block[0],block[1]+1)]
            block_date=get_line_date(block_lines[0]) # Check date only for first line
            if block_date['Error']==None:
                date=time.strptime(block_date['Date'], '%Y-%m-%d %H:%M:%S')
            else:
                print_in_color('Failed to parse date on line: '+str(block_date),'yellow')
                print('--- Failed block lines are: ---')
                for l in block_lines:
                    print(l)
                continue # Failed on block, continue to another block
            if date < time_grep:
                continue
            LogDataDic['TotalNumberOfErrors']+=1
            block_lines_to_save = [line for line in block_lines]
            filtered_lines=[]
            for line in block_lines:
                for string in strings:
                    if string in line:
                        filtered_lines.append(string+line.split(string)[1])
                        break
            block_lines=filtered_lines
            # Save to file block lines #
            if save_raw_data=='yes':
                append_to_file(file_to_save,'\n'+'~'*20+log+'~'*20+'\n')
                append_to_file(file_to_save, 'Block_Date:'+str(date)+'\n')
                append_to_file(file_to_save, 'BlockLinesTuple:'+str(block)+'\n')
                for l in block_lines_to_save:
                    append_to_file(result_file,l+'\n')
            # Check fuzzy match and count matches #
            to_add = True
            is_trace = False
            if 'Traceback (most recent call last)' in str(block_lines):
                is_trace = True
            block_tuple = block
            block_size = len(block_lines)
            for key in existing_messages:
                if similar(key[1], str(block_lines)) >= fuzzy_match:
                    to_add = False
                    messages_index=existing_messages.index(key)
                    counter=existing_messages[messages_index][0]
                    message=existing_messages[messages_index][1]
                    existing_messages[messages_index]=[counter+1,message,is_trace,block_tuple,block_size]
                    break
            if to_add == True:
                existing_messages.append([1,block_lines,is_trace,block_tuple,block_size])
    for i in existing_messages:
        dic={}
        dic['UniqueCounter']=i[0]
        dic['BlockLines']=i[1]
        dic['IsTracebackBlock']= i[2]
        dic['BlockTuple']=i[3]
        dic['BlockLinesSize']=i[4]
        LogDataDic['AnalyzedBlocks'].append(dic)
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
    return [(m.start(0), m.end(0)) for m in re.finditer(string, line)]

def create_underline(line, list_of_strings):
    underline=''
    length=len(line)
    line = line.lower()
    lis_line=[' ' for char in line]
    strings=[string.lower() for string in list_of_strings]
    for string in strings:
        if line.find(string)>0:
            start=line.find(string)
            for char in string:
                lis_line[start]='^'
                start+=1
    underline=''
    for c in lis_line:
        underline+=c
    return underline

def cut_huge_block(block, limit_line_size=150, number_of_characters_after_match=120,number_of_characters_before_match=50):
    block_lines=block.splitlines()
    new_block=''
    matches = []
    for line in block_lines:
        if len(line) < limit_line_size:
            new_block += line + '\n'
        else:
            new_block+=line[0:limit_line_size]+'... <-- LogTool: THIS LINE IS TOO LONG!\n'
            for string in magic_words:
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
        unique_matches=unique_list_by_fuzzy(matches,fuzzy_match)
        for item in unique_matches:
            new_block+=item+'\n'
            new_block+=create_underline(item,magic_words)+'\n'

    # Drop if not relevant block using "ignore_block"
    if ignore_block(block,ignore_strings)==True:
        new_block=None

    # If block is too long, cut it
    if new_block!=None:
        block_lines = new_block.splitlines()
        length_new_block=len(block_lines)
        if length_new_block>20:
            new_small_block=''
            for line in block_lines[0:5]:
                new_small_block+=line+'\n'
            new_small_block+='...\n...\n...\nLogTool --> THIS BLOCK IS TOO LONG!\n'
            if "LogTool --> POTENTIAL BLOCK'S ISSUES:" in new_block:
                new_small_block+=new_block[new_block.find("LogTool --> POTENTIAL BLOCK'S ISSUES:"):]
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
        commands.append("grep -in -A7 -B2 traceback " + log+" >> "+temp_grep_result_file)
        commands.append('grep -in -E ^stderr: -A7 -B2 '+log+' >> '+temp_grep_result_file)
        commands.append('grep -n -A7 -B2 STDERR ' + log + ' >> '+temp_grep_result_file)
        commands.append('grep -in -A7 -B2 failed ' + log + ' >> '+temp_grep_result_file)
        commands.append('grep -in -A7 -B2 fatal ' + log + ' >> ' + temp_grep_result_file)
        commands.append('grep -in -A7 -B2 critical ' + log + ' >> ' + temp_grep_result_file)
    if '/var/log/messages' in log:
        if 'error' in string_for_grep.lower():
            string_for_grep='level=error'
        if 'warn' in string_for_grep.lower():
            string_for_grep = 'level=warn'
        commands = ["grep -n '" + string_for_grep + "' " + log + " > zahlabut.txt"]
    if 'consoleFull' in log:
        string_for_grep=string_for_grep+'\|background:red\|fatal:'
        commands = ["grep -n -A7 -B2 '" + string_for_grep.replace(' ','') + "' " + log + " > zahlabut.txt"]
    commands=[command.replace('grep','zgrep') if log.endswith('.gz') else command for command in commands]
    command=''
    for com in commands:
        command+=com+';'
    exec_command_line_command(command)

    # Read temp_grep_result_file txt and create list of blocks
    if os.path.exists(temp_grep_result_file) and os.path.getsize(temp_grep_result_file)!=0:
        if '--\n' in open(temp_grep_result_file,'r').read():
            list_of_blocks=open(temp_grep_result_file,'r').read().split('--\n')
        else:
            list_of_blocks = [open(temp_grep_result_file, 'r').read()]
    else: #zahlabut.txt is empty
        return {log: unique_messages}

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
    for block in relevant_blocks:
        to_add=True
        for key in unique_messages:
            if similar(key, block) >= fuzzy_match:
                to_add = False
                break
        if to_add == True:
            unique_messages.append(block)
    return {log:unique_messages}

if __name__ == "__main__":
    not_standard_logs=[]
    analyzed_logs_result=[]
    not_standard_logs_unique_messages=[] #Use it for all NOT STANDARD log files, add to this list {log_path:[list of all unique messages]}
    if __name__ == "__main__":
        empty_file_content(result_file)
        append_to_file(result_file,'\n\n\n'+'#'*20+' Raw Data - extracted Errors/Warnings from standard OSP logs since: '+time_grep+' '+'#'*20)
        start_time=time.time()
        logs=collect_log_paths(log_root_dir)
        for log in logs:
            print_in_color('--> '+log, 'bold')
            Log_Analyze_Info = {}
            Log_Analyze_Info['Log']=log
            Log_Analyze_Info['IsSingleLine']=is_single_line_file(log)
            # Get the time of last line, if fails will be added to ignored logs
            last_line=get_file_last_line(log)
            last_line_date=get_line_date(last_line)
            Log_Analyze_Info['ParseLogTime']=last_line_date
            if last_line_date['Error'] != None or '-ir-' in log:  # Infrared logs are not standard logs
                #print_in_color(log+' --> \n'+str(last_line_date['Error']),'yellow')
                # Check if last line contains: proper debug level: INFO or WARN or ERROR string
                log_last_lines=get_file_last_line(log, '10')
                if ('ERROR' in log_last_lines or 'WARN' in log_last_lines or
                    'INFO' in log_last_lines or 'DEBUG' in log_last_lines) is False:
                    not_standard_logs.append({'Log':log,'Last_Lines':'\n' + log_last_lines})
                # Extract all ERROR or WARN lines and provide the unique messages
                if 'WARNING' in string_for_grep:
                    string_for_grep='WARN'
                if 'ERROR' in string_for_grep:
                    string_for_grep=' ERROR'
                not_standard_logs_unique_messages.append(extract_log_unique_greped_lines(log, string_for_grep))
            else:
                if time.strptime(last_line_date['Date'], '%Y-%m-%d %H:%M:%S') > time.strptime(time_grep, '%Y-%m-%d %H:%M:%S'):
                    log_result=analyze_log(Log_Analyze_Info['Log'],string_for_grep,time_grep,result_file)
                    analyzed_logs_result.append(log_result)

    ### Fill statistics section ###
    print_in_color('\nAggregating statistics','bold')
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
                               '\n\n\n'+'#'*20+' Statistics - Number of Errors/Warnings per standard OSP log since: '+time_grep+'#'*20+'\n')

    ### Fill Statistics - Unique(Fuzzy Matching) section ###
    #print_in_color('\nArrange Statistics - Unique(Fuzzy Matching) per log file ','bold')
    append_to_file(result_file,'\n\n\n'+'#'*20+' Statistics - Unique messages, per STANDARD OSP log file since: '+time_grep+'#'*20+'\n')
    for item in analyzed_logs_result:
        #print 'LogPath --> '+item['Log']
        for block in item['AnalyzedBlocks']:
            append_to_file(result_file, '\n'+'-'*30+' LogPath:' + item['Log']+'-'*30+' \n')
            append_to_file(result_file, 'IsTracebackBlock:' + str(block['IsTracebackBlock'])+'\n')
            append_to_file(result_file, 'BlockTuple:' + str(block['BlockTuple'])+'\n')
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
        key=list(dir.keys())[0]
        if len(dir[key])>0:
            append_to_file(result_file,'\n'+'~'*40+key+'~'*40+'\n')
            write_list_to_file(result_file,dir[key])

    ### Fill statistics section - Table of Content: line+index ###
    section_indexes=[]
    messages=[
        'Raw Data - extracted Errors/Warnings from standard OSP logs since: '+time_grep,
        # 'Skipped logs - no debug level string (Error, Info, Debug...) has been detected',
        'Statistics - Number of Errors/Warnings per standard OSP log since: '+time_grep,
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