from wsgiref import headers
from bottle import run, request, route, post
import time
import sqlite3
from contextlib import closing
from webdav3.client import Client
import requests
from os import getenv
from os.path import realpath, dirname, basename
import json
from multiprocessing import Process, Manager
import pandas as pd

PORT=8080
THIS = getenv("THIS") or f"http://172.17.6.175:{PORT}"
this = dirname(realpath(__file__))


def query(db_name, sql):
    with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:
        cur.execute(sql)
        return cur.fetchall()


@post('/')
def index():
    ts = time.time()
    body = json.loads(request.body.read())
    req_id = body["msg"]
    req_id= str(req_id//10*10)
    sql = f"UPDATE asyncRequests SET FinishTime ={ts} WHERE ReqID='{req_id}'"
    query(f'{this}/db.sqlite', sql)

    print(f"Async Callback: Call-Id: {req_id}, res: {str(request.body.read())}")


def reqs(endpoint, attempts, sleeptime):
    payload = {
    "ctx": {
        "workflowID": "hashchain",
        "execID": None,
        "state": "Invoke"
    },
    "data": {
        "msg": 0,
        "hash": "123"
    }
    }
   
    for i in range(attempts):
        call_id = (i+1)*10  # fails if chain is > 9 elements
        payload["data"]["msg"] = call_id
        response = requests.request("POST", endpoint, json=payload)
        ts = time.time()
       
        sql = f"INSERT INTO asyncRequests VALUES ('{str(call_id)}', {ts}, 0)"
        #print(sql)
        query(f'{this}/db.sqlite', sql)
        #async_times[call_id] = {"kind": kind, "endpoint": endpoint, "start": ts}
        print(f"Async Invoker {i}/{attempts-1}: Call-Id: {call_id}, res: {response.status_code}")
        time.sleep(sleeptime)


def fetch_sqlite(*args):
    sql = "SELECT FinishTime-StartTime FROM asyncRequests"
    data = query(f'{this}/db.sqlite', sql)
    rows = []
    for s in data:
        row = list(args) + list(s)
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



def run_server(this):
    run(server="paste", host='0.0.0.0', port=PORT)


if __name__ == '__main__':
    with open("./config.json") as f:
        config = json.load(f)
        query(f'{this}/db.sqlite', "delete from asyncRequests where 1=1")
        server = Process(target=run_server, args=(this, ))
        server.start()
        reqs(config["agent"], config["attempts"], config["sleep"])
        data = fetch_sqlite(config["kind"])
        df = pd.DataFrame(data, columns=['Kind', "Execution Time"])
        file = f"{this}/ow-chain-test-{config['kind']}.xlsx"
        df.to_excel(file, index=False)
        upload_file(file)
        time.sleep(20)
        server.terminate()
