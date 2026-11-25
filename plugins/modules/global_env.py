#!/usr/bin/python
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

DOCUMENTATION = r"""
module: global_env
short_description: Set the global environment file of the openmediavault compose plugin
version_added: 0.1.0
author: Noah Vogt (@noahvogt)
description:
  - Writes C(global.env) into the database of the openmediavault compose plugin and enables it,
    the same way the web UI does. Every stack gets these variables.
  - Same check for changes made outside Ansible as M(noahvogt.omv_compose.stack).
options:
  content:
    description: Content of C(global.env).
    type: str
    required: true
  mask:
    description: Values hidden in all output (diffs, errors), e.g. the secrets in O(content).
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
  - Runs on the openmediavault host, as root.
  - Containers keep the old values until they are recreated (C(docker compose up -d)).
"""

EXAMPLES = r"""
- name: Set global.env
  noahvogt.omv_compose.global_env:
    content: "{{ lookup('ansible.builtin.template', 'stacks/global.env') }}"
    mask: "{{ omv_compose_secrets.values() | list }}"
"""

RETURN = r"""
pending:
  description:
    - Whether the content in OMV is not yet applied to the containers of all stacks, from this run or an
      earlier one that failed before C(docker compose up -d).
    - Kept as the file C(<state_dir>/global.env.pending). Remove it after applying.
  returned: always
  type: bool
stacks:
  description: Names of all stacks in OMV.
  returned: always
  type: list
  elements: str
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.noahvogt.omv_compose.plugins.module_utils.omv_compose import (
    read_db, read_files, rpc, sync)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            content=dict(type="str", required=True),
            mask=dict(type="list", elements="str", default=[], no_log=True),
            state_dir=dict(type="path", default="/var/lib/omv-compose-ansible"),
            force=dict(type="bool", default=False),
        ),
        supports_check_mode=True,
    )
    record = read_db(module, "conf.service.compose.globalenv")
    current = {"globalenv": record["globalenv"]}
    wanted = {"globalenv": module.params["content"]}

    def write():
        rpc(module, "Compose", "setGlobalEnv", {"enabled": True, "globalenv": wanted["globalenv"]})

    sync(module, "global.env", current, wanted, write,
         dict(changed=False, stacks=[f["name"] for f in read_files(module)]))


if __name__ == "__main__":
    main()
