from urllib import response
from requests_futures.sessions import FuturesSession
from concurrent.futures import ProcessPoolExecutor

import time
session = FuturesSession(executor=ProcessPoolExecutor(max_workers=10))

a = time.time()
for i in range(0, 100):
    future_one = session.get('http://172.17.6.175:8000/test',headers={"nome": "christian"} )
print(time.time() -a )
print("ciao")