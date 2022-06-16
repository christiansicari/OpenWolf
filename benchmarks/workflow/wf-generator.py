from os import path
import json

this = path.dirname(path.realpath(__file__))
from sys import argv
template = {
  "id": "timeloggerchain",
  "callbackUrl": "http://172.17.6.175:8080",
  "states": {
    "A": {
      "id": "A",
      "function": {
        "ref": "timelogger"
      },
      "start": True
    },
  },
  "functions": {
    "timelogger": {
      "id": "",
      "platform": "openfaas",
      "config": {
        "id": "timelogger"
      },
      "endpoint": "http://gateway.openfaas.svc.cluster.local:8080/async-function/timelogger",
      "data": {
        "type": "intern",
        "uri": "."
      }
    }
  },
  "workflow": {
    "A": {
      "activation": "True",
      "inputFilter": "",
      "outputFilter": ""
    },
  }
}


def add_state(wf, sid, prev):
    wf["states"][sid] = template["states"]["A"].copy()
    wf["states"][sid]["id"] = sid
    del wf["states"][sid]["start"]
    wf["workflow"][sid] = template["workflow"]["A"].copy()
    wf["workflow"][sid]["activation"] = prev

if __name__ == '__main__':
    states = int(argv[1])
    prev = "A"
    wf = template.copy()
    for i in range(1, states):
        sid = f"s{i}"
        add_state(wf, sid, prev)
        prev = sid
    name = f"s{states}"
    add_state(wf, name, prev)
    wf["states"][name]["end"] = True
    template["id"] = f"{states}-{template['id']}"
    
    with open(path.join(this, f"./workflow.{name}.json"), "w") as f:
        json.dump(template, f)