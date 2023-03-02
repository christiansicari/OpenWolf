import json
from lib2to3.pgen2 import token
from requests import request
from os import getenv, path
from time import time
from redis import Redis, lock
from redis.commands.json.path import Path
from typing import Union
from jose import jwt
from datetime import datetime, timedelta
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


this ={'path': path.dirname(path.realpath(__file__)), "host": getenv("THIS") }
redis_host = getenv("REDIS_HOST") or "localhost"
redis_password = getenv("REDIS_PASS") or ""
redis_port = getenv("REDIS_PORT") or 6379

openfaas_admin = "admin"
openfaas_password = ""

with open('/vault/secrets/openfaas', 'r') as f:
    secret = json.load(f)
    openfaas_admin = secret["data"]["admin"]
    openfaas_password = secret["data"]["password"]

secret_key = ""
with open('/vault/secrets/jwt', 'r') as f:
    secret = json.load(f)
    secret_key = secret["data"]["key"]

algorithm = getenv("JWT_ALGORITHM")
expire_minutes = int(getenv("JWT_EXPIRE_MINUTES"))

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
        
def openfaas_invoker(conf, data):
    # TODO: merge config in the State and in the function definition. Give priority to the State. 
    
    headers = conf["config"]
    headers["X-Callback-Url"] = f'{this["host"]}exec'
    #headers["X-Callback-Url"] = 'http://172.16.1.176:31114/exec'
    print("Invoke", conf["endpoint"], headers)
    print("Data sent:")
    print(data)
    request("POST", url=conf["endpoint"], headers=headers, data=json.dumps(data))

def encrypt(data,key,iv):
    print("to be encrypted:")
    print(data)

    cipher = Cipher(algorithms.AES(key), modes.CFB(iv))
    enc = cipher.encryptor()

    data_string = json.dumps(data)
    data_bytes = bytes(data_string,'utf-8')

    data_encrypted = str(base64.b64encode(enc.update(data_bytes) + enc.finalize()))

    return data_encrypted

def decrypt(data,key,iv):
    print("to be decrypted:")
    print(data)

    cipher = Cipher(algorithms.AES(key), modes.CFB(iv))
    dec = cipher.decryptor()

    b64decoded_cdata = base64.b64decode(eval(data))
    
    data_decrypted = eval((dec.update(b64decoded_cdata) + dec.finalize()).decode("utf-8"))

    if (type(data_decrypted) == str):
        data = json.dumps(data_decrypted)

    return data_decrypted

def trigger(wf, state, data):
    print(f"I am triggering {state}")
    fun_ref = wf["states"][state]["function"]["ref"]
    fun = wf["functions"][fun_ref]

     ######  QUA CIFRARE DATI CON CHIAVE STATO NUOVO ######
    crypted = False 
    if "crypted" in wf["functions"][fun_ref]:
        crypted = wf["functions"][fun_ref]["crypted"]

    if crypted and type(data["data"]) != str:
        endpoint = fun["endpoint"]
        role = endpoint.split(".")[-1]
        if role == "openfaas-fn":
            role = "world"
        key = ""
        iv = ""
        with open('/vault/secrets/' + role, 'r') as f:
            secret = json.load(f)
            key = bytes(secret["data"]["key"], 'utf-8')
            iv = bytes(secret["data"]["iv"], 'utf-8')
        data["data"] = encrypt(data["data"], key, iv)
   
   

    if fun["platform"] == "openfaas":
        openfaas_invoker(fun, data)
    else:
        raise ValueError("Platform not supported")

def finalize(url, data):
    exec_id = data['ctx']['execID']
    print(f"Finalizing {exec_id} to", url)
    request("POST", url=url, data=json.dumps(data["data"]))
    
def create_exec_token(data: dict, expires_delta: Union[timedelta, None] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm)
    return encoded_jwt

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

