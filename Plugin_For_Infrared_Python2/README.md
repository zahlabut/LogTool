# General
This plugin can be used by Infrared in order to export Error messages from OSP logs on both: Undercloud and Overcloud.
LogTool will be installed and executed on remote host (Undercoud), once execution is competed, it will prompt
all the UNIQUE Error messages for each OSP component. In addition to that, it will generate report files for each
OSP component, that could be used for deeper investigation. The plan is to include these files into Jenkins Job Artifacts.

# Install Infrared
*sudo yum install git gcc libffi-devel openssl-devel<br/>*
*sudo yum install python-virtualenv<br/>*
*sudo yum install libselinux-python<br/>*
*git clone https://github.com/redhat-openstack/infrared.git<br/>*
*cd infrared<br/>*
*virtualenv .venv && source .venv/bin/activate<br/>*
*sudo pip install --upgrade pip<br/>*
*sudo pip install --upgrade setuptools<br/>*
*sudo pip install . <br/>*


# Install LogTool Plugin
*ir plugin add https://github.com/zahlabut/LogTool.git --src-path Plugin_For_Infrared_Python3*

# Uninstall LogTool Plugin
*ir plugin remove logtool*

# Inventory file (Import inventory file)
*ir workspace import http://YOUR_CI_SETUP/workspace.tgz<br/>*
For example <br/>
*ir workspace import http://staging-jenkins2-qe-playground.usersys.redhat.com/job/DFG-hardware_provisioning-rqci-14_director-7.6-vqfx-ipv4-vxlan-IR-networking_ansible-poc/30/artifact/workspace.tgz*<br/>
**Note:** <br/>
There is a need to run "ssh-copy-id" in order to enable SSH connection using keys. This is the way
Ansible connects to Hypervisors (without Password).<br/>


# Start LogTool plugin
*ir logtool*

# Troubleshooting
There are two log files created on runtime on remote host (undercloud) under /home/stack/LogTool/Plugin_for_Infrared:
 _"Error.log"_ and _"Runtime.log"_.
Please add the content of both into the description of issue you'd like to open.


# To Do list
1) Increase the execution time by adding threads
2) Support Python3
3) LogTool stage will always been executed on NEW setup, don't handle timestamps in logs
4) RabbitMQ log, are currently in Black List add support to parse this log