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
import itertools
import json
import warnings
warnings.simplefilter("ignore", UserWarning)
import difflib
import datetime
import operator
import collections



### Parameters ###

# Log path #
try:
    log_root_dir=sys.argv[1].strip()
except:
    log_root_dir='/var/log/containers'
    #log_root_dir='/root/Overcloud_Logs/com0'
    #log_root_dir='/root/tzach/containers'
# String for Grep #
try:
    string_for_grep=sys.argv[2].strip()
except:
    string_for_grep=' ERROR '
# Result file #
try:
    result_file=sys.argv[3]
except:
    result_file='Exported_Delta.log'
result_file=os.path.join(os.path.abspath('.'),result_file)
# Operation mode #
try:
    mode=sys.argv[4]
except:
    mode='stop'
log_last_lines_file='LastLines.txt'

def exec_command_line_command(command):
    try:
        command_as_list = command.split(' ')
        command_as_list = [item.replace(' ', '') for item in command_as_list if item != '']
        result = subprocess.check_output(command, shell=True)
        json_output = None
        try:
            json_output = json.loads(result.lower())
        except:
            pass
        return {'ReturnCode': 0, 'CommandOutput': result, 'JsonOutput': json_output}
    except subprocess.CalledProcessError as e:
        return {'ReturnCode': e.returncode, 'CommandOutput': str(e)}

def get_file_last_line(log):
    if log.endswith('.gz'):
        return exec_command_line_command('zcat '+log+' | tail -1')['CommandOutput']
    else:
        return exec_command_line_command('tail -1 '+log)['CommandOutput']

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

def to_ranges(iterable):
    iterable = sorted(set(iterable))
    for key, group in itertools.groupby(enumerate(iterable), lambda t: t[1] - t[0]):
        group = list(group)
        yield group[0][1], group[-1][1]

def collect_log_paths(log_root_path):
    logs=[]
    for root, dirs, files in os.walk(log_root_path):
        for name in files:
            if name.endswith('.log')==True:
                file_abs_path=os.path.join(os.path.abspath(root), name)
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
            append_to_file(fil,str(k)+' --> '+str(l[k])+'\n')

def get_file_line_index(fil,line):
    return exec_command_line_command("grep -n '"+line+"' "+fil)['CommandOutput'].split(':')[0]

def unique_list(lis):
    return list(collections.OrderedDict.fromkeys(lis).keys())

def get_file_last_line_index(fil_path):
    return exec_command_line_command('wc -l '+fil_path)['CommandOutput'].split(' ')[0]

def grep_by_start_line(fil,start_line,grep_string):
    lines=exec_command_line_command("grep -n '"+grep_string+"' "+fil)['CommandOutput'].split('\n')
    indexes = [int(line.split(':')[0]) for line in lines]
    blocks = list(to_ranges(indexes))
    blocks=[block for block in blocks if block[0]>start_line]
    return  blocks






if __name__ == "__main__":
    if mode == 'start':

        empty_file_content(log_last_lines_file)
        empty_file_content(result_file)
        start_time=time.time()
        logs=collect_log_paths(log_root_dir)
        for log in logs:
            print_in_color('--> '+log, 'bold')
            last_line_index=get_file_last_line_index(log)
            append_to_file(log_last_lines_file,log+'-->'+last_line_index+'\n')

    if mode=='stop':
        logs=collect_log_paths(log_root_dir)
        #Check if NEW files created
        for log in logs:
            if log not in open(log_last_lines_file,'r').read():
                append_to_file(log_last_lines_file,log+'-->1\n')
        for item in open(log_last_lines_file,'r').readlines():
            print(grep_by_start_line(log,int(item.split('-->')[1]),string_for_grep))





