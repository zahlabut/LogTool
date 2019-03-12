#!/usr/bin/python
import subprocess,time,os,sys
import itertools
import json
try:
    from fuzzywuzzy import fuzz
    fuzzy_installed=True
except:
    fuzzy_installed=False

import difflib
import gzip
import re
import datetime


start_time=time.time()

## Grep by time ###
try:
    grep=sys.argv[1].strip()
except:
    grep='2018-11-26 00:04:00'
## Log path ##
try:
    log_root_dir=sys.argv[2].strip()
except:
    log_root_dir='/var/log/containers'
## String for Grep##
try:
    string_for_grep=sys.argv[3].strip()
except:
    string_for_grep=' ERROR '
# Result file
try:
    result_file=sys.argv[4]
except:
    result_file='All_Greps.log'
result_file=os.path.join(os.path.abspath('.'),result_file)

all_data_for_unique_info=[[{'BlockValues':''},1]]
not_supported_logs=['redis.log','swift.log','rabbit@overcloud','cinder-rowsflush.log','.log.swp','karaf.log']
# /var/log/containers/opendaylight/karaf/logs/karaf.log
# /var/log/containers/opendaylight/karaf/logs/karaf.log: ASCII text, with very long lines


fuzzy_match = 0.7

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

def get_file_last_modified(file_path):
    return exec_command_line_command('stat -c "%y" '+file_path)['CommandOutput'].split('.')[0]

def get_file_last_line(log):
    if log.endswith('.gz'):
        return exec_command_line_command('zcat '+log+' | tail -1')['CommandOutput']
    else:
        return exec_command_line_command('tail -1 '+log)['CommandOutput']

def print_in_color(string,color_or_format=None):
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
    for key, group in itertools.groupby(enumerate(iterable),
                                        lambda t: t[1] - t[0]):
        group = list(group)
        yield group[0][1], group[-1][1]

def collect_log_paths(log_root_path):
    logs=[]
    for root, dirs, files in os.walk(log_root_path):
        for name in files:
            if '.log' in name:
                file_abs_path=os.path.join(os.path.abspath(root), name)
                if os.path.getsize(file_abs_path)!=0:
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

def file_content_to_list(file_path):
    if file_path.endswith('.gz'):
        with gzip.open(file_path, 'rb') as f:
            fil_data=f.readlines()
    else:
        with open(file_path, 'r') as f:
            fil_data=f.readlines()
    return fil_data

def get_line_date(line):
    if line.startswith('[')==True:
        date=line[line.find('[')+1:line.find(']')].replace('T',' ')
    else:
        date=line[0:19].replace('T',' ')
    # Delta 27 []
    if line.find(']') - line.find('[') == 27:
        try:
            date = line[line.find('[') + 1:line.find(']')]
            date=datetime.datetime.strptime(date.split(' +')[0], "%d/%b/%Y:%H:%M:%S")
            return date.strftime('%Y-%m-%d %H:%M:%S.%f').split('.')[0]
        except Exception, e:
            return {'Error': e, 'Line': line.strip()}
    # Delta 32 []
    if line.find(']') - line.find('[') == 32:
        try:
            date = line[line.find('[') + 1:line.find(']')]
            date=datetime.datetime.strptime(date.split(' +')[0], "%a %b %d %H:%M:%S.%f %Y")
            return date.strftime('%Y-%m-%d %H:%M:%S.%f').split('.')[0]
        except Exception, e:
            return {'Error': e, 'Line': line.strip()}
    else:
        try:
            time.strptime(date, '%Y-%m-%d %H:%M:%S')
            return date
        except Exception,e:
            return {'Error':e,'Line':line.strip()}
        #return date

def stdout_same_place_print(string):
    string=str(string)
    sys.stdout.flush()
    sys.stdout.write(string+'\r')
    sys.stdout.write("\b")

