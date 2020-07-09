#!/usr/bin/python2

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
from Params import *
import unittest
import warnings
import threading
import sys
import time
from urllib2 import urlparse
from urlparse import urljoin

spec_print(['Job Parameters:',artifact_url,user_start_time],'bold')

# Parameters #
errors_on_execution = {}
competed_nodes={}
workers_output={}

### Check given by user user_start_time ###
if check_user_time(user_start_time)['Error']!=None:
    spec_print(['ERROR - Provided "user_start_time" is invalid!',
                'Provided user_start_time is: '+user_start_time,'See expected value, used by default.'],'red')
    sys.exit(1)
if 'artifact' not in artifact_url.lower():
    spec_print(["ERROR - Provided 'artifact_url' doesn't seem to be proper artifact URL!",
                'Provided artifact_url is: '+artifact_url,'See expected value, used by default.'],'red')
    sys.exit(1)



### Create Result Folders ###
if result_dir in os.listdir('.'):
    shutil.rmtree(result_dir)
os.mkdir(result_dir)

class LogTool(unittest.TestCase):
    @staticmethod
    def raise_warning(msg):
        warnings.warn(message=msg, category=Warning)

    def test_1_download_jenkins_job(selfself):
        # Create destination directory
        mode_start_time=time.time()
        destination_dir = 'Jenkins_Job_Files'
        destination_dir = os.path.join(os.path.dirname(os.path.abspath('.')), destination_dir)
        if os.path.exists(destination_dir):
            shutil.rmtree(destination_dir)
        os.mkdir(destination_dir)
        #Import BeautifulSoup
        try:
            from BeautifulSoup import BeautifulSoup
        except Exception as e:
            print_in_color(str(e), 'red')
            print_in_color('Execute "pip install beautifulsoup" to install it!', 'yellow')
            exit('Install beautifulsoup and rerun!')
        # Download logs
        response = urllib2.urlopen(artifact_url)
        html = response.read()
        parsed_url = urlparse.urlparse(artifact_url)
        base_url = parsed_url.scheme + '://' + parsed_url.netloc
        soup = BeautifulSoup(html)
        tar_gz_files = []
        ir_logs_urls = []
        tempest_log_url = None
        for link in soup.findAll('a'):
            if 'tempest-results' in link:
                tempest_results_url = urljoin(artifact_url, link.get('href'))
                tempest_response = urllib2.urlopen(tempest_results_url)
                html = tempest_response.read()
                soup = BeautifulSoup(html)
                for link in soup.findAll('a'):
                    if str(link.get('href')).endswith('.html'):
                        tempest_html = link.get('href')
                        tempest_log_url = urljoin(artifact_url, 'tempest-results') + '/' + tempest_html
                        break
            if str(link.get('href')).endswith('.tar.gz'):
                tar_gz_files.append(link)
                tar_link = urlparse.urljoin(artifact_url, link.get('href'))
                res=download_file(tar_link,destination_dir)
                if res['Status']!=200:
                    print_in_color('Failed to download: '+tar_link,'red')
                else:
                    print_in_color('OK --> ' + tar_link, 'blue')

            if str(link.get('href')).endswith('.sh'):
                sh_page_link = urlparse.urljoin(artifact_url, link.get('href'))
                response = urllib2.urlopen(sh_page_link)
                html = response.read()
                soup = BeautifulSoup(html)
                for link in soup.findAll('a'):
                    if str(link.get('href')).endswith('.log'):
                        ir_logs_urls.append(sh_page_link + '/' + link.get('href'))
        console_log_url=artifact_url.strip().replace('artifact','consoleFull').strip('/')
        res = download_file(console_log_url, destination_dir)
        if res['Status'] != 200:
            print_in_color('Failed to download: ' + console_log_url, 'red')
        else:
            print_in_color('OK --> ' + console_log_url, 'blue')

        shutil.move(os.path.join(destination_dir, 'consoleFull'),os.path.join(destination_dir,'consoleFull.log'))
        # Download Infared Logs .sh, files in .sh directory on Jenkins
        if len(ir_logs_urls)!=0:
            for url in ir_logs_urls:
                res = download_file(url, destination_dir)
                if res['Status'] != 200:
                    print_in_color('Failed to download: ' + url, 'red')
                else:
                    print_in_color('OK --> ' + url, 'blue')


        # Download tempest log (html #)
        if tempest_log_url!=None:
            res = download_file(tempest_log_url,destination_dir)
            if res['Status'] != 200:
                print_in_color('Failed to download: ' + tempest_log_url, 'red')
            else:
                print_in_color('OK --> ' + tempest_log_url, 'blue')

            shutil.move(os.path.join(destination_dir, tempest_html),os.path.join(destination_dir,tempest_html.replace('.html','.log')))

        # Print list of downloaded files
        spec_print(['Downloaded files:']+os.listdir(destination_dir),'bold')

        # Unzip all downloaded .tar.gz files
        for fil in os.listdir(os.path.abspath(destination_dir)):
            if fil.endswith('.tar.gz'):
                cmd = 'tar -zxvf ' + os.path.join(os.path.abspath(destination_dir), fil) + ' -C ' + os.path.abspath(
                    destination_dir) + ' >/dev/null' + ';' + 'rm -rf ' + os.path.join(
                    os.path.abspath(destination_dir), fil)
                print_in_color('Unzipping ' + fil + '...', 'bold')
                os.system(cmd)
                os.system('rm -rf '+fil)
        # Run LogTool analyzing
        print_in_color('\nStart analyzing downloaded OSP logs locally', 'bold')
        result_dir = 'Jenkins_Job_' + grep_string.replace(' ', '')
        if os.path.exists(os.path.abspath(result_dir)):
            shutil.rmtree(os.path.abspath(result_dir))
        result_file = os.path.join(os.path.abspath(result_dir),
                                   'LogTool_Result_' + grep_string.replace(' ', '') + '.log')
        command = "python2 Extract_On_Node.py '" +user_start_time+ "' " + os.path.abspath(
            destination_dir) + " '" + grep_string + "'" + ' ' + result_file

        # shutil.copytree(destination_dir, os.path.abspath(result_dir))
        exec_command_line_command('cp -r ' + destination_dir + ' ' + os.path.abspath(result_dir))
        print_in_color('\n --> ' + command, 'bold')
        com_result = exec_command_line_command(command)
        # print (com_result['CommandOutput'])
        end_time = time.time()
        if 'SUCCESS!!!' in com_result['CommandOutput']:
            spec_print(com_result['CommandOutput'].splitlines()[-3:],'bold')
            spec_print(['Completed!!!',
                        "\nCheck LogTool results in 'Build Artifacts' directory: "+os.path.basename(result_dir),
                        '\nLogTool ResultFile is: '+os.path.basename(result_file),
                        'Analyzing time: ' + str(round(end_time - mode_start_time, 2)) + '[sec]'],
                        'blue')
        else:
            spec_print(['Failed to analyze logs :-(', 'Result Directory: ' + result_dir,
                        'Execution time: ' + str(round(end_time - mode_start_time, 2)) + '[sec]'],'red')