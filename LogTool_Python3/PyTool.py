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

import shutil
from Common import *
import random
#import signal
import datetime
import threading

### Check if updated LogTool is available ###
cur_dir=os.path.abspath('')
git_command='cd '+cur_dir+'; git pull --dry-run > git_status.txt'
cur_dir=os.path.abspath('')
git_command='cd '+cur_dir+'; git pull --dry-run'
git_result=exec_command_line_command(git_command)
if git_result['CommandOutput']!='':
    spec_print(["-------Important-------","New LogTool version is available","Use 'git pull' command to upgrade!"],'yellow')

# # Ignore Ctrl+Z if pressed #
# def handlROR
#     print('Ctrl+Z pressed, but ignored')
#     print('Use Ctrl+C to stop execution!')
# signal.signal(signal.SIGTSTP, handler)


# Parameters #
overcloud_logs_dir = '/var/log'
overcloud_ssh_user = 'heat-admin'
overcloud_ssh_key = '/home/stack/.ssh/id_rsa'
undercloud_logs = ['/var/log','/home/stack','/usr/share/','/var/lib/']
source_rc_file_path='/home/stack/'
log_storage_host='cougar11.scl.lab.tlv.redhat.com'
log_storage_directory='/srv/static'
overcloud_home_dir = '/home/' + overcloud_ssh_user + '/'
mode_execution_status={}

empty_file_content('Runtime.log')
empty_file_content('Error.log')
# sys.stdout=MyOutput('Runtime.log')
# sys.stderr=MyOutput('Error.log')

# On interrupt "ctrl+c" executed script will be killed
executed_script_on_overcloud = []
executed_script_on_undercloud = []

def run_on_node(node, log_type):
    print('-' * 90)
    print('Remote Overcloud Node -->', str(node))
    try:
        result_file = node['Name'].replace(' ', '') + '_' + grep_string.replace(' ', '_') + '.log'
        s = SSH(node['ip'], user=overcloud_ssh_user, key_path=overcloud_ssh_key)
        s.ssh_connect_key()
        s.scp_upload('Extract_On_Node.py', overcloud_home_dir + 'Extract_On_Node.py')
        s.ssh_command('chmod 777 ' + overcloud_home_dir + 'Extract_On_Node.py')
        command = "sudo " + overcloud_home_dir + "Extract_On_Node.py '" + str(
            start_time) + "' " + overcloud_logs_dir + " '" + grep_string + "'" + ' ' + result_file + ' ' + save_raw_data+' None '+log_type
        print('Executed command on host --> ', command)
        com_result = s.ssh_command(command)
        print(com_result['Stdout'])  # Do not delete me!!!
        if 'SUCCESS!!!' in com_result['Stdout']:
            print_in_color(str(node) + ' --> OK', 'green')
        else:
            print_in_color(str(node) + ' --> FAILED', 'red')
            errors_on_execution[node['Name']] = False
        result_file=result_file+'.gz'
        s.scp_download(overcloud_home_dir + result_file, os.path.join(os.path.abspath(result_dir), result_file))
        # Clean all #
        files_to_delete = ['Extract_On_Node.py', result_file]
        for fil in files_to_delete:
            s.ssh_command('rm -rf ' + fil)
        # Close SSH #
        s.ssh_close()
    except Exception as e:
        spec_print('Failed on node:' + str(node) + 'with: ' + str(e))



def execute_on_node(**kwargs):



    print(kwargs)



    if kwargs['Mode']=='Export_Range':
        print('-' * 90)
        print('Remote Overcloud Node -->', str(node))
        try:
            result_file=kwargs['ResultFile']+'.gz' # This file will be created by worker script
            result_dir=kwargs['ResultDir']
            s = SSH(kwargs['ip'], user=overcloud_ssh_user, key_path=overcloud_ssh_key)
            s.ssh_connect_key()
            s.scp_upload('Extract_Range.py', overcloud_home_dir + 'Extract_Range.py')
            s.ssh_command('chmod 777 ' + overcloud_home_dir + 'Extract_Range.py')
            command = "sudo "+overcloud_home_dir+"Extract_Range.py '"+kwargs['StartRange']+"' '"+kwargs['StopRange']+\
                      "' "+kwargs['LogDir']+" "+kwargs['ResultFile']+' '+kwargs['ResultDir']
            print('Executed command on host --> ', command)
            com_result = s.ssh_command(command)
            print(com_result['Stdout'])  # Do not delete me!!!
            if 'SUCCESS!!!' in com_result['Stdout']:
                print_in_color(str(node) + ' --> OK', 'green')
            else:
                print_in_color(str(node) + ' --> FAILED', 'red')
                errors_on_execution[node['Name']] = False
            os.makedirs(result_dir,exist_ok=True)
            s.scp_download(overcloud_home_dir + result_file, os.path.join(os.path.abspath(result_dir), result_file))
            s.scp_download(overcloud_home_dir + result_dir+'.zip', os.path.join(os.path.abspath(result_dir), result_dir+'.zip'))
            # Clean all #
            files_to_delete = ['Extract_Range.py', result_file, result_dir, result_dir+'.zip',kwargs['ResultFile']]
            for fil in files_to_delete:
                s.ssh_command('rm -rf ' + fil)
            # Close SSH #
            s.ssh_close()
        except Exception as e:
            spec_print('Failed on node:' + str(node) + 'with: ' + str(e))






# dic_for_thread={'ip':'ip','Mode':'Export_Range','StartRange':'start_range_time',
#                             'StopRange':'stop_range_time','LogDir':'overcloud_logs_dir',
#                             'ResultFile':'ExportedTimeRange.log','ResultDir':'Overcloud_Exported_Time_Range'}
# execute_on_node(dic_for_thread)
# sys.exit(1)



# execute_on_node({'ip':'192.168.24.11',
#                  'Mode':'Export_Range',
#                  'StartRange':'2020-04-22 12:10:00',
#                  'StopRange':'2020-04-22 12:10:00',
#                  'LogDir':overcloud_logs_dir,
#                  'ResultFile':'ExportedTimeRange.log',
#                  'ResultDir':'Overcloud_Exported_Time_Range'})
# sys.exit(1)




