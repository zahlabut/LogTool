# General
This LogTool plugin can be used by Infrared in order to export Error messages from OSP logs: Undercloud and Overcloud.
The plugin will activate LogTool on remote host (Undercoud), once LogTool execution will be completed it will prompt
into the output all the UNIQUE Error messages for each OSP component. Also it will generate report file for each
component, that could be used for deeper investigation. The plan is to include these files into Job Artifact.

# Install Infrared
*sudo yum install git gcc libffi-devel openssl-devel<br/>*
*sudo yum install python-virtualenv<br/>*
*sudo yum install libselinux-python<br/>*
*git clone https://github.com/redhat-openstack/infrared.git<br/>*
*cd infrared<br/>*
*virtualenv .venv && source .venv/bin/activate<br/>*
*pip install --upgrade pip<br/>*
*pip install --upgrade setuptools<br/>*
*pip install .<br/>*


# Install LogTool Plugin
*ir plugin add https://github.com/zahlabut/LogTool.git --src-path Plugin_for_Infrared*

# Uninstall LogTool Plugin
*ir plugin remove logtool*

# Inventory file
*ir workspace import http://staging-jenkins2-qe-playground.usersys.redhat.com/job/DFG-hardware_provisioning-rqci-14_director-7.6-vqfx-ipv4-vxlan-IR-networking_ansible-poc/30/artifact/workspace.tgz*

# Start LogTool plugin
*ir logtool*

# Troubleshooting
There are two log files created on runtime on remote host (undercloud) under /home/stack/LogTool/Plugin_for_Infrared:
 _"Error.log"_ and _"Runtime.log"_.
Please add the content of both into the description of issue you'd like to open.