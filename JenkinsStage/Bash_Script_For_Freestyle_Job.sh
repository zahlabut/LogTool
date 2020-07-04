#rm -rf LogTool
#rm -rf infrared
#wget http://google.com
#yum install -y wget
#git clone https://github.com/redhat-openstack/infrared.git
#virtualenv .venv && source .venv/bin/activate
#cd infrared;pip install --upgrade pip;pip install --upgrade setuptools;pip install paramiko;
#pip install beautifulsoup4;pip install request;pip install .
#ir plugin remove logtool
#ir plugin add https://github.com/zahlabut/LogTool.git --src-path Plugin_For_Infrared_Python2
#ir workspace delete workspace > /dev/null
#ir workspace import $workspace_url
#ir logtool






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
cd LogTool/JenkinsStage; python -m unittest LogToolStage.LogTool.test_1_download_jenkins_job


#Save artifacts with:LogTool/**/*.*
