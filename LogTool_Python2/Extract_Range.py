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

#!/usr/bin/python
import subprocess,time,os,sys
import itertools
import json
import difflib
import datetime
import collections




### Parameters ###
not_supported_logs=['cinder-rowsflush.log','redis.log','dnsmasq.log']
# Time start #
try:
    time_start=sys.argv[1].strip()
except:
    time_start='2018-10-02 00:04:00'
# Time end #
try:
    time_end=sys.argv[2].strip()
except:
    time_end='2018-10-02 01:04:00'
# Log path #
try:
    log_root_dir=sys.argv[3].strip()
except:
    log_root_dir='/var/log/containers'
# Result file #
try:
    result_file=sys.argv[4]
except:
    result_file='All_Range_Messages.log'
result_file=os.path.join(os.path.abspath('.'),result_file)




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
        print bcolors.OKGREEN + string + bcolors.ENDC
    elif color_or_format =='red':
        print bcolors.FAIL + string + bcolors.ENDC
    elif color_or_format =='yellow':
        print bcolors.WARNING + string + bcolors.ENDC
    elif color_or_format =='blue':
        print bcolors.OKBLUE + string + bcolors.ENDC
    elif color_or_format =='bold':
        print bcolors.BOLD + string + bcolors.ENDC
    else:
        print string

def collect_log_paths(log_root_path):
    logs=[]
    for root, dirs, files in os.walk(log_root_path):
        for name in files:
            if '.log' in name:
                file_abs_path=os.path.join(os.path.abspath(root), name)
                if os.path.getsize(file_abs_path)!=0 and 'LogTool' not in file_abs_path:
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

def get_line_date(line):
    line=line[0:50] # Use first 50 characters to get line timestamp
    # Delta 27 []
    if line.find(']') - line.find('[') == 27:
        try:
            date = line[line.find('[') + 1:line.find(']')]
            date=datetime.datetime.strptime(date.split(' +')[0], "%d/%b/%Y:%H:%M:%S")
            return {'Error': None, 'Date':date.strftime('%Y-%m-%d %H:%M:%S.%f').split('.')[0],'Line':line}
        except Exception, e:
            return {'Error': e, 'Line': line.strip(), 'Date':None}

    # Delta 32 []
    elif line.find(']') - line.find('[') == 32:
        try:
            date = line[line.find('[') + 1:line.find(']')]
            date=datetime.datetime.strptime(date.split(' +')[0], "%a %b %d %H:%M:%S.%f %Y")
            return {'Error': None, 'Date': date.strftime('%Y-%m-%d %H:%M:%S.%f').split('.')[0], 'Line': line}
        except Exception, e:
            return {'Error': e, 'Line': line.strip(),'Date':None}
    else:
        try:
            date=line[0:19].replace('T',' ')
            date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
            return {'Error': None, 'Date': date.strftime('%Y-%m-%d %H:%M:%S').split('.')[0], 'Line': line}
        except Exception,e:
            return {'Error':str(e),'Line':line.strip(),'Date':None}

def analyze_log(log, string, time_grep, file_to_save='Exported.txt'):
    LogDataDic={'Log':log, 'AnalyzedBlocks':[],'TotalNumberOfErrors':0}
    time_grep=time.strptime(time_grep, '%Y-%m-%d %H:%M:%S')
    existing_messages = []
    if log.endswith('.gz'):
        command = "zgrep -n '" + string + "' " + log+" > grep.txt"
    else:
        command="grep -n '"+string+"' "+log+" > grep.txt"
    command_result=exec_command_line_command(command)
    if command_result['ReturnCode']==0:
        lines=open('grep.txt','r').readlines()
        lines=[line for line in lines if string in line[0:60]] #ignore if ERROR for example is not debug level string
        lines_dic={}
        for line in lines:
            lines_dic[line.split(':')[0]]=line[line.find(':')+1:].strip() #{index1:line1,....indexN:lineN}
        indexes=[int(line.split(':')[0]) for line in lines]# [1,2,3,....15,26]
        blocks=list(to_ranges(indexes)) #[(1,2)...(4,80)]
        for block in blocks:
            if block[0]==block[1]:# Single line
                block_lines=[lines_dic[str(block[0])]]
            else:
                block_lines=[lines_dic[str(indx)] for indx in range(block[0],block[1])]
            block_date=get_line_date(block_lines[0]) # Check date only for first line
            if block_date['Error']==None:
                date=time.strptime(block_date['Date'], '%Y-%m-%d %H:%M:%S')
            else:
                print_in_color('Failed to parse date on line: '+str(block_date),'yellow')
                print '--- Failed block lines are: ---'
                for l in block_lines:
                    print l
                continue # Failed on block, continue to another block
            if date < time_grep:
                continue
            LogDataDic['TotalNumberOfErrors']+=1
            block_lines_to_save = [line for line in block_lines]
            block_lines=[line.split(string)[1] for  line in block_lines if string in line] # Block lines split by string and save all after ERROR
             # Raw data to result file
            # Save to file block lines #
            if save_raw_data=='yes':
                append_to_file(file_to_save,'\n'+'~'*20+log+'~'*20+'\n')
                append_to_file(file_to_save, 'Block_Date:'+str(date)+'\n')
                append_to_file(file_to_save, 'BlockLinesTuple:'+str(block)+'\n')
                for l in block_lines_to_save:
                    append_to_file(file_to_save,l+'\n')
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
            print str(l).strip()

def print_dic(dic):
    for k in dic.keys():
        print '~'*80
        print k,' --> ',dic[k]

