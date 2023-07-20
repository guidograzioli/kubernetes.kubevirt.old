#!/usr/bin/env bash
set -eux

{
export ANSIBLE_CALLBACKS_ENABLED=profile_tasks
export ANSIBLE_INVENTORY_ENABLED=kubernetes.kubevirt.kubevirt,yaml

[ -d files ] || mkdir files
[ -f files/priv_key ] || (ssh-keygen -t ed25519 -C test@test -f files/priv_key ; ssh-keygen -y -f priv_key > files/pub_key)

ansible-playbook playbook.yml -vvv --private-key=files/priv_key "$@"

ansible-inventory -i test.kubevirt.yml -y -vvv --list "$@"

ansible-playbook verify.yml -i test.kubevirt.yml -vvv --private-key=files/priv_key "$@"

} || {
    exit 1
}
