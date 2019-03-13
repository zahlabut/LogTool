### Parameters ###

# Log debug level to export #
grep_string = ' ERROR '

# LogTool Report file name
report_file_name='LogTool_Report.log'

# Path that will be used for saving LogTool result files
result_dir = 'Overcloud_' + grep_string.replace(' ', '')+'_Log_Tool_Results'

# Path to OSP logs on Overcloud nodes
overcloud_logs_dir = '/var/log/containers'

# Path to OSP logs on Undercloud
undercloud_logs_dir = '/var/log/containers'

# SSH credentials used for connection to Overcloud nodes
overcloud_ssh_user = 'heat-admin'
overcloud_ssh_key = '/home/stack/.ssh/id_rsa'
overcloud_home_dir = '/home/' + overcloud_ssh_user + '/'

# Path to source files on Undercloud
source_rc_file_path='/home/stack/'

# Start time that will be used to export Errors/Warnings
user_start_time='2019-03-01 00:00:00'