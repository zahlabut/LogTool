#!/usr/bin/python
import subprocess,time,os,sys
import itertools
import json
import warnings
warnings.simplefilter("ignore", UserWarning)
try:
    from fuzzywuzzy import fuzz
    fuzzy_installed=True
except:
    fuzzy_installed=False
import difflib
import gzip
import datetime
import operator
import collections

### Parameters ###
fuzzy_match = 0.6
not_supported_logs=['.swp','.login']

# Grep by time #
try:
    time_grep=sys.argv[1].strip()
except:
    time_grep='2018-01-01 00:00:00'
# Log path #
try:
    log_root_dir=sys.argv[2].strip()
except:
    log_root_dir='/var/log/containers'
# String for Grep #
try:
    string_for_grep=sys.argv[3].strip()
except:
    string_for_grep=' ERROR '
# Result file #
try:
    result_file=sys.argv[4]
except:
    result_file='All_Greps.log'
result_file=os.path.join(os.path.abspath('.'),result_file)
# Save raw data messages #
try:
    save_raw_data=sys.argv[5]
except:
    save_raw_data='yes'

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

def get_file_last_line(log, tail_lines='1'):
    if log.endswith('.gz'):
        return exec_command_line_command('zcat '+log+' | tail -'+tail_lines)['CommandOutput']
    else:
        return exec_command_line_command('tail -'+tail_lines+' '+log)['CommandOutput']

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

def similar(a, b):
    if fuzzy_installed==True:
        return fuzz.ratio(str(a),str(b))/100.0
    else:
        return difflib.SequenceMatcher(None, str(a), str(b)).ratio()

def to_ranges(iterable):
    iterable = sorted(set(iterable))
    for key, group in itertools.groupby(enumerate(iterable), lambda t: t[1] - t[0]):
        group = list(group)
        yield group[0][1], group[-1][1]

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

def write_list_to_file(fil, list):
    for item in list:
        append_to_file(fil, '\n'+str(item)+'\n')

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

# Parsers for not standard logs
def parse_rabbit_log(log,string_for_grep):
    unique_messages=[]
    content_as_list=open(log, 'r').read().split('\n\n')
    content_as_list=[item for item in content_as_list if string_for_grep in item]
    for block in content_as_list:
        to_add=True
        for key in unique_messages:
            if similar(key, block) >= fuzzy_match:
                to_add = False
                break
        if to_add == True:
            unique_messages.append(block)
    return {log:unique_messages}

# Extract WARN or ERROR messages from log and return unique messages #
def extract_log_unique_greped_lines(log, string_for_grep):
    unique_messages = []
    if os.path.exists('grep.txt'):
        os.remove('grep.txt')
    if log.endswith('.gz'):
        command = "zgrep -n -A3 '" + string_for_grep + "' " + log+" > grep.txt"
    else:
        command="grep -n -A3 '"+string_for_grep+"' "+log+" > grep.txt"
    command_result=exec_command_line_command(command)
    if command_result['ReturnCode']==0:
        content_as_list=open('grep.txt','r').read().split('--\n')
    else: #grep.txt is empty
        return {log: unique_messages}
    content_as_list=[item[0:1000] if len(item)>1000 else item.strip() for item in content_as_list] # If line is bigger than 100 cut it
    for block in content_as_list:
        to_add=True
        for key in unique_messages:
            if similar(key, block) >= fuzzy_match:
                to_add = False
                break
        if to_add == True:
            unique_messages.append(block)

    if 'csh.login' in log:
        print 'hete'*100
        sys.exit(1)


    return {log:unique_messages}

def parse_overcloud_install_log(log, string_for_grep):
    unique_messages = []
    content_as_list=[item for item in open(log,'r').readlines() if string_for_grep in item]
    for block in content_as_list:
        if len(block)>1000:
            block = block[0:1000]+'... \nLogTool --> The above line is to long!!!'
        to_add=True
        for key in unique_messages:
            if similar(key, block) >= fuzzy_match:
                to_add = False
                break
        if to_add == True:
            unique_messages.append(block)
    return {log:unique_messages}

