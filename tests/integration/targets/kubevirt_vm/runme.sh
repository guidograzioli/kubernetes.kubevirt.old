#!/usr/bin/env bash
set -eux
set -o pipefail

{
export ANSIBLE_CALLBACKS_ENABLED=profile_tasks
export ANSIBLE_INVENTORY_ENABLED=kubernetes.kubevirt.kubevirt,yaml

[ -d files ] || mkdir files
[ -f files/priv_key ] || (ssh-keygen -t ed25519 -C test@test -f files/priv_key ; ssh-keygen -y -f files/priv_key > files/pub_key)

ansible-playbook playbook.yml "$@"

ansible-inventory -i test.kubevirt.yml -y --list "$@"

ansible-playbook verify.yml -i test.kubevirt.yml --private-key=files/priv_key "$@"

} || {
    exit 1
}
