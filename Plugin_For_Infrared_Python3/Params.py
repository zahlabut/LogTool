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

### Parameters ###

# Log debug level to export #
grep_string = ' ERROR '

# Path that will be used for saving LogTool result files
result_dir = 'LogTool_Result_Files'

# Path to OSP logs on Overcloud nodes
overcloud_logs_dir = '/var/log/containers'

# Path to OSP logs on Undercloud
undercloud_logs_dir = ['/var/log/containers','/home/stack']

# SSH credentials used for connection to Overcloud nodes
overcloud_ssh_user = 'heat-admin'
overcloud_ssh_key = '/home/stack/.ssh/id_rsa'
overcloud_home_dir = '/home/' + overcloud_ssh_user + '/'

# Path to source files on Undercloud
source_rc_file_path='/home/stack/'

# Start time that will be used to export Errors/Warnings
user_start_time='2019-03-01 00:00:00'

# Save raw data section inside the result file
save_raw_data='yes'

# Analyze all  logs, another option for this parameter is: osp_logs_only
log_type='all_logs'

# Directories on Undercloud host that are going to be analyzed
undercloud_logs = ['/var/log','/home/stack','/usr/share/','/var/lib/']
