# General
Openstack has a bunch of log files existing and managed on its Overcloud nodes and Undercloud host.
Therefore, when you encountering into some problem and might want to investigate it basing on OSP log files, it's not
an easy stuff, especially when you don't even know which area could have cause to that problem.
If that's the case, LogTool will make your "life" much more easier!
It will save your time and "donkey work" needed for manually investigation.
Basing on fuzzy string matching algorithm, LogToll will provide you all the unique Errors/Warnings messages occurred in the past,
in addition to that, basing on timestamp logged in log's lines, LogTool applying you to "export" such messages for
particular time period in the past, for example: 10 minutes ago, hour ago a day ago e.t.c.
LogTool is a set of Python scripts, its main module PyTool.py is executed on Undercloud host.
Some operation modes are using additional scripts being executed directly on Overcloud nodes, for example:
"Export ERRORs/WARNINGs from Overcloud logs".

**Note**: LogTool supports Python V2 and V3, change working directory according to your needs: LogTool_Python2 or LogTool_Python3.

# Operation modes
**1) Export ERRORs/WARNINGs from Overcloud logs**

This mode is used to extract all unique ERRORs/WARNINGs messages from Overcloud nodes, that took place some time ago.
As user you'll be prompted to provide the "Since Time" and debug level that will be used for extraction: Errors or Warnings.
For example, if something went wrong in the last 10 minutes you'll be able to extract Errors/Warnings messages for this time period only.
This operation mode generates result directory containing result files per Overcloud node.
Result file is a simple text file, that is coming compressed (*.gz) in order to reduce time needed for downloading from Overcloud node.
Note: use "zcat" or any other tool to read/convert compressed file to a regular text file, BTW some of "vi" versions supports reading
compressed data, so you can simply try and use "vi" to read the result file content.
Result file is divided into sections and contains "Table of content" on the bottom.

**Note:**
There are two kinds of log files being detected by LogTool on the fly, "Standard" and "Not Standard" logs.
"Standard" - each log's line has known and defined structure: timestamp, debug level, msg ...
"Not Standard" - log's structure is unknown, it could be third parties logs for example.
In "Table of Content" you'll find: "Section name --> Line number" per section, for example:
1) Raw Data - extracted Errors/Warnings from standard OSP logs since: <Given Timestamp>
   In this section you'll find all extracted Errors/Warnings messages as is without being modified or changed by LogTool.
   Actually these messages are the "Raw Data" used by LogTool for "Fuzzy matching" analysis.
2) Statistics - Number of Errors/Warnings per standard OSP log since: <Given Timestamp>
   In this section, you'll find the amount of Errors/Warnings per Standard log file, this may help you to understand
   what could be potential component, to search for "Root Cause".
3) Statistics - Unique messages, per STANDARD OSP log file since: <Given Timestamp>
   In this section you'll find the unique Errors/Warnings messages since given by you timestamp.
   For more details about each one of unique Error/Warning you can always search for the same message in "Raw Data" section.
4) Statistics - Unique messages per NOT STANDARD log file, since ever
   In this section you'll find the unique messages per not standard log files, unfortunately LogTool cannot handle such
   log files in the same manner as standard Log files, therefor "Since Time" provided by you on extraction, will be ignored and
   you'll see all the unique Errors/Warnings messages since ever.

So the **first thing** you'll have to do, is scrolling down to the bottom of result file, to the "Table of content" and then passing through
its sections (use line indexes mentioned in "Table of Content" to jump into relevant section), where: #2 #3 and #4 are most important.

**2) Download all logs from Overcloud nodes**

Logs from all Overcloud nodes will be compressed and downloaded to local directory on your Undercloud host.

**3) "Grep" some string for all Overcloud logs**

This mode will "grep" some string (given by user) on all Overcloud logs. For example, you might want to see all loged messages for specific request ID, let's say the request ID of "Create VM" that is failed.

**4) Check current:CPU,RAM and Disk on Overcloud**

This mode will display the current: CPU, RAM and Disk info, on each Overcloud node.

**5) Execute user's script**

This mode provides user the ability to run his own script on Overcloud nodes.
Create your own script and save it in UserScripts directory, set proper interpreter in it (for example: #!/usr/bin/bash).

**6) Download "relevant logs" only, by given timestamp**

This mode will download the only Overcloud logs with *"Last Modified" > "given by user timestamp"*.
For example if you got some error 10 minutes ago, you'll probably need to investigate the actual logs only, it means that old logs won't be relevant to you and therefore download such log files is unecessary.
In addition, on Bugzila you can attach file only if its size is less than 21MB, so this mode might help.

**7) Export ERRORs/WARNINGs from Undercloud logs**

This mode is the same as #1, the only difference is that it will use Undercloud logs.

**8) Overcloud - check Unhealthy dockers

This mode is used to search for "Unhealthy" dockers on Nodes

**9)  Download OSP logs and run LogTool locally**

This mode applies you to download OSP logs from Jenkins or Log Storage (cougar11.scl.lab.tlv.redhat.com) and to analyze downloaded logs locally.

**10)  Undercloud - analyze deployment log**

This mode may help you to understand what went wrong while OC or UC deployment, basing on generated log.
Deployment logs are generated when ""--log" option is used, for example inside the "overcloud_deploy.sh" script, the
problem is that such logs are not "friendly" and it's hard to understand what exactly went wrong, especially
when verbosity is set to "vv" or more, this will make the log not readable with a bunch of data inside it.
This mode will provide you some details about all failed TASKs.

**11) Analyze Gerrit(Zuul) failed gate logs**

This mode is used to analyze Gerrit(Zuul) log files.
It will automatically download all files from remote Gerrit gate (HTTP download) and analyze all
files locally.


# Installation
This tool is available on GitHub, clone it to your **Undercloud** host with:

    git clone https://github.com/zahlabut/LogTool.git

**Note**: some external python modules are used by tool:

1)_Paramiko_ - SSH module

This module is usually installed on Undercloud by default
Use **"ls -a /usr/lib/python2.7/site-packages | grep paramiko"** command to verify that.
Follow "Install Paramiko" section if you don't have this module installed.

2)_BeautifulSoup_ - HTML parser
This module is used in #11 and #13 modes only, where Log files are downloaded using HTTP and it's used to parse the Artifacts HTML
page to get all links in it. Follow "Install BeautifulSoup" section to install it

**Note**: you can also use "requirements.txt" file to install all the required modules, by executing:

    pip install -r requirements.txt

# Configuration
All required parameters are set directly inside PyTool.py script, defaults are:

    overcloud_logs_dir = '/var/log/containers'
    overcloud_ssh_user = 'heat-admin'
    overcloud_ssh_key = '/home/stack/.ssh/id_rsa'
    undercloud_logs_dir ='/var/log/containers'
    source_rc_file_path='/home/stack/'



# Usage
This tool is interactive, so all you have to do is to start it with:

    cd LogTool
    python PyTool.py

# Install Paramiko
On your Undercloud execute the following commands:

    sudo easy_install pip
    sudo pip install paramiko==2.1.1

# Install BeutifulSoup

     pip install beautifulsoup4

# Troubleshooting
There are two log files created on runtime: _"Error.log"_ and _"Runtime.log"_.
Please add the content of both into the description of issue you'd like to open.
