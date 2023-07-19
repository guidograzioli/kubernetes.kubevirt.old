#!/usr/bin/env bash
set -eux
export ANSIBLE_CALLBACKS_ENABLED=profile_tasks
export ANSIBLE_ROLES_PATH=../
export ANSIBLE_INVENTORY_ENABLED=kubernetes.kubevirt.kubevirt,yaml


mkdir files
ssh-keygen -t ed25519 -C test@test -f files/priv_key
ssh-keygen -y -f priv_key > files/pub_key

ansible-playbook playbook.yml --private-key=files/priv_key $@"