def write_list_of_dict_to_file(fil, lis,msg_start='',msg_delimeter=''):
    append_to_file(fil,msg_start)
    for l in lis:
        append_to_file(fil,msg_delimeter)
        for k in l.keys():
            append_to_file(fil,str(k)+' --> '+str(l[k])+'\n')

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
    return collections.OrderedDict.fromkeys(lis).keys()




not_standard_logs=[{'Log':item,'LastLine':"Log is in black list by default"} for item in not_supported_logs]
analyzed_logs_result=[]
if __name__ == "__main__":
    empty_file_content(result_file)
    append_to_file(result_file,'\n\n\n'+'#'*20+' Extracted Errors/Warnings (raw data)'+'#'*20)
    start_time=time.time()
    logs=collect_log_paths(log_root_dir)
    #logs=['/var/log/containers/nova/nova-compute.log.2.gz']
    for log in logs:
        print_in_color('--> '+log, 'bold')
        Log_Analyze_Info = {}
        Log_Analyze_Info['Log']=log
        Log_Analyze_Info['IsSingleLine']=is_single_line_file(log)
        # Get the time of last line, if fails will be added to ignored logs
        last_line=get_file_last_line(log)
        last_line_date=get_line_date(last_line)
        Log_Analyze_Info['ParseLogTime']=last_line_date
        if last_line_date['Error']!=None:
            print_in_color(last_line_date['Error'],'yellow')
            not_standard_logs.append({'Log':log,'LogLastLine':last_line.strip()})
                                      #'IsSingleLineLog':Log_Analyze_Info['IsSingleLine'],
                                      #'ParseError':last_line_date['Error'],
                                      #'DateToParse':last_line_date['Date']})
        else:
            if time.strptime(last_line_date['Date'], '%Y-%m-%d %H:%M:%S') > time.strptime(time_grep, '%Y-%m-%d %H:%M:%S'):
                log_result=analyze_log(Log_Analyze_Info['Log'],string_for_grep,time_grep,result_file)
                analyzed_logs_result.append(log_result)

### Fill Failed log Section ###
if len(not_standard_logs)>0:
    print_in_color('Failed to parse the following logs:','yellow')
    print_list(not_standard_logs)

    write_list_of_dict_to_file(result_file,
                               not_standard_logs,
                               '\n\n\n'+'#'*20+' Warning, following logs failed on parsing due to non standard date format '+'#'*20+'\n'+
                               'In Total:'+str(len(not_standard_logs))+'\n',
                               msg_delimeter='~'*100+'\n')


### Fill statistics section ###
print_in_color('\nCollecting statistics','bold')
statistics_list=[{item['Log']:item['TotalNumberOfErrors']} for item in analyzed_logs_result if item['TotalNumberOfErrors']!=0]
total_number_of_all_logs_errors=sum([item['TotalNumberOfErrors'] for item in analyzed_logs_result if item['TotalNumberOfErrors']!=0])
print_list(statistics_list)
write_list_of_dict_to_file(result_file,statistics_list,'\n\n\n'+'#'*20+' Statistics - Number of Errors/Warnings per log '+'#'*20+'\n'+
                           'Total Number of Errors/Warnings is:'+str(total_number_of_all_logs_errors)+'\n')


### Fill Statistics - Unique(Fuzzy Matching) section ###
print_in_color('\nArrange Statistics - Unique(Fuzzy Matching) per log file ','bold')
append_to_file(result_file,'\n\n\n'+'#'*20+' Statistics - Unique(Fuzzy Matching per log file '+'#'*20+'\n')
for item in analyzed_logs_result:
    print 'LogPath --> '+item['Log']
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


### Fill Statistics - Unique(Fuzzy Matching) for messages in total ###
print_in_color('\nArrange Statistics - Unique(Fuzzy Matching) for all messages in total','bold')
append_to_file(result_file,'\n\n\n'+'#'*20+' Statistics - Unique(Fuzzy Matching for all messages in total '+'#'*20+'\n')
unique_messages=[]
for item in analyzed_logs_result:
    print 'LogPath --> '+item['Log']
    for block in item['AnalyzedBlocks']:
        block_lines=block['BlockLines']
        lines_number=block['BlockLinesSize']
        is_traceback=block['IsTracebackBlock']
        to_add = True

        if is_traceback==False:
            block_lines=unique_list_by_fuzzy(block_lines,fuzzy_match)
        if is_traceback == True:
            block_lines=unique_list(block_lines)

        if lines_number>5:
            block_lines = [l for l in block_lines[-5:]]

        for key in unique_messages:
            if similar(key[1], str(block_lines)) >= fuzzy_match:
                to_add = False
                break
        if to_add == True:
            unique_messages.append([lines_number,block_lines,item['Log'],is_traceback])

for item in unique_messages:
    print item
    append_to_file(result_file, '\n'+'~' * 40 + item[2] + '~' * 40 + '\n')
    append_to_file(result_file, '### IsTraceback:'+str(item[3])+'###\n')
    for line in item[1]:
        append_to_file(result_file, line + '\n')

### Fill statistics section - line indexes ###
section_indexes=[]
messages=[
    'Extracted Errors/Warnings (raw data)',
    'Warning, following logs failed on parsing due to non standard date format',
    'Statistics - Number of Errors/Warnings per log',
    'Statistics - Unique(Fuzzy Matching per log file',
    'Statistics - Unique(Fuzzy Matching for all messages in total'
    ]
for msg in messages:
    section_indexes.append({msg:get_file_line_index(result_file,msg)})
print section_indexes
write_list_of_dict_to_file(result_file,section_indexes,'\n\n\n'+'#'*20+' Table of content (Section name --> Line number)'+'#'*20+'\n')
print 'Execution time:'+str(time.time()-start_time)
print 'SUCCESS!!!'