#!/usr/bin/python
import os
for com in ['vmstat','free','df -h']:
    print('-->'+com)
    print(os.system(com))