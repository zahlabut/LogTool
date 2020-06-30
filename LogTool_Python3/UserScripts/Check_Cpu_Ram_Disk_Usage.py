#!/usr/bin/python3
import os
for com in ['vmstat','free','df -h']:
    print('\n-->'+com)
    print(os.system(com))