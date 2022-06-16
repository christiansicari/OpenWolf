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
this ={'path': path.dirname(path.realpath(__file__)), "host": "http://172.17.6.175:8000/" }
redis_host = "172.17.5.157"
redis_port= 31113
'''

def get_redis():
    r = Redis(host=redis_host, password=redis_password, port=redis_port)
    return r

def new_execution(db, wf, exec_id):
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
    db[exec_id] = doc


def update_execution(db, wf, exec_id, state, output):
    #print(f"{db}\n")
    db[exec_id]["outputs"][state] = {
        "data": output
    }
    equation = db[exec_id]["equations"].pop(state, None)
    db[exec_id]["solved_equations"][state] = equation
    activable = find_activable(wf, db[exec_id])
    db[exec_id]["triggered"] += activable
    return activable
    



def find_activable(wf, exec):
    vars = {state: state in exec["outputs"].keys() for state in wf["states"].keys()}
    locals().update(vars)
    #print(f"exec: {json.dumps(exec)}\n")
    #print(f"locals: {json.dumps(locals())}\n")
    activable = []
    for state, eq in exec["equations"].items():
        if state not in exec["triggered"] and eval(eq):
            activable.append(state)
    return activable
        

def openfaas_invoker(conf, data):
    # TODO: merge config in the State and in the function definition. Give priority to the State. 
    
    headers = conf["config"]
    headers["X-Callback-Url"] = f'{this["host"]}'
    request("POST", url=conf["endpoint"], headers=headers, data=json.dumps(data))
    print("Invoke", conf["endpoint"], headers)
    #print(res.status_code, res.content, res.headers)



def trigger(wf, state, data):
    print(f"I am triggering {state}")
    fun_ref = wf["states"][state]["function"]["ref"]
    fun = wf["functions"][fun_ref]
    if fun["platform"] == "openfaas":
        openfaas_invoker(fun, data)
    else:
        raise ValueError("Platform not supported")

def finalize(db, url, data):
    exec_id = data['ctx']['execID']
    #print(exec_id, db)
    print(f"Finalizing {exec_id} to", url)
    request("POST", url=url, data=json.dumps(data["data"]))
    #r = get_redis()
    #r.json().set(exec_id, Path.rootPath(), db[exec_id])
    


def get_workflow(workflows, wid):
    if wid not in workflows:
        print(f"Download Workflow {wid}")
        r = get_redis()
        wf = r.json().get(f"{wid}")
        if not wf:
            msg = f"{wid} not found"
            raise ValueError(msg)
        workflows[wid] = wf
    else:
        print(f"Workflow {wid} in cache")
    return workflows[wid]



def handle(db, workflows, req):
    #db = {}
    print("Received body", req, type(req))
    wid = f'workflow.{req["ctx"]["workflowID"]}'
    wf = get_workflow(workflows, wid)
    #print("wf", wf)
    state = req["ctx"]["state"]
    exec_id = req["ctx"]["execID"]
    output = req["data"]

    # this is the first invokation
    is_trigger = False
    if not exec_id:
        is_trigger = True
        exec_id = f'exec.{wid}-{int(time())}'
        req["ctx"]["execID"] = exec_id
        req["ctx"]["state"] = "__invoke__"
        new_execution(db, wf, exec_id)

    print(f"Received {state}\n")
    activable = update_execution(db, wf, exec_id, state, output)
    for act_state in activable:
        req["ctx"]["state"] = act_state
        trigger(wf, act_state, req)
    if  not is_trigger and "end" in wf["states"][state] and wf["states"][state]["end"]:
        finalize(db, wf["callbackUrl"], req)

