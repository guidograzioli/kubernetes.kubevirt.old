# Copyright (c) 2018 Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = """
    name: kubevirt
    author:
      - Felix Matouschek (@0xFelix)

    short_description: KubeVirt inventory source

    description:
      - Fetch running VirtualMachineInstances for one or more namespaces.
      - Groups by namespace, namespace_vms and labels.
      - Uses kubevirt.(yml|yaml) YAML configuration file to set parameter values.

    extends_documentation_fragment:
      - inventory_cache
      - constructed

    options:
      plugin:
        description: Token that ensures this is a source file for the "kubevirt" plugin.
        required: True
        choices: ["kubevirt", "kubernetes.kubevirt.kubevirt"]
      host_format:
        description:
          - Specify the format of the host in the inventory group.
        default: "{namespace}-{name}"
      connections:
        description:
          - Optional list of cluster connection settings. If no connections are provided, the default
            I(~/.kube/config) and active context will be used, and objects will be returned for all namespaces
            the active user is authorized to access.
        suboptions:
          name:
            description:
              - Optional name to assign to the cluster. If not provided, a name is constructed from the server
                and port.
          kubeconfig:
            description:
              - Path to an existing Kubernetes config file. If not provided, and no other connection
                options are provided, the Kubernetes client will attempt to load the default
                configuration file from I(~/.kube/config). Can also be specified via K8S_AUTH_KUBECONFIG
                environment variable.
          context:
            description:
              - The name of a context found in the config file. Can also be specified via K8S_AUTH_CONTEXT environment
                variable.
          host:
            description:
              - Provide a URL for accessing the API. Can also be specified via K8S_AUTH_HOST environment variable.
          api_key:
            description:
              - Token used to authenticate with the API. Can also be specified via K8S_AUTH_API_KEY environment
                variable.
          username:
            description:
              - Provide a username for authenticating with the API. Can also be specified via K8S_AUTH_USERNAME
                environment variable.
          password:
            description:
              - Provide a password for authenticating with the API. Can also be specified via K8S_AUTH_PASSWORD
                environment variable.
          client_cert:
            description:
              - Path to a certificate used to authenticate with the API. Can also be specified via K8S_AUTH_CERT_FILE
                environment variable.
            aliases: [ cert_file ]
          client_key:
            description:
              - Path to a key file used to authenticate with the API. Can also be specified via K8S_AUTH_KEY_FILE
                environment variable.
            aliases: [ key_file ]
          ca_cert:
            description:
              - Path to a CA certificate used to authenticate with the API. Can also be specified via
                K8S_AUTH_SSL_CA_CERT environment variable.
            aliases: [ ssl_ca_cert ]
          validate_certs:
            description:
              - Whether or not to verify the API server's SSL certificates. Can also be specified via
                K8S_AUTH_VERIFY_SSL environment variable.
            type: bool
            aliases: [ verify_ssl ]
          namespaces:
            description:
              - List of namespaces. If not specified, will fetch all containers for all namespaces user is authorized
                to access.
          network_name:
            description:
              - In case of multiple network attached to virtual machine, define which interface should be returned as primary IP
                address.
            aliases: [ interface_name ]
          api_version:
            description:
              - Specify the KubeVirt API version.
          annotation_variable:
            description:
              - Specify the name of the annotation which provides data, which should be used as inventory host variables.
              - Note, that the value in ansible annotations should be json.
            default: "ansible"

    requirements:
    - "python >= 3.8"
    - "kubernetes >= 12.0.0"
"""

EXAMPLES = """
# Filename must end with kubevirt.[yml|yaml]

# Authenticate with token, and return all virtual machines for all namespaces
plugin: kubernetes.kubevirt.kubevirt
connections:
 - host: https://kubevirt.io
   token: xxxxxxxxxxxxxxxx
   ssl_verify: false

# Use default config (~/.kube/config) file and active context, and return vmis with interfaces
# connected to network myovsnetwork and from namespace vmis
plugin: kubernetes.kubevirt.kubevirt
connections:
  - namespaces:
      - vmis
    network_name: myovsnetwork
