#!/usr/bin/python
import shutil
from Common import *
import random
#import signal
import datetime
import threading


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

def run_on_node(node):
    print('-' * 90)
    print('Remote Overcloud Node -->', str(node))
    try:
        result_file = node['Name'].replace(' ', '') + '_' + grep_string.replace(' ', '_') + '.log'
        s = SSH(node['ip'], user=overcloud_ssh_user, key_path=overcloud_ssh_key)
        s.ssh_connect_key()
        s.scp_upload('Extract_On_Node.py', overcloud_home_dir + 'Extract_On_Node.py')
        s.ssh_command('chmod 777 ' + overcloud_home_dir + 'Extract_On_Node.py')
        command = "sudo " + overcloud_home_dir + "Extract_On_Node.py '" + str(
            start_time) + "' " + overcloud_logs_dir + " '" + grep_string + "'" + ' ' + result_file + ' ' + save_raw_data
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


### Operation Modes ###
try:
    modes=[#'Export ERRORs/WARNINGs from Overcloud logs OLD',
           'Export ERRORs/WARNINGs from Overcloud logs',
           'Download all logs from Overcloud',
           '"Grep" some string for all Overcloud logs',
           'Check current:CPU,RAM and Disk on Overcloud',
           "Execute user's script",
           'Download "relevant logs" only, by given timestamp',
           'Export ERRORs/WARNINGs from Undercloud logs',
           'Overcloud - check Unhealthy dockers',
           'Extract all logs messages for given time range',
           'Extract NEW (DELTA) messages from Overcloud',
           'Download OSP logs and run LogTool locally',
           '--- Install Python FuzzyWuzzy on Nodes ---',
           ]
    mode=choose_option_from_list(modes,'Please choose operation mode: ')

    if mode[1]=='Download OSP logs and run LogTool locally':
        # Start mode
        options = ['ERROR', 'WARNING']
        option=choose_option_from_list(options,'Please choose debug level: ')
        if option[1]=='ERROR':
            grep_string=' ERROR '
        if option[1]=='WARNING':
            grep_string=' WARNING '

        # Create folder to save the logs
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
            artifacts_url = input('Copy and paste Jenkins URL to to Job Artifacts for example \nhttps://rhos-qe-jenkins.rhev-ci-vms.eng.rdu2.redhat.com/job/DFG-hardware_provisioning-rqci-14_director-7.6-vqfx-ipv4-vxlan-IR-networking_ansible/39/artifact/\nYour URL: ')
            mode_start_time=time.time()
            response = urllib.request.urlopen(artifacts_url)
            html = response.read()
            parsed_url = urlparse(artifacts_url)
            base_url = parsed_url.scheme + '://' + parsed_url.netloc
            #soup = BeautifulSoup(html)
            soup = BeautifulSoup(html, 'lxml')
            tar_gz_files=[]
            for link in soup.findAll('a'):
                if str(link.get('href')).endswith('.tar.gz'):
                    tar_gz_files.append(link)
                    link = urljoin(artifacts_url, link.get('href'))
                    os.system('wget -P ' + destination_dir + ' ' + link)
            if len(tar_gz_files)==0:
                spec_print(['There is no links to *.tar.gz on provided URL page','Nothing to work on :-)'],'red')
                exit('Check your: '+artifacts_url)


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

        # Run LogTool analyzing
        print_in_color('\nStart analyzing downloaded OSP logs locally','bold')
        result_dir='Jenkins_Job_'+grep_string.replace(' ','')
        if os.path.exists(os.path.abspath(result_dir)):
            shutil.rmtree(os.path.abspath(result_dir))
        result_file = os.path.join(os.path.abspath(result_dir), 'LogTool_Result_'+grep_string.replace(' ','')+'.log')
        command = "python3 Extract_On_Node.py '"+"2019-01-01 00:00:00"+"' "+os.path.abspath(destination_dir)+" '"+grep_string+"'" + ' '+result_file
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
            print_in_color('Current date on Overcloud is: ' + com_result['Stdout'].strip(), 'blue')
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
        log_root_dir=choose_option_from_list(undercloud_logs,'Plese choose logs path to analyze:')[1]
        if check_time(start_time)==False:
            print_in_color('Bad timestamp format: '+start_time,'yellow')
            exit('Execution will be interrupted!')
        options=['ERROR','WARNING','failed','fatal']
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
        command="sudo python3 Extract_On_Node.py '" + str(start_time) + "' " + log_root_dir + " '" + grep_string + "'" + ' ' + result_file
        print(command)
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

    if mode[1]=='--- Install Python FuzzyWuzzy on Nodes ---':
        ### Get all nodes ###
        start_time = time.time()
        commands = ['']
        nodes = exec_command_line_command('source ' + source_rc_file_path + 'stackrc;openstack server list -f json')['JsonOutput']
        nodes = [{'Name': item['name'], 'ip': item['networks'].split('=')[-1]} for item in nodes]
        for node in nodes:
            try:
                print(str(node))
                s = SSH(node['ip'], user=overcloud_ssh_user, key_path=overcloud_ssh_key)
                s.ssh_connect_key()
                # Check if pip is installed #
                pip_installed='sudo which pip'
                if len(s.ssh_command(pip_installed)['Stderr'])!=0:
                    print_in_color('Warning - pip is not installed!','yellow')
                    print(s.ssh_command('sudo easy_install pip')['Stdout'])
                    print(s.ssh_command('sudo pip install pip --upgrade'))
                else:
                    print_in_color('pip OK','green')
                # Install FuzzyWuzzy #
                if len(s.ssh_command('pip freeze | grep fuzzywuzzy')['Stdout'])==0:
                    print_in_color('Warning - FuzzyWuzzy is not installed!','yellow')
                    print(s.ssh_command('sudo pip install fuzzywuzzy'))
                else:
                    print_in_color('FuzzyWuzzy OK','green')
                s.ssh_close()
            except Exception as e:
                print_in_color('Failed with: '+str(e))
        spec_print(['Completed!!!', 'Execution Time: ' + str(time.time() - start_time) + '[sec]'],'bold')

    if mode[1]=='"Grep" some string for all Overcloud logs':
        ### Get all nodes ###
        nodes = exec_command_line_command('source ' + source_rc_file_path + 'stackrc;openstack server list -f json')['JsonOutput']
        nodes = [{'Name': item['name'], 'ip': item['networks'].split('=')[-1]} for item in nodes]
        print_in_color("1) You can use special characters in your string\n2) Ignore case sensitive flag is used by default",'yellow')
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
            print(command)
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

    if mode[1] == 'Download all logs from Overcloud':
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
            t = threading.Thread(target=run_on_node, args=(node,))
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



