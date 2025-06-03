# General
Openstack has a bunch of log files existing and managed on its Overcloud nodes and Undercloud host.
Therefore, when you encountering into some problem and might want to investigate it basing on OSP log files, it's not
an easy stuff, especially when you don't even know which area could have cause to that problem.
If that's the case, LogTool will make your "life" much more easier!
It will save your time and "donkey work" needed for manually investigation.
Basing on fuzzy string matching algorithm, LogToll will provide you all the unique Errors/Warnings messages occurred in the past,
in addition to that, basing on timestamp logged in log's lines, LogTool applying you to "export" such messages for
particular time period in the past, for example: 10 minutes ago, hour ago a day ago e.t.c.

# Operation modes
**1) Export ERRORs/WARNINGs from Overcloud logs**

This mode is used to extract all unique ERRORs/WARNINGs messages from Overcloud nodes, that took place some time ago.
As user you'll be prompted to provide the "Since Time" and debug level that will be used for extraction: Errors or Warnings.
For example, if something went wrong in the last 10 minutes you'll be able to extract Errors/Warnings messages for this time period only.
This operation mode generates result directory containing result files per Overcloud node.
Result file is a simple text file, that is coming compressed (*.gz) in order to reduce time needed for downloading from Overcloud node.
Note: use "zcat",'vim' or any other tool to read/convert compressed file to a regular text file, BTW some of "vi" versions supports reading
compressed data, so you can simply try and use "vi" to read the result file content.
Result file is divided into sections and contains "Table of content" on the bottom.

**Note:**
There are two kinds of log files being detected by LogTool on the fly, "Standard" and "Not Standard" logs.
"Standard" - each log's line has known and defined structure: timestamp, debug level, msg ...
"Not Standard" - log's structure is unknown, it could be third parties logs for example.
In "Table of Content" you'll find: "Section name --> Line number" per section, for example:

1) Statistics - Number of Errors/Warnings per standard OSP log since: <Given Timestamp>
   In this section, you find the amount of Errors/Warnings per Standard OSP log file.
   All these Errors/Warnings took place in the past after provided timestamp.
2) Statistics - Number of Errors/Warnings per Not Standard OSP log since ever
   In this section, you find the amount of Errors and Warnings per Not Standard OSP log file since ever.
3) Statistics - Unique messages, per STANDARD OSP log file since: <Given Timestamp>
   In this section you'll find the unique Errors/Warnings messages since given by you timestamp for Standard OSP logs.
4) Statistics - Unique messages per NOT STANDARD log file, since ever
   In this section you'll find the unique Errors/Warnings messages since ever for Not Standard OSP logs.

So the **first thing** you'll have to do, is scrolling down to the bottom of result file, to the "Table of content" and then passing through
its sections (use line indexes mentioned in "Table of Content" to jump into relevant section), where: #2 #3 and #4 are most important.

**2) Download all logs from Overcloud nodes (up to OSP17)**

Logs from all Overcloud nodes will be compressed and downloaded to local directory on your Undercloud host.
This mode is also applies you to upload logs to remote RedHat's WEB server, so you can share the
lnnk latter on while filing BZ for example.

**3) "Grep" some string for all Overcloud logs (up to OSP17)**

This mode will "grep" some string (given by user) on all Overcloud logs. For example, you might want to see all loged messages for specific request ID, let's say the request ID of "Create VM" that is failed.

**4) Extract messages for given time range (up to OSP17)**

This mode is useful when you might want to get the only log messages logged in particular time range.
For example you might want to get all messages for all OC Nodes logs, logged between 2020:05:01 12:00:00 up untill 2020:05:01 12:05:00 for debug purposes.
This mode will create Result Directory including two files per OC Node: NodeName.log.gz and NodeName.zip.
<br/>    _1. NodeName.zip_ - contains all log files for given time range. It means that matched messages have been detected for given time range in these logs.
BTW - this file could be used as attachment when you report BZ
<br/>    _2. NodeName.log.gz_ - LogTool result file, here you'll find statistics per OSP log.<br/>
Only "unique" messages per OSP log file are being saved in this result file. Duplicated lines are dropped.<br/>
**Note:** this mode is available in LogTool Python3 version only.


**5) Check current:CPU,RAM and Disk on Overcloud (up to OSP17)**

This mode will display the current: CPU, RAM and Disk info, on each Overcloud node.

**6) Execute user's script (up to OSP17)**

This mode provides user the ability to run his own script on Overcloud nodes.
Create your own script and save it in UserScripts directory, set proper interpreter in it (for example: #!/usr/bin/bash).
Let's say that Overcloud deployment failed and that you need to execute the same procedure on each Controller node to fix that.
So, you can implement "work around" script and to run this script on Controllers using this mode.

**7) Download "relevant logs" only, by given timestamp (up to OSP17)**

This mode will download the only Overcloud logs with *"Last Modified" > "given by user timestamp"*.
For example if you got some error 10 minutes ago, you'll probably need to investigate the actual logs only, it means that old logs won't be relevant to you and therefore download such log files is unecessary.
In addition, on Bugzila you can attach file only if its size is less than 21MB, so this mode might help.

**8) Export ERRORs/WARNINGs from Undercloud logs (up to OSP17)**

This mode is the same as #1, the only difference is that it will use Undercloud logs.

**9) OSP18 - analyze PODs logs**

This mode supports OSP18 deployd setup and applies analyzing PODs' logs on controller-0 for example.
Provided options are: specific PODs, LogLevel, "Since Time".
It will use "oc get pods" command to list the PODs within a project, followed by "oc logs -n PROJECT --timestamps POD_NAME"
to create log files on the file system that are later on analyzed.
When running on Controller it will also upload log files to Hypervisor and appropriate "SCP" command to download 
the logs from Hypervisor to your Desktop will be provided. Note: ZIP needs to be installed on your Linux host.

**10) OSP18 - use "openstack-must-gather" tool**

This mode uses "openstack-must-gather" tool:
https://ci-framework.pages.redhat.com/docs/ci-framework/07_collect_logs.html
to collect the logs. Once collected logs will be analyzed.  
When running on Controller it will also upload log files to Hypervisor and appropriate "SCP" command to download 
the logs from Hypervisor to your Desktop will be provided. Note: ZIP needs to be installed on your Linux host.


# Installation
This tool is available on GitHub, clone it to your **Undercloud/Controller-0** host with:

    git clone https://github.com/zahlabut/LogTool.git
    cd LogTool/LogTool_Python3/
    python3 -m venv .
    source bin/activate
    pip3 install -r requirements.txt 

# Configuration (up to OSP17)
All required parameters are set directly inside PyTool.py script, defaults are:

    overcloud_logs_dir = '/var/log/containers'
    overcloud_ssh_user = 'heat-admin'
    overcloud_ssh_key = '/home/stack/.ssh/id_rsa'
    undercloud_logs_dir ='/var/log/containers'
    source_rc_file_path='/home/stack/'


# Usage
This tool is interactive, so all you have to do is to start it with:

    cd LogTool/LogTool_Python3/
    python3 PyTool.py


# Gemini API Configuration
To use the Gemini API, define your API_ENDPOINT
(default: https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent)
and obtain your GOOGLE_API_KEY from Google AI Studio (https://aistudio.google.com/), setting
it as an environment variable by executing **export GOOGLE_API_KEY='your_key_here'** in your terminal.
Both values are set in PyTool.py


# Troubleshooting
There are two log files created on runtime: _"Error.log"_ and _"Runtime.log"_.
Please add the content of both into the description of issue you'd like to open.


# Limitations
1) LogTool is hardcoded to handle log files up to 1GB.


