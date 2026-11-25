# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared code of the modules: OMV database and RPC, drift check, export."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re

# OMV's uuid for "new object"
NEW_UUID = "fa4b1c66-ef79-11e5-87a0-0002b3a176b4"

# Like omv-rpc, but the params come from stdin, so secrets stay out of the process list.
RPC_PHP = r"""
require_once("openmediavault/autoloader.inc");
require_once("openmediavault/globals.inc");
require_once("openmediavault/functions.inc");
$params = json_decode_safe(stream_get_contents(STDIN));
$context = ["username" => "admin", "role" => OMV_ROLE_ADMINISTRATOR];
print json_encode_safe(\OMV\Rpc\Rpc::call($argv[1], $argv[2], $params, $context,
    \OMV\Rpc\Rpc::MODE_REMOTE));
"""

FILE_FIELDS = ("description", "body", "env", "override")

# Name of the variable the exported templates use for secrets
SECRETS_VAR = "omv_compose_secrets"

# KEY=value or KEY: value, with a name that suggests a secret
SECRET_LINE = re.compile(
    r"^\s*-?\s*['\"]?(\w*(PASS|_PW|SECRET|TOKEN|HASH|API_KEY)\w*)['\"]?\s*[:=]\s*(\S.*)$",
    re.IGNORECASE,
)


def run(module, args, stdin=None):
    rc, out, err = module.run_command(args, data=stdin, binary_data=True)
    if rc != 0:
        module.fail_json(msg=f"{args[0]} failed: {err or out}")
    return out


def read_db(module, conf_id):
    return json.loads(run(module, ["omv-confdbadm", "read", conf_id]))


def read_files(module):
    """All stacks in OMV's database, in the order of the web UI."""
    files = read_db(module, "conf.service.compose.file")
    return files if isinstance(files, list) else [files]


def rpc(module, service, method, params):
    run(module, ["php", "-c", "/etc/openmediavault", "-r", RPC_PHP, service, method],
        stdin=json.dumps(params))


def normalize(record):
    return {k: (v or "").rstrip("\n") for k, v in record.items()}


def digest(record):
    return hashlib.sha256(json.dumps(normalize(record), sort_keys=True).encode()).hexdigest()


def make_diff(key, before, after):
    """One entry per changed field, in the format of Ansible's --diff."""
    before = normalize(before or {})
    after = normalize(after)
    return [
        {"before_header": f"{key}: {field} (OMV)", "after_header": f"{key}: {field} (wanted)",
         "before": before.get(field, "") + "\n", "after": after[field] + "\n"}
        for field in after if before.get(field, "") != after[field]
    ]


def diff_text(diffs):
    lines = []
    for d in diffs:
        lines += difflib.unified_diff(d["before"].splitlines(), d["after"].splitlines(),
                                      d["before_header"], d["after_header"], lineterm="")
    return "\n".join(lines)


def sync(module, key, current, wanted, write, result):
    """Set wanted unless OMV holds a change made outside Ansible. Exits the module.

    current: what OMV holds now (None if missing), wanted: what it should hold,
    write: function that writes wanted into OMV.

    After a write, <state_dir>/<key>.pending marks the change as not yet applied to the
    containers. result["pending"] tells the caller, who removes the file after applying.
    """
    p = module.params
    state_file = os.path.join(p["state_dir"], key + ".sha256")
    pending_file = os.path.join(p["state_dir"], key + ".pending")
    try:
        with open(state_file) as fh:
            last_written = fh.read().strip()
    except FileNotFoundError:
        last_written = None
    result["pending"] = os.path.exists(pending_file)

    def save_state():
        if not module.check_mode:
            os.makedirs(p["state_dir"], mode=0o700, exist_ok=True)
            with open(state_file, "w") as fh:
                fh.write(digest(wanted) + "\n")

    if current is not None and normalize(current) == normalize(wanted):
        if last_written != digest(wanted):
            save_state()
        module.exit_json(**result)

    diffs = make_diff(key, current, wanted)
    if current is not None and last_written != digest(current) and not p["force"]:
        module.fail_json(
            msg=f"{key} was changed outside Ansible (web UI?). Take the change over "
                "(export role) or overwrite it (force).\n" + diff_text(diffs))

    result.update(changed=True, created=current is None, diff=diffs, pending=True)
    if not module.check_mode:
        os.makedirs(p["state_dir"], mode=0o700, exist_ok=True)
        with open(pending_file, "w"):
            pass
        write()
        save_state()
    module.exit_json(**result)


def to_template(text, secrets):
    """Secret values -> {{ omv_compose_secrets.<key> }}, Jinja delimiters escaped."""
    tokens = {}
    for i, (key, value) in enumerate(sorted(secrets.items(), key=lambda kv: -len(kv[1]))):
        token = f"\0{i}\0"
        if value and value in text:
            text = text.replace(value, token)
            tokens[token] = "{{ %s.%s }}" % (SECRETS_VAR, key)
    text = re.sub(r"\{[{%#]", lambda m: "{{ '%s' }}" % m.group(0), text)
    for token, ref in tokens.items():
        text = text.replace(token, ref)
    return text


def literal_secrets(path, text):
    """Lines that look like a secret written in plain text."""
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        m = SECRET_LINE.match(line)
        if m and "${" not in m.group(3) and SECRETS_VAR not in m.group(3):
            found.append(f"{path}:{n}: {m.group(1)}")
    return found
