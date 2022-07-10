from datetime import datetime, timedelta
import jwt
import string
import random
from fastapi import FastAPI, Response, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from handler import wf_trigger, handle
from typing import Union, Any, Dict
from pydantic import BaseModel
import uvicorn
import traceback
import json

SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


fake_users_db = {
    "johndoe": {
        "username": "johndoe",
        "full_name": "John Doe",
        "email": "johndoe@example.com",
        "hashed_password": "$2a$12$JTPqc.n8rH3H7ltxO5QyYOxtpUJhp09Z/9L4hgSCntLSldXS.9RZi",
        "disabled": False,
    }
}


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Union[str, None] = None


class User(BaseModel):
    username: str
    email: Union[str, None] = None
    full_name: Union[str, None] = None
    disabled: Union[bool, None] = None


class UserInDB(User):
    hashed_password: str


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class Context(BaseModel):
    workflowID: str
    execID: Union[str, None] = None
    state: Union[str, None] = None

class Event(BaseModel):
    ctx: Context
    data: dict

#user1 = User(id=1,uname="gamorabito",pwd="gamorabito")
""" user1.uname = "gamorabito"
user1.pwd = "gamorabito"
user1.id = 1 """


app = FastAPI()

@app.get("/test")
async def hi(response: Response):
    print("hello")
    import time
    time.sleep(10)
    return

def get_random_string(length):
    # choose from all lowercase letter
    letters = string.ascii_lowercase
    result_str = ''.join(random.choice(letters) for i in range(length))
    print("Random string of length", length, "is:", result_str)
    return result_str

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        return UserInDB(**user_dict)


def authenticate_user(fake_db, username: str, password: str):
    user = get_user(fake_db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: Union[timedelta, None] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = get_user(fake_users_db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/users/me/", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user


@app.get("/users/me/items/")
async def read_own_items(current_user: User = Depends(get_current_active_user)):
    return [{"item_id": "Foo", "owner": current_user.username}]

@app.post("/trigger")
#def event(request: Event, response: Response):
def event(request: Union[Dict,Any], response: Response, current_user: User = Depends(get_current_active_user)):
#def event(request: Union[Dict,Any], response: Response):
    #print("incoming event, status: ", request.headers.get('x-function-status'))
    if type(request) == str: 
        request = json.dumps(request)
    elif type(request) == bytes:
        request = json.loads(request.decode('utf-8'))
    elif type(request) != dict:
        raise ValueError("type in body not recognized")
    try:
        wf_trigger(request)
        response.status_code = 202
    except Exception as e:
        print(e)
        traceback.print_exc()
        
        response.status_code = 501
    return

@app.post("/exec")
#def event(request: Event, response: Response):
def event(request: Union[Dict,Any], response: Response):
#def event(request: Union[Dict,Any], response: Response):
    #print("incoming event, status: ", request.headers.get('x-function-status'))
    if type(request) == str: 
        request = json.dumps(request)
    elif type(request) == bytes:
        request = json.loads(request.decode('utf-8'))
    elif type(request) != dict:
        raise ValueError("type in body not recognized")
    try:
        handle(request)
        response.status_code = 202
    except Exception as e:
        print(e)
        traceback.print_exc()
        
        response.status_code = 501
    return


if __name__ == '__main__':
    #uvicorn.run("web:app", host="0.0.0.0", port=8000, workers=10)
    uvicorn.run(app, host="0.0.0.0", port=8000)


""" def encode_auth_token(user_id, secret):
    try:
        payload = {
            'exp': datetime.utcnow() + timedelta(days=0, seconds=3600),
            'iat': datetime.utcnow(),
            'sub': user_id
        }
        return jwt.encode(
            payload,
            secret,
            algorithm='HS256'
        )
    except Exception as e:
        return e """


""" @app.post("/login")
def login(request: Union[Dict,Any], response: Response):
    #print("incoming event, status: ", request.headers.get('x-function-status'))
    if type(request) == str: 
        request = json.dumps(request)
    elif type(request) == bytes:
        request = json.loads(request.decode('utf-8'))
    elif type(request) != dict:
        raise ValueError("type in body not recognized")
    try:
        print(request)
        if(request["uname"] == user1.uname and request["pwd"] == user1.pwd):
            user1.sec = get_random_string(32)
            token = encode_auth_token(user1.id, user1.sec)
            user1.token = token
            print(user1.token)
            response.status_code = 200
        else:
            response.status_code = 401
    except Exception as e:
        print(e)
        traceback.print_exc()
        response.status_code = 500
    return """