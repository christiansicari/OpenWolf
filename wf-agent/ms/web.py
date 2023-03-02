from datetime import datetime, timedelta
from fastapi import FastAPI, Response, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from os import getenv
from passlib.context import CryptContext
from handler import wf_trigger, handle, get_redis, el_deploy
from typing import Union, Any, Dict
from pydantic import BaseModel
import uvicorn
import traceback
import json

secret_key = ""
with open('/vault/secrets/jwt', 'r') as f:
    secret = json.load(f)
    secret_key = secret["data"]["key"]

algorithm = getenv("JWT_ALGORITHM")
expire_minutes = int(getenv("JWT_EXPIRE_MINUTES"))

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Union[str, None] = None

class WFTokenData(BaseModel):
    wid: Union[str, None] = None
    exec_id: Union[str, None] = None

""" class User(BaseModel):
    username: str
    email: Union[str, None] = None
    full_name: Union[str, None] = None

class UserInDB(User):
    hashed_password: str """

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI()

@app.get("/test")
async def hi(response: Response):
    print("hello")
    import time
    time.sleep(10)
    return

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


#def authenticate_user(fake_db, username: str, password: str):
def authenticate_user(username: str, password: str):
    r = get_redis()
    #user = get_user(r, username=token_data.username)
    user = r.json().get(f'{username}')
    if not user:
        return False
    if not verify_password(password, user["hashed_password"]):
        return False
    return user

def create_access_token(data: dict, expires_delta: Union[timedelta, None] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=algorithm)
    return encoded_jwt

""" async def get_current_user_token(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    r = get_redis()
    #user = get_user(r, username=token_data.username)
    user = r.json().get(f'{token_data.username}')
    if user is None:
        raise credentials_exception
    return token """

async def get_current_user_username(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    r = get_redis()
    #user = get_user(r, username=token_data.username)
    user = r.json().get(f'{token_data.username}')
    if user is None:
        raise credentials_exception
    return user["username"]

def get_current_user(token):
    
    payload = jwt.decode(token, secret_key, algorithms=[algorithm])
    username: str = payload.get("sub")
    if username is None:
        return None
    token_data = TokenData(username=username)
    r = get_redis()
    #user = get_user(r, username=token_data.username)
    user = r.json().get(f'{token_data.username}')
    if user is None:
        raise credentials_exception
    return user

def decode_exec_token(token: str):
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        #print(f"decoded payload: {payload}")
        wid: str = payload.get("workflowID")
        exec_id: str = payload.get("execID")
        #exp = payload.get("exp")
        #if wid is None or exec_id is None or exp is None:
        if wid is None or exec_id is None:
            print("Not valid exec token: wid or exec_id None")
            return None
        else:
            """ if(exp >= datetime.utcnow()):
                print("Not valid exec token")
                return None
            else:
                token_data = WFTokenData(wid=wid, exec_id = exec_id) """
            token_data = WFTokenData(wid=wid, exec_id = exec_id)
    except JWTError:
        print("Not valid exec token: JWT ERROR")
        return None
    r = get_redis()
    wf = r.json().get("workflow." + token_data.wid)
    execution = r.json().get(token_data.exec_id)
    if wf is None or execution is None:
        print("Not valid exec token: not found WF or Exec")
        return None
    return token_data

@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    #user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=expire_minutes)
    access_token = create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


""" @app.get("/users/me/", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user """

@app.post("/trigger")
def event(request: Union[Dict,Any], response: Response, current_user: str = Depends(get_current_user_username)):
    if type(request) == str: 
        request = json.dumps(request)
    elif type(request) == bytes:
        request = json.loads(request.decode('utf-8'))
    elif type(request) != dict:
        raise ValueError("type in body not recognized")
    try:
        triggered = wf_trigger(request, current_user)
        if(triggered):
            response.status_code = 202
        else:
            response.status_code=401
        return {"triggered": triggered}
    except Exception as e:
        print(e)
        traceback.print_exc()  
        response.status_code = 501
        return "Not implemented"

@app.post("/exec")
def event(request: Union[Dict,Any], response: Response):
    print(f"request-unmarshalled{request}")
    if type(request) == str: 
        request = json.dumps(request)
    elif type(request) == bytes:
        request = json.loads(request.decode('utf-8'))
    elif type(request) != dict:
        raise ValueError("type in body not recognized")
    print(f"request{request}")
    try:
        #exec_token_data = decode_exec_token(request["exec_token"])
        """ user = get_current_user(request["token"])
        print("user:")
        print(user) """
        #print(f"token-data: {token_data}")
        if "exec_token" in request:
            exec_token_data = decode_exec_token(request["exec_token"])
            if exec_token_data is None:
                response.status_code = 401
            elif exec_token_data.exec_id == request["ctx"]["execID"] and exec_token_data.wid == request["ctx"]["workflowID"]:
                handle(request)
                response.status_code = 202
            else:
                response.status_code = 401 
        else:
            response.status_code = 401
    except Exception as e:
        print(e)
        traceback.print_exc()
        response.status_code = 501
    return

@app.post("/deploy")
def deploy(request: Union[Dict,Any], response: Response, current_user: str = Depends(get_current_user_username)):
    if type(request) == str: 
        request = json.dumps(request)
    elif type(request) == bytes:
        request = json.loads(request.decode('utf-8'))
    elif type(request) != dict:
        raise ValueError("type in body not recognized")
    try:
        status_code = el_deploy(request, current_user, False)
        response.status_code = status_code
        if status_code == 202:
            return {"deployed": True}
        else:
            return {"deployed": False}
    except Exception as e:
        print(e)
        traceback.print_exc()  
        response.status_code = 501
        return "Wrong request format"

@app.put("/replace")
def replace(request: Union[Dict,Any], response: Response, current_user: str = Depends(get_current_user_username)):
    if type(request) == str: 
        request = json.dumps(request)
    elif type(request) == bytes:
        request = json.loads(request.decode('utf-8'))
    elif type(request) != dict:
        raise ValueError("type in body not recognized")
    try:
        status_code = el_deploy(request, current_user, True)
        response.status_code = status_code
        if status_code == 202:
            return {"replaced": True}
        else:
            return {"replaced": False}
    except Exception as e:
        print(e)
        traceback.print_exc()  
        response.status_code = 501
        return "Wrong request format"


if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000)