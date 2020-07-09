# Download CI artifact files and Analyze logs #
virtualenv .venv && source .venv/bin/activate
pip install beautifulsoup
pip install requests
git clone https://github.com/zahlabut/LogTool.git
echo "user_start_time='"$user_start_time"'" >> LogTool/JenkinsStage/Params.py
echo "artifact_url='"$artifact_url"'" >> LogTool/JenkinsStage/Params.py
cd LogTool/JenkinsStage; python -m unittest LogToolStage.LogTool.test_1_download_jenkins_job