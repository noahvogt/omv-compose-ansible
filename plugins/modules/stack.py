#!/usr/bin/python
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

DOCUMENTATION = r"""
module: stack
short_description: Set a stack of the openmediavault compose plugin
version_added: 0.1.0
author: Noah Vogt (@noahvogt)
description:
  - Writes a compose file, its environment and its override into the database of the
    openmediavault compose plugin, the same way the web UI does. The plugin keeps running,
    backing up and updating the stack.
  - Refuses to overwrite a stack that was changed outside Ansible, e.g. in the web UI. After
    every write it keeps a hash of what it wrote in O(state_dir). If OMV holds something
    else than both the wanted content and that hash, the module fails with the diff,
    unless O(force=true).
  - Does not start or recreate containers and never deletes stacks.
    The P(noahvogt.omv_compose.deploy#role) role runs C(docker compose up -d) after changes,
    see RV(pending).
options:
  name:
    description: Name of the stack.
    type: str
    required: true
  description:
    description: Description shown in the web UI.
    type: str
    default: ""
  body:
    description: Content of the compose file.
    type: str
    required: true
  env:
    description: Content of the environment file of the stack.
    type: str
    default: ""
  override:
    description: Content of C(compose.override.yml).
    type: str
    default: ""
  mask:
    description: Values hidden in all output (diffs, errors), e.g. the secrets in O(body).
    type: list
    elements: str
    default: []
  state_dir:
    description: Where the hashes of the last writes are kept.
    type: path
    default: /var/lib/omv-compose-ansible
  force:
    description: Overwrite changes made outside Ansible.
    type: bool
    default: false
extends_documentation_fragment:
  - ansible.builtin.action_common_attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
  platform:
    platforms: posix
notes:
  - Runs on the openmediavault host, as root. Tested with openmediavault 8 and openmediavault-compose 8.2.
  - Parameters reach OMV's RPC through stdin, so secrets do not show up in the process list.
"""

EXAMPLES = r"""
- name: Set the pihole stack
  noahvogt.omv_compose.stack:
    name: pihole
    description: DNS and DHCP
    body: "{{ lookup('ansible.builtin.template', 'stacks/pihole/pihole.yml') }}"
    mask: "{{ omv_compose_secrets.values() | list }}"
  register: pihole

- name: Apply the change
  ansible.builtin.command: /usr/sbin/omv-compose-run pihole up -d
  when: pihole.pending

- name: Mark the change as applied
  ansible.builtin.file:
    path: /var/lib/omv-compose-ansible/pihole.pending
    state: absent
  when: pihole.pending
"""

RETURN = r"""
pending:
  description:
    - Whether the content in OMV is not yet applied to the containers, from this run or an
      earlier one that failed before C(docker compose up -d).
    - Kept as the file C(<state_dir>/<name>.pending). Remove it after applying.
  returned: always
  type: bool
created:
  description: Whether the stack was new.
  returned: always
  type: bool
stacks:
  description: Names of all stacks in OMV before this run.
  returned: always
  type: list
  elements: str
  sample: [nginx_proxy_manager, pihole]
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.noahvogt.omv_compose.plugins.module_utils.omv_compose import (
    FILE_FIELDS, NEW_UUID, read_files, rpc, sync)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(type="str", required=True),
            description=dict(type="str", default=""),
            body=dict(type="str", required=True),
            env=dict(type="str", default=""),
            override=dict(type="str", default=""),
            mask=dict(type="list", elements="str", default=[], no_log=True),
            state_dir=dict(type="path", default="/var/lib/omv-compose-ansible"),
            force=dict(type="bool", default=False),
        ),
        supports_check_mode=True,
    )
    p = module.params
    files = read_files(module)
    record = next((f for f in files if f["name"] == p["name"]), None)
    current = {k: record[k] for k in FILE_FIELDS} if record else None
    wanted = {k: p[k] for k in FILE_FIELDS}

    def write():
        rpc(module, "Compose", "setFile", dict(
            wanted,
            uuid=record["uuid"] if record else NEW_UUID,
            name=p["name"],
            showenv=bool(wanted["env"].strip()) or bool(record and record["showenv"]),
            showoverride=bool(wanted["override"].strip()) or bool(record and record["showoverride"]),
        ))

    sync(module, p["name"], current, wanted, write,
         dict(changed=False, created=False, stacks=[f["name"] for f in files]))


if __name__ == "__main__":
    main()
