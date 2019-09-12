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
        print v