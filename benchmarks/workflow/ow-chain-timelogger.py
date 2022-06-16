from wsgiref import headers
from bottle import run, request, route, post
import time
import sqlite3
from contextlib import closing
from webdav3.client import Client
import requests
from os import getenv
from os.path import realpath, dirname, basename, join
import json
from multiprocessing import Process, Manager
import pandas as pd
from sys import argv

PORT=8080
THIS = getenv("THIS") or f"http://172.17.6.175:{PORT}"
this = dirname(realpath(__file__))
time_required = []

@post('/')
def index():
    ts = time.time()
    body = json.loads(request.body.read())
    t = max(body["timelogs"]) - min(body["timelogs"])
    print(t)

    with open(join(this, "./res.txt"), "a") as f:
        f.write(f"{t}\n")
    time_required.append(t)
    print("Received Callback")


def reqs(wid, endpoint, attempts, sleeptime):
    payload = {
    "ctx": {
        "workflowID": wid,
        "execID": None,
        "state": "Invoke"
    },
    "data": {
       "timelogs": []
    }
}
   
    for i in range(attempts):
        print(f"Sent request {i}/{attempts-1}")
        payload["timelogs"] = [time.time()]
        requests.request("POST", endpoint, json=payload)
        time.sleep(sleeptime)




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
    wid = argv[1]
    print("Testing ", wid)
    with open("./config.json") as f:
        config = json.load(f)
        server = Process(target=run_server, args=(this, ))
        server.start()
        #reqs(wid, f"http://172.17.6.175:8000/", config["attempts"], config["sleep"])
        reqs(wid, f"http://172.16.1.136:31114/", config["attempts"], config["sleep"])

        time.sleep(10)

       # df = pd.DataFrame(time_required, columns=["Execution Time"])
       # file = f"{this}/outputs/ow-chain-timelogger-{config['kind']}.xlsx"
       # df.to_excel(file, index=False)
       # upload_file(file)
       # server.terminate()
