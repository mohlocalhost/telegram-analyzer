"""
Manage API keys for the signals server.

Usage:
    python3 manage_keys.py create                      # generate new key
    python3 manage_keys.py create --label "user@x"     # with label
    python3 manage_keys.py list                        # list all keys
    python3 manage_keys.py revoke <key>                # disable a key
    python3 manage_keys.py delete <key>                # permanently remove
"""
import json, sys, uuid
from datetime import datetime, timezone

KEYS_FILE = "api_keys.json"

def load():
    try:
        with open(KEYS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save(keys):
    with open(KEYS_FILE, "w") as f:
        json.dump(keys, f, indent=2)

def cmd_create(label=None):
    keys = load()
    new_key = str(uuid.uuid4())
    label = label or f"user_{len(keys) + 1}"
    keys[new_key] = {
        "label": label,
        "created": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "active": True,
    }
    save(keys)
    print(f"Created API key:")
    print(f"  Key:   {new_key}")
    print(f"  Label: {label}")
    print(f"  Total: {len(keys)} keys registered")
    return new_key

def cmd_list():
    keys = load()
    if not keys:
        print("No API keys registered.")
        return
    print(f"{'Status':<8} {'Key':<38} {'Label':<20} {'Created'}")
    print("-" * 90)
    for k, v in sorted(keys.items(), key=lambda x: x[1].get("created", "")):
        status = "✓ active" if v.get("active", True) else "✗ revoked"
        label = v.get("label", "")
        created = v.get("created", "")[:19]
        print(f"{status:<8} {k:<38} {label:<20} {created}")
    print(f"\nTotal: {len(keys)} keys ({sum(1 for v in keys.values() if v.get('active', True))} active)")

def cmd_revoke(key):
    keys = load()
    if key not in keys:
        print(f"Key not found: {key}")
        return 1
    if not keys[key].get("active", True):
        print(f"Key already revoked: {key}")
        return
    keys[key]["active"] = False
    save(keys)
    print(f"Revoked: {key} ({keys[key].get('label', '')})")

def cmd_delete(key):
    keys = load()
    if key not in keys:
        print(f"Key not found: {key}")
        return 1
    label = keys[key].get("label", "")
    del keys[key]
    save(keys)
    print(f"Deleted: {key} ({label})")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "create":
        label = None
        if len(sys.argv) >= 4 and sys.argv[2] == "--label":
            label = sys.argv[3]
        cmd_create(label)
    elif cmd == "list":
        cmd_list()
    elif cmd == "revoke" and len(sys.argv) >= 3:
        cmd_revoke(sys.argv[2])
    elif cmd == "delete" and len(sys.argv) >= 3:
        cmd_delete(sys.argv[2])
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)
