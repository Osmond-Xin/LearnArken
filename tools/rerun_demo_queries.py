"""INV-6 helper: repeat the three demo queries and report what each run did."""

import json, sys
from fastapi.testclient import TestClient
from learnarken.api.app import app

RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
QS = [
    ("A answer", "What safety precautions apply before removing the hydraulic pump?"),
    ("B refusal", "How do I replace the coffee maker in the galley?"),
    ("C retraction", "APU automatic start sequence"),
]
c = TestClient(app)
for tag, q in QS:
    for i in range(RUNS):
        r = c.post("/query", json={"question": q})
        ev, seq, toks, gate, refused = None, [], 0, None, None
        for line in r.text.splitlines():
            if line.startswith("event: "):
                ev = line[7:].strip()
                seq.append(ev)
                if ev == "token":
                    toks += 1
            elif line.startswith("data: ") and ev == "result":
                d = json.loads(line[6:])
                gate = d.get("refusal_gate")
                refused = d.get("refused")
        print(
            f"{tag:13} run{i + 1}  tokens={toks:<3} retract={'retract' in seq!s:5} "
            f"refused={refused!s:5} gate={gate}",
            flush=True,
        )
