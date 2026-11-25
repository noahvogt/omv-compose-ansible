# noahvogt.omv_compose

Ansible collection to keep the stacks of the [openmediavault](https://www.openmediavault.org/) compose plugin in git.

The compose plugin keeps every stack in OMV's database and regenerates the files on disk from it, so templating the files does not stick. This collection writes into the database the same way the web UI does. OMV keeps running the stacks and keeps its backup and update jobs.

- **Deploy** a directory of stacks into OMV, then `docker compose up -d` for what changed.
- **Refuse to overwrite changes made in the web UI.** After every write a hash of what was written is kept on the host. If OMV holds something else than both the repo and that hash, the run fails with the diff.
- **Export** all stacks from OMV into the directory, with known secrets replaced by variables, so a change made in the web UI can be taken over and reviewed with `git diff`.
- **Secrets** stay in Ansible Vault. They are masked in all output and reach OMV through stdin, not the command line.

Tested with openmediavault 8 and openmediavault-compose 8.2.

## Content

| Name | Type | Purpose |
| :--- | :--- | :--- |
| `noahvogt.omv_compose.deploy` | role | Deploy `stacks/` into OMV |
| `noahvogt.omv_compose.export` | role | Export the stacks from OMV into `stacks/` |
| `noahvogt.omv_compose.stack` | module | Set one stack, with the check for changes made in the web UI |
| `noahvogt.omv_compose.global_env` | module | Set `global.env`, same check |
| `noahvogt.omv_compose.stack_info` | module | Read all stacks as templates |

## Install

```yaml
# requirements.yml
collections:
  - name: https://github.com/noahvogt/omv-compose-ansible.git
    type: git
    version: v0.1.0
```

```sh
ansible-galaxy collection install -r requirements.yml
```

## Layout of the stacks directory

```text
stacks/
├── stacks.yml                  # name: description, one line per stack
├── global.env                  # optional
└── pihole/
    ├── pihole.yml              # compose file
    ├── pihole.env              # optional
    └── compose.override.yml    # optional
```

All files are Jinja templates. Secrets are written as `{{ omv_compose_secrets.<key> }}`, with `omv_compose_secrets` a dict from the vault. The export role creates this layout from a running OMV, which is the easiest way to start.

## Usage

```yaml
# group_vars/nas/vars.yml
omv_compose_secrets: "{{ vault_omv_compose_secrets }}"

# deploy.yml
- hosts: nas
  gather_facts: false
  become: true
  roles:
    - noahvogt.omv_compose.deploy

# export.yml: same, with noahvogt.omv_compose.export
```

```sh
ansible-playbook export.yml --diff           # OMV -> stacks/, first time and after changes in the web UI
ansible-playbook deploy.yml --check --diff   # what would change in OMV
ansible-playbook deploy.yml --diff           # stacks/ -> OMV
```

### Role variables

| Variable | Default | Role | Meaning |
| :--- | :--- | :--- | :--- |
| `omv_compose_dir` | `{{ playbook_dir }}/stacks` | both | Stacks directory. The export deletes files and directories in it that are gone from OMV. |
| `omv_compose_secrets` | `{}` | both | Secrets, key to value |
| `omv_compose_stacks` | from `stacks.yml` | deploy | Stacks to deploy, name to description |
| `omv_compose_force` | `false` | deploy | Overwrite changes made in the web UI, ignore stacks missing in the directory |
| `omv_compose_state_dir` | `/var/lib/omv-compose-ansible` | deploy | Hashes of the last writes, on the host |
| `omv_compose_export_force` | `false` | export | Write even if a line looks like a secret in plain text |

## When the deploy stops

- **Changed outside Ansible:** someone edited the stack in the web UI. Run the export, review and commit, or overwrite with `-e omv_compose_force=true`.
- **Missing in the directory:** a stack exists in OMV but not in `stacks/`. Run the export, or delete the stack in the web UI. The collection never deletes stacks.

On the first run (no hashes yet) every difference counts as a change outside Ansible. Start with the export.

## How it works

The modules read OMV's database with `omv-confdbadm` and write through the plugin's RPC methods `Compose.setFile` and `Compose.setGlobalEnv`, the same calls the web UI makes. `omv-rpc` only takes parameters on the command line, so the modules call the RPC from a short PHP snippet that reads them from stdin. After a change the deploy role runs `omv-compose-run <stack> up -d`, which recreates only containers whose config changed. A change of `global.env` runs it for every stack.

## License

GPL-3.0-or-later, see [COPYING](COPYING).
