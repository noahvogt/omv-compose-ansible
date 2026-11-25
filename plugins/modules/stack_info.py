#!/usr/bin/python
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

DOCUMENTATION = r"""
module: stack_info
short_description: Read the stacks of the openmediavault compose plugin as templates
version_added: 0.1.0
author: Noah Vogt (@noahvogt)
description:
  - Reads all stacks and C(global.env) from the database of the openmediavault compose plugin
    and returns them as files for a repo, in the layout the P(noahvogt.omv_compose.deploy#role)
    role reads.
  - The content is returned as Jinja templates. Values of O(secrets) are replaced by
    C({{ omv_compose_secrets.<key> }}), Jinja delimiters in the content are escaped.
  - Lines that still look like a secret in plain text are listed in RV(suspicious).
options:
  secrets:
    description: Known secrets, key to value. Their values never appear in the result.
    type: dict
    default: {}
extends_documentation_fragment:
  - ansible.builtin.action_common_attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: none
  platform:
    platforms: posix
notes:
  - Runs on the openmediavault host, as root.
  - Secrets not listed in O(secrets) are returned in plain text, check RV(suspicious).
"""

EXAMPLES = r"""
- name: Read the stacks
  noahvogt.omv_compose.stack_info:
    secrets: "{{ omv_compose_secrets }}"
  register: omv
"""

RETURN = r"""
stacks:
  description: Name to description of every stack, in the order of the web UI.
  returned: always
  type: dict
  sample: {pihole: DNS and DHCP}
files:
  description: Non-empty files, path relative to the stacks directory.
  returned: always
  type: list
  elements: dict
  sample: [{path: pihole/pihole.yml, content: "services: ..."}, {path: global.env, content: "TZ=..."}]
suspicious:
  description: "Lines that look like a secret in plain text, as C(path:line: KEY)."
  returned: always
  type: list
  elements: str
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.noahvogt.omv_compose.plugins.module_utils.omv_compose import (
    literal_secrets, read_db, read_files, to_template)


def main():
    module = AnsibleModule(
        argument_spec=dict(secrets=dict(type="dict", default={}, no_log=True)),
        supports_check_mode=True,
    )
    secrets = {k: str(v) for k, v in module.params["secrets"].items()}
    files = read_files(module)

    raw = {"global.env": read_db(module, "conf.service.compose.globalenv")["globalenv"]}
    for f in files:
        name = f["name"]
        raw[f"{name}/{name}.yml"] = f["body"]
        raw[f"{name}/{name}.env"] = f["env"]
        raw[f"{name}/compose.override.yml"] = f["override"]

    out = [{"path": path, "content": to_template(text, secrets).rstrip("\n") + "\n"}
           for path, text in raw.items() if text.strip()]
    module.exit_json(
        changed=False,
        stacks={f["name"]: f["description"] for f in files},
        files=out,
        suspicious=[s for f in out for s in literal_secrets(f["path"], f["content"])],
    )


if __name__ == "__main__":
    main()
