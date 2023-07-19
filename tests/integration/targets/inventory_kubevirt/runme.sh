#!/usr/bin/env bash

set -eux

export ANSIBLE_ROLES_PATH="../"

USER_CREDENTIALS_DIR=$(pwd)
export USER_CREDENTIALS_DIR

{
export ANSIBLE_CALLBACKS_ENABLED=profile_tasks
export ANSIBLE_INVENTORY_ENABLED=kubernetes.kubevirt.kubevirt,yaml
export ANSIBLE_PYTHON_INTERPRETER=auto_silent

cat << EOF > "test.kubevirt.yml"
plugin: kubernetes.kubevirt.kubevirt
connections:
  - namespaces:
    - default
EOF

ansible-inventory -i test.kubevirt.yml -vvv --list "$@"

} || {
    exit 1
}
