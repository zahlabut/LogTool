---
config:
  entry_point: ./logtool.yaml
  plugin_type: install
subparsers:
    logtool:
        description: LogTool - export Overcloud errors from logs
        include_groups: ["Ansible options", "Inventory", "Common options", "Answers file"]
        groups:
           - title: logtool
             options:
                logtool_action:
                    type: Value
                    default: install
                    help: |
                      Can be 'install' or 'uninstall'
                setup_type:
                    type: Value
                    default: virt
                    help: |
                      Type of OSP deployment
                undercloud_host:
                    type: Value
                    help: |
                      Baremetal/Virt node where undercloud resides on