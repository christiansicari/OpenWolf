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

redis_host = getenv("REDIS_HOST") or "localhost"
redis_password = getenv("REDIS_PASS") or ""
redis_port = getenv("REDIS_PORT") or 6379

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

def new_execution(r, wf, exec_id):
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
    r.json().set(f"exec.{exec_id}", Path.rootPath(), doc)
    #db[exec_id] = doc


def update_execution(r, wf, exec_id, state, output):
    xid = f"exec.{exec_id}"
    exec = r.json().get(xid)
    exec["outputs"][state] = {
        "data": output
    }
    equation = exec["equations"].pop(state, None)
    exec["solved_equations"][state] = equation
    activable = find_activable(wf, exec)
    exec["triggered"] += activable
    r.json().set(xid, Path.rootPath(), exec)
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
        r = Redis(host=redis_host, password=redis_password, port=redis_port)
        req = json.loads(req)

        wid = req["ctx"]["workflowID"]
        wf = r.json().get(f"workflow.{wid}")
        state = req["ctx"]["state"]
        exec_id = req["ctx"]["execID"]
        output = req["data"]
        sys.stderr.write(f"Received {state}\n")


        if not exec_id:
            if "start" in wf["states"][state] and wf["states"][state]["start"]:
                exec_id = f'{wid}-{int(time())}'
                req["ctx"]["execID"] = exec_id
                new_execution(r, wf, exec_id)

            else: 
                raise ValueError("No Execution ID found")
        lockname = f'lock-{exec_id}'
        sem = lock.Lock(redis=r, name=lockname, timeout=60)
        sem.acquire()
        #print("semaphore acquired")
        activable = update_execution(r, wf, exec_id, state, output)
        #activable = find_activable(r, wf, exec_id)
        #print("lock released")
        sem.release()
        req["data"] = output
        for act_state in activable:
            req["ctx"]["state"] = act_state
            trigger(wf, act_state, req)
        #sys.stderr.write(f'{state},  {wf["states"]}, {"end" in wf["states"][state] and wf["states"][state]["end"]}\n')
        if  "end" in wf["states"][state] and wf["states"][state]["end"]:
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