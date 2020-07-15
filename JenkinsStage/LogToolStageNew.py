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
import sys
import time
from urllib2 import urlparse
from urlparse import urljoin
from BeautifulSoup import BeautifulSoup

spec_print(['Job Parameters:','artifact_url: '+artifact_url,'user_start_time: '+user_start_time,
            'analyze_overcloud_logs: '+analyze_overcloud_logs,
            'overcloud_log_dirs: '+overcloud_log_dirs,'analyze_undercloud_logs: '+analyze_undercloud_logs,
            'undercloud_log_dirs: '+undercloud_log_dirs],'bold')

### Create Result Folders ###
if result_dir in os.listdir('.'):
    shutil.rmtree(result_dir)
os.mkdir(result_dir)

# Set boolean parameters
if analyze_overcloud_logs == 'true':
    analyze_overcloud_logs = True
else:
    analyze_overcloud_logs = False
if analyze_undercloud_logs == 'true':
    analyze_undercloud_logs = True
else:
    analyze_undercloud_logs = False
# Set List parameters
if ',' in overcloud_log_dirs:
    overcloud_log_dirs = overcloud_log_dirs.split(',')
else:
    overcloud_log_dirs = [overcloud_log_dirs]
if ',' in undercloud_log_dirs:
    undercloud_log_dirs = undercloud_log_dirs.split(',')
else:
    undercloud_log_dirs = [undercloud_log_dirs]

