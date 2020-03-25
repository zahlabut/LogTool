# Copyright 2014 Red Hat, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

# Common config, from tripleo-heat-templates/puppet/manifests/overcloud_common.pp
# The content of this file will be used to generate
# the puppet manifests for all roles, the placeholder
# Undercloud will be replaced by 'controller', 'blockstorage',
# 'cephstorage' and all the deployed roles.

if hiera('step') >= 4 {
  hiera_include('Undercloud_classes', [])
}

$package_manifest_name = join(['/var/lib/tripleo/installed-packages/overcloud_Undercloud', hiera('step')])
package_manifest{$package_manifest_name: ensure => present}

# End of overcloud_common.pp

include ::tripleo::trusted_cas
include ::tripleo::profile::base::certmonger_user

include tripleo::masquerade_networks

include ::tripleo::profile::base::database::mysql::client
include ::aodh::client
include ::barbican::client
include ::cinder::client
include ::designate::client
include ::glance::client
include ::gnocchi::client
include ::heat::client
include ::ironic::client
include ::keystone::client
include ::manila::client
include ::mistral::client
include ::neutron::client
include ::nova::client
include ::openstacklib::openstackclient
include ::panko::client
include ::sahara::client
include ::swift::client
include ::zaqar::client

include ::tripleo::profile::base::sshd

include ::tripleo::firewall