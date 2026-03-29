import requests
import sys

def submit(prompt):
    payload = {"AgentType": "dummy", "Prompt": prompt}
    r = requests.post("http://localhost:5156/tasks", json=payload)
    r.raise_for_status()
    print("Submitted:", r.json())

if __name__ == '__main__':
    p = sys.argv[1] if len(sys.argv) > 1 else "Echo this"
    submit(p)