### Operation Modes ###
try:
    modes=[#'Export ERRORs/WARNINGs from Overcloud logs OLD',
           'Export ERRORs/WARNINGs from Overcloud logs',
           'Download all logs from Overcloud nodes',
           '"Grep" some string on all Overcloud logs',
           'Extract messages for given time range',
           'Check current:CPU,RAM and Disk on Overcloud',
           "Execute user's script",
           'Download "relevant logs" only, by given timestamp',
           'Export ERRORs/WARNINGs from Undercloud logs',
           'Overcloud - check Unhealthy dockers',
           #'Extract all logs messages for given time range',
           #'Extract NEW (DELTA) messages from Overcloud',
           'Download Jenkins Job logs and run LogTool locally',
           'Undercloud - analyze Ansible Deployment log',
           'Analyze Gerrit(Zuul) failed gate logs',
           ]
    mode=choose_option_from_list(modes,'Please choose operation mode: ')


    if mode[1] == 'Analyze Gerrit(Zuul) failed gate logs':
        wget_exists=exec_command_line_command('wget -h')
        if wget_exists['ReturnCode']!=0:
            exit('WGET tool is not installed on your host, please install and rerun this operation mode!')
        # Make sure that BeutifulSoup is installed
        try:
            from bs4 import BeautifulSoup
        except Exception as e:
            print_in_color(str(e), 'red')
            print_in_color('Execute "sudo yum install python3-setuptools" to install pip3', 'yellow')
            print_in_color('Execute "pip3 install beautifulsoup4 --user" to install it!', 'yellow')
            exit('Install beautifulsoup and rerun!')
        # Make sure that requests is installed
        try:
            import requests
        except Exception as e:
            print_in_color(str(e), 'red')
            print_in_color('Execute "pip3 install requests --user" to install it!', 'yellow')
            exit('Install requests and rerun!')

        # Function to receive all Urls recursively, works slow :(
        listUrl = []
        checked_urls=[]
        def recursiveUrl(url):
            if url in checked_urls:
                return 1
            checked_urls.append(url)
            headers = {'Accept-Encoding': 'gzip'}
            try:
                page = requests.get(url, headers=headers)
                soup = BeautifulSoup(page.text, 'html.parser')
                links = soup.find_all('a')
                links = [link for link in links if 'href="' in str(links) if '<a href=' in str(link) if
                         link['href'] != '../']
            except Exception as e:
                print(e)
                links=None
            if links is None or len(links) == 0:
                listUrl.append(url)
                print(url)
                return 1;
            else:
                listUrl.append(url)
                print(url)
                for link in links:
                    recursiveUrl(url + link['href'][0:])

        # Start mode
        options = ['ERROR', 'WARNING']
        option=choose_option_from_list(options,'Please choose debug level option: ')
        if option[1]=='ERROR':
            grep_string=' ERROR '
        if option[1]=='WARNING':
            grep_string=' WARNING '
        destination_dir='Zuul_Log_Files'
        destination_dir=os.path.join(os.path.dirname(os.path.abspath('.')),destination_dir)
        if os.path.exists(destination_dir):
            shutil.rmtree(destination_dir)
        os.mkdir(destination_dir)
        zuul_log_url=input("Please enter Log URL, open failed gate, then you'll find it under Summary section in 'log_url'\nYour URL: ")
        mode_start_time = time.time()
        if '//storage' in zuul_log_url:
            # spec_print(['Warning - "wget -r" (recursively) cannot be used','This storage server is always responding with "gzip" content',
            #             'causing wget to download index.html only (as gzip compressed file)','Python will be used instead to export all Urls recursievly',
            #             'works a bit slow :-('],'yellow')
            recursiveUrl(zuul_log_url)
            for link in listUrl:
                #if link.endswith('log.txt.gz'):
                save_to_path=os.path.join(destination_dir,link.replace('https://','').replace('http://',''))
                exec_command_line_command('wget -P '+save_to_path+' '+link)
        else:
            # Download  Zuul log files with Wget
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/68.0.3440.106 Safari/537.36'
            download_command='wget -r --random-wait '+'"'+user_agent+'"'+' --no-parent -e robots=off -P '+destination_dir+' '+zuul_log_url
            print ('WGET is now running and recursively downloading all files...')
            return_code=exec_command_line_command(download_command)
            #if return_code['ReturnCode']!=0:
            #    print_in_color('Failed to download Zuul logs!', 'red')

        # Run LogTool analyzing
        print_in_color('\nStart analyzing downloaded OSP logs locally','bold')
        result_dir='Gerrit_Failed_Gate_'+grep_string.replace(' ','')
        if os.path.exists(os.path.abspath(result_dir)):
            shutil.rmtree(os.path.abspath(result_dir))
        result_file = os.path.join(os.path.abspath(result_dir), 'LogTool_Result_'+grep_string.replace(' ','')+'.log')
        command = "python3 Extract_On_Node.py '"+"2019-01-01 00:00:00"+"' "+os.path.abspath(destination_dir)+" '"+grep_string+"'" + ' '+result_file+" yes 'Analyze Gerrit(Zuul) failed gate logs'"
        #shutil.copytree(destination_dir, os.path.abspath(result_dir))
        exec_command_line_command('cp -r '+destination_dir+' '+os.path.abspath(result_dir))
        print_in_color('\n --> '+command,'bold')
        start_time=time.time()
        com_result=exec_command_line_command(command)
        end_time=time.time()
        if com_result['ReturnCode']==0:
            spec_print(['Completed!!!', 'You can find the result file + downloaded logs in:',
                        'Result Directory: ' + result_dir,
                        'Analyze logs execution time: ' + str(end_time - mode_start_time) + '[sec]'], 'green')
        else:
            spec_print(['Completed!!!', 'Result Directory: ' + result_dir,
                        'Analyze logs execution time: ' + str(end_time - mode_start_time) + '[sec]'], 'red')

    if mode[1] == 'Undercloud - analyze Ansible Deployment log':
        from Extract_On_Node import *
        result_file='Ansible_Deploy_Log_Result.txt'
        undercloud_home_path = '/home/stack'
        if os.path.exists(undercloud_home_path) is False:
            undercloud_home_path=input('Enter absolute path to directory containing deployment log: ')
        fatal_lines=[]
        error_lines=[]
        failed_tasks=[]
        magic_words = ['FAILED', 'TASK', 'msg', 'stderr', 'WARN', 'fatal', 'traceback']
        magic_dic_result = {}
        for word in magic_words:
            magic_dic_result[word] = []
        log_path=[os.path.join(undercloud_home_path,path) for path in os.listdir(undercloud_home_path) if path.endswith('.log')]
        log_path=choose_option_from_list(log_path,'Please choose your Ansible deployment log file path: ')
        empty_file_content(result_file)
        data = open(log_path[1], 'r').read().splitlines()
        lines_to_analyze=[]
        lines_to_unique=[]
        append_to_file(result_file,'#'*40+' Raw Data Lines '+'#'*40+'\n')
        for line in data:
            # Print some lines that might be relevant #
            words = [' error:', ' error ', ' failed:', ' failed ', ' fatal ', ' fatal:']
            for w in words:
                if w in line.lower():
                    append_to_file(result_file, '_'*200+'\n')
                    append_to_file(result_file,'Detected string is: "'+w+'"\n')
                    w_index=line.find(w)
                    if len(line) < 5000:
                        append_to_file(result_file, line+'\n')
                        lines_to_unique.append('Detected string is: "' + w + '"\n' + line + '\n')
                    else:
                        if w_index+1000<len(line):
                            lines_to_unique.append('Detected string is: "' + w + '\n...Line is too long ...' + line[w_index:w_index+1000] + '\n...Line is too long ...'+'\n')
                            append_to_file(result_file, '\n...Line is too long ...' + line[w_index:w_index+1000] + '\n...Line is too long ...'+'\n')
                        else:
                            append_to_file(result_file, '...Line is too long ...' + line[w_index:] + '\n')
                            lines_to_unique.append('Detected string is: "' + w + '\n...Line is too long ...' + line[w_index:] + '\n')
                    break
            if ' ERROR ' in line and line not in error_lines:
                error_lines.append(line)
            if 'fatal: [' in line:
                is_task_line=False
                counter=1
                while is_task_line==False:
                    previous_line=data[data.index(line)-counter]
                    if 'TASK' in previous_line:
                        is_task_line=True
                        lines_to_analyze.append(previous_line)
                    counter+=1
                lines_to_analyze.append(line)
                failed_task=previous_line[previous_line.find('TASK'):previous_line.find('*****')]
                if len(failed_task)!=0:
                    failed_tasks.append(failed_task)

        # Print unique list into result file
        append_to_file(result_file, '\n' * 10 + '#' * 7 + ' Unique "problematical" lines ' + '#' * 7 + '\n')
        unique_errors_list = unique_list_by_fuzzy(lines_to_unique, 0.5)
        for item in unique_errors_list:
            append_to_file(result_file, '-' * 100 + '\n' + item)

        for line in lines_to_analyze:
            line = line.split('\\n')
            for item in line:
                if 'fatal' in item.lower() and item not in fatal_lines:
                    fatal_lines.append(item)
                append_to_file(result_file,item)
                for w in magic_words:
                    if w in item:
                        magic_dic_result[w].append(item)
        append_to_file(result_file,'\n'*10+'#'*50+' Unique statistics for these magic keys:'+str(magic_words)+' '+'#'*50+'\n\n\n')
        for key in magic_dic_result:
            append_to_file(result_file,'\n\n\n' + '_' * 40 + key + '_' * 40+'\n')
            if key in ['fatal','FAILED']:
                fuzzy=1
            else:
                fuzzy=0.6
            for v in unique_list_by_fuzzy(magic_dic_result[key], fuzzy):
                if key in ['stderr','msg']:
                    append_to_file(result_file,'\n'+v+'\n')
                else:
                    append_to_file(result_file,v+'\n')
        append_to_file(result_file, '\n\n\n' + '*' * 7 + ' Failed_Tasks: ' + '*' * 7)
        write_list_to_file(result_file, failed_tasks, False)
        append_to_file(result_file,'\n\n\n### Search for these keys: '+str(magic_words)+' surrounded by underscore for example: "__stderr__" to find the statistics!!! ###')
        print_in_color('\n\n\n####### Detected lines with "fatal" string:#######', 'red')
        for f in fatal_lines:
            print_in_color(f,'bold')
        print_in_color('\n\n\n####### Detected lines with " ERROR " string:#######', 'red')
        for e in error_lines:
            print_in_color(e,'bold')
        print_in_color('\n\n\n####### Detected failed TASKs: #######', 'red')
        for t in failed_tasks:
            print_in_color(t, 'bold')
        append_to_file(result_file,'\n*** Check - (Unique "problematical" lines) section as well!')
        spec_print(['Result File is: ', '"'+result_file+'"', 'Vi and scroll down to the bottom for details!'],'green')

    if mode[1]=='Download Jenkins Job logs and run LogTool locally':
        wget_exists=exec_command_line_command('wget -h')
        if wget_exists['ReturnCode']!=0:
            exit('WGET tool is not installed on your host, please install and rerun this operation mode!')
        # Start mode
        options = ['ERROR', 'WARNING']
        option=choose_option_from_list(options,'Please choose debug level option: ')
        if option[1]=='ERROR':
            grep_string=' ERROR '
        if option[1]=='WARNING':
            grep_string=' WARNING '
        destination_dir='Jenkins_Job_Files'
        destination_dir=os.path.join(os.path.dirname(os.path.abspath('.')),destination_dir)
        if os.path.exists(destination_dir):
            shutil.rmtree(destination_dir)
        os.mkdir(destination_dir)

        #Download log files
        options=["Download files through Jenkins Artifacts URL using HTTP", "Download files using SCP from: "+log_storage_host]
        option=choose_option_from_list(options,'Please choose your option to download files: ')
        if option[1]=='Download files through Jenkins Artifacts URL using HTTP':
            # Make sure that BeutifulSoup is installed
            try:
                from bs4 import BeautifulSoup
            except Exception as e:
                print_in_color(str(e), 'red')
                print_in_color('Execute "sudo yum install python3-setuptools" to install pip3', 'yellow')
                print_in_color('Execute "pip3 install beautifulsoup4" to install it!', 'yellow')
                exit('Install beautifulsoup and rerun!')
            artifacts_url = input('Copy and paste Jenkins URL to Job Artifacts for example \nhttps://rhos-qe-jenkins.rhev-ci-vms.eng.rdu2.redhat.com/job/DFG-hardware_provisioning-rqci-14_director-7.6-vqfx-ipv4-vxlan-IR-networking_ansible/39/artifact/\nYour URL: ')

            if 'artifact' not in artifacts_url.lower():
                print_in_color("Provided URL doesn't seem to be proper artifact URL, please rerun using correct URL address!",'red')
                sys.exit(1)

            # Use since time
            start_time = input('\nEnter your "since time" to analyze log files,'
                               '\nFor example it could be start time of some failed stage'
                               '\nTime format example: 2020-04-22 12:10:00 enter your time: ')

            mode_start_time=time.time()
            response = urllib.request.urlopen(artifacts_url)
            html = response.read()
            parsed_url = urlparse(artifacts_url)
            base_url = parsed_url.scheme + '://' + parsed_url.netloc
            #soup = BeautifulSoup(html)
            soup = BeautifulSoup(html, 'lxml')
            tar_gz_files=[]
            ir_logs_urls = []
            # Create tempest log url #
            tempest_log_url = None
            for link in soup.findAll('a'):
                if 'tempest-results' in link:
                    tempest_results_url=urljoin(artifacts_url, link.get('href'))
                    tempest_response = urllib.request.urlopen(tempest_results_url)
                    html = tempest_response.read()
                    soup = BeautifulSoup(html, 'lxml')
                    for link in soup.findAll('a'):
                        if str(link.get('href')).endswith('.html'):
                            tempest_html=link.get('href')
                            tempest_log_url=urljoin(artifacts_url,'tempest-results')+'/'+tempest_html
                            break
                if str(link.get('href')).endswith('.tar.gz'):
                    tar_gz_files.append(link)
                    tar_link = urljoin(artifacts_url, link.get('href'))
                    os.system('wget -P ' + destination_dir + ' ' + tar_link)
                if str(link.get('href')).endswith('.sh'):
                    sh_page_link=urljoin(artifacts_url, link.get('href'))
                    response = urllib.request.urlopen(sh_page_link)
                    html = response.read()
                    soup = BeautifulSoup(html)
                    for link in soup.findAll('a'):
                        if str(link.get('href')).endswith('.log'):
                            ir_logs_urls.append(sh_page_link+'/'+link.get('href'))
            # if len(tar_gz_files)==0:
            #     spec_print(['There is no links to *.tar.gz on provided URL page','Nothing to work on :-)'],'red')
            #     exit('Check your: '+artifacts_url)


        if option[1]=="Download files using SCP from: "+log_storage_host:
            # Make sure that Paramiko is installed
            try:
                import paramiko
            except Exception as e:
                print_in_color(str(e), 'red')
                print_in_color('Execute "pip install paramiko" to install it!', 'yellow')
                exit('Install Paramiko and rerun!')
            log_storage_user=input('SSH User - '+log_storage_host+': ')
            log_storage_password=input('SSH password - '+log_storage_host+': ')
            mode_start_time = time.time()
            s = SSH(log_storage_host, user=log_storage_user, password=log_storage_password)
            s.ssh_connect_password()
            job_name=input('Please enter Job name: ')
            job_build=input('Please enter build number: ')
            job_full_path=os.path.join(os.path.join(log_storage_host,log_storage_directory),job_name)
            job_full_path=os.path.join(job_full_path,job_build)
            files=s.ssh_command('ls -ltrh '+job_full_path)['Stdout'].split('\n')
            files=[f.split(' ')[-1] for f in files if '.tar.gz' in f]
            for fil in files:
                print_in_color('Downloading "'+fil+'"...', 'bold')
                s.scp_download(os.path.join(job_full_path,fil),os.path.join(destination_dir,fil))
            s.ssh_close()

        #Unzip all downloaded .tar.gz files
        for fil in os.listdir(os.path.abspath(destination_dir)):
            cmd = 'tar -zxvf '+os.path.join(os.path.abspath(destination_dir),fil)+' -C '+os.path.abspath(destination_dir)+' >/dev/null'+';'+'rm -rf '+os.path.join(os.path.abspath(destination_dir),fil)
            print_in_color('Unzipping '+fil+'...', 'bold')
            os.system(cmd)

        # Download console.log
        console_log_url=artifacts_url.strip().replace('artifact','consoleFull').strip('/')
        os.system('wget -P ' + destination_dir + ' ' + console_log_url)
        shutil.move(os.path.join(destination_dir, 'consoleFull'),os.path.join(destination_dir,'consoleFull.log'))

        # Download Infared Logs .sh, files in .sh directory on Jenkins
        if len(ir_logs_urls)!=0:
            for url in ir_logs_urls:
                os.system('wget -P ' + destination_dir + ' ' + url)

        # Download tempest log (html #)
        if tempest_log_url!=None:
            os.system('wget -P ' + destination_dir + ' ' + tempest_log_url)
            shutil.move(os.path.join(destination_dir, tempest_html),os.path.join(destination_dir,tempest_html.replace('.html','.log')))

        # Run LogTool analyzing
        print_in_color('\nStart analyzing downloaded OSP logs locally','bold')
        result_dir='Jenkins_Job_'+grep_string.replace(' ','')
        if os.path.exists(os.path.abspath(result_dir)):
            shutil.rmtree(os.path.abspath(result_dir))
        result_file = os.path.join(os.path.abspath(result_dir), 'LogTool_Result_'+grep_string.replace(' ','')+'.log')
        command = "python3 Extract_On_Node.py '"+start_time+"' "+os.path.abspath(destination_dir)+" '"+grep_string+"'" + ' '+result_file
        #shutil.copytree(destination_dir, os.path.abspath(result_dir))
        exec_command_line_command('cp -r '+destination_dir+' '+os.path.abspath(result_dir))
        print_in_color('\n --> '+command,'bold')
        start_time=time.time()
        com_result=exec_command_line_command(command)
        #print (com_result['CommandOutput'])
        end_time=time.time()
        if com_result['ReturnCode']==0:
            spec_print(['Completed!!!','You can find the result file + downloaded logs in:', 'Result Directory: '+result_dir,'Analyze logs execution time: '+str(end_time-mode_start_time)+'[sec]'],'green')
        else:
            spec_print(['Completed!!!', 'Result Directory: ' + result_dir,
                        'Analyze logs execution time: ' + str(end_time - mode_start_time) + '[sec]'], 'red')

    if mode[1]=='Export ERRORs/WARNINGs from Undercloud logs':
        undercloud_time=exec_command_line_command('date "+%Y-%m-%d %H:%M:%S"')['CommandOutput'].strip()
        print('Current date is: '+undercloud_time)
        start_time_options=['10 Minutes ago','30 Minutes ago','One Hour ago','Three Hours ago', 'Ten Hours ago', 'One Day ago', 'Custom']
        start_time_option = choose_option_from_list(start_time_options, 'Please choose your "since time": ')
        if start_time_option[1]=='Custom':
            print_in_color('Current date on Undercloud is: ' + undercloud_time, 'blue')
            print_in_color('Use the same date format as in previous output', 'blue')
            start_time = input('And enter your "since time" to extract log messages: ')
        if start_time_option[1]=='10 Minutes ago':
            start_time = datetime.datetime.strptime(undercloud_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(minutes=10)
        if start_time_option[1]=='30 Minutes ago':
            start_time = datetime.datetime.strptime(undercloud_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(minutes=30)
        if start_time_option[1]=='One Hour ago':
            start_time = datetime.datetime.strptime(undercloud_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(hours=1)
        if start_time_option[1]=='Three Hours ago':
            start_time = datetime.datetime.strptime(undercloud_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(hours=3)
        if start_time_option[1]=='Ten Hours ago':
            start_time = datetime.datetime.strptime(undercloud_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(hours=10)
        if start_time_option[1]=='One Day ago':
            start_time = datetime.datetime.strptime(undercloud_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(hours=24)
        if start_time_option[1]=='Two Days ago':
            start_time = datetime.datetime.strptime(undercloud_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(hours=48)
        start_time=str(start_time)
        print_in_color('\nYour "since time" is set to: '+start_time,'blue')
        if check_time(start_time)==False:
            print_in_color('Bad timestamp format: '+start_time,'yellow')
            exit('Execution will be interrupted!')
        options=['ERROR','WARNING']
        option=choose_option_from_list(options,'Please choose debug level: ')
        mode_start_time=time.time()
        if option[1]=='ERROR':
            grep_string=' ERROR '
        elif option[1]=='WARNING':
            grep_string=' WARNING '
        else:
            grep_string=' '+option[1]+' '
        result_dir='Undercloud_'+grep_string.replace(' ','')
        if result_dir in os.listdir('.'):
            shutil.rmtree(result_dir)
        os.mkdir(result_dir)
        result_file='Undercloud'+'_'+grep_string.replace(' ','_')+'.log.gz'
        log_root_dir=str(undercloud_logs)
        command="sudo python3 Extract_On_Node.py '" + str(start_time) + "' " +"'"+ log_root_dir +"'"+ " '" + grep_string + "'" + ' ' + result_file
        print_in_color(command,'bold')
        executed_script_on_undercloud.append('Extract_On_Node.py')
        com_result=exec_command_line_command(command)
        shutil.move(result_file, os.path.join(os.path.abspath(result_dir),result_file))
        end_time=time.time()
        if com_result['ReturnCode']==0:
            spec_print(['Completed!!!','Result Directory: '+result_dir,'Execution Time: '+str(end_time-mode_start_time)+'[sec]'],'green')
        else:
            spec_print(['Completed!!!', 'Result Directory: ' + result_dir,
                        'Execution Time: ' + str(end_time - mode_start_time) + '[sec]'], 'red')

    if mode[1]=='Check current:CPU,RAM and Disk on Overcloud':
        ### Get all nodes ###
        nodes = exec_command_line_command('source ' + source_rc_file_path + 'stackrc;openstack server list -f json')['JsonOutput']
        nodes = [{'Name': item['name'], 'ip': item['networks'].split('=')[-1]} for item in nodes]
        start_time=time.time()
        cpu = 'vmstat'
        mem = 'free'
        disk = 'df -h'
        commands=[cpu,mem,disk]
        for node in nodes:
            print_in_color('#'*20+str(node)+'#'*20,'blue')
            s = SSH(node['ip'], user=overcloud_ssh_user, key_path=overcloud_ssh_key)
            s.ssh_connect_key()
            # Check if pip is installed #
            pip_installed='sudo which pip'
            for com in commands:
                print('--> '+com)
                out=s.ssh_command(com)
                print(out['Stdout'])
                if len(out['Stderr'])!=0:
                    print(out['Stderr'])
            s.ssh_close()
        end_time=time.time()
        spec_print(['Completed!!!', 'Execution Time: ' + str(end_time - start_time) + '[sec]'],'bold')

    if mode[1]=='"Grep" some string on all Overcloud logs':
        ### Get all nodes ###
        nodes = exec_command_line_command('source ' + source_rc_file_path + 'stackrc;openstack server list -f json')['JsonOutput']
        nodes = [{'Name': item['name'], 'ip': item['networks'].split('=')[-1]} for item in nodes]
        print_in_color("1) You can use special characters in your string"
                       "\n2) Ignore case sensitive flag is used by default",'yellow')
                       #"\n3) It's possible to use additional grep flags, for example '-e ^' a to grep all lines started with 'a' character",'yellow')
        string_to_grep = "'"+input("Please enter your 'grep' string: ")+"'"
        start_time = time.time()
        result_dir='All_Greped_Strings'
        if result_dir in os.listdir('.'):
            shutil.rmtree(result_dir)
        os.mkdir(result_dir)
        executed_script_on_overcloud.append('Grep_String.py')
        for node in nodes:
            print(str(node))
            output_greps_file = 'All_Grep_Strings_'+node['Name']+'.log'
            s = SSH(node['ip'], user=overcloud_ssh_user, key_path=overcloud_ssh_key)
            s.ssh_connect_key()
            print(s.scp_upload('Grep_String.py', overcloud_home_dir + 'Grep_String.py'))
            print(s.ssh_command('chmod 777 ' + overcloud_home_dir + 'Grep_String.py'))
            command='sudo ' + overcloud_home_dir + 'Grep_String.py ' + overcloud_logs_dir + ' ' + string_to_grep + ' ' + output_greps_file
            print_in_color(command,'bold')
            s.ssh_command(command)
            print(s.scp_download(overcloud_home_dir + output_greps_file, os.path.join(os.path.abspath(result_dir), output_greps_file)))
            # Clean all #
            files_to_delete=[output_greps_file,'Grep_String.py']
            for fil in files_to_delete:
                s.ssh_command('rm -rf ' + fil)
            # Close SSH #
            s.ssh_close()
        end_time=time.time()
        spec_print(['Completed!!!','Result Directory: '+result_dir,'Execution Time: '+str(end_time-start_time)+'[sec]'],'bold')

    if mode[1] == 'Download all logs from Overcloud nodes':
        ### Get all nodes ###
        nodes = exec_command_line_command('source ' + source_rc_file_path + 'stackrc;openstack server list -f json')['JsonOutput']
        nodes = [{'Name': item['name'], 'ip': item['networks'].split('=')[-1]} for item in nodes]
        start_time=time.time()
        result_dir='Overcloud_Logs'
        if result_dir in os.listdir('.'):
            shutil.rmtree(result_dir)
        os.mkdir(result_dir)
        for node in nodes:
            print('-'*90)
            print(str(node))
            s = SSH(node['ip'], user=overcloud_ssh_user, key_path=overcloud_ssh_key)
            s.ssh_connect_key()
            zip_file_name=node['Name']+'.zip'
            command='sudo zip -r ' + zip_file_name +' ' + overcloud_logs_dir
            print(command)
            s.ssh_command(command)
            print(s.scp_download(overcloud_home_dir + zip_file_name, os.path.join(os.path.abspath(result_dir), zip_file_name)))
            # Clean all #
            files_to_delete=[zip_file_name]
            for fil in files_to_delete:
                s.ssh_command('rm -rf ' + fil)
            # Close SSH #
            s.ssh_close()
        end_time=time.time()
        spec_print(['Completed!!!','Result Directory: '+result_dir,'Execution Time: '+str(end_time-start_time)+'[sec]'],'bold')

    if mode[1] == 'Download "relevant logs" only, by given timestamp':
        # Change log path if needed #
        osp_versions=['Older than OSP13?', "Newer than OSP13?"]
        if choose_option_from_list(osp_versions,'Choose your OSP Version: ')[1]=='Newer than OSP13?':
            overcloud_logs_dir=os.path.join(overcloud_logs_dir,'containers')
        ### Get all nodes ###
        nodes = exec_command_line_command('source ' + source_rc_file_path + 'stackrc;openstack server list -f json')['JsonOutput']
        nodes = [{'Name': item['name'], 'ip': item['networks'].split('=')[-1]} for item in nodes]
        random_node=random.choice(nodes)
        s = SSH(random_node['ip'], user=overcloud_ssh_user, key_path=overcloud_ssh_key)
        s.ssh_connect_key()
        com_result=s.ssh_command('date "+%Y-%m-%d %H:%M:%S"')
        print_in_color('Current date on '+random_node['Name']+' is: '+com_result['Stdout'].strip(),'blue')
        s.ssh_close()
        print_in_color('Use the same date format as in previous output','blue')
        start_time = input('And Enter your "since time" to extract log messages: ')
        mode_start_time=time.time()
        result_dir='Overcloud_Logs_Relevant'
        if result_dir in os.listdir('.'):
            shutil.rmtree(result_dir)
        os.mkdir(result_dir)
        for node in nodes:
            errors_on_execution={}
            print(str(node))
            s = SSH(node['ip'], user=overcloud_ssh_user, key_path=overcloud_ssh_key)
            s.ssh_connect_key()
            print(s.scp_upload('Download_Logs_By_Timestamp.py', overcloud_home_dir + 'Download_Logs_By_Timestamp.py'))
            print(s.ssh_command('chmod 777 ' + overcloud_home_dir + 'Download_Logs_By_Timestamp.py'))
            command="sudo " + overcloud_home_dir + "Download_Logs_By_Timestamp.py '" + str(start_time) + "' " + overcloud_logs_dir +' '+ node['Name']
            print(command)
            com_result=s.ssh_command(command)
            print(com_result['Stdout']) # Do not delete me!!!
            if 'SUCCESS!!!' in com_result['Stdout']:
                print_in_color(str(node)+' --> OK','green')
            else:
                print_in_color(str(node) + ' --> FAILED','red')
                errors_on_execution[node['Name']]=False
            print(s.scp_download(overcloud_home_dir + node['Name']+'.zip', os.path.join(os.path.abspath(result_dir), node['Name']+'.zip')))
            # Clean all #
            files_to_delete=['Download_Logs_By_Timestamp.py',node['Name']+'.zip', node['Name']]
            for fil in files_to_delete:
                s.ssh_command('rm -rf '+fil)
            # Close SSH #
            s.ssh_close()
        end_time=time.time()
        if len(errors_on_execution) == 0:
            spec_print(['Completed!!!','Result Directory: '+result_dir,'Execution Time: '+str(end_time-mode_start_time)+'[sec]'],'green')
        else:
            spec_print(['Completed!!!','Result Directory: '+result_dir,'Execution Time: '+str(end_time-mode_start_time)+'[sec]'],'red')

    if mode[1] == "Execute user's script":
        user_scripts_dir=os.path.join(os.path.abspath('.'),'UserScripts')
        user_scripts=[os.path.join(user_scripts_dir,fil) for fil in os.listdir(user_scripts_dir)]
        script_path=choose_option_from_list(user_scripts,'Choose script to execute on OC nodes:')[1]
        result_dir='Overcloud_User_Script_Result'
        if result_dir in os.listdir('.'):
            shutil.rmtree(result_dir)
        os.mkdir(result_dir)
        start_time = time.time()

        ### Get all nodes ###
        nodes = exec_command_line_command('source ' + source_rc_file_path + 'stackrc;openstack server list -f json')['JsonOutput']
        nodes = [{'Name': item['name'], 'ip': item['networks'].split('=')[-1]} for item in nodes]
        executed_script_on_overcloud.append(os.path.basename(script_path))
        for node in nodes:
            print(str(node))
            output_file = node['Name']+'.log'
            s = SSH(node['ip'], user=overcloud_ssh_user, key_path=overcloud_ssh_key)
            s.ssh_connect_key()
            print(s.scp_upload(script_path, os.path.basename(script_path)))
            print(s.ssh_command('chmod 777 ' + os.path.basename(script_path)))
            command='sudo ./' + os.path.basename(script_path)+' | tee '+output_file
            print('Executed command on host is: ',command)
            print(s.ssh_command_only(command)['Stdout'])
            print(overcloud_home_dir + output_file, os.path.join(os.path.abspath(result_dir), output_file))
            print(s.scp_download(overcloud_home_dir + output_file, os.path.join(os.path.abspath(result_dir), output_file)))
            # Clean all #
            files_to_delete=[output_file,os.path.basename(script_path)]
            for fil in files_to_delete:
                s.ssh_command('rm -rf ' + fil)
            # Close SSH #
            s.ssh_close()
        end_time=time.time()
        spec_print(['Completed!!!','Result Directory: '+result_dir,'Execution Time: '+str(end_time-start_time)+'[sec]'],'bold')

    if mode[1]=='Overcloud - check Unhealthy dockers':
        ### Get all nodes ###
        nodes = exec_command_line_command('source ' + source_rc_file_path + 'stackrc;openstack server list -f json')['JsonOutput']
        nodes = [{'Name': item['name'], 'ip': item['networks'].split('=')[-1]} for item in nodes]
        start_time=time.time()
        cpu = 'sudo top -n 1 | head -6'
        mem = 'sudo free'
        disk = 'sudo df -h'
        commands=['sudo podman ps | grep -i unhealthy']
        for node in nodes:
            try:
                print_in_color('#'*20+str(node)+'#'*20,'blue')
                s = SSH(node['ip'], user=overcloud_ssh_user, key_path=overcloud_ssh_key)
                s.ssh_connect_key()
                for com in commands:
                    print(com)
                    out=s.ssh_command(com)
                    err = out['Stderr']
                    out=out['Stdout']
                    if len(out) !=0:
                        print_in_color(out,'red')
                    if len(out) ==0:
                        print_in_color(str(node)+" --> OK", 'green')
                    if len(err)!=0:
                        print(err)
                s.ssh_close()
            except Exception as e:
                print_in_color('Execution has failed on node: '+str(node)+'with: '+str(e), 'red')
        end_time=time.time()
        spec_print(['Completed!!!', 'Execution Time: ' + str(end_time - start_time) + '[sec]'],'bold')

    if mode[1]=='Export ERRORs/WARNINGs from Overcloud logs':
        ### Get all nodes ###
        nodes=[]
        all_nodes = exec_command_line_command('source ' + source_rc_file_path + 'stackrc;openstack server list -f json')['JsonOutput']
        all_nodes = [{'Name': item['name'], 'ip': item['networks'].split('=')[-1]} for item in all_nodes]
        for node in all_nodes:
            if check_ping(node['ip']) is True:
                nodes.append(node)
            else:
                print_in_color('Warning - '+str(node)+' will be skipped, due to connectivity issue!!!','yellow')
        if len(nodes)==0:
            print_in_color('No Overcloud nodes detected, looks like your OSP installation has failed!','red')
            sys.exit(1)
        random_node=random.choice(nodes)
        s = SSH(random_node['ip'], user=overcloud_ssh_user, key_path=overcloud_ssh_key)
        s.ssh_connect_key()
        com_result=s.ssh_command('date "+%Y-%m-%d %H:%M:%S"')
        overcloud_time=com_result['Stdout'].strip()
        s.ssh_close()
        print_in_color('Current date on Overcloud is: ' + com_result['Stdout'].strip(), 'blue')

        start_time_options=['10 Minutes ago','30 Minutes ago','One Hour ago','Three Hours ago', 'Ten Hours ago', 'One Day ago', 'Custom']
        start_time_option = choose_option_from_list(start_time_options, 'Please choose your "since time": ')
        if start_time_option[1]=='Custom':
            print_in_color('Current date on Overcloud is: ' + com_result['Stdout'].strip(), 'blue')
            print_in_color('Use the same date format as in previous output', 'blue')
            start_time = input('And enter your "since time" to extract log messages: ')
        if start_time_option[1]=='10 Minutes ago':
            start_time = datetime.datetime.strptime(overcloud_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(minutes=10)
        if start_time_option[1]=='30 Minutes ago':
            start_time = datetime.datetime.strptime(overcloud_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(minutes=30)
        if start_time_option[1]=='One Hour ago':
            start_time = datetime.datetime.strptime(overcloud_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(hours=1)
        if start_time_option[1]=='Three Hours ago':
            start_time = datetime.datetime.strptime(overcloud_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(hours=3)
        if start_time_option[1]=='Ten Hours ago':
            start_time = datetime.datetime.strptime(overcloud_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(hours=10)
        if start_time_option[1]=='One Day ago':
            start_time = datetime.datetime.strptime(overcloud_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(hours=24)
        if start_time_option[1]=='Two Days ago':
            start_time = datetime.datetime.strptime(overcloud_time, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(hours=48)
        start_time=str(start_time)
        print_in_color('\nYour "since time" is set to: '+start_time,'blue')

        mode_start_time = time.time()
        if check_time(start_time)==False:
            print_in_color('Bad timestamp format: '+start_time,'yellow')
            exit('Execution will be interrupted!')
        options=['ERROR','WARNING']
        option=choose_option_from_list(options,'Please choose debug level: ')
        osp_logs_only='all_logs'
        handle_all_logs=choose_option_from_list(['OSP logs only','All logs'], "Log files to analyze?")[1]
        if handle_all_logs=="OSP logs only":
            osp_logs_only='osp_logs_only'
        #save_raw_data=choose_option_from_list(['yes','no'],'Save "Raw Data" in result files?')[1]
        save_raw_data='yes'
        if option[1]=='ERROR':
            grep_string=' ERROR '
        if option[1]=='WARNING':
            grep_string=' WARNING '
        #result_dir='Overcloud_'+start_time+'_'+grep_string.replace(' ','_').replace(':','_').replace('\n','')
        result_dir='Overcloud_'+grep_string.replace(' ','')
        if result_dir in os.listdir('.'):
            shutil.rmtree(result_dir)
        os.mkdir(result_dir)
        errors_on_execution={}
        executed_script_on_overcloud.append('Extract_On_Node.py')
        threads = []
        for node in nodes:
            t = threading.Thread(target=run_on_node, args=(node,osp_logs_only))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        end_time=time.time()
        if len(errors_on_execution)==0:
            spec_print(['Completed!!!','Result Directory: '+result_dir,'Execution Time: '+str(end_time-mode_start_time)+'[sec]'],'green')
        else:
            if len(errors_on_execution) == len(nodes):
                spec_print(['Execution has failed for all nodes :-( ',
                            'Execution Time: ' + str(end_time-mode_start_time) + '[sec]'], 'red')
            else:
                spec_print(['Completed with failures!!!', 'Result Directory: ' + result_dir,
                            'Execution Time: ' + str(end_time-mode_start_time) + '[sec]',
                            'Failed nodes:'] + [k for k in list(errors_on_execution.keys())], 'yellow')









    if mode[1]=='Extract messages for given time range':
        ### Get all nodes ###
        nodes=[]
        all_nodes = exec_command_line_command('source ' + source_rc_file_path + 'stackrc;openstack server list -f json')['JsonOutput']
        all_nodes = [{'Name': item['name'], 'ip': item['networks'].split('=')[-1]} for item in all_nodes]
        for node in all_nodes:
            if check_ping(node['ip']) is True:
                nodes.append(node)
            else:
                print_in_color('Warning - '+str(node)+' will be skipped, due to connectivity issue!!!','yellow')
        if len(nodes)==0:
            print_in_color('No Overcloud nodes detected, looks like your OSP installation has failed!','red')
            sys.exit(1)
        start_range_time = input('\nEnter range "start time":'
                           '\nTime format example: 2020-04-22 12:10:00 enter your time: ')
        stop_range_time = input('\nEnter range "stop time":'
                           '\nTime format example: 2020-04-22 12:20:00 enter your time: ')
        mode_start_time = time.time()
        for item in [start_range_time,stop_range_time]:
            if check_time(item)==False:
                print_in_color('Bad timestamp format: '+item,'yellow')
                exit('Execution will be interrupted!')
        result_dir='Overcloud_Exported_Time_Range'
        os.makedirs(result_dir,exist_ok=True)







        errors_on_execution={}
        executed_script_on_overcloud.append('Extract_Range.py')
        threads = []
        for node in nodes:
            #t = threading.Thread(target=run_on_node, args=(node,osp_logs_only))

            # t = threading.Thread(target=execute_on_node,args=(node, Mode='Export_Range',
            #                        StartRange='2020-04-13 16:26:57', StopRange='2020-04-13 16:28:57',
            #                        LogDir='/var/log', ResultFile='ExportedTimeRange.log',
            #                        ResultDir='Overcloud_Exported_Time_Range'))

            dic_for_thread={'ip':node['ip'],
                            'Mode':'Export_Range',
                            'StartRange':start_range_time,
                            'StopRange':stop_range_time,
                            'LogDir':overcloud_logs_dir,
                            'ResultFile':node['Name'],
                            'ResultDir':node['Name']}
            t = threading.Thread(target=execute_on_node, kwargs=dic_for_thread)




            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        end_time=time.time()
        if len(errors_on_execution)==0:
            spec_print(['Completed!!!','Result Directory: '+result_dir,'Execution Time: '+str(end_time-mode_start_time)+'[sec]'],'green')
        else:
            if len(errors_on_execution) == len(nodes):
                spec_print(['Execution has failed for all nodes :-( ',
                            'Execution Time: ' + str(end_time-mode_start_time) + '[sec]'], 'red')
            else:
                spec_print(['Completed with failures!!!', 'Result Directory: ' + result_dir,
                            'Execution Time: ' + str(end_time-mode_start_time) + '[sec]',
                            'Failed nodes:'] + [k for k in list(errors_on_execution.keys())], 'yellow')







    if mode[1]=='Extract all logs messages for given time range':
        print_in_color('ToDo - Not implemented yet :-(','yellow')

    if mode[1]=='Extract NEW (DELTA) messages from Overcloud':
        print_in_color('ToDo - Not implemented yet :-(', 'yellow')

except KeyboardInterrupt:
    print_in_color("\n\n\nJust a minute, killing all tool's running scripts if any :-) ",'yellow')
    if len(executed_script_on_undercloud)!=0:
        for script in executed_script_on_undercloud:
            os.system('sudo pkill -f '+script)
    if len(executed_script_on_overcloud)!=0:
        nodes = exec_command_line_command('source ' + source_rc_file_path + 'stackrc;openstack server list -f json')['JsonOutput']
        nodes = [{'Name': item['name'], 'ip': item['networks'].split('=')[-1]} for item in nodes]
        for node in nodes:
            print('-'*90)
            print([str(node)])
            s = SSH(node['ip'], user=overcloud_ssh_user, key_path=overcloud_ssh_key)
            s.ssh_connect_key()
            for script in executed_script_on_overcloud:
                command='sudo pkill -f '+script
                print('--> '+command)
                com_result=s.ssh_command(command)
            s.ssh_close()
# except Exception as e:
#     print_in_color(e,'red')




