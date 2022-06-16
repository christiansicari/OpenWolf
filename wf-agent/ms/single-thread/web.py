from fastapi import FastAPI, Response, File, UploadFile
from handler import handle
from typing import Union, Any, Dict, List
from pydantic import BaseModel
import uvicorn
import traceback
import json
import sys

class Context(BaseModel):
    workflowID: str
    execID: Union[str, None] = None
    state: Union[str, None] = None

class Event(BaseModel):
    ctx: Context
    data: dict


app = FastAPI()

db = {}
workflows = {}
@app.post("/")
#def event(request: Event, response: Response):
def event(request: Union[Dict,Any], response: Response):
    print(request, type(request))
    if type(request) == str: 
        request = json.dumps(request)
    elif type(request) == bytes:
        request = json.loads(request.decode('utf-8'))
    elif type(request) != dict:
        raise ValueError("type in body not recognized")
    try:
        handle(db, workflows, request)
        response.status_code = 202
    except Exception as e:
        print(e)
        traceback.print_exc()
        traceback.print_exception(*sys.exc_info())
        print(sys.exc_info()[2])
        response.status_code = 501
    return

@app.get("/test")
async def hi(response: Response):
    print("hello")
    import time
    time.sleep(10)
    return



if __name__ == '__main__':
    #uvicorn.run("web:app", host="0.0.0.0", port=8000, workers=10)
    uvicorn.run(app, host="0.0.0.0", port=8000)
