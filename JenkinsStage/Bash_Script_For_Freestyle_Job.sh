# Download CI artifact files and Analyze logs #
virtualenv .venv && source .venv/bin/activate
pip install beautifulsoup
pip install requests
git clone https://github.com/zahlabut/LogTool.git
echo "user_start_time='"$user_start_time"'" >> LogTool/JenkinsStage/Params.py
echo "artifact_url='"$artifact_url"'" >> LogTool/JenkinsStage/Params.py
echo "analyze_overcloud_logs='"$analyze_overcloud_logs"'" >> LogTool/JenkinsStage/Params.py
echo "overcloud_log_dirs='"$overcloud_log_dirs"'" >> LogTool/JenkinsStage/Params.py
echo "analyze_undercloud_logs='"$analyze_undercloud_logs"'" >> LogTool/JenkinsStage/Params.py
echo "undercloud_log_dirs='"$undercloud_log_dirs"'" >> LogTool/JenkinsStage/Params.py
cd LogTool/JenkinsStage; python -m unittest LogToolStage.LogTool.test_1_download_jenkins_job
