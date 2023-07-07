# Copyright (c) 2023 KubeVirt Project
# Based on the kubernetes.core.k8s inventory
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = """
name: kubevirt

short_description: KubeVirt inventory source
    
author:
- "Felix Matouschek (@0xFelix)"

description:
- Fetch running VirtualMachineInstances for one or more namespaces with an optional label selector.
- Groups by namespace, namespace_vmis and labels.
- Uses the kubectl connection plugin to access the Kubernetes cluster.
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
    - Specify the format of the host in the inventory group. Available specifiers: name, namespace, uid.
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
        - List of namespaces. If not specified, will fetch all VirtualMachineInstances for all namespaces
          the user is authorized to access.
      label_selector:
        description:
        - Define a label selector to select a subset of the fetched VirtualMachineInstances.
      network_name:
        description:
        - In case multiple networks are attached to a VirtualMachineInstance, define which interface should
          be returned as primary IP address.
        aliases: [ interface_name ]
      kube_secondary_dns:
        description:
        - Enable kubesecondarydns derived host names when using a secondary network interface.
        type: bool
        default: False
      api_version:
        description:
        - Specify the used KubeVirt API version.
        default: "kubevirt.io/v1"

requirements:
- "python >= 3.6"
- "kubernetes >= 12.0.0"
- "PyYAML >= 3.11"
"""

EXAMPLES = """
# Filename must end with kubevirt.[yml|yaml]

# Authenticate with token, and return all VirtualMachineInstances for all accessible namespaces
plugin: kubernetes.kubevirt.kubevirt
connections:
- host: https://192.168.64.4:8443
  api_key: xxxxxxxxxxxxxxxx
  validate_certs: false

# Use default config (~/.kube/config) file and active context, and return VirtualMachineInstances
# from namespace testing with interfaces connected to network bridge-network
plugin: kubernetes.kubevirt.kubevirt
connections:
- namespaces:
  - testing
  network_name: bridge-network

# Use default config (~/.kube/config) file and active context, and return VirtualMachineInstances
# from namespace testing with label app=test
plugin: kubernetes.kubevirt.kubevirt
connections:
- namespaces:
  - testing
  label_selector: app=test

# Use a custom config file, and a specific context.
plugin: kubernetes.kubevirt.kubevirt
connections:
- kubeconfig: /path/to/config
  context: 'awx/192-168-64-4:8443/developer'
"""

from dataclasses import dataclass
from json import loads

from kubernetes.dynamic.resource import ResourceField
from kubernetes.dynamic.exceptions import DynamicApiError

from ansible.plugins.inventory import BaseInventoryPlugin, Constructable, Cacheable

from ansible_collections.kubernetes.core.plugins.module_utils.common import (
    HAS_K8S_MODULE_HELPER,
    k8s_import_exception,
)

from ansible_collections.kubernetes.core.plugins.module_utils.k8s.client import (
    get_api_client,
)


class KubeVirtInventoryException(Exception):
    pass


@dataclass
class GetVmiOptions:
    """
    This class holds the options defined by the user.
    """

    api_version: str
    label_selector: str
    network_name: str
    kube_secondary_dns: bool
    base_domain: str
    host_format: str

    def __post_init__(self):
        if self.api_version is None:
            self.api_version = "kubevirt.io/v1"
        if self.host_format is None:
            self.host_format = "{namespace}-{name}"


