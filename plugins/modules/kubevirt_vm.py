# Copyright (c) 2023 KubeVirt Project
# Based on the kubernetes.core.k8s module
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = """
module: kubevirt_vm

short_description: Create or delete KubeVirt VirtualMachines on Kubernetes

author:
- "Felix Matouschek (@0xFelix)"

description:
- Use the Kubernetes Python client to perform create or delete operations on KubeVirt VirtualMachines.
- Pass options to create the VirtualMachine as module arguments.
- Authenticate using either a config file, certificates, password or token.
- Supports check mode.

extends_documentation_fragment:
- kubernetes.core.k8s_auth_options

options:
  state:
    description:
    - Determines if a VirtualMachine should be created or deleted. When set to C(present), a VirtualMachine
      will be created, if it does not already exist. If set to C(absent), an existing VirtualMachine will be
      deleted. If set to C(present) and attributes of an existing VirtualMachine differ from from those specified
      an error is raised.
    type: str
    default: present
    choices: [ absent, present ]
  api_version:
    description:
    - Use this to set the API version of KubeVirt.
    type: str
    default: kubevirt.io/v1
  name:
    description:
    - Specify the name of the VirtualMachine.
    - This option is ignored when I(state) is not set to C(present).
    - mutually exclusive with C(generate_name).
    type: str
  generate_name:
    description:
    - Specify the basis of the VirtualMachine name and random characters will be added automatically on server to
      generate a unique name.
    - Only used when I(state=present).
    - mutually exclusive with C(name).
    type: str
  namespace:
    description:
    - Specify the name of the VirtualMachine.
    type: str
  annotations:
    description:
    - Specify annotations to set on the VirtualMachine.
    - Only used when I(state=present).
    type: dict
  labels:
    description:
    - Specify labels to set on the VirtualMachine.
    type: dict
  instancetype:
    description:
    - Specify the instancetype of the VirtualMachine.
    - Only used when I(state=present).
    type: str
  preference:
    description:
    - Specify the preference of the VirtualMachine.
    - Only used when I(state=present).
    type: str
  infer_from_volume:
    description:
    - Specify volumes to infer an instancetype or a preference from.
    - Only used when I(state=present).
    type: dict
    suboptions:
      instancetype:
        description:
        - Name of the volume to infer the instancetype from.
        type: str
      preference:
        description:
        - Name of the volume to infer the preference from.
        type: str
  interfaces:
    description:
    - Specify the interfaces of the VirtualMachine.
    - See: https://kubevirt.io/api-reference/main/definitions.html#_v1_interface
    type: list
  networks:
    description:
    - Specify the networks of the VirtualMachine.
    - See: https://kubevirt.io/api-reference/main/definitions.html#_v1_network
    type: list
  volumes:
    description:
    - Specify the volumes of the VirtualMachine.
    - See: https://kubevirt.io/api-reference/main/definitions.html#_v1_volume
    type: list
  wait:
    description:
    - Whether to wait for the VirtualMachine to end up in the ready state.
    type: bool
    default: no
  wait_sleep:
    description:
    - Number of seconds to sleep between checks.
    - Ignored if C(wait) is not set.
    default: 5
    type: int
  wait_timeout:
    description:
    - How long in seconds to wait for the resource to end up in the desired state.
    - Ignored if C(wait) is not set.
    default: 120
    type: int

requirements:
- "python >= 3.6"
- "kubernetes >= 12.0.0"
- "PyYAML >= 3.11"
- "jsonpatch"
- "jinja2"
"""

EXAMPLES = """
- name: Create a VirtualMachine
  kubernetes.kubevirt.kubevirt_vm:
     state: present
     name: testvm
     namespace: default
     labels:
       app: test
     instancetype: u1.medium
     preference: fedora
     interfaces:
     - name: default
       masquerade: {}
     - name: bridge-network
       bridge: {}
     networks:
     - name: default
       pod: {}
     - name: bridge-network
       multus:
         networkName: kindexgw
     volumes:
     - containerDisk:
         image: quay.io/containerdisks/fedora:latest
       name: containerdisk
     - cloudInitNoCloud:
         userData: |-
           #cloud-config
           # The default username is: fedora
           ssh_authorized_keys:
             - ssh-ed25519 AAAA...
       name: cloudinit

- name: Delete a VirtualMachine
  kubernetes.kubevirt.kubevirt_vm:
    name: testvm
    namespace: default
    state: absent
"""

