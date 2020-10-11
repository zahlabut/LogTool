#!/bin/bash
# Download CI artifact files and Analyze logs #
virtualenv .venv && source .venv/bin/activate
pip3 install beautifulsoup4
pip3 install requests
pip3 install lxml
git clone https://github.com/zahlabut/LogTool.git
echo "user_start_time='"$user_start_time"'" >> LogTool/JenkinsStage/Params.py
echo "artifact_url='"$artifact_url"'" >> LogTool/JenkinsStage/Params.py
echo "download_overcloud_logs='"$download_overcloud_logs"'" >> LogTool/JenkinsStage/Params.py
echo "overcloud_log_dirs='"$overcloud_log_dirs"'" >> LogTool/JenkinsStage/Params.py
echo "download_undercloud_logs='"$download_undercloud_logs"'" >> LogTool/JenkinsStage/Params.py
echo "undercloud_log_dirs='"$undercloud_log_dirs"'" >> LogTool/JenkinsStage/Params.py
echo "grep_string_only='"$grep_string_only"'" >> LogTool/JenkinsStage/Params.py
echo "delete_downloaded_files='"$delete_downloaded_files"'" >> LogTool/JenkinsStage/Params.py
echo "grep_command='''"$grep_command"'''" >> LogTool/JenkinsStage/Params.py
#cd LogTool/JenkinsStage; python -m unittest LogToolStage.LogTool.test_1_download_jenkins_job
cd LogTool/JenkinsStage; python -m unittest LogToolStageNew