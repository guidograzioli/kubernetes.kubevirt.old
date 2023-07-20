#!/usr/bin/env bash

set -eux

export ANSIBLE_ROLES_PATH="../"

USER_CREDENTIALS_DIR=$(pwd)
export USER_CREDENTIALS_DIR

{
export ANSIBLE_CALLBACKS_ENABLED=profile_tasks
export ANSIBLE_INVENTORY_ENABLED=kubernetes.kubevirt.kubevirt,yaml
export ANSIBLE_PYTHON_INTERPRETER=auto_silent

ansible-inventory -i test.kubevirt.yml -y -vvv --list "$@"

ansible-playbook playbooks/create.yml

ansible-inventory -i test.kubevirt.label.yml -y -vvv --list "$@"

} || {
    exit 1
}