not_standard_logs=[]
analyzed_logs_result=[]
not_standard_logs_unique_messages=[] #Use it for all not standard log files, add to this list {log_path:[list of all unique messages]}
if __name__ == "__main__":
    empty_file_content(result_file)
    append_to_file(result_file,'\n\n\n'+'#'*20+' Raw Data - Raw Data - extracted Errors/Warnings from standard OSP logs since: '+time_grep+'#'*20)
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
            #print_in_color(log+' --> \n'+str(last_line_date['Error']),'yellow')
            # Check if last line contains: proper debug level: INFO or WARN or ERROR string
            log_last_ten_lines=get_file_last_line(log,'10')
            if ('ERROR' in log_last_ten_lines or 'WARN' in log_last_ten_lines or 'INFO' in log_last_ten_lines) is False:
                not_standard_logs.append({'Log':log,'Last_Lines':'\n'+log_last_ten_lines})
            # Extract all ERROR or WARN lines and provide the unique messages
            if 'WARNING' in string_for_grep:
                string_for_grep='WARN'
            if 'ERROR' in string_for_grep:
                string_for_grep='ERROR'
            not_standard_logs_unique_messages.append(extract_log_unique_greped_lines(log, string_for_grep))
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
                               '\n\n\n'+'#'*20+' Warning - not standard logs, no debug indication string detected in log content '+'#'*20+'\n'+
                               'In Total:'+str(len(not_standard_logs))+'\n',
                               msg_delimeter='~'*100+'\n')

### Fill statistics section ###
print_in_color('\nAggregating statistics','bold')
statistics_dic={item['Log']:item['TotalNumberOfErrors'] for item in analyzed_logs_result if item['TotalNumberOfErrors']!=0}
statistics_dic = sorted(statistics_dic.items(), key=operator.itemgetter(1))
statistics_list=[{item[0]:item[1]} for item in statistics_dic]
total_number_of_all_logs_errors=sum([item['TotalNumberOfErrors'] for item in analyzed_logs_result if item['TotalNumberOfErrors']!=0])
if 'error' in string_for_grep.lower():
    statistics_list.insert(0,{'Total_Number_Of_Errors':total_number_of_all_logs_errors})
if 'warn' in string_for_grep.lower():
    statistics_list.insert(0,{'Total_Number_Of_Warnings':total_number_of_all_logs_errors})
print_list(statistics_list)
write_list_of_dict_to_file(result_file,statistics_list,
                           '\n\n\n'+'#'*20+' Statistics - Number of Errors/Warnings per standard OSP log since: '+time_grep+'#'*20+'\n'+
                           'Total Number of Errors/Warnings is:'+str(total_number_of_all_logs_errors)+'\n')

### Fill Statistics - Unique(Fuzzy Matching) section ###
#print_in_color('\nArrange Statistics - Unique(Fuzzy Matching) per log file ','bold')
append_to_file(result_file,'\n\n\n'+'#'*20+' Statistics - Unique(Fuzzy Matching per standard OSP log file since: '+time_grep+'#'*20+'\n')
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

### Statistics - Unique messages per not standard log file, since ever  ###
append_to_file(result_file,'\n\n\n'+'#'*20+' Statistics - Unique messages per not standard log file, since ever '+'#'*20+'\n')
for dir in not_standard_logs_unique_messages:
    key=dir.keys()[0]
    if len(dir[key])>0:
        append_to_file(result_file,'\n'+'~'*40+key+'~'*40+'\n')
        write_list_to_file(result_file,dir[key])

### Fill Statistics - Unique(Fuzzy Matching) for messages in total ###
#print_in_color('\nArrange Statistics - Unique(Fuzzy Matching) for all messages in total','bold')
append_to_file(result_file,'\n\n\n'+'#'*20+' Statistics - Unique(Fuzzy Matching for all messages in total for standard OSP logs '+'#'*20+'\n')
unique_messages=[]
for item in analyzed_logs_result:
    #print 'LogPath --> '+item['Log']
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
    append_to_file(result_file, '\n'+'~' * 40 + item[2] + '~' * 40 + '\n')
    append_to_file(result_file, '### IsTraceback:'+str(item[3])+'###\n')
    for line in item[1]:
        append_to_file(result_file, line + '\n')

### Fill statistics section - Table of Content: line+index ###
section_indexes=[]
messages=[
    'Raw Data - extracted Errors/Warnings from standard OSP logs since: '+time_grep,
    'Warning - not standard logs, no debug indication string detected in log content',
    'Statistics - Number of Errors/Warnings per standard OSP log since: '+time_grep,
    'Statistics - Unique(Fuzzy Matching per standard OSP log file since: '+time_grep,
    'Statistics - Unique messages per not standard log file, since ever',
    'Statistics - Unique(Fuzzy Matching for all messages in total for standard OSP logs'
    ]
for msg in messages:
    section_indexes.append({msg:get_file_line_index(result_file,msg)})
write_list_of_dict_to_file(result_file,section_indexes,'\n\n\n'+'#'*20+' Table of content (Section name --> Line number)'+'#'*20+'\n')
print 'Execution time:'+str(time.time()-start_time)
print 'SUCCESS!!!'