#
#
# ### Fill Failed log Section ###
# if len(not_standard_logs)>0:
#     print_in_color('Failed to parse the following logs:','yellow')
#     print_list(not_standard_logs)
#
#     write_list_of_dict_to_file(result_file,
#                                not_standard_logs,
#                                '\n\n\n'+'#'*20+' Warning, following logs failed on parsing due to non standard date format '+'#'*20+'\n'+
#                                'In Total:'+str(len(not_standard_logs))+'\n',
#                                msg_delimeter='~'*100+'\n')
#
#
# ### Fill statistics section ###
# print_in_color('\nAggregating statistics','bold')
# statistics_dic={item['Log']:item['TotalNumberOfErrors'] for item in analyzed_logs_result if item['TotalNumberOfErrors']!=0}
# statistics_dic = sorted(statistics_dic.items(), key=operator.itemgetter(1))
# statistics_list=[{item[0]:item[1]} for item in statistics_dic]
# total_number_of_all_logs_errors=sum([item['TotalNumberOfErrors'] for item in analyzed_logs_result if item['TotalNumberOfErrors']!=0])
# if 'error' in string_for_grep.lower():
#     statistics_list.insert(0,{'Total_Number_Of_Errors':total_number_of_all_logs_errors})
# if 'warn' in string_for_grep.lower():
#     statistics_list.insert(0,{'Total_Number_Of_Warnings':total_number_of_all_logs_errors})
# print_list(statistics_list)
# write_list_of_dict_to_file(result_file,statistics_list,'\n\n\n'+'#'*20+' Statistics - Number of Errors/Warnings per log '+'#'*20+'\n'+
#                            'Total Number of Errors/Warnings is:'+str(total_number_of_all_logs_errors)+'\n')
#
#
# ### Fill Statistics - Unique(Fuzzy Matching) section ###
# #print_in_color('\nArrange Statistics - Unique(Fuzzy Matching) per log file ','bold')
# append_to_file(result_file,'\n\n\n'+'#'*20+' Statistics - Unique(Fuzzy Matching per log file '+'#'*20+'\n')
# for item in analyzed_logs_result:
#     #print 'LogPath --> '+item['Log']
#     for block in item['AnalyzedBlocks']:
#         append_to_file(result_file, '\n'+'-'*30+' LogPath:' + item['Log']+'-'*30+' \n')
#         append_to_file(result_file, 'IsTracebackBlock:' + str(block['IsTracebackBlock'])+'\n')
#         append_to_file(result_file, 'BlockTuple:' + str(block['BlockTuple'])+'\n')
#         append_to_file(result_file, 'UniqueCounter:' + str(block['UniqueCounter'])+'\n')
#         append_to_file(result_file, 'BlockLinesSize:' + str(block['BlockLinesSize']) + '\n')
#         if block['BlockLinesSize']<30:
#             for line in block['BlockLines']:
#                 append_to_file(result_file,line+'\n')
#         else:
#             for line in block['BlockLines'][0:10]:
#                 append_to_file(result_file, line + '\n')
#             append_to_file(result_file,'...\n---< BLOCK IS TOO LONG >---\n...\n')
#             for line in block['BlockLines'][-10:-1]:
#                 append_to_file(result_file, line + '\n')
#         #append_to_file(result_file, '~' * 100 + '\n')
#
#
# ### Fill Statistics - Unique(Fuzzy Matching) for messages in total ###
# #print_in_color('\nArrange Statistics - Unique(Fuzzy Matching) for all messages in total','bold')
# append_to_file(result_file,'\n\n\n'+'#'*20+' Statistics - Unique(Fuzzy Matching for all messages in total '+'#'*20+'\n')
# unique_messages=[]
# for item in analyzed_logs_result:
#     #print 'LogPath --> '+item['Log']
#     for block in item['AnalyzedBlocks']:
#         block_lines=block['BlockLines']
#         lines_number=block['BlockLinesSize']
#         is_traceback=block['IsTracebackBlock']
#         to_add = True
#
#         if is_traceback==False:
#             block_lines=unique_list_by_fuzzy(block_lines,fuzzy_match)
#         if is_traceback == True:
#             block_lines=unique_list(block_lines)
#
#         if lines_number>5:
#             block_lines = [l for l in block_lines[-5:]]
#
#         for key in unique_messages:
#             if similar(key[1], str(block_lines)) >= fuzzy_match:
#                 to_add = False
#                 break
#         if to_add == True:
#             unique_messages.append([lines_number,block_lines,item['Log'],is_traceback])
#
# for item in unique_messages:
#     append_to_file(result_file, '\n'+'~' * 40 + item[2] + '~' * 40 + '\n')
#     append_to_file(result_file, '### IsTraceback:'+str(item[3])+'###\n')
#     for line in item[1]:
#         append_to_file(result_file, line + '\n')
#
# ### Fill statistics section - Table of Content: line+index ###
# section_indexes=[]
# messages=[
#     'Extracted Errors/Warnings (raw data)',
#     'Warning, following logs failed on parsing due to non standard date format',
#     'Statistics - Number of Errors/Warnings per log',
#     'Statistics - Unique(Fuzzy Matching per log file',
#     'Statistics - Unique(Fuzzy Matching for all messages in total'
#     ]
# for msg in messages:
#     section_indexes.append({msg:get_file_line_index(result_file,msg)})
# write_list_of_dict_to_file(result_file,section_indexes,'\n\n\n'+'#'*20+' Table of content (Section name --> Line number)'+'#'*20+'\n')
# print 'Execution time:'+str(time.time()-start_time)
# print 'SUCCESS!!!'