class LogTool(unittest.TestCase):
    @staticmethod
    def raise_warning(msg):
        warnings.warn(message=msg, category=Warning)


    '''This test is planned to validate all the parameters,provided by user'''
    def test_1_validate_parameterts(self):
        print ('\ntest_1_validate_parameterts')
        self.assertEqual(check_user_time(user_start_time)['Error'],None,'ERROR - Provided "user_start_time" is invalid!'+
                        '\nProvided value  was: ' + user_start_time+ '\nSee expected value, used by default.')
        self.assertIn('artifact',artifact_url.lower(),"ERROR - Provided 'artifact_url' doesn't seem to be proper artifact URL!"+
                        '\nProvided value  was: ' + artifact_url+'\nSee expected value, used by default.')
        self.assertIn(analyze_overcloud_logs,[True,False],'ERROR - boolean "analyze_overcloud_logs" is invalid!')
        self.assertIn(analyze_undercloud_logs,[True,False],'ERROR - boolean "analyze_undercloud_logs" is invalid!')
        self.assertIn('list',str(type(overcloud_log_dirs)),'ERROR - "overcloud_logs_dirs" is not list type!')
        self.assertIn('list',str(type(undercloud_log_dirs)),'ERROR - "undercloud_log_dirs" is not list type!')

    '''This test is planned to parse artifact_url and to create a dictionary
    of relevant links: *.tar.gz file, IR logs, Tempest Logs and Console log'''
    def test_2_parse_artifact_url(self):
        print('\ntest_2_parse_artifact_url')
        # Parse artifact_url html
        #response = urllib2.urlopen(artifact_url,c)

        response=requests.get(artifact_url,verify=False).content

        html = response.read()
        parsed_url = urlparse.urlparse(artifact_url)
        base_url = parsed_url.scheme + '://' + parsed_url.netloc
        soup = BeautifulSoup(html)
        tar_gz_files = []
        ir_logs_urls = []
        tempest_log_urls = []
        for link in soup.findAll('a'):
            if 'tempest-results' in link:
                tempest_results_url = urljoin(artifact_url, link.get('href'))
                tempest_response = urllib2.urlopen(tempest_results_url)
                html = tempest_response.read()
                soup = BeautifulSoup(html)
                for link in soup.findAll('a'):
                    if str(link.get('href')).endswith('.html'):
                        tempest_html = link.get('href')
                        tempest_log_urls.append(urljoin(artifact_url, 'tempest-results') + '/' + tempest_html)
            if str(link.get('href')).endswith('.tar.gz'):
                tar_link = urlparse.urljoin(artifact_url, link.get('href'))
                tar_gz_files.append(tar_link)

            if str(link.get('href')).endswith('.sh'):
                sh_page_link = urlparse.urljoin(artifact_url, link.get('href'))
                response = urllib2.urlopen(sh_page_link)
                html = response.read()
                soup = BeautifulSoup(html)
                for link in soup.findAll('a'):
                    if str(link.get('href')).endswith('.log'):
                        ir_logs_urls.append(sh_page_link + '/' + link.get('href'))
        console_log_url=artifact_url.strip().replace('artifact','consoleFull').strip('/')
        all_links={'CosoleLog':console_log_url,'TempestLogs':tempest_log_urls,
                   'InfraredLogs':ir_logs_urls,'TarGzFiles':tar_gz_files}
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
            if analyze_overcloud_logs==True:
                for name in overcloud_node_names:
                    if name.lower() in basename.lower():
                        filtered_urls.append(url)
                        break
            if analyze_undercloud_logs==True:
                for name in undercloud_node_names:
                    if name.lower() in basename.lower():
                        filtered_urls.append(url)
                        break
        spec_print(['Filtered *.tar.gz files after phase one filtering']+filtered_urls,'bold')
        LogTool.all_links['TarGzFiles']=filtered_urls

    def test_4_download_files(self):
        print('\ntest_4_download_files')
        print_dic(LogTool.all_links)

        import ssl
        ssl._create_default_https_context = ssl._create_unverified_context


        # Create temp directory
        temp_dir = 'temp_dir'
        temp_dir = os.path.join(os.path.dirname(os.path.abspath('.')), temp_dir)
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.mkdir(temp_dir)
        for key in LogTool.all_links.keys():
            for url in LogTool.all_links[key]:
                print_in_color(url,'bold')
                a = urlparse.urlparse(url)
                basename = os.path.basename(a.path)
                if url.endswith('.html'):
                    res = download_file(url, temp_dir)
                    if res['Status'] != 200:
                        print_in_color('Failed to download: ' + url, 'red')
                    else:
                        print_in_color('OK --> ' + url, 'blue')
                    shutil.move(os.path.join(temp_dir, basename),os.path.join(temp_dir,basename.replace('.html','.log')))
                else:
                    res = download_file(url, temp_dir)
                    if res['Status'] != 200:
                        print_in_color('Failed to download: ' + url, 'red')
                    else:
                        print_in_color('OK --> ' + url, 'blue')









        #destination_dir = 'Jenkins_Job_Files'
    #
    #
    #
    #
    #
    #     shutil.move(os.path.join(destination_dir, 'consoleFull'),os.path.join(destination_dir,'consoleFull.log'))
    #     # Download Infared Logs .sh, files in .sh directory on Jenkins
    #     if len(ir_logs_urls)!=0:
    #         for url in ir_logs_urls:
    #             res = download_file(url, destination_dir)
    #             if res['Status'] != 200:
    #                 print_in_color('Failed to download: ' + url, 'red')
    #             else:
    #                 print_in_color('OK --> ' + url, 'blue')
    #
    #
    #     # Download tempest log (html #)
    #     if tempest_log_url!=None:
    #         res = download_file(tempest_log_url,destination_dir)
    #         if res['Status'] != 200:
    #             print_in_color('Failed to download: ' + tempest_log_url, 'red')
    #         else:
    #             print_in_color('OK --> ' + tempest_log_url, 'blue')
    #
    #
    #     # Print list of downloaded files
    #     spec_print(['Downloaded files:']+os.listdir(destination_dir),'bold')
    #
    #     # Unzip all downloaded .tar.gz files
    #     for fil in os.listdir(os.path.abspath(destination_dir)):
    #         if fil.endswith('.tar.gz'):
    #             cmd = 'tar -zxvf ' + os.path.join(os.path.abspath(destination_dir), fil) + ' -C ' + os.path.abspath(
    #                 destination_dir) + ' >/dev/null' + ';' + 'rm -rf ' + os.path.join(
    #                 os.path.abspath(destination_dir), fil)
    #             print_in_color('Unzipping ' + fil + '...', 'bold')
    #             os.system(cmd)
    #             os.system('rm -rf '+fil)
    #     # Run LogTool analyzing
    #     print_in_color('\nStart analyzing downloaded OSP logs locally', 'bold')
    #     result_dir = 'Jenkins_Job_' + grep_string.replace(' ', '')
    #     if os.path.exists(os.path.abspath(result_dir)):
    #         shutil.rmtree(os.path.abspath(result_dir))
    #     result_file = os.path.join(os.path.abspath(result_dir),
    #                                'LogTool_Result_' + grep_string.replace(' ', '') + '.log')
    #     command = "python2 Extract_On_Node.py '" +user_start_time+ "' " + os.path.abspath(
    #         destination_dir) + " '" + grep_string + "'" + ' ' + result_file
    #
    #     # shutil.copytree(destination_dir, os.path.abspath(result_dir))
    #     exec_command_line_command('cp -r ' + destination_dir + ' ' + os.path.abspath(result_dir))
    #     print_in_color('\n --> ' + command, 'bold')
    #     com_result = exec_command_line_command(command)
    #     # print (com_result['CommandOutput'])
    #     end_time = time.time()
    #     if 'SUCCESS!!!' in com_result['CommandOutput']:
    #         spec_print(com_result['CommandOutput'].splitlines()[-3:],'bold')
    #         spec_print(['Completed!!!',
    #                     "\nCheck LogTool results in 'Build Artifacts' directory: "+os.path.basename(result_dir),
    #                     '\nLogTool ResultFile is: '+os.path.basename(result_file),
    #                     'Analyzing time: ' + str(round(end_time - mode_start_time, 2)) + '[sec]'],
    #                     'blue')
    #     else:
    #         spec_print(['Failed to analyze logs :-(', 'Result Directory: ' + result_dir,
    #                     'Execution time: ' + str(round(end_time - mode_start_time, 2)) + '[sec]'],'red')