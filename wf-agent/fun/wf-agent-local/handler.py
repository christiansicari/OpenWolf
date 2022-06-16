from email import header
import json
from multiprocessing.sharedctypes import Value
from sre_parse import State
from requests import request
from os import getenv, path
from time import time, sleep
from pprint import pprint
from redis import Redis, lock
from redis.commands.json.path import Path
import sys


this ={'path': path.dirname(path.realpath(__file__)), "host": getenv("THIS") }
with open(path.join(this["path"], "./files/workflows.json")) as f:
    workflows = json.load(f)
db = {}


'''
db = {
    "appendchain-123": {
        "outputs": {
            "A": {
                "data": {}
            },
        },
        
        "equations": {

        },
        "solved_equations": {

        },
        "triggered": {}
    }
}
'''

def new_execution(wf, exec_id):
    equations = {}
    for key, value in wf["workflow"].items():
        equations[key] = value["activation"]
    doc = {
        "outputs": {

        },
        "equations": equations,
        "solved_equations": {},
        "triggered": []
    }
    db[f"exec.{exec_id}"] = doc


def update_execution(wf, exec_id, state, output):
    xid = f"exec.{exec_id}"
    sys.stderr.write(f"{db}\n")
    db[xid]["outputs"][state] = {
        "data": output
    }
    equation = db[xid]["equations"].pop(state, None)
    db[xid]["solved_equations"][state] = equation
    activable = find_activable(wf, db[xid])
    db[xid]["triggered"] += activable
    return activable
    



def find_activable(wf, exec):
    vars = {state: state in exec["outputs"].keys() for state in wf["states"].keys()}
    locals().update(vars)
    #sys.stderr.write(f"exec: {json.dumps(exec)}\n")
    #sys.stderr.write(f"locals: {json.dumps(locals())}\n")
    activable = []
    for state, eq in exec["equations"].items():
        if state not in exec["triggered"] and eval(eq):
            activable.append(state)
    return activable
        

def openfaas_invoker(conf, data):
    # TODO: merge config in the State and in the function definition. Give priority to the State. 
    
    headers = conf["config"]
    headers["X-Callback-Url"] = f'{this["host"]}'
    res = request("POST", url=conf["endpoint"], headers=headers, data=json.dumps(data))
    #print(conf["endpoint"], headers, data)
    #print(res.status_code, res.content, res.headers)



def trigger(wf, state, data):
    sys.stderr.write(f"I am triggering {state}\n")
    fun_ref = wf["states"][state]["function"]["ref"]
    fun = wf["functions"][fun_ref]
    if fun["platform"] == "openfaas":
        openfaas_invoker(fun, data)
    else:
        raise ValueError("Platform not supported")

def finalize(url, data):
    res = request("POST", url=url, data=json.dumps(data))
    #print(res.status_code)
    #print(res.status_code, res.content, res.headers)




def handle(req):
    try:
        sys.stderr.write(f"Received {req}\n")
        req = json.loads(req)

        wid = req["ctx"]["workflowID"]
        wf = workflows[f"workflow.{wid}"]
        state = req["ctx"]["state"]
        exec_id = req["ctx"]["execID"]
        output = req["data"]

        # this is the first invokation
        is_trigger = False
        if not exec_id:
            is_trigger = True
            exec_id = f'{wid}-{int(time())}'
            req["ctx"]["execID"] = exec_id
            req["ctx"]["state"] = "__invoke__"
            new_execution(wf, exec_id)

        sys.stderr.write(f"Received {state}\n")
        activable = update_execution(wf, exec_id, state, output)
        #req["data"] = output
        for act_state in activable:
            req["ctx"]["state"] = act_state
            trigger(wf, act_state, req)
        #sys.stderr.write(f'{state},  {wf["states"]}, {"end" in wf["states"][state] and wf["states"][state]["end"]}\n')
        if  not is_trigger and "end" in wf["states"][state] and wf["states"][state]["end"]:
            finalize(wf["callbackUrl"], req["data"])
    except:
        import traceback
        traceback.print_exc(file=sys.stderr)


#handle(b"{'ctx': {'workflowID': 'appendchain', 'execID': 'appendchain-1654031078', 'state': 'B'}, 'data': {'id': 0, 'chain': [0]}}\n")
'''
try:

    handle(json.dumps({"ctx": { "workflowID": "appendchain", "execID": None, "state": "A" }, "data": {}}))
except:
    import traceback
    traceback.print_exc()

'''