class InventoryModule(BaseInventoryPlugin, Constructable, Cacheable):
    """
    This class implements the actual inventory module.
    """

    NAME = "kubernetes.kubevirt.kubevirt"

    connection_plugin = "kubernetes.core.kubectl"
    transport = "kubectl"

    @staticmethod
    def get_default_host_name(host):
        """
        get_default_host_name strips URL schemes from the host name and
        replaces invalid characters.
        """
        return (
            host.replace("https://", "")
            .replace("http://", "")
            .replace(".", "-")
            .replace(":", "_")
        )

    @staticmethod
    def format_dynamic_api_exc(exc):
        """
        format_dynamic_api_exc tries to extract the message from the JSON body
        of a DynamicException.
        """
        if exc.body:
            if exc.headers and exc.headers.get("Content-Type") == "application/json":
                message = loads(exc.body).get("message")
                if message:
                    return message
            return exc.body

        return f"{exc.status} Reason: {exc.reason}"

    def __init__(self):
        super().__init__()
        self.host_format = None

    def verify_file(self, path):
        """
        verify_file ensures the inventory file is compatible with this plugin.
        """
        return super().verify_file(path) and path.endswith(
            ("kubevirt.yml", "kubevirt.yaml")
        )

    def parse(self, inventory, loader, path, cache=True):
        """
        parse runs basic setup of the inventory.
        """
        super().parse(inventory, loader, path)
        cache_key = self._get_cache_prefix(path)
        config_data = self._read_config_data(path)
        self.host_format = config_data.get("host_format")
        self.setup(config_data, cache, cache_key)

    def setup(self, config_data, cache, cache_key):
        """
        setup checks for availability of the Kubernetes Python client,
        gets the configured connections and runs fetch_objects on them.
        If there is a cache it is returned instead.
        """
        connections = config_data.get("connections")

        if not HAS_K8S_MODULE_HELPER:
            raise KubeVirtInventoryException(
                "This module requires the Kubernetes Python client. "
                + f"Try `pip install kubernetes`. Detail: {k8s_import_exception}"
            )

        source_data = None
        if cache and cache_key in self._cache:
            try:
                source_data = self._cache[cache_key]
            except KeyError:
                pass

        if not source_data:
            self.fetch_objects(connections)

    def fetch_objects(self, connections):
        """
        fetch_objects populates the inventory with every configured connection.
        """
        if connections:
            if not isinstance(connections, list):
                raise KubeVirtInventoryException("Expecting connections to be a list.")

            for connection in connections:
                if not isinstance(connection, dict):
                    raise KubeVirtInventoryException(
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
                    connection.get("label_selector"),
                    connection.get("network_name", connection.get("interface_name")),
                    connection.get("kube_secondary_dns", False),
                    self.get_cluster_domain(client),
                    self.host_format,
                )
                for namespace in namespaces:
                    self.get_vmis_for_namespace(client, name, namespace, opts)
        else:
            client = get_api_client()
            name = self.get_default_host_name(client.configuration.host)
            namespaces = self.get_available_namespaces(client)
            opts = GetVmiOptions(None, None, None, False, None, self.host_format)
            for namespace in namespaces:
                self.get_vmis_for_namespace(client, name, namespace, opts)

    def get_cluster_domain(self, client):
        """
        get_cluster_domain tries to get the base domain of the cluster.
        """
        v1_dns = client.resources.get(api_version="config.openshift.io/v1", kind="DNS")
        try:
            obj = v1_dns.get(name="cluster")
        except DynamicApiError as exc:
            self.display.debug(
                f"Failed to fetch cluster DNS config: {self.format_dynamic_api_exc(exc)}"
            )
            return None
        return obj.get("spec", None).get("baseDomain", None)

    def get_available_namespaces(self, client):
        """
        get_available_namespaces lists all namespaces accessible with the
        configured credentials and returns them.
        """
        v1_namespace = client.resources.get(api_version="v1", kind="Namespace")
        try:
            obj = v1_namespace.get()
        except DynamicApiError as exc:
            self.display.debug(exc)
            raise KubeVirtInventoryException(
                f"Error fetching Namespace list: {self.format_dynamic_api_exc(exc)}"
            ) from exc
        return [namespace.metadata.name for namespace in obj.items]

    def get_vmis_for_namespace(self, client, name, namespace, opts):
        """
        get_vmis_for_namespace lists all VirtualMachineInstances in a namespace
        and adds groups and hosts to the inventory.
        """
        vmi_client = client.resources.get(
            api_version=opts.api_version, kind="VirtualMachineInstance"
        )
        try:
            vmi_list = vmi_client.get(
                namespace=namespace, label_selector=opts.label_selector
            )
        except DynamicApiError as exc:
            self.display.debug(exc)
            raise KubeVirtInventoryException(
                f"Error fetching VirtualMachineInstance list: {self.format_dynamic_api_exc(exc)}"
            ) from exc

        namespace_group = f"namespace_{namespace}"
        namespace_vmis_group = f"{namespace_group}_vmis"

        name = self._sanitize_group_name(name)
        namespace_group = self._sanitize_group_name(namespace_group)
        namespace_vmis_group = self._sanitize_group_name(namespace_vmis_group)

        self.inventory.add_group(name)
        self.inventory.add_group(namespace_group)
        self.inventory.add_child(name, namespace_group)
        self.inventory.add_group(namespace_vmis_group)
        self.inventory.add_child(namespace_group, namespace_vmis_group)

        for vmi in vmi_list.items:
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
                    group_name = f"label_{key}_{value}"
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

            # Set ansible_host to the kubesecondarydns derived host name if enabled
            # See https://github.com/kubevirt/kubesecondarydns#parameters
            if opts.kube_secondary_dns and opts.network_name is not None:
                ansible_host = f"{opts.network_name}.{vmi.metadata.name}.{vmi.metadata.namespace}.vm"
                if opts.base_domain is not None:
                    ansible_host += f".{opts.base_domain}"
            else:
                ansible_host = interface.ipAddress
            self.inventory.set_variable(vmi_name, "ansible_host", ansible_host)

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

    def __resource_field_to_dict(self, field):
        """
        Replace this with ResourceField.to_dict() once available in a stable release of
        the Kubernetes Python client
        See
        https://github.com/kubernetes-client/python/blob/main/kubernetes/base/dynamic/resource.py#L393
        """
        if isinstance(field, ResourceField):
            return {
                k: self.__resource_field_to_dict(v) for k, v in field.__dict__.items()
            }

        if isinstance(field, (list, tuple)):
            return [self.__resource_field_to_dict(item) for item in field]

        return field
