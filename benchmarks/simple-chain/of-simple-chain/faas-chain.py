import requests
from time import sleep
# start the script
# collect the function log in a file
# parse log with decode faas chain script
url = "http://pi1:31112/async-function/hash"

payload = {
    "ctx": {},
    "data": {
        "msg": 0,
        "hash": "47de7af5400e6e6244d58cf35d751447b2444f5b31aca52d85f5c959352d9eaf"
    }
}
headers = {
    "X-Callback-Url": "http://gateway.openfaas.svc.cluster.local:8080/function/hash"
}


TESTS = 30
SLEEP=5
for i in range(TESTS):
    print(f"Test: {i}/{TESTS-1}")
    response = requests.request("POST", url, headers=headers, json=payload)
    sleep(SLEEP)
