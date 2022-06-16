import time
import requests
from bottle import run, request, route, post
import paste
from multiprocessing import Process, Manager
import json
import pandas as pd
from os.path import realpath, dirname, basename
from os import getenv
import sqlite3
from contextlib import closing
from webdav3.client import Client

PORT=8080
THIS = getenv("THIS") or "http://172.17.6.175:8080"
this = dirname(realpath(__file__))

#manager = Manager()
#async_times = manager.dict()


def query(db_name, sql):
    with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:
        cur.execute(sql)
        return cur.fetchall()



def sync_req(kind, endpoint, attempts, sleeptime):
    rows = []
    payload = {
    "ctx": {},
    "data": {
        "msg": "Init",
        "hash": "123"}
    }
    for i in range(attempts):
        s = time.time()
        response = requests.request("POST", endpoint, json=payload)
        req_time = time.time() - s
        print(f"Sync Invoker {i}/{attempts-1}", response.status_code)
        
        rows.append(("sync", kind, endpoint, req_time))
        time.sleep(sleeptime)
    return rows
    

def async_req(kind, endpoint, attempts, sleeptime):
    payload = {
    "ctx": {},
    "data": {
        "msg": "Init",
        "hash": "123"}
    }
    headers = {
        "X-Callback-Url": THIS
    }
    for i in range(attempts):
        response = requests.request("POST", endpoint, json=payload, headers=headers)
        call_id = response.headers.get("X-Call-Id")
        ts = time.time()
       
        sql = f"INSERT INTO asyncRequests VALUES ('{call_id}', {ts}, 0)"
        query(f'{this}/db.sqlite', sql)
        #async_times[call_id] = {"kind": kind, "endpoint": endpoint, "start": ts}
        print(f"Async Invoker {i}/{attempts-1}: Call-Id: {call_id}, res: {response.status_code}")
        time.sleep(sleeptime)


@post('/')
def index():
    ts = time.time()
    req_id = request.headers.get("X-Call-Id")
    #async_times[req_id]["duration"] = async_times[req_id]["start"] -  ts
    sql = f"UPDATE asyncRequests SET FinishTime ={ts} WHERE ReqID='{req_id}'"
    query(f'{this}/db.sqlite', sql)

    print(f"Async Callback: Call-Id: {req_id}, res: {request.headers.get('X-Function-Status')}")



def run_server(this):
    run(server="paste", host='0.0.0.0', port=PORT)

def dict_to_pandas_rows(data):
    rows = []
    for  k, v in data.items():
        rows.append("Async", v["kind"], v["endpoint"], v["duration"])
    return rows


def fetch_sqlite(*args):
    sql = "SELECT StartTime, FinishTime FROM asyncRequests"
    data = query(f'{this}/db.sqlite', sql)
    rows = []
    for s in data:
        row = list(args) + [s[-1]-s[-2]]
        rows.append(tuple(row))
    return rows


def upload_file(filepath):
    options = {
    'webdav_hostname': "https://nc.me.pi2s2.it/nextcloud/remote.php/dav/files/chris_bot/",
    'webdav_login':    "chris_bot",
    'webdav_password': "chris_bot!", 
    }
    client = Client(options)
    client.upload_sync(remote_path=f"wftest/{basename(filepath)}", local_path=filepath)


if __name__ == '__main__':
    with open("./openfaas-config.json") as f:
        config = json.load(f)
        query(f'{this}/db.sqlite', "delete from asyncRequests where 1=1")
        server = Process(target=run_server, args=(this, ))
        server.start()
        sync_rows = sync_req(config["kind"], f"http://pi1:31112/function/{config['fun']}", config["attempts"], config["sleep"])
        
        async_ep = f"http://pi1:31112/async-function/{config['fun']}"
        async_req(config["kind"], async_ep, config["attempts"], config["sleep"])
        data = fetch_sqlite("Async", config["kind"], async_ep) + sync_rows
        df = pd.DataFrame(data, columns=['Mode', 'Kind', 'Endpoint', "Execution Time"])
        file = f"{this}/outputs/test-{config['kind']}.xlsx"
        df.to_excel(file, index=False)
        upload_file(file)
        server.terminate()
        
