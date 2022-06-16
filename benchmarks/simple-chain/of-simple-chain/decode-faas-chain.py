
from os.path import dirname, realpath, join
import re

# once decoded open excel and create a pivot table
# rows = req-id columns = max(time) min(time)
this = dirname(realpath(__file__))

with open(join(this, "./faas-chain.logs")) as f:
    lines = f.readlines()
    rows = []
    for line in lines:
        if "<msg>" in line:
            row = (line.split("<msg>", 1)[1]).replace("</msg>", "").replace("<msg>", "")
            rows.append(row)       
with open(join(this, "./faas-logs.csv"), "w") as g:
    g.writelines(rows)
