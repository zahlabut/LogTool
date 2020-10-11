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
from .Common import *
from .Params import *
import unittest
import warnings
import sys
import time
import ssl
from urllib2 import urlparse
from urllib.parse import urljoin
from BeautifulSoup import BeautifulSoup

spec_print(['Job Parameters:','artifact_url: ' + artifact_url,'user_start_time: ' + user_start_time,
            'download_overcloud_logs: ' + download_overcloud_logs,
            'overcloud_log_dirs: ' + overcloud_log_dirs,'download_undercloud_logs: ' + download_undercloud_logs,
            'undercloud_log_dirs: ' + undercloud_log_dirs],'bold')

### Create Result Folders ###
create_dir(result_dir)

# Set boolean parameters
if download_overcloud_logs == 'true':
    download_overcloud_logs = True
else:
    download_overcloud_logs = False
if download_undercloud_logs == 'true':
    download_undercloud_logs = True
else:
    download_undercloud_logs = False
if ',' in overcloud_log_dirs:
    overcloud_log_dirs = overcloud_log_dirs.split(',')
else:
    overcloud_log_dirs = [overcloud_log_dirs]
if ',' in undercloud_log_dirs:
    undercloud_log_dirs = undercloud_log_dirs.split(',')
else:
    undercloud_log_dirs = [undercloud_log_dirs]
# Add grep mode parameters
if grep_string_only=='true':
    grep_string_only=True
if delete_downloaded_files=='true':
    delete_downloaded_files=True

#class LogTool(unittest.TestCase):
class LogTool(unittest.TestCase):
    # This will stop the execution on any failure/error
    def run(self, result=None):
        if result.failures or result.errors:
            print("\nAborted")
        else:
            super(LogTool, self).run(result)
    @staticmethod
    def raise_warning(msg):
        warnings.warn(message=msg, category=Warning)

    '''This test is planned to validate all the parameters, provided by user'''
    def test_1_validate_parameterts(self):
        print ('\ntest_1_validate_parameterts')
        self.assertEqual(check_user_time(user_start_time)['Error'],None,'ERROR - Provided "user_start_time" is invalid!'+
                        '\nProvided value  was: ' + user_start_time+ '\nSee expected value, used by default.')

        self.assertEqual((artifact_url.lower().endswith('artifact') or artifact_url.lower().endswith('artifact/')),
                         True,"ERROR - Provided 'artifact_url' doesn't seem to be proper artifact URL!"+
                         '\nProvided value  was: ' + artifact_url+'\nSee expected value, used by default.')

        self.assertIn(download_overcloud_logs, [True, False], 'ERROR - boolean "download_overcloud_logs" is invalid!')
        self.assertIn(download_undercloud_logs,[True,False],'ERROR - boolean "download_undercloud_logs" is invalid!')
        self.assertIn('list',str(type(overcloud_log_dirs)),'ERROR - "overcloud_logs_dirs" is not list type!')
        self.assertIn('list',str(type(undercloud_log_dirs)),'ERROR - "undercloud_log_dirs" is not list type!')
        if grep_string_only==True and 'grep' not in grep_command:
            to_fail=True
            self.assertEqual(to_fail,False,"ERROR - 'grep_string_only' options is checked, but there is no proper 'grep_command' detected!"+
                             '\nProvided value  was: \n' + grep_command+'\nSee an example value, used by default.')

    '''This test is planned to parse artifact_url and to create a dictionary
    of relevant links: *.tar.gz file, IR logs, Tempest Logs and Console log'''
    #@unittest.skipIf(LogTool.stop_execution==True,'Skip!')
    def test_2_parse_artifact_url(self):
        print('\ntest_2_parse_artifact_url')
        # Parse artifact_url html

        import os, ssl
        if (not os.environ.get('PYTHONHTTPSVERIFY', '') and
                getattr(ssl, '_create_unverified_context', None)):
            ssl._create_default_https_context = ssl._create_unverified_context
        html=download_file(artifact_url)['Content']



        soup = BeautifulSoup(html)
        tar_gz_files = []
        ir_logs_urls = []
        tempest_log_urls = []
        tobiko_log_urls=[]
        for link in soup.findAll('a'):
            if 'tempest-results' in link:
                tempest_results_url = urljoin(artifact_url, link.get('href'))
                tempest_response = urllib.request.urlopen(tempest_results_url)
                html = tempest_response.read()
                soup = BeautifulSoup(html)
                for link in soup.findAll('a'):
                    if str(link.get('href')).endswith('.html'):
                        tempest_html = link.get('href')
                        tempest_log_urls.append(urljoin(artifact_url, 'tempest-results') + '/' + tempest_html)

            if 'Test Result' in link:
                tobiko_results_url = urljoin(artifact_url, link.get('href'))
                tobiko_link_name=link.get('href')
                tobiko_response = urllib.request.urlopen(tobiko_results_url)
                html = tobiko_response.read()
                soup = BeautifulSoup(html)
                for link in soup.findAll('a'):
                    if str(link.get('href')).startswith('tobiko.tests'):
                        tobiko_html = link.get('href')
                        tobiko_log_urls.append(urljoin(artifact_url, tobiko_link_name) + '/' + tobiko_html)
                tobiko_log_urls=list(set(tobiko_log_urls))

            if str(link.get('href')).endswith('.tar.gz'):
                tar_link = urlparse.urljoin(artifact_url, link.get('href'))
                tar_gz_files.append(tar_link)
            if str(link.get('href')).endswith('.sh'):
                sh_page_link = urlparse.urljoin(artifact_url, link.get('href'))
                response = urllib.request.urlopen(sh_page_link)
                html = response.read()
                soup = BeautifulSoup(html)
                for link in soup.findAll('a'):
                    if str(link.get('href')).endswith('.log'):
                        ir_logs_urls.append(sh_page_link + '/' + link.get('href'))
        console_log_url=artifact_url.strip().replace('artifact','consoleFull').strip('/')
        all_links={'ConsoleLog':[console_log_url],'TempestLogs':tempest_log_urls,
                   'InfraredLogs':ir_logs_urls,'TarGzFiles':tar_gz_files,'TobikoLogs':tobiko_log_urls}
        print_dic(all_links)
        LogTool.all_links=all_links

    '''This test is planned to filter the previous created dictionary (in test3) according to
    user's needs. In phase one it will only filter out tar.gz files, for example Undercloud
     files if user is intresting in Overcloud nodes only, will be filtered out'''
    def test_3_filtering_phase_one(self):
        print('\ntest_3_filtering_phase_one')
        filtered_urls=[]
        tar_gz_urls = LogTool.all_links['TarGzFiles']
        for url in tar_gz_urls:
            a = urlparse.urlparse(url)
            basename=os.path.basename(a.path)
            if download_overcloud_logs==True:
                for name in overcloud_node_names:
                    if name.lower() in basename.lower():
                        filtered_urls.append(url)
                        break
            if download_undercloud_logs==True:
                for name in undercloud_node_names:
                    if name.lower() in basename.lower():
                        filtered_urls.append(url)
                        break
        spec_print(['Filtered *.tar.gz files after phase one filtering']+filtered_urls,'bold')
        LogTool.all_links['TarGzFiles']=list(set(filtered_urls))

    ''''This test is planned to download all files after the first filtering phase'''
    def test_4_download_files(self):
        print('\ntest_4_download_files')
        # Create temp directory
        create_dir(temp_dir)
        for key in list(LogTool.all_links.keys()):
            for url in LogTool.all_links[key]:
                res = download_file(url, temp_dir)
                if res['Status'] == 200:
                    print_in_color('OK --> ' + url, 'blue')
                else:
                    print_in_color('Failed to download: ' + url, 'red')
                if key=='TempestLogs':
                    shutil.move(res['FilePath'],res['FilePath'].replace('.html','.log'))
                if key=='ConsoleLog':
                    shutil.move(res['FilePath'],res['FilePath']+'.log')
        spec_print(['Downloaded files:']+os.listdir(temp_dir),'bold')

    '''This test is planned to Unzip all *tar.gz files inside the temp dir'''
    def test_5_unzip_tar_gz_files(self):
        print('\ntest_5_unzip_tar_gz_files')
        for fil in os.listdir(os.path.abspath(temp_dir)):
            if fil.endswith('.tar.gz'):
                cmd = 'tar -zxvf ' + os.path.join(os.path.abspath(temp_dir), fil) + ' -C ' + os.path.abspath(
                    temp_dir) + ' >/dev/null' + ';' + 'rm -rf ' + os.path.join(
                    os.path.abspath(temp_dir), fil)
                print_in_color('Unzipping ' + fil + '...', 'bold')
                print_in_color(cmd,'bold')
                os.system(cmd)

    ''''This test is planned to filter out all not relevant path (as provided by user in: "undercloud_log_dirs"
    and "overcloud_log_dirs") parameters'''
    #@unittest.skipIf(grep_command==True,'Grep Only Mode used')
    def test_6_filtering_phase_two(self):
        create_dir(destination_dir)
        node_types=[(undercloud_node_names,undercloud_log_dirs),(overcloud_node_names,overcloud_log_dirs)]
        for node_type in node_types:
            node_dirs_to_copy=[]
            for fil in os.listdir(temp_dir):
                for name in node_type[0]:
                    if (name.lower() in fil.lower()) and os.path.isdir(os.path.join(os.path.abspath(temp_dir),fil)):
                        node_dirs_to_copy.append(os.path.join(os.path.abspath(temp_dir),fil))
                        break
            for item in node_dirs_to_copy:
                for path in node_type[1]:
                    if os.path.isdir(os.path.join(item,path))==True:
                        shutil.copytree(os.path.join(item,path),os.path.join(destination_dir,os.path.basename(item),path))
        for log in os.listdir(temp_dir):
            if log.endswith('.log'):
                shutil.copyfile(os.path.join(temp_dir,log),os.path.join(destination_dir,log))

    ''''This test is analyzing logs and running grep mode if enabled'''
    #@unittest.skipIf(grep_string_only==True,'Grep Only Mode used')
    def test_7_analyze_logs(self):
        mode_start_time=time.time()
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
                        'Execution time: ' + str(round(end_time-mode_start_time, 2)) + '[sec]'],'red')
            print((com_result['CommandOutput']))

    '''This test is planned to run "grep" mode'''
    #@unittest.skipIf(grep_command=='','No provided grep command')
    def test_8_grep_string(self):
        print('\ntest_8_grep_string')
        grep_result_folder='Grep_HTML_Report'
        create_dir(grep_result_folder)
        file_name = 'GrepCommandOutput.txt'
        empty_file_content(file_name)
        for log in collect_log_paths(destination_dir,[]):
            command=grep_command+' '+log
            #print_in_color(command,'bold')
            output=exec_command_line_command(command)
            if output['ReturnCode']==0:
                append_to_file(file_name,'\n\n\n### '+log+' ###\n')
                append_to_file(file_name,output['CommandOutput'])
        shutil.move(os.path.abspath(file_name),os.path.abspath(grep_result_folder))

    '''This test is planned to delete all downloaded files'''
    def test_9_delete_downloaded_files(self):
        print('\ntest_9_delete_downloaded_files')
        if delete_downloaded_files==True:
            shutil.rmtree(destination_dir)
            shutil.rmtree(temp_dir)

