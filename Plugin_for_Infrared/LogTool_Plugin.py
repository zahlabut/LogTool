#!/usr/bin/python
import shutil
from Common import *
from Params import *
import unittest
import warnings

usage = ['LogTool - extracts Overcloud Errors and provides statistics',
         '1) Set needed configuration in Common.py configuration file.',
         '2) Type: "python -m unittest Take_Me_Jenkins" to start this script']
if len(sys.argv)==1 or (sys.argv[1] in ['-h','--help']):
    spec_print(usage, 'yellow')
    sys.exit(1)



# Parameters #
errors_on_execution = {}
competed_nodes={}


# Runtime Logs #
empty_file_content('Runtime.log')
empty_file_content('Error.log')
sys.stdout=MyOutput('Runtime.log')
sys.stderr=MyOutput('Error.log')

### Check given user_start_time ###
if check_time(user_start_time)!=True:
    print_in_color('FATAL ERROR - provided "user_start_time" value: "'+user_start_time+'" in Params.py is incorrect!!!')
    sys.exit(1)

### Get all nodes ###
nodes = exec_command_line_command('source ' + source_rc_file_path + 'stackrc;openstack server list -f json')['JsonOutput']
nodes = [{'Name': item['name'], 'ip': item['networks'].split('=')[-1]} for item in nodes]

### Create Result Folders ###
if result_dir in os.listdir('.'):
    shutil.rmtree(result_dir)
os.mkdir(result_dir)

class LogTool(unittest.TestCase):
    @staticmethod
    def raise_warning(msg):
        warnings.warn(message=msg, category=Warning)

    """ Start LogTool and export Errors from Overcloud """
    def test_1_Export_Overcloud_Errors(self):
        print '\ntest_1_Export_Overcloud_Errors'
        mode_start_time = time.time()
        for node in nodes:
            print '\n'+'-'*40+'Remote Overcloud Node -->', str(node)+'-'*40
            result_file = node['Name'].replace(' ', '') + '.log'
            s = SSH(node['ip'], user=overcloud_ssh_user, key_path=overcloud_ssh_key)
            s.ssh_connect_key()
            s.scp_upload('Extract_On_Node_NEW.py', overcloud_home_dir + 'Extract_On_Node_NEW.py')
            s.ssh_command('chmod 777 ' + overcloud_home_dir + 'Extract_On_Node_NEW.py')
            command = "sudo " + overcloud_home_dir + "Extract_On_Node_NEW.py '" + str(
                user_start_time) + "' " + overcloud_logs_dir + " '" + grep_string + "'" + ' ' + result_file
            print 'Executed command on host --> ', command
            com_result = s.ssh_command(command)
            print com_result['Stdout']  # Do not delete me!!!
            if 'SUCCESS!!!' in com_result['Stdout']:
                print_in_color(str(node) + ' --> OK', 'green')
                competed_nodes[node['Name']] = True
            else:
                print_in_color(str(node) + ' --> FAILED', 'yellow')
                self.raise_warning(str(node) + ' --> FAILED')
                errors_on_execution[node['Name']] = False
            s.scp_download(overcloud_home_dir + result_file, os.path.join(os.path.abspath(result_dir), result_file))
            # Clean all #
            files_to_delete = ['Extract_On_Node_NEW.py', result_file]
            for fil in files_to_delete:
                s.ssh_command('rm -rf ' + fil)
            s.ssh_close()
        script_end_time = time.time()
        if len(errors_on_execution) == 0:
            spec_print(['Completed!!!', 'Result Directory: ' + result_dir,
                        'Execution Time: ' + str(script_end_time - mode_start_time) + '[sec]'], 'green')
        else:
            if len(errors_on_execution)==len(nodes):
                spec_print(['Execution has failed for all nodes :-( ',
                           'Execution Time: ' + str(script_end_time - mode_start_time) + '[sec]'],'red')
            else:
                spec_print(['Completed with failures!!!', 'Result Directory: ' + result_dir,
                            'Execution Time: ' + str(script_end_time - mode_start_time) + '[sec]',
                            'Failed nodes:'] + [k for k in errors_on_execution.keys()], 'yellow')
        if len(competed_nodes)==0:
            self.raise_warning('LogTool execution has failed to be executed on all Overcloud nodes :-(')

    """ Start LogTool and export Errors from Undercloud """
    def test_2_Export_Undercloud_Errors(self):
        print '\ntest_2_Export_Undercloud_Errors'
        mode_start_time = time.time()
        result_file='Undercloud.log'
        command="sudo python Extract_On_Node_NEW.py '" + str(user_start_time) + "' " + undercloud_logs_dir + " '" + grep_string + "'" + ' ' + result_file
        com_result=exec_command_line_command(command)
        shutil.move(result_file, os.path.join(os.path.abspath(result_dir),result_file))
        end_time=time.time()
        if com_result['ReturnCode']==0:
            spec_print(['Completed!!!','Result Directory: '+result_dir,'Execution Time: '+str(end_time-mode_start_time)+'[sec]'],'green')
        else:
            spec_print(['Completed!!!', 'Result Directory: ' + result_dir,
                        'Execution Time: ' + str(end_time - mode_start_time) + '[sec]'], 'red')
        if com_result['ReturnCode']!=0:
            self.raise_warning('LogTool execution has failed to be executed on Underloud logs :-(')

    """ This test will create a Final report. The report file will be created only when ERRORs have been detected.
        Report file will be used as indication to ansible to PASS or FAIl, in case of failure it will "cat" its
        content. 
    """
    def test_3_create_final_report(self):
        print '\ntest_3_create_final_report'
        report_file_name = 'LogTool_Report.log'
        if report_file_name in os.listdir('.'):
            os.remove(report_file_name)
        failed_nodes={}
        detected_unique_errors=''
        for fil in os.listdir(os.path.abspath(result_dir)):
            fil_path=os.path.join(os.path.abspath(result_dir),fil)
            data=open(fil_path,'r').readlines()
            if 'Total Number of Errors/Warnings is:0' not in str(data):
                failed_nodes[fil]=fil_path
                detected_unique_errors+='\n\n\n### Unique ERRORs in: '+fil+'###'
                unique_section_start_index=int(data[-1].split(' --> ')[-1])
                for line in data[unique_section_start_index:-7]:
                    detected_unique_errors+=line
        if len(failed_nodes)!=0:
            append_to_file(report_file_name,'Failed - Errors have been detected on: '+str(failed_nodes.keys())+
                        '\nDetected Unique ERRORs are:\n'+detected_unique_errors+
                          '\nCheck LogTool result files in: "'+result_dir+'" for more details')