def get_grep_blocks(log, string, time_grep):
    time_grep=time.strptime(time_grep, '%Y-%m-%d %H:%M:%S')
    indexes=[]
    save_to_file='errors.txt'
    if log.endswith('.gz'):
        command="zgrep -n '"+string+"' "+log+" > "+save_to_file
    else:
        command="grep -n '"+string+"' "+log+" > "+save_to_file
    exec_command_line_command(command)
    lines=open(save_to_file,'r').readlines()
    if len(lines)>0:# not empty file
        for line in lines:
            date=get_line_date(line[line.find(':')+1:])
            line_index=line.split(':')[0]
            if string in line[0:40]: #Eran setup issue, ERROR was in message not as debug level
                try:
                    date=time.strptime(date, '%Y-%m-%d %H:%M:%S')
                except Exception,e:
                    print_in_color('Warning failed to proceed line:\n'+line,'yellow')
                    continue
                if date>time_grep:
                    indexes.append(line_index)
        indexes=[int(i)-1 for i in indexes]
    os.remove(save_to_file)
    return to_ranges(indexes)

def analyze_block(block_lines, block_tuple,log_name):
    result={'BlockTuple':tuple_add(block_tuple,1)}
    if 'traceback' in str(block_lines).lower():
        result['IsTraceback'] = True
        #block_lines=block_lines[-4:]
    else:
        result['IsTraceback'] = False
    lines_keys=[None]
    for line in block_lines:
        line_key=line.split(string_for_grep)[-1].strip()
        to_add = True
        for key in lines_keys:
            if similar(key,line_key) >= fuzzy_match:
                to_add=False
                break
        if to_add==True:
            lines_keys.append(line_key)
    lines_keys.remove(None)
    if lines_keys!=[]:
        result['BlockValues'] = lines_keys
        result['LogName']=log_name
    return result

def print_list(lis):
    for l in lis:
        if l!='':
            print str(l).strip()

def print_dic(dic):
    for k in dic.keys():
        print '~'*80
        print k,' --> ',dic[k]

def tuple_add(tup,int_to_add):
    lis=list(tup)
    lis=[l+1 for l in lis]
    return tuple(lis)

def write_list_of_dict_to_file(fil, lis,msg_start='',msg_delimeter=''):
    append_to_file(fil,msg_start+'\n')
    for l in lis:
        append_to_file(fil,msg_delimeter+'\n')
        for k in l.keys():
            append_to_file(fil,str(k)+' --> '+str(l[k])+'\n')

def write_list_of_dict_and_counter_to_file(fil, lis,msg_start='',msg_delimeter=''):
    append_to_file(fil,msg_start+'\n')
    for l in lis:
        print l
        append_to_file(fil,msg_delimeter+'\n')
        append_to_file(fil,'Counter: --> '+str(l[-1])+'\n')
        for k in l[0].keys():
            if 'list' in str(type(l[0][k])):
                append_to_file(fil,str(k)+' --> \n')
                for item in l[0][k]:
                    append_to_file(fil,item+'\n')
            else:
                append_to_file(fil,str(k)+' --> '+str(l[0][k])+'\n')

def is_single_line_file(log):
    if log.endswith('.gz'):
        result=exec_command_line_command('zcat ' + log + ' | wc -l')['CommandOutput'].strip()
    else:
        result = exec_command_line_command('cat ' + log + ' | wc -l')['CommandOutput'].strip()
    if result=='1':
        return True
    else:
        return False

def zip_file(file):
    with gzip.open(file+'.zip', 'wb') as f:
        f.write(open(file,'r').read())

def check_time(time_string):
    try:
        t=time.strptime(time_string, '%Y-%m-%d %H:%M:%S')
        return True
    except:
        return False


