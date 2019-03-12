# Parameters #
grep_string = ' ERROR '
result_dir = 'Overcloud_' + grep_string.replace(' ', '')+'_CLI_Log_Tool'
overcloud_logs_dir = '/var/log/containers'
overcloud_ssh_user = 'heat-admin'
overcloud_ssh_key = '/home/stack/.ssh/id_rsa'
source_rc_file_path='/home/stack/'
overcloud_home_dir = '/home/' + overcloud_ssh_user + '/'
user_start_time='2019-03-01 00:00:00'