RETURN = """
result:
  description:
  - The created object. Will be empty in the case of a deletion.
  type: complex
  contains:
     changed:
       description: Whether the VirtualMachine was changed
       type: bool
       sample: True
     duration:
       description: elapsed time of task in seconds
       returned: when C(wait) is true
       type: int
       sample: 48
     method:
       description: Method executed on the Kubernetes API.
       returned: success
       type: str
"""

from typing import Dict
import copy
import yaml

from jinja2 import Environment

from ansible_collections.kubernetes.core.plugins.module_utils.ansiblemodule import (
    AnsibleModule,
)
from ansible_collections.kubernetes.core.plugins.module_utils.args_common import (
    AUTH_ARG_SPEC,
)
from ansible_collections.kubernetes.core.plugins.module_utils.k8s import (
    runner,
)
from ansible_collections.kubernetes.core.plugins.module_utils.k8s.core import (
    AnsibleK8SModule,
)
from ansible_collections.kubernetes.core.plugins.module_utils.k8s.exceptions import (
    CoreException,
    ResourceTimeout,
)
from ansible_collections.kubernetes.core.plugins.module_utils.k8s.service import (
    diff_objects,
)

VM_TEMPLATE = """
apiVersion: {{ api_version }}
kind: VirtualMachine
metadata:
  {% if name %}
  name: "{{ name }}"
  {% endif %}
  {% if generate_name %}
  generateName: "{{ generate_name }}"
  {% endif %}
  namespace: "{{ namespace }}"
  {% if annotations %}
  annotations:
    {{ annotations | to_yaml | indent(4) }}
  {%- endif %}
  {% if labels %}
  labels:
    {{ labels | to_yaml | indent(4) }}
  {%- endif %}
spec:
  {% if instancetype or infer_from_volume.instancetype %}
  instancetype:
    {% if instancetype %}
    name: "{{ instancetype }}"
    {% endif %}
    {% if infer_from_volume.instancetype %}
    inferFromVolume: "{{ infer_from_volume.instancetype }}"
    {% endif %}
  {% endif %}
  {% if preference or infer_from_volume.preference %}
  preference:
    {% if preference %}
    name: "{{ preference }}"
    {% endif %}
    {% if infer_from_volume.preference %}
    inferFromVolume: "{{ infer_from_volume.preference }}"
    {% endif %}
  {% endif %}
  running: true
  template:
    {% if annotations or labels %}
    metadata:
      {% if annotations %}
      annotations:
        {{ annotations | to_yaml | indent(8) }}
      {%- endif %}
      {% if labels %}
      labels:
        {{ labels | to_yaml | indent(8) }}
      {%- endif %}
    {% endif %}
    spec:
      domain:
        {% if interfaces %}
        devices:
          interfaces:
          {{ interfaces | to_yaml | indent(10) }}
        {%- else %}
        devices: {}
        {% endif %}
      {% if networks %}
      networks:
      {{ networks | to_yaml | indent(6) }}
      {%- endif %}
      {% if volumes %}
      volumes:
      {{ volumes | to_yaml | indent(6) }}
      {%- endif %}
"""


def perform_action(svc, definition: Dict, params: Dict) -> Dict:
    """
    perform_action creates or deletes objects on the Kubernetes API.

    This is stripped down version of
    ansible_collections.kubernetes.core.plugins.module_utils.k8s.runner.perform_action
    """
    result = {"changed": False}
    instance = {}

    # Dynamically lookup CRD and fill in correct kind and apiVersion
    resource = svc.find_resource(
        definition.get("kind"), definition.get("apiVersion"), fail=True
    )
    definition["kind"] = resource.kind
    definition["apiVersion"] = resource.group_version

    # Retrieve potentially already existing object
    existing = svc.retrieve(resource, definition)

    if params.get("state", None) == "absent":
        # Delete object
        instance = svc.delete(resource, definition, existing)
        result["method"] = "delete"
        if existing:
            result["changed"] = True
    else:
        if not existing:
            # Create object
            instance = svc.create(resource, definition)
            result["result"] = instance
            result["method"] = "create"
            result["changed"] = True
        else:
            # Do a best effort comparison so the module might return success with no changes
            compare_existing(definition, result, existing, svc, resource)

    # Wait if needed
    success = True

    method = result.get("method")
    if method == "delete" or method == "create":
        if params.get("wait") and not svc.module.check_mode:
            success, instance, result["duration"] = svc.wait(resource, instance)

    if not success:
        name = instance["metadata"]["name"]
        raise ResourceTimeout(
            f'"{resource.kind}" "{name}": Timed out waiting on VirtualMachine',
            result,
        )

    return result


