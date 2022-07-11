import json
from requests import request
from os import getenv, path
from time import time
from redis import Redis, lock
from redis.commands.json.path import Path


this ={'path': path.dirname(path.realpath(__file__)), "host": getenv("THIS") }
redis_host = getenv("REDIS_HOST") or "localhost"
redis_password = getenv("REDIS_PASS") or ""
redis_port = getenv("REDIS_PORT") or 6379

def get_redis():
    r = Redis(host=redis_host, password=redis_password, port=redis_port)
    return r

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
    r.json().set(exec_id, Path.rootPath(), doc)


def update_execution(r, wf, exec_id, state, output):
    doc = r.json().get(exec_id)
    doc["outputs"][state] = {
        "data": output
    }
    equation = doc["equations"].pop(state, None)
    doc["solved_equations"][state] = equation
    activable = find_activable(wf, doc)
    doc["triggered"] += activable
    r.json().set(exec_id, Path.rootPath(), doc)
    return activable


def find_activable(wf, exec):
    vars = {state: state in exec["outputs"].keys() for state in wf["states"].keys()}
    locals().update(vars)
    activable = []
    for state, eq in exec["equations"].items():
        if state not in exec["triggered"] and eval(eq):
            activable.append(state)
    return activable
        

def openfaas_invoker(conf, data, session):
    # TODO: merge config in the State and in the function definition. Give priority to the State. 
    
    headers = conf["config"]
    headers["X-Callback-Url"] = f'{this["host"]}exec'
    print("Invoke", conf["endpoint"], headers)
    resp = request("POST", url=conf["endpoint"], headers=headers, data=json.dumps(data))
    print(resp.headers)



def trigger(wf, state, data, session):
    print(f"I am triggering {state}")
    fun_ref = wf["states"][state]["function"]["ref"]
    fun = wf["functions"][fun_ref]
    if fun["platform"] == "openfaas":
        openfaas_invoker(fun, data, session)
    else:
        raise ValueError("Platform not supported")

def finalize(r, url, data):
    exec_id = data['ctx']['execID']
    print(f"Finalizing {exec_id} to", url)
    request("POST", url=url, data=json.dumps(data["data"]))
    


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

def wf_trigger(req):
    print("Received body", req, type(req))
    wid = f'workflow.{req["ctx"]["workflowID"]}'
    r = Redis(host=redis_host, password=redis_password, port=redis_port)
    wf = r.json().get(wid)
    
    
    state = req["ctx"]["state"]
    exec_id = req["ctx"]["execID"]
    output = req["data"]

    exec_id = f'exec.{wid}-{int(time())}'
    req["ctx"]["execID"] = exec_id
    req["ctx"]["state"] = "__invoke__"

    lockname = f'lock-{exec_id}'
    sem = lock.Lock(redis=r, name=lockname, timeout=60)
    sem.acquire()
    print("Acquiring semaphore")

    print("Init new execution")
    new_execution(r, wf, exec_id)

    print("Updating execution")

    print(f"Received {state}\n")
    activable = update_execution(r, wf, exec_id, state, output)
    print("Releasing semaphore")
    sem.release()
    
    if len(activable) > 0:
        session = None
        for act_state in activable:
            req["ctx"]["state"] = act_state
            trigger(wf, act_state, req, session)

def handle(req):
    print("Received body", req, type(req))
    wid = f'workflow.{req["ctx"]["workflowID"]}'
    r = Redis(host=redis_host, password=redis_password, port=redis_port)
    wf = r.json().get(wid)
    
    state = req["ctx"]["state"]
    exec_id = req["ctx"]["execID"]
    output = req["data"]
        
    lockname = f'lock-{exec_id}'
    sem = lock.Lock(redis=r, name=lockname, timeout=60)
    sem.acquire()
    print("Acquiring semaphore")
    print("Updating execution")
    print(f"Received {state}\n")
    activable = update_execution(r, wf, exec_id, state, output)
    print("Releasing semaphore")
    sem.release()
    if len(activable) > 0:
        session = None
        for act_state in activable:
            req["ctx"]["state"] = act_state
            trigger(wf, act_state, req, session)
    if "end" in wf["states"][state] and wf["states"][state]["end"]:
        finalize(r, wf["callbackUrl"], req)