if __name__ == "__main__":
    empty_file_content(result_file)
    f=open(result_file,'a')
    logs=collect_log_paths(log_root_dir)
    statistics_list=[] #list for statistics
    failed_logs=[]
    total_nymber_of_errors=0
    for log in logs:
        print '--> '+log
        number_of_tracbacks, number_of_others = 0, 0 # Counters for statistics #
        last_line=get_file_last_line(log)
        # #Skip log if its content is a single line message
        # if is_single_line_file(log)==True:
        #     failed_logs.append({'Log':log,'Error':'Single line log file','Line':file_content_to_list(log)})
        #     continue
        # Not all logs has the same format, not supported logs will be ignored
        last_line_date=get_line_date(last_line)
        if str(type(last_line_date))=="<type 'dict'>":
            last_line_date['Log']=log
            last_line_date['SingleLineFile']=is_single_line_file(log)
            failed_logs.append(last_line_date)
            continue
        #Skip log if too old #
        if time.strptime(last_line_date, '%Y-%m-%d %H:%M:%S') > time.strptime(grep, '%Y-%m-%d %H:%M:%S'):
            log_data = file_content_to_list(log)
            greped_bloks=get_grep_blocks(log,string_for_grep,grep)
            for block_tuple in greped_bloks:
                if block_tuple[0]!=block_tuple[1]: # Not a single line block
                    block_lines=log_data[block_tuple[0]:block_tuple[1]+1]
                if block_tuple[0]==block_tuple[1]: # Single line block
                    block_lines=log_data[block_tuple[0]:block_tuple[1]+1]
                msg = '\n'+'~' * 30 + log + ' ' + str(tuple_add(block_tuple, 1)) + '~' * 30 + '\n'
                append_to_file(result_file,msg)
                for line in block_lines:
                    append_to_file(result_file,line)
                analyze_block_result=analyze_block(block_lines,block_tuple,log)
                if analyze_block_result['IsTraceback']==True:
                    number_of_tracbacks+=1
                    total_nymber_of_errors+=1
                if analyze_block_result['IsTraceback']==False:
                    number_of_others+=1
                    total_nymber_of_errors+=1
                # Add to statistic list if not fuzzy matched found #
                to_add = True
                for item in all_data_for_unique_info:
                    if similar(item[0]['BlockValues'],analyze_block_result['BlockValues']) >= fuzzy_match:
                        to_add=False
                        item_index=all_data_for_unique_info.index(item)
                        all_data_for_unique_info[item_index]=[item[0],item[1]+1]
                        break
                if to_add==True:
                    all_data_for_unique_info.append([analyze_block_result,1])
            if number_of_others+number_of_tracbacks!=0:
                statistics_list.append({'Log_Path':log,'NumberOfTracebacks':number_of_tracbacks,'NumberOfNonTracebacks':number_of_others})
    print '\n\n--------------------------- Statistics - in total:' +str(total_nymber_of_errors)+ ' ------------------------------------'
    print_list(statistics_list)
    print '\n\n--------------------- Not standard formatted logs - in total: '+str(len(failed_logs))+ ' --------------------------'
    failed_logs_to_print=[str(item['Error'])+' --> '+item['Log'] for item in failed_logs]
    print_in_color('Warning - '+str(len(failed_logs))+' logs has been ignored due to not standard format','yellow')
    print_list(failed_logs_to_print)
    print '\n\n---------------------- Statistics - Unique(Fuzzy Matching) --------------------------'
    all_data_for_unique_info.remove([{'BlockValues':''},1])
    print_list(all_data_for_unique_info)
    write_list_of_dict_to_file(result_file,statistics_list,'\n'*10+'#'*30+' Statistics - in total:'+str(total_nymber_of_errors)+' '+'#'*30,'~'*80)
    write_list_of_dict_to_file(result_file, failed_logs, '\n' * 10 + '#' * 20 + ' Not standard formatted logs - in total:' +(str(len(failed_logs)))+' '+ '#' * 20, '~' * 80)
    write_list_of_dict_and_counter_to_file(result_file, all_data_for_unique_info, '\n' * 10 + '#' * 30 + ' Unique(Fuzzy Matching) ' + '#' * 30, '~' * 80)
    end_time=time.time()
    print_in_color('OK - Execution Time:'+str(end_time-start_time)+'[sec]','green')
    print 'SUCCESS!!!'
