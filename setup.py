from setuptools import setup

setup(
    name='LogTool',
    version='0.1',
    packages=['JenkinsStage',
              'JenkinsStage.temp_dir.undercloud-0.usr.share.openstack-tripleo-heat-templates.container_config_scripts',
              'JenkinsStage.temp_dir.undercloud-0.usr.share.openstack-tripleo-heat-templates.container_config_scripts.tests',
              'JenkinsStage.Jenkins_Job_ERROR.undercloud-0.usr.share.openstack-tripleo-heat-templates.container_config_scripts',
              'JenkinsStage.Jenkins_Job_ERROR.undercloud-0.usr.share.openstack-tripleo-heat-templates.container_config_scripts.tests',
              'JenkinsStage.Jenkins_Job_Files.undercloud-0.usr.share.openstack-tripleo-heat-templates.container_config_scripts',
              'JenkinsStage.Jenkins_Job_Files.undercloud-0.usr.share.openstack-tripleo-heat-templates.container_config_scripts.tests',
              'LogTool_Package', 'LogTool_Python2', 'LogTool_Python2.UserScripts',
              'LogTool_Python2.Jenkins_Job_ERROR.undercloud-0.usr.share.openstack-tripleo-heat-templates.container_config_scripts',
              'LogTool_Python2.Jenkins_Job_ERROR.undercloud-0.usr.share.openstack-tripleo-heat-templates.container_config_scripts.tests',
              'LogTool_Python3.Jenkins_Job_ERROR.undercloud-0.usr.share.openstack-tripleo-heat-templates.container_config_scripts',
              'LogTool_Python3.Jenkins_Job_ERROR.undercloud-0.usr.share.openstack-tripleo-heat-templates.container_config_scripts.tests',
              'Jenkins_Job_Files.undercloud-0.usr.share.openstack-tripleo-heat-templates.container_config_scripts',
              'Jenkins_Job_Files.undercloud-0.usr.share.openstack-tripleo-heat-templates.container_config_scripts.tests',
              'Plugin_For_Infrared_Python2', 'Plugin_For_Infrared_Python3'],
    url='https://github.com/zahlabut/LogTool/tree/master/LogTool_Package',
    license='Apache 2.0',
    author='Arkady Shtempler',
    author_email='arkadysh@gmail.com',
    description='Extract unique Errors from logs using provided "start time" timestamp.'
)
