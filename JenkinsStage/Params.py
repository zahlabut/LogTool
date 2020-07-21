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


# Log debug level to export #
grep_string = ' ERROR '

# Path that will be used for saving LogTool result files
result_dir = 'LogTool_Result_Files'

# Directories names needed for execution
temp_dir = 'temp_dir'
destination_dir = 'Jenkins_Job_Files'

# Path to source files on Undercloud
source_rc_file_path='/home/stack/'

# Save raw data section inside the result file
save_raw_data='yes'

# Analyze all  logs, another option for this parameter is: osp_logs_only
log_type='all_logs'

# Overcloud node names
overcloud_node_names=['aio', 'ceph', 'cfme', 'cfme_tester', 'compute', 'compute_dvr', 'computehci',
                      'contnet', 'controller', 'database', 'diskless', 'freeipa', 'hcicephall',
                      'heat', 'ironic', 'loadbalancer', 'mds', 'messaging', 'monitor', 'networker',
                      'novacontrol', 'odl', 'openshift-infra', 'openshift-master', 'openshift-tester',
                      'openshift-worker', 'opstools', 'osdcompute', 'patcher', 'radosgw', 'serviceapi',
                      'standalone', 'swift', 'telemetry', 'tester', 'tripleo', 'undercloud', 'veos',
                      'vqfx-pfe', 'vqfx']

# Undercloud "node" names
undercloud_node_names=['undercloud','hypervisor']


#Parameter is added with: echo "artifact_url='"$artifact_url"'" >> Params.py
artifact_url='https://rhos-qe-jenkins.rhev-ci-vms.eng.rdu2.redhat.com/job/OSPD-Customized-Deployment-virt/15926/artifact/'
#artifact_url='https://rhos-qe-jenkins.rhev-ci-vms.eng.rdu2.redhat.com/view/Phase3/view/OSP%2016.1/view/storage/job/DFG-all-unified-16.1_director-rhel-virthost-3cont_2comp_3ceph-ipv4-geneve-ceph-native-default/104/artifact/'


#Parameter is added with: echo "start_time='"suser_tart_time"'" >> Params.py
user_start_time='2020-01-01 00:00:00'

#Parameter is added with: echo "download_overcloud_logs='"download_overcloud_logs"'" >> Params.py
download_overcloud_logs='true'

#Parameter is added with: echo "overcloud_logs_dirs='"overcloud_logs_dirs"'" >> Params.py
overcloud_log_dirs = 'var/log/'

#Parameter is added with: echo "download_undercloud_logs='"download_undercloud_logs"'" >> Params.py
download_undercloud_logs='true'

#Parameter is added with: echo "undercloud_log_dirs='"undercloud_log_dirs"'" >> Params.py
undercloud_log_dirs = 'var/log,home/stack,usr/share,var/lib,etc/ssh'


grep_string_only=True
grep_command="grep ' ERROR '"

delete_downloaded_files=True


# Do not delete empty last line!!! #