"""

from dataclasses import dataclass
import json

from ansible_collections.kubernetes.core.plugins.module_utils.k8s.client import (
    get_api_client,
)
from ansible_collections.kubernetes.core.plugins.inventory.k8s import (
    K8sInventoryException,
    InventoryModule as K8sInventoryModule,
    format_dynamic_api_exc,
)

try:
    from kubernetes.dynamic.resource import ResourceField
except ImportError:
    pass

try:
    from kubernetes.dynamic.exceptions import DynamicApiError
except ImportError:
    pass


@dataclass
class GetVmiOptions:
    api_version: str
    network_name: str
    host_format: str

    def __post_init__(self):
        if self.api_version is None:
            self.api_version = "kubevirt.io/v1"
        if self.host_format is None:
            self.host_format = "{namespace}-{name}"


class InventoryModule(K8sInventoryModule):
    NAME = "kubernetes.kubevirt.kubevirt"

    def setup(self, config_data, cache, cache_key):
        self.host_format = config_data.get("host_format")
        super(InventoryModule, self).setup(config_data, cache, cache_key)

    def fetch_objects(self, connections):
        if connections:
            if not isinstance(connections, list):
                raise K8sInventoryException("Expecting connections to be a list.")

            for connection in connections:
                if not isinstance(connection, dict):
                    raise K8sInventoryException(
                        "Expecting connection to be a dictionary."
                    )
                client = get_api_client(**connection)
                name = connection.get(
                    "name", self.get_default_host_name(client.configuration.host)
                )
                if connection.get("namespaces"):
                    namespaces = connection["namespaces"]
                else:
                    namespaces = self.get_available_namespaces(client)

                opts = GetVmiOptions(
                    connection.get("api_version"),
                    connection.get("network_name", connection.get("interface_name")),
                    self.host_format,
                )
                for namespace in namespaces:
                    self.get_vmis_for_namespace(client, name, namespace, opts)
        else:
            client = get_api_client()
            name = self.get_default_host_name(client.configuration.host)
            namespaces = self.get_available_namespaces(client)
            opts = GetVmiOptions(host_format=self.host_format)
            for namespace in namespaces:
                self.get_vmis_for_namespace(client, name, namespace, opts)

    def get_vmis_for_namespace(self, client, name, namespace, opts):
        v1_vmi = client.resources.get(
            api_version=opts.api_version, kind="VirtualMachineInstance"
        )
        try:
            obj = v1_vmi.get(namespace=namespace)
        except DynamicApiError as exc:
            self.display.debug(exc)
            raise K8sInventoryException(
                f"Error fetching VirtualMachineInstance list: {format_dynamic_api_exc(exc)}"
            )

        namespace_group = "namespace_{0}".format(namespace)
        namespace_vmis_group = "{0}_vmis".format(namespace_group)

        name = self._sanitize_group_name(name)
        namespace_group = self._sanitize_group_name(namespace_group)
        namespace_vmis_group = self._sanitize_group_name(namespace_vmis_group)

        self.inventory.add_group(name)
        self.inventory.add_group(namespace_group)
        self.inventory.add_child(name, namespace_group)
        self.inventory.add_group(namespace_vmis_group)
        self.inventory.add_child(namespace_group, namespace_vmis_group)

        for vmi in obj.items:
            if not (vmi.status and vmi.status.interfaces):
                continue

            # Find interface by its name:
            if opts.network_name is None:
                interface = vmi.status.interfaces[0]
            else:
                interface = next(
                    (i for i in vmi.status.interfaces if i.name == opts.network_name),
                    None,
                )

            # If interface is not found or IP address is not reported skip this VM:
            if interface is None or interface.ipAddress is None:
                continue

            vmi_name = opts.host_format.format(
                namespace=vmi.metadata.namespace,
                name=vmi.metadata.name,
                uid=vmi.metadata.uid,
            )
            vmi_groups = []
            vmi_annotations = (
                {}
                if not vmi.metadata.annotations
                else self.__resource_field_to_dict(vmi.metadata.annotations)
            )

            if vmi.metadata.labels:
                # create a group for each label_value
                for key, value in vmi.metadata.labels:
                    group_name = "label_{0}_{1}".format(key, value)
                    group_name = self._sanitize_group_name(group_name)
                    if group_name not in vmi_groups:
                        vmi_groups.append(group_name)
                    self.inventory.add_group(group_name)
                vmi_labels = self.__resource_field_to_dict(vmi.metadata.labels)
            else:
                vmi_labels = {}

            # Add vmi to the namespace group, and to each label_value group
            self.inventory.add_host(vmi_name)
            self.inventory.add_child(namespace_vmis_group, vmi_name)
            for group in vmi_groups:
                self.inventory.add_child(group, vmi_name)

            # Set up the connection
            self.inventory.set_variable(vmi_name, "ansible_connection", "ssh")
            self.inventory.set_variable(vmi_name, "ansible_host", interface.ipAddress)

            # Add hostvars from metadata
            self.inventory.set_variable(vmi_name, "object_type", "vmi")
            self.inventory.set_variable(vmi_name, "labels", vmi_labels)
            self.inventory.set_variable(vmi_name, "annotations", vmi_annotations)
            self.inventory.set_variable(
                vmi_name, "cluster_name", vmi.metadata.clusterName
            )
            self.inventory.set_variable(
                vmi_name, "resource_version", vmi.metadata.resourceVersion
            )
            self.inventory.set_variable(vmi_name, "uid", vmi.metadata.uid)

            # Add hostvars from status
            vmi_active_pods = (
                {}
                if not vmi.status.activePods
                else self.__resource_field_to_dict(vmi.status.activePods)
            )
            self.inventory.set_variable(vmi_name, "vmi_active_pods", vmi_active_pods)
            vmi_conditions = (
                []
                if not vmi.status.conditions
                else [self.__resource_field_to_dict(c) for c in vmi.status.conditions]
            )
            self.inventory.set_variable(vmi_name, "vmi_conditions", vmi_conditions)
            vmi_guest_os_info = (
                {}
                if not vmi.status.guestOSInfo
                else self.__resource_field_to_dict(vmi.status.guestOSInfo)
            )
            self.inventory.set_variable(
                vmi_name, "vmi_guest_os_info", vmi_guest_os_info
            )
            vmi_interfaces = (
                []
                if not vmi.status.interfaces
                else [self.__resource_field_to_dict(i) for i in vmi.status.interfaces]
            )
            self.inventory.set_variable(vmi_name, "vmi_interfaces", vmi_interfaces)
            self.inventory.set_variable(
                vmi_name,
                "vmi_launcher_container_image_version",
                vmi.status.launcherContainerImageVersion,
            )
            self.inventory.set_variable(
                vmi_name, "vmi_migration_method", vmi.status.migrationMethod
            )
            self.inventory.set_variable(
                vmi_name, "vmi_migration_transport", vmi.status.migrationTransport
            )
            self.inventory.set_variable(vmi_name, "vmi_node_name", vmi.status.nodeName)
            self.inventory.set_variable(vmi_name, "vmi_phase", vmi.status.phase)
            vmi_phase_transition_timestamps = (
                []
                if not vmi.status.phaseTransitionTimestamps
                else [
                    self.__resource_field_to_dict(p)
                    for p in vmi.status.phaseTransitionTimestamps
                ]
            )
            self.inventory.set_variable(
                vmi_name,
                "vmi_phase_transition_timestamps",
                vmi_phase_transition_timestamps,
            )
            self.inventory.set_variable(vmi_name, "vmi_qos_class", vmi.status.qosClass)
            self.inventory.set_variable(
                vmi_name,
                "vmi_virtual_machine_revision_name",
                vmi.status.virtualMachineRevisionName,
            )
            vmi_volume_status = (
                []
                if not vmi.status.volumeStatus
                else [self.__resource_field_to_dict(v) for v in vmi.status.volumeStatus]
            )
            self.inventory.set_variable(
                vmi_name, "vmi_volume_status", vmi_volume_status
            )

    def verify_file(self, path):
        if super(InventoryModule, self).verify_file(path):
            if path.endswith(("kubevirt.yml", "kubevirt.yaml")):
                return True
        return False

    def __resource_field_to_dict(self, field):
        if isinstance(field, ResourceField):
            return {
                k: self.__resource_field_to_dict(v) for k, v in field.__dict__.items()
            }
        elif isinstance(field, (list, tuple)):
            return [self.__resource_field_to_dict(item) for item in field]
        else:
            return field