def compare_existing(definition: Dict, result: Dict, existing: Dict, svc, resource):
    """
    compare_existing tries to do a best effort comparison to potentially allow
    the module to return success without changes
    """
    old = copy.deepcopy(existing.to_dict())
    name = definition["metadata"]["name"]

    # Dry-run apply the new definition to receive all changes from mutating admitters
    old_dry_run = svc.client.dry_run
    svc.client.dry_run = True
    try:
        new = svc.apply(resource, definition)
    # Catch exception if apply fails and return early
    except CoreException as exc:
        raise CoreException(
            f'"{resource.kind}" "{name}": VirtualMachine already exists',
            result,
        ) from exc
    svc.client.dry_run = old_dry_run

    # Clear fields which will never be idempotent
    del old["metadata"]
    del new["metadata"]
    del old["status"]
    del new["status"]

    match, diffs = diff_objects(old, new)
    if match and diffs:
        result.setdefault("warnings", []).append(
            "No meaningful diff was generated, but the API may not be idempotent"
        )

    if diffs:
        result["diff"] = diffs

    if not match:
        raise CoreException(
            f'"{resource.kind}" "{name}": VirtualMachine already exists',
            result,
        )


def render_template(params: Dict) -> str:
    """
    render_template uses Jinja2 to render the VM_TEMPLATE into a string.
    """
    env = Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)
    env.filters["to_yaml"] = lambda data, *_, **kw: yaml.dump(
        data, allow_unicode=True, default_flow_style=False, **kw
    )

    template = env.from_string(VM_TEMPLATE.strip())
    return template.render(params)


def arg_spec() -> Dict:
    """
    arg_spec defines the argument spec of this module.
    """
    spec = {
        "state": {"default": "present", "choices": ["present", "absent"]},
        "api_version": {"default": "kubevirt.io/v1"},
        "name": {},
        "generate_name": {},
        "namespace": {"required": True},
        "annotations": {"type": "dict"},
        "labels": {"type": "dict"},
        "instancetype": {},
        "preference": {},
        "infer_from_volume": {
            "type": "dict",
            "options": {"instancetype": {}, "preference": {}},
        },
        "interfaces": {"type": "list", "element": "dict"},
        "networks": {"type": "list", "element": "dict"},
        "volumes": {"type": "list", "element": "dict"},
        "wait": {"type": "bool", "default": False},
        "wait_sleep": {"type": "int", "default": 5},
        "wait_timeout": {"type": "int", "default": 120},
    }
    spec.update(copy.deepcopy(AUTH_ARG_SPEC))

    return spec


def main():
    """
    main instantiates the AnsibleK8SModule, creates the resource
    definition and runs the module.
    """
    module = AnsibleK8SModule(
        module_class=AnsibleModule,
        argument_spec=arg_spec(),
        mutually_exclusive=[
            ("name", "generate_name"),
        ],
        required_one_of=[
            ("name", "generate_name"),
        ],
        required_together=[("interfaces", "networks")],
        supports_check_mode=True,
    )

    # Set resource_definition to our rendered template
    module.params["resource_definition"] = render_template(module.params)

    # Set wait_condition to allow waiting for the ready state of the VirtualMachine
    module.params["wait_condition"] = {"type": "Ready", "status": True}

    # Override the perform_action func of kubernetes.core with our own
    runner.perform_action = perform_action
    try:
        runner.run_module(module)
    except CoreException as exc:
        module.fail_from_exception(exc)


if __name__ == "__main__":
    main()
