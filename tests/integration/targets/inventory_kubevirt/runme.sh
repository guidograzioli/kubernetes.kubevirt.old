#!/usr/bin/env bash
set -eux
set -o pipefail

export ANSIBLE_ROLES_PATH="../"

USER_CREDENTIALS_DIR=$(pwd)
export USER_CREDENTIALS_DIR

{
export ANSIBLE_CALLBACKS_ENABLED=profile_tasks
export ANSIBLE_INVENTORY_ENABLED=kubernetes.kubevirt.kubevirt,yaml
export ANSIBLE_PYTHON_INTERPRETER=auto_silent

ansible-inventory -i test.kubevirt.yml -y --list --output empty.yml "$@"

ansible-playbook playbook.yml

# should list 2 vmi
ansible-inventory -i test.kubevirt.yml -y --list --output all.yml "$@"

# should list 1 vm with label_app_test
ansible-inventory -i test.label.kubevirt.yml -y --list --output label.yml "$@"

# should list 1 vm with multus interface
ansible-inventory -i test.net.kubevirt.yml -y --list --output net.yml "$@"

ansible-playbook verify.yml "$@"

} || {
    exit 1
}
