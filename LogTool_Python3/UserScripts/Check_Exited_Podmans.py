#!/usr/bin/python
import os
print(os.system('sudo podman ps -a | grep -i exited'))