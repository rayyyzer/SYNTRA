import json
import os

results_file = r"d:\Samsung_Hackathon\Theme02_Engine\results.jsonl"
with open(results_file, "r", encoding="utf-8") as f:
    lines = [json.loads(l) for l in f if l.strip()]

print(f"Total scenarios in results.jsonl: {len(lines)}")
for i, l in enumerate(lines, 1):
    q = l["query"]
    ctx = l["response"]["contexts"][0]
    acts = [a["actionName"] for a in ctx["actions"]]
    dls = [sg["actionableDeeplink"]["deeplink"] for a in ctx["actions"] for sg in a["stepGroups"] if sg.get("actionableDeeplink")]
    val_dls = [sg["validationDeeplink"]["deeplink"] for a in ctx["actions"] for sg in a["stepGroups"] if sg.get("validationDeeplink")]
    print(f"[{i:02d}] Query: {q[:45]}...")
    print(f"     Title:    {ctx['title']}")
    print(f"     Goal:     {ctx['goal']}")
    print(f"     Actions:  {acts}")
    print(f"     Act DL:   {dls}")
    print(f"     Val DL:   {val_dls}")
    print()
