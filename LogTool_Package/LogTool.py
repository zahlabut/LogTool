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
from string import digits
import re
import configparser
from sys import platform
if 'linux' not in platform:
    print('Your OS: '+platform+' is not supported! \nThis tool is running on Linux only!')
    sys.exit(1)

class LogTool:
    # Class attrributes
    fuzzy_match = 0.55
    time_grep = None
    log_root_dir = None
    string_for_grep = None
    log_tool_result_file = None
    magic_words = None
    ignore_strings = None
    logs_to_ignore = None
    python_exceptions = None
    create_logtool_result_file = None
    analyze_log_as_not_standard = None
    save_standard_logs_raw_data_file = None
    save_not_standard_logs_raw_data_file = None

    def __init__(self, log):
        self.log=log

    @staticmethod
    def remove_digits_from_string(s):
        remove_digits = str.maketrans('', '', digits)
        return str(s).translate(remove_digits)

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def similar(a, b):
        return difflib.SequenceMatcher(None,LogTool.remove_digits_from_string(a), LogTool.remove_digits_from_string(b)).ratio()

    @staticmethod
    def collect_log_paths(log_root_dir, logs_to_ignore):
        logs=[]
        black_list=logs_to_ignore
        black_list=logs_to_ignore
        for path in log_root_dir:
            for root, dirs, files in os.walk(path):
                for name in files:
                    if '.log' in name or 'messages' in name:
                        to_add=False
                        file_abs_path=os.path.join(os.path.abspath(root), name)
                        if os.path.getsize(file_abs_path)!=0 and 'LogTool' in file_abs_path:
                            if 'Jenkins_Job_Files' in file_abs_path:
                                to_add = True
                            if 'Zuul_Log_Files' in file_abs_path:
                                to_add=True
                        if os.path.getsize(file_abs_path):
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
            sys.exit('Failed - No log files detected in: '+log_root_dir)
        return filtered_logs

    @staticmethod
    def empty_file_content(log_file_name):
        f = open(log_file_name, 'w')
        f.write('')
        f.close()

    @staticmethod
    def append_to_file(log_file, msg):
        log_file = open(log_file, 'a')
        log_file.write(msg)

    @staticmethod
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
            match = re.search(r'(...)-\d{2}\s\d{2}:\d{2}:\d{2}', line)  #Oct-15 13:30:46
            if match:
                date = datetime.datetime.strptime(year+match.group(), '%Y%b-%d %H:%M:%S')
                return {'Error': None, 'Line': None, 'Date': str(date)}
            match = re.search(r'(...)\s\s\d{1}\s\d{2}:\d{2}:\d{2}', line) #Jul  6 22:19:00
            if match:
                date=datetime.datetime.strptime(year+match.group(), '%Y%b  %d %H:%M:%S')
                return {'Error': None, 'Line': None, 'Date': str(date)}
            if len(line)>100:
                line=line[0:100]+'...'
            return {'Error': 'Unknown or missing timestamp in line!', 'Line': line.strip(), 'Date':None}
        except Exception as e:
            return {'Error': str(e), 'Line': line.strip(), 'Date':None}

    @staticmethod
    def print_list(lis):
        for l in lis:
            if l!='':
                print(str(l).strip())

    @staticmethod
    def print_dic(dic):
        for k in list(dic.keys()):
            print('~'*80)
            print(k,' --> ',dic[k])

    @staticmethod
    def write_list_of_dict_to_file(fil, lis,msg_start='',msg_delimeter=''):
        LogTool.append_to_file(fil,msg_start)
        for l in lis:
            LogTool.append_to_file(fil,msg_delimeter)
            for k in l.keys():
                LogTool.append_to_file(fil,str(k)+' --> '+str(l[k])+'\n')

    @staticmethod
    def write_list_to_file(fil, list, add_new_line=True):
        for item in list:
            if add_new_line==True:
                LogTool.append_to_file(fil, '\n'+str(item)+'\n')
            else:
                LogTool.append_to_file(fil, '\n'+str(item))

    @staticmethod
    def unique_list_by_fuzzy(lis,fuzzy):
        unique_messages=[]
        for item in lis:
            to_add = True
            for key in unique_messages:
                if LogTool.similar(key, str(item)) >= fuzzy:
                    to_add = False
                    break
            if to_add == True:
                unique_messages.append(str(item))
        return unique_messages

    @staticmethod
    def get_file_line_index(fil,line):
        return LogTool.exec_command_line_command("grep -n '"+line+"' "+fil)['CommandOutput'].split(':')[0]

    @staticmethod
    def unique_list(lis):
        return list(collections.OrderedDict.fromkeys(lis).keys())

    @staticmethod
    #This function is used for Non Standard logs only
    def ignore_block(block, ignore_strings, indicator_line=2):
        block_lines=block.splitlines()
        if len(block_lines)<3:
            return False
        for string in ignore_strings:
            if string.lower() in block_lines[indicator_line].lower():
                return True
        return False

    @staticmethod
    def find_all_string_matches_in_line(line, string):
        line,string=line.lower(),string.lower()
        if string=='\|err\|':
            return [(i.start(), i.start() + len(string)-2) for i in re.finditer(string.lower(), line.lower())]
        else:
            return [(i.start(),i.start()+len(string)) for i in re.finditer(string.lower(), line.lower())]

    @staticmethod
    def create_underline(line, list_of_strings):
        underline=''
        line = str(line).lower()
        lis_line=[' ' if char!='\t' else '\t' for char in line]
        strings=[string.lower() for string in list_of_strings]
        for string in strings:
            matches=LogTool.find_all_string_matches_in_line(line,string)
            for match in matches:
                for start in range(match[0],match[1]):
                    lis_line[start]='^'
        underline=''
        for c in lis_line:
            underline+=c
        return underline

    @staticmethod
    def escape_ansi(line):
        ansi_escape =re.compile(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')
        return ansi_escape.sub('', line)

    @staticmethod
    def sort_list_by_index(lis, index):
        return (sorted(lis, key=lambda x: x[index]))

    def cut_huge_block(self, block, limit_line_size=150, number_of_characters_after_match=120,number_of_characters_before_match=50):
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
        block_lines=[LogTool.escape_ansi(line) for line in block_lines]
        new_block=''
        matches = []
        for line in block_lines:
            for string in self.magic_words+self.python_exceptions:
                match_indexes=LogTool.find_all_string_matches_in_line(line.lower(),string.lower())
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
                unique_matches = LogTool.unique_list_by_fuzzy(matches, 0.2) #To reduce execution time
            else:
                unique_matches = LogTool.unique_list_by_fuzzy(matches, self.fuzzy_match)
            for item in unique_matches:
                new_block+=item+'\n'
                new_block+=LogTool.create_underline(item,self.magic_words+self.python_exceptions)+'\n'
        if matches==[]: #Nothing was found, so it's not relevant block
            new_block=None
        # Drop if not relevant block using "ignore_block"
        if self.ignore_block(block,self.ignore_strings)==True:
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
    def extract_log_unique_greped_lines(self):
        temp_grep_result_file = 'zahlabut.txt'
        unique_messages = []
        if os.path.exists(temp_grep_result_file):
            os.remove(temp_grep_result_file)
        commands=["grep -in -A7 -B2 '" + self.string_for_grep.lower() + "' " + self.log+" >> "+temp_grep_result_file]
        if 'error' in self.string_for_grep.lower():
            commands.append("grep -in -A7 -B2 traceback " + self.log+" >> "+temp_grep_result_file+"; echo -e '--' >> "+temp_grep_result_file)
            commands.append('grep -in -E ^stderr: -A7 -B2 '+self.log+' >> '+temp_grep_result_file+"; echo -e '--' >> "+temp_grep_result_file)
            commands.append('grep -n -A7 -B2 STDERR ' + self.log + ' >> '+temp_grep_result_file+"; echo -e '--' >> "+temp_grep_result_file)
            commands.append('grep -in -A7 -B2 failed ' + self.log + ' >> '+temp_grep_result_file+"; echo -e '--' >> "+temp_grep_result_file)
            commands.append("grep -in -A7 -B2 fatal " + self.log + ' >> ' + temp_grep_result_file+"; echo -e '--' >> "+temp_grep_result_file)
            commands.append('grep -in -A7 -B2 critical ' + self.log + ' >> ' + temp_grep_result_file+"; echo -e '--' >> "+temp_grep_result_file)
            commands.append('grep -in -A7 -B2 |ERR| ' + self.log + ' >> ' + temp_grep_result_file+"; echo -e '--' >> "+temp_grep_result_file)
            for string in self.python_exceptions:
                commands.append(
                    'grep -n -A7 -B2 '+string+' ' + self.log + ' >> ' + temp_grep_result_file + "; echo -e '--' >> " + temp_grep_result_file)
        if '/var/log/messages' in self.log:
            if 'error' in self.string_for_grep.lower():
                string_for_grep='level=error'
            if 'warn' in self.string_for_grep.lower():
                string_for_grep = 'level=warn'
            commands = ["grep -n '" + string_for_grep + "' " + self.log + " > "+temp_grep_result_file]
        if 'consoleFull' in self.log:
            string_for_grep=string_for_grep+'\|background:red\|fatal:'
            commands = ["grep -n -A7 -B2 '" + string_for_grep.replace(' ','') + "' " + self.log + " > "+temp_grep_result_file]
        commands=[command.replace('grep','zgrep') if self.log.endswith('.gz') else command for command in commands]
        command=''
        for com in commands:
            command+=com+';'
        LogTool.exec_command_line_command(command)
        # Read temp_grep_result_file txt and create list of blocks
        if os.path.exists(temp_grep_result_file) and os.path.getsize(temp_grep_result_file)!=0:
            temp_data=open(temp_grep_result_file,'r').read()
            if '--\n' in temp_data:
                list_of_blocks=temp_data.split('--\n')
            else:
                list_of_blocks = [temp_data]
        else: #zahlabut.txt is empty
            return {'UniqueMessages': unique_messages, 'AnalyzedBlocks': len(unique_messages), 'Log': self.log}
        # Pass through all blocks and normilize the size (huge blocks oredering) and filter it out if not relevant block is detected
        list_of_blocks=[self.cut_huge_block(block)+'\n' for block in list_of_blocks if self.cut_huge_block(block)!=None]
        # Fill out "relevant_blocks" by filtering out all "ignore strings" and by "third_line" if such a line was already handled before
        relevant_blocks = []
        third_lines = []
        for block in list_of_blocks:
            block_lines=block.splitlines()
            if len(block_lines)>=6:# Do nothing if len of blocks is less than 4
                third_line=block_lines[2:5]
                third_line=LogTool.remove_digits_from_string(third_line)
                if third_line not in third_lines:
                    third_lines.append(third_line)
                    relevant_blocks.append(block)
        # Run fuzzy match
        number_of_blocks=len(relevant_blocks)
        for block in relevant_blocks:
            to_add=True
            for key in unique_messages:
                if LogTool.similar(key, block) >= self.fuzzy_match:
                    to_add = False
                    break
            if to_add == True:
                unique_messages.append(block)
        if os.path.exists(temp_grep_result_file):
            os.remove(temp_grep_result_file)
        return {'UniqueMessages':unique_messages,'AnalyzedBlocks':len(unique_messages),'Log':self.log}

    def get_file_last_line(self, tail_lines='1'):
        command='cat ' + self.log + ' | tail -' + tail_lines
        if self.log.endswith('.gz'):
            command=command.replace('cat','zcat')
        try:
            return LogTool.exec_command_line_command(command)['CommandOutput']
        except Exception as e:
            print (e)
            return ''

    #log_result = obj.analyze_log(string_for_grep, time_grep, last_line_date['Date'])
    def analyze_log(self, last_line_date):
        grep_file='zahlabut.txt'
        strings=[]
        string=self.string_for_grep
        third_lines=[]
        LogDataDic={'Log':self.log, 'AnalyzedBlocks':[],'TotalNumberOfErrors':0}
        time_grep=time.strptime(self.time_grep, '%Y-%m-%d %H:%M:%S')
        last_line_date=time.strptime(last_line_date, '%Y-%m-%d %H:%M:%S')
        existing_messages = []
        # Let's check if log has standard DEBUG level
        is_standard_log=False
        last_ten_lines=self.get_file_last_line('10')
        last_ten_lines=[line[0:100] for line in last_ten_lines.splitlines()]
        for level in ['ERROR','CRITICAL','FATAL','TRACE','|ERR|','DEBUG','INFO','WARN']:
            if level in str(last_ten_lines):
                is_standard_log=True
                break
        # Sorry, but this block will change the "is_standard_log" to False,
        # once by default log is listed in "analyze_log_as_not_standard"
        for item in self.analyze_log_as_not_standard:
            if item in self.log:
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
            strings = self.python_exceptions+[' ' + item for item in self.magic_words]
            for item in strings:
                command+="grep -B2 -A7 -in '"+item+"' " + self.log + " >> "+grep_file+";echo -e '--' >> "+grep_file+';'
        if is_standard_log==True:
            for item in strings+self.python_exceptions:
                command+="grep -B2 -A7 -in '"+item+"' " +self.log+ " >> "+grep_file+";echo -e '--' >> "+grep_file+';'
        if self.log.endswith('.gz'):
            command.replace('grep','zgrep')
        self.exec_command_line_command(command)
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
            block_date=self.get_line_date(block)
            if block_date['Error']==None:
                date=time.strptime(block_date['Date'], '%Y-%m-%d %H:%M:%S')
            else:
                self.print_in_color('Failed to get block date\n: '+block_date['Line'],'yellow')
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
                    third_line=self.remove_digits_from_string(third_line)
                else:
                    third_line=block_lines[0]
                    if len(third_line) > 1000:
                        third_line = third_line[0:1000]
                    third_line=self.remove_digits_from_string(third_line)
                # Block is relevant only when the debug level or python standard exeption is in the first 60 characters in THIRD LINE (no digits in it)
                relevant_block=False
                if is_standard_log==True:
                    cut_line = third_line[0:60].lower()
                    legal_debug_strings = strings
                    legal_debug_strings.append('warn')
                    for item in legal_debug_strings+self.python_exceptions:
                        if item.lower() in cut_line.lower():
                            relevant_block=True
                            break
                if is_standard_log==False:
                    relevant_block=True
                if relevant_block==True:
                    if third_line not in third_lines:
                        third_lines.append(third_line)
                        block=self.cut_huge_block(block)
                        if block!=None:
                            block_lines=block.splitlines()
                            LogDataDic['TotalNumberOfErrors'] += 1
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
                        if self.similar(key[1], str(block_lines)) >=self.fuzzy_match:
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
            unique_date=self.get_line_date(str(dic['BlockLines']))
            if unique_date['Error']==None:
                unique_block_date=unique_date['Date']
            else:
                unique_block_date='No timestamp in block, last  "parsed date" was used!'
            dic['BlockDate']=unique_block_date
            dic['Log']=self.log
            LogDataDic['AnalyzedBlocks'].append(dic)
        if os.path.exists(grep_file):
            os.remove(grep_file)
        return LogDataDic

    def is_single_line_file(self):
        if self.log.endswith('.gz'):
            result=LogTool.exec_command_line_command('zcat ' + self.log + ' | wc -l')['CommandOutput'].strip()
        else:
            result = LogTool.exec_command_line_command('cat ' + self.log + ' | wc -l')['CommandOutput'].strip()
        if result=='1':
            return True
        else:
            return False

# Load *ini file
config = configparser.ConfigParser()
if len(sys.argv) > 1:
    conf_file=sys.argv[1]
else:
    conf_file = 'conf.ini'
print

LogTool.print_in_color('Provided configuration file is: '+conf_file,'green')

config.read(conf_file)
LogTool.time_grep = config.get("Settings", "time_grep")
LogTool.log_root_dir = eval(config.get("Settings", "log_root_dir"))
LogTool.string_for_grep = config.get("Settings", "string_for_grep")
LogTool.log_tool_result_file = config.get("Settings", "log_tool_result_file")
LogTool.magic_words = eval(config.get("Settings", "magic_words"))
LogTool.ignore_strings = eval(config.get("Settings", "ignore_strings"))
LogTool.logs_to_ignore = eval(config.get("Settings", "logs_to_ignore"))
LogTool.python_exceptions = eval(config.get("Settings", "python_exceptions"))
LogTool.create_logtool_result_file = config.get("Settings", "create_logtool_result_file").lower()
LogTool.log_tool_result_file = os.path.join(os.path.abspath('.'), LogTool.log_tool_result_file)
LogTool.analyze_log_as_not_standard = eval(config.get("Settings", "analyze_log_as_not_standard"))
LogTool.save_standard_logs_raw_data_file = eval(config.get("Settings", "save_standard_logs_raw_data_file"))
LogTool.save_not_standard_logs_raw_data_file = eval(config.get("Settings", "save_not_standard_logs_raw_data_file"))



def start_analyzing():
    # Start the process
    analyzed_logs_result=[]
    not_standard_logs_unique_messages=[] #Use it for all NOT STANDARD log files, add to this list {log_path:[list of all unique messages]}
    if LogTool.create_logtool_result_file!='no':
        LogTool.empty_file_content(LogTool.log_tool_result_file)
    start_time=time.time()
    logs=LogTool.collect_log_paths(LogTool.log_root_dir, LogTool.logs_to_ignore)
    for log in logs:
        obj=LogTool(log)
        LogTool.print_in_color(log,'bold')
        # Skip log file if bigger than 1GB, save this information into not standard logs section
        log_size = os.path.getsize(obj.log)
        if log_size > 1024 * 1024 * 1024:  # 1GB
            LogTool.print_in_color(log + ' size is too big, skipped!!!', 'yellow')
            if LogTool.create_logtool_result_file != 'no':
                LogTool.append_to_file(LogTool.log_tool_result_file,'~'*100+'\nWARNING the size of:'+obj.log+' is: '
                            + str(log_size /(1024.0*1024.0*1024.0)) + ' [GB] LogTool is hardcoded to support log files up to 1GB, this log was skipped!\n')
            continue
        Log_Analyze_Info = {}
        Log_Analyze_Info['Log']=obj.log
        Log_Analyze_Info['IsSingleLine']=obj.is_single_line_file()
        # Try to check if there is a known timestamp in last 100 lines
        last_line=obj.get_file_last_line('100')
        is_known_time_format=False
        for line in last_line.splitlines():
            last_line_date=LogTool.get_line_date(line)
            if last_line_date['Error']==None:
                is_known_time_format=True
                break
        Log_Analyze_Info['ParseLogTime']=last_line_date
        if is_known_time_format==True:
            if time.strptime(last_line_date['Date'], '%Y-%m-%d %H:%M:%S') >= time.strptime(LogTool.time_grep, '%Y-%m-%d %H:%M:%S'):
                log_result=obj.analyze_log(last_line_date['Date'])
                analyzed_logs_result.append(log_result)
        else:
            if 'WARNING' in LogTool.string_for_grep:
                string_for_grep='WARN'
            if 'ERROR' in LogTool.string_for_grep:
                string_for_grep=' ERROR'
            not_standard_logs_unique_messages.append(obj.extract_log_unique_greped_lines())

    # Generate LogTool result file
    if LogTool.create_logtool_result_file!='no':
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
        LogTool.append_to_file(LogTool.log_tool_result_file,info)

        ### Fill statistics section for Standard OSP logs###
        LogTool.print_in_color('\nAggregating statistics for Standard OSP logs','bold')
        statistics_dic={item['Log']:item['TotalNumberOfErrors'] for item in analyzed_logs_result if item['TotalNumberOfErrors']>=1}
        statistics_dic = sorted(list(statistics_dic.items()), key=operator.itemgetter(1))
        statistics_list=[{item[0]:item[1]} for item in statistics_dic]
        total_number_of_all_logs_errors=sum([item['TotalNumberOfErrors'] for item in analyzed_logs_result if item['TotalNumberOfErrors']!=0])
        statistics_list.insert(0,{'Total_Number_Of_'+str(string_for_grep).replace(' ','')+'s':total_number_of_all_logs_errors})
        LogTool.print_list(statistics_list)
        LogTool.write_list_of_dict_to_file(LogTool.log_tool_result_file,statistics_list,
                                   '\n\n\n'+'#'*20+' Statistics - Number of Errors/Warnings per Standard OSP log since: '+LogTool.time_grep+' '+'#'*20+'\n')


        ### Fill statistics section for Not Standard OSP logs###
        LogTool.print_in_color('\nAggregating statistics for Not Standard OSP logs','bold')
        statistics_list = [[item['Log'],item['AnalyzedBlocks']] for item in not_standard_logs_unique_messages if item['AnalyzedBlocks']!=0]
        statistics_list = LogTool.sort_list_by_index(statistics_list, 1)
        total_number_of_errors=sum([i[1] for i in statistics_list])
        statistics_list.insert(0,['Total_Number_Of_'+string_for_grep.replace(' ','')+'s',total_number_of_errors])
        LogTool.print_list(statistics_list)
        LogTool.append_to_file(LogTool.log_tool_result_file,'\n\n\n'+'#'*20+' Statistics - Number of Errors/Warnings per Not Standard OSP log since ever '+'#'*20)
        LogTool.write_list_to_file(LogTool.log_tool_result_file,statistics_list,False)



        ### Fill Statistics - Unique(Fuzzy Matching) section ###
        #print_in_color('\nArrange Statistics - Unique(Fuzzy Matching) per log file ','bold')
        LogTool.append_to_file(LogTool.log_tool_result_file,'\n\n\n'+'#'*20+' Exported unique messages, per STANDARD OSP log file since: '+LogTool.time_grep+'#'*20+'\n')
        common_list_of_all_blocks=[]
        for item in analyzed_logs_result:
            for block in item['AnalyzedBlocks']:
                common_list_of_all_blocks.append(block)
        for block in sorted(common_list_of_all_blocks,key=lambda i: i['BlockDate']):
            LogTool.append_to_file(LogTool.log_tool_result_file, '\n'+'-'*30+' LogPath: ' + block['Log']+' '+'-'*30+' \n')
            LogTool.append_to_file(LogTool.log_tool_result_file, 'IsTracebackBlock:' + str(block['IsTracebackBlock'])+'\n')
            LogTool.append_to_file(LogTool.log_tool_result_file, 'UniqueCounter:' + str(block['UniqueCounter'])+'\n')
            LogTool.append_to_file(LogTool.log_tool_result_file, 'AnalyzedBlockLinesSize:' + str(block['AnalyzedBlockLinesSize']) + '\n')
            LogTool.append_to_file(LogTool.log_tool_result_file, 'BlockDate:' + str(block['BlockDate']) + '\n')
            LogTool.append_to_file(LogTool.log_tool_result_file, 'Log:' + str(block['Log']) + '\n')
            for line in block['BlockLines']:
                LogTool.append_to_file(LogTool.log_tool_result_file, line + '\n')


        ### Exported Unique messages per NOT STANDARD log file, since ever  ###
        LogTool.append_to_file(LogTool.log_tool_result_file,'\n\n\n'+'#'*20+' Exported unique messages per NOT STANDARD log file, since ever '+'#'*20+'\n')
        for dir in not_standard_logs_unique_messages:
            if len(dir['UniqueMessages'])>0:
                LogTool.append_to_file(LogTool.log_tool_result_file,'\n'+'~'*40+' '+dir['Log']+' '+'~'*40+'\n')
                LogTool.write_list_to_file(LogTool.log_tool_result_file,dir['UniqueMessages'])

        ### Fill statistics section - Table of Content: line+index ###
        section_indexes=[]
        messages=[
            #'Raw Data - extracted Errors/Warnings from standard OSP logs since: '+time_grep,
            # 'Skipped logs - no debug level string (Error, Info, Debug...) has been detected',
            'Statistics - Number of Errors/Warnings per Standard OSP log since: '+LogTool.time_grep,
            'Statistics - Number of Errors/Warnings per Not Standard OSP log since ever',
            'Exported unique messages, per STANDARD OSP log file since: '+LogTool.time_grep,
            'Exported unique messages per NOT STANDARD log file, since ever',
            #'Statistics - Unique(Fuzzy Matching for all messages in total for standard OSP logs'
            ]
        for msg in messages:
            section_indexes.append({msg:"SectionStartLine: "+LogTool.get_file_line_index(LogTool.log_tool_result_file,msg)})
        LogTool.write_list_of_dict_to_file(LogTool.log_tool_result_file,section_indexes,'\n\n\n'+'#'*20+' Table of content (Section name --> Line number)'+'#'*20+'\n')
        print('Execution time:'+str(time.time()-start_time))
        if total_number_of_all_logs_errors+total_number_of_errors>0:
            print('Total_Number_Of_Errors:'+str(total_number_of_all_logs_errors+total_number_of_errors))

    # Save raw data to file
    if LogTool.save_standard_logs_raw_data_file!='':
        LogTool.empty_file_content(LogTool.save_standard_logs_raw_data_file)
        LogTool.append_to_file(LogTool.save_standard_logs_raw_data_file,str(analyzed_logs_result))
    if LogTool.save_not_standard_logs_raw_data_file!='':
        LogTool.empty_file_content(LogTool.save_not_standard_logs_raw_data_file)
        LogTool.append_to_file(LogTool.save_not_standard_logs_raw_data_file,str(not_standard_logs_unique_messages))
    print('Execution time:' + str(time.time() - start_time))
    print('SUCCESS!!!')

if __name__ == "__main__":
    start_analyzing()