def wf_trigger(req, username):
    print("Received body", req, type(req))
    wid = f'workflow.{req["ctx"]["workflowID"]}'
    r = get_redis()
    
    wf = r.json().get(f"{wid}")
    user = r.json().get(username)

    allowed = user["groups"]
    allowed.append(username)
    allowed.append("openfaas-fn")

    functions = wf["functions"]

    scopes = set()

    for key in functions.keys():
        endpoint = functions[key]["endpoint"]
        scope = endpoint.split(".")[-1]
        scopes.add(scope)

    for scope in scopes:
        if scope not in allowed:
            return False
        
    
    state = req["ctx"]["state"]
    exec_id = req["ctx"]["execID"]
    output = req["data"]

    exec_id = f'exec.{wid}-{int(time())}'
    req["ctx"]["execID"] = exec_id
    req["ctx"]["state"] = "__invoke__"

    token_payload = req["ctx"].copy()
    del token_payload["state"]
    #print(f'to_encode: {to_encode}')
    expires_delta = timedelta(minutes=expire_minutes)
    exec_token = create_exec_token(token_payload, expires_delta)
    #print(exec_token)
    req["exec_token"] = exec_token
    #req["token"] = token
    
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
    ##### QUA NON SI DECIFRA #######
    if len(activable) > 0:
        session = None
        for act_state in activable:
            req["ctx"]["state"] = act_state
            trigger(wf, act_state, req)
    return True

def handle(req):
    print("Received body", req, type(req))
    wid = f'workflow.{req["ctx"]["workflowID"]}'
    r = get_redis()
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

    ##### QUA DECIFRARE CON CHIAVE STATO RICEVUTO #######

    crypted = False 
    fun_ref = wf["states"][state]["function"]["ref"]
    if "crypted" in wf["functions"][fun_ref]:
        crypted = wf["functions"][fun_ref]["crypted"]
    if crypted:
        endpoint = wf["functions"][fun_ref]["endpoint"]
        role = endpoint.split(".")[-1]
        if role == "openfaas-fn":
            role = "world"
        key = ""
        iv = ""
        with open('/vault/secrets/' + role, 'r') as f:
            secret = json.load(f)
            key = bytes(secret["data"]["key"], 'utf-8')
            iv = bytes(secret["data"]["iv"], 'utf-8')
        req["data"] = decrypt(req["data"], key, iv)


    if len(activable) > 0:
        session = None
        for act_state in activable:
            req["ctx"]["state"] = act_state
            trigger(wf, act_state, req)
    if "end" in wf["states"][state] and wf["states"][state]["end"]:
        finalize(wf["callbackUrl"], req)

def el_deploy(req, username, update):
    print("Received body", req, type(req))
    r = get_redis()
    user = r.json().get(username)

    allowed = [username, "openfaas-fn"]

    if req["group"] == True:
        allowed = user["groups"]
    
    if req["namespace"] not in allowed:
        return 401

    constraints = []
    role = ""

    if req["namespace"] != "openfaas-fn":
        constraints = [req["namespace"] + "=true"]
        role = req["namespace"]
    else:
        role= "world"

    annotations = dict()

    if req["cryptography"]:
        annotations = annotate_function(role)

    headers = {}
    headers["Content-Type"] = "application/json"
    headers["Authorization"] = "Basic " + base64.b64encode((openfaas_admin + ":" + openfaas_password).encode("ascii")).decode("ascii")
    
    payload = {
        "service": req["service"],
        "image": req["image"],
        "constraints": constraints,
        "labels": req["labels"],
        "annotations": annotations,
        "secrets": req["secrets"],
        "namespace": req["namespace"]
    }
    
    resp = "Empty response"

    if(update):
        resp = request("PUT", url="http://gateway.openfaas.svc.cluster.local:8080/system/functions", headers=headers, data=json.dumps(payload))
    else:
        resp = request("POST", url="http://gateway.openfaas.svc.cluster.local:8080/system/functions", headers=headers, data=json.dumps(payload))
    print(resp)
    return resp.status_code
    if (resp.status_code == 202):
        return True
    else:
        return False

def annotate_function(role):
    annotations = dict()
    annotations["vault.hashicorp.com/agent-inject"] = "true"
    annotations["vault.hashicorp.com/secret-volume-path"] = "/var/openfaas/secrets"
    annotations["vault.hashicorp.com/agent-inject-secret-secret_key"] = "openfaas/" + role + "-secret"
    annotations["vault.hashicorp.com/agent-inject-status"] = "update"
    annotations["vault.hashicorp.com/role"] = role
    return annotations
    