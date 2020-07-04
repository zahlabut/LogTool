
# HTTP Download and Analyze log #
df -h
hostname
virtualenv .venv && source .venv/bin/activate
pip install beautifulsoup
pip install request
pip install paramiko
git clone https://github.com/zahlabut/LogTool.git
echo "start_time='"$user_tart_time"'" >> LogTool/JenkinsStage/Params.py
echo "artifact_url='"$artifact_url"'" >> LogTool/JenkinsStage/Params.py
cd LogTool/JenkinsStage; python -m unittest LogToolStage.test_1_download_jenkins_job