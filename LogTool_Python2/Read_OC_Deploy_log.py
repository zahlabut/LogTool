# Copyright 2018 Arkady Shtempler.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import difflib
magic_words=['FAILED','TASK','msg','stderr', 'WARN']
magic_dic_result={}
log_name='overcloud_deployment.log'
for word in magic_words:
    magic_dic_result[word]=[]

def unique_list_by_fuzzy(lis,fuzzy):
    unique_messages=[]
    for item in lis:
        to_add = True
        for key in unique_messages:
            if similar(key, str(item)) >= fuzzy:
                to_add = False
                break
        if to_add == True:
            unique_messages.append(str(item))
    return unique_messages

def similar(a, b):
    return difflib.SequenceMatcher(None, str(a), str(b)).ratio()


data=open(log_name,'r').read().splitlines()
for line in data:
    # if 'FAILED!' or ' ERROR 'in line:
    #     print line
    if 'fatal: [' in line:
        print '\n\n\n\n\n'+'-'*40+'Line with "fatal : [" string'+'-'*40
        line=line.split('\\n')
        for item in line:
            print item
            for w in magic_words:
                if w in item:
                    magic_dic_result[w].append(item)

for key in magic_dic_result:
    print '\n'+'-'*40+key+'-'*40
    for v in unique_list_by_fuzzy(magic_dic_result[key],0.6):
        print '\n'+v