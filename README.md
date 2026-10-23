# Caelestia KVM dashboard

A compact KVM/libvirt monitoring tab and an optional Kubernetes health tab for Caelestia, with native connection preferences in Caelestia Settings.

The tab shows VM status, allocated vCPUs and RAM, CPU load, and guest memory usage. Each VM has an SSH button. There are no input fields or update timestamps in the monitoring tab.

The **Kubernetes** tab monitors one selected cluster: API connectivity, node readiness, system pods, application availability and resource problems. It uses host `kubectl` and works independently of libvirt. Kubernetes monitoring is disabled by default.

## Install

Use your normal desktop account, without `sudo`:

```sh
./setup.sh check
./setup.sh install --restart
```

Existing requirements: Caelestia, Quickshell, Python 3.10+, Python's `libvirt` bindings, OpenSSH, and working access to your existing libvirt connections. On Arch, the Python bindings are supplied by `libvirt-python`. The installer checks dependencies; it does not install packages.

Tested with Caelestia Shell **2.5.0**, Quickshell **0.3.2**, Qt **6.12**, and libvirt **12.8.0**. The installer checks the integration points before writing anything. Other Caelestia versions may need an updated adapter in `scripts/setup.py`.

For a differently located Caelestia installation:

```sh
./setup.sh install --source /path/to/caelestia --restart
```

`--target` selects an alternative overlay directory. The default is `$XDG_CONFIG_HOME/quickshell/caelestia`, or `~/.config/quickshell/caelestia`.

## Use

Open Caelestia's top dashboard and select **VMs**. Both system and user-session libvirt connections are enabled by default.

Click **SSH** to launch the terminal configured in Caelestia. If no username is saved, the terminal asks for it. When no IP or host override is available, it also asks for the host. OpenSSH handles keys, passwords, host-key verification and your existing SSH configuration. The widget never stores passwords or private-key contents.

SSH is disabled for stopped, suspended and paused VMs, and when displayed information is stale. An unsuccessful SSH command remains visible in the terminal until you press Enter.

Open **Caelestia Settings → Virtual machines** to change:

| Setting | Purpose |
| --- | --- |
| System VMs / User session VMs | Select `qemu:///system` and/or `qemu:///session` |
| Refresh interval | Read statistics every 1–60 seconds while the tab or its settings page is visible |
| Startup indicator | How long to show “Starting up” after an observed start; 0 disables the timed indicator |
| ARP address fallback | Check host ARP data when libvirt DHCP leases provide no address |
| SSH username, port, timeout, identity file | Default client connection settings |
| Per-VM SSH settings | Override host, username, port, timeout and identity file for individual VMs |

Empty per-VM text fields inherit defaults; port/timeout `0` inherit the corresponding default. With no saved username, SSH prompts in the terminal. A configured SSH port changes the **client's destination port**, not the guest's SSH daemon.

Settings save automatically. Monitoring preferences apply on the next polling cycle; SSH preferences apply on the next connection. The native settings page uses Caelestia's existing layout and controls, without a separate settings application.

## Kubernetes setup

1. Install a version of `kubectl` compatible with your cluster on the desktop host. The installer does not install packages; Kubernetes is an optional dependency.
2. Obtain a trusted kubeconfig for a reachable, initialized cluster. Its API address must be reachable from this host and match its certificate. Store credentials in the kubeconfig or its referenced files, not in dashboard settings.
3. Open **Caelestia Settings → Kubernetes**. Enter the kubeconfig path, or leave it empty to use `KUBECONFIG` / `~/.kube/config`. Click **Refresh contexts**, select a context explicitly, and enable monitoring.
4. Open the **Kubernetes** dashboard tab. Refresh defaults to 10 seconds and can be set to 5–60 seconds.

The selection never changes kubectl's current context. Changing kubeconfig clears the context selection; changing context clears the previous cluster's cached data. Authentication helpers must work without interactive input; renew expired credentials in a terminal if necessary. An API request has a five-second timeout and the complete kubectl process has an eight-second deadline.

The credential must allow `get`/`list` on core `nodes` and `pods`, and on `apps` `deployments`, `statefulsets` and `daemonsets`, across all namespaces. [examples/kubernetes-reader.yaml](examples/kubernetes-reader.yaml) defines the corresponding ClusterRole. A cluster administrator can create it and bind it to the identity used by your kubeconfig. The dashboard does not create roles, users, tokens or bindings. A standard namespace-scoped `view` binding alone does not provide the required node and cluster-wide access.

Verify access from a terminal, substituting your context and optional kubeconfig:

```sh
kubectl --kubeconfig=/path/to/config --context=lab get nodes
kubectl --kubeconfig=/path/to/config --context=lab get pods --all-namespaces
kubectl --kubeconfig=/path/to/config --context=lab get deployments,statefulsets,daemonsets --all-namespaces
```

See [Kubernetes cluster access](https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/) and [kubectl installation](https://kubernetes.io/docs/tasks/tools/).

### Reading cluster health

| Indicator | Meaning |
| --- | --- |
| API | Whether this host received an API response; reachability does not imply application health |
| Nodes ready | Nodes with `Ready=True` / registered nodes; pressure conditions appear as findings |
| System pods ready | Ready / active, non-terminating pods in `kube-system` |
| Workloads available | Available Deployment/StatefulSet/DaemonSet objects outside `kube-system` / active workload objects; intentionally zero-sized workloads are excluded |
| Findings | Resources with errors, partial availability, pending startup or unknown state; a resource is counted once, but a failing pod and its controller can each appear |

Resources requiring attention appear first. Expand a card to inspect its conditions, replica counts, pod node and container state. The list also includes normal resources, inactive workloads and completed pods. Labels use the shell extension's existing English UI convention.

**No problems detected** requires successful current reads of every resource type, observed system pods, and no problems. Normal rollouts can show **Update in progress**. **Needs attention** includes pending pods or incomplete availability as well as errors; it does not imply the whole cluster is down. A controller generation that has not yet been observed is shown as updating, not as a confirmed failure. OnDelete strategies and StatefulSet partitions do not by themselves indicate failure.

**Verification incomplete** means some checks are unavailable. Each resource type is collected independently: denied pod access does not hide readable nodes. Failed reads retain prior resource cards marked **Stale**, while affected metric totals display a dash. Known findings remain visible. Missing credentials, rejected access and transport failures are reported separately; raw credential-helper diagnostics are never displayed. An unreachable API is not proof that the cluster is powered off.

Historical restart counts alone do not mark healthy pods as failing. Successful jobs and ordinary termination are not problems. System health uses pods and workloads in `kube-system`, including static control-plane mirror pods when present; it does not perform DNS/network probes or verify external services. Deployments, StatefulSets and DaemonSets are the supported application controllers; Job/CronJob and custom-controller status are not aggregated, though their pods are visible.

Only one collector runs across visible Kubernetes tabs/settings pages. Closing them stops collection and any in-flight kubectl processes. No background service, metrics-server, Prometheus, guest agent, role detection or VM/node association is required. This version provides current state, without history, notifications, resource-usage metrics or workload management.

## What the numbers mean

- **Up / total:** VMs currently labeled Up, out of all defined VMs in the connected sources.
- **vCPU / vRAM allocated:** Totals for active VMs, including paused, starting and shutting-down guests. Stopped guests do not contribute.
- **CPU percentage:** Change in libvirt CPU time divided by elapsed time and the VM's vCPU count. 100% means all allocated vCPUs are busy. The first reading shows a dash until a second sample is available.
- **RAM:** Guest used / allocated RAM. Used memory is `available - usable` from existing balloon statistics, accepted only when updated within the last 60 seconds. A dash means those statistics are unavailable or stale. The widget does not enable balloon polling or install guest agents.
- **Host RSS:** Available by hovering over RAM. It is the resident memory of the VM process and is distinct from guest RAM usage.

Libvirt reports hypervisor state, not guest application readiness. **Up**, **Down** and **Shutting down** reflect that state. **Starting up** briefly marks a VM that starts or appears after monitoring has begun, or an active domain whose state is not yet known. Opening the tab on an already running VM does not mark it as starting. **Paused**, **Suspended**, **Crashed** and **Unknown** remain explicit.

References: [libvirt domain statistics](https://libvirt.org/html/libvirt-libvirt-domain.html), [libvirt connection URIs](https://libvirt.org/uri.html).

## Files and architecture

| File or directory | Responsibility |
| --- | --- |
| `backend/vm_monitor.py` | Read-only libvirt connections, CPU sampling, memory statistics, address discovery and lifecycle labels |
| `backend/kube_monitor.py` | Independent read-only kubectl collection, health interpretation, partial results and timeouts |
| `backend/vm_config.py` | Single source for defaults, validation, inheritance and atomic settings writes |
| `backend/ssh_connect.py` | Terminal prompts and argument-based OpenSSH invocation |
| `qml/VmTab.qml`, `qml/VmCard.qml`, `qml/Metric.qml` | Monitoring layout and reusable cards |
| `qml/VmMonitor.qml` | JSON stream, stable VM identifiers, retry handling and process lifetime |
| `qml/VmSettingsPage.qml`, `qml/SshFields.qml` | Native Nexus settings page and shared SSH controls |
| `qml/VmPreferences.qml`, `qml/VmCommands.qml` | Settings persistence bridge and shared Python command construction |
| `qml/KubeMonitor.qml`, `qml/KubeActivity.qml` | Shared Kubernetes collector and visibility-based process lifetime |
| `qml/KubeTab.qml`, `qml/KubeCard.qml`, `qml/KubeSettingsPage.qml` | Cluster overview, expandable resource details and native Kubernetes settings |
| `scripts/setup.py` | Version-checked, repeatable overlay installation and removal |
| `tests/` | Measurement, connection, configuration, installer and GUI checks |

The installer creates a user-owned overlay under `~/.config/quickshell/caelestia/`. Unchanged files link to your installed Caelestia source. It makes three small adaptations in the overlay:

1. `modules/dashboard/Content.qml` registers the VMs and Kubernetes tabs.
2. `modules/nexus/PageRegistry.qml` registers their settings navigation entries.
3. `modules/nexus/PageCompRegistry.qml` registers their page components.

The overlay also contains a real copy of `shell.qml`, because Quickshell resolves a symlinked entry point to its original location. Extension files are copied into `modules/dashboard/vms/`, so moving the source repository does not break the installed tab.

When you first edit a setting, it is stored in `~/.config/caelestia/vm-dashboard.json` (respecting `XDG_CONFIG_HOME`). Per-VM profiles are keyed by connection URI plus UUID, so duplicate VM names and renames do not mix up profiles. `config.example.json` shows the defaults; copying it is optional.

No Cockpit, libvirt, QEMU, guest, network or systemd configuration is changed. The monitor opens libvirt with `openReadOnly`, prevents automatic spawning of session daemons with `LIBVIRT_AUTOSTART=0`, and uses existing DHCP/ARP information. It is a child process of the visible UI, not an installed service. See [libvirt's connection API](https://libvirt.gitlab.io/libvirt/html/libvirt-libvirt-host.html#virConnectOpen).

## Update and remove

After changing this repository or upgrading Caelestia, run:

```sh
./setup.sh install --restart
```

This rebuilds the adaptations from the currently installed upstream files. If an integration point has changed, setup fails before replacing the working overlay. Edit this repository and reinstall, rather than editing generated files.

To return to the packaged Caelestia shell:

```sh
./setup.sh uninstall --restart
```

Setup refuses to overwrite an unmanaged user configuration, or update/remove managed files that have local edits. It tracks generated files with `.vm-dashboard-install.json`. Settings are retained on uninstall so connection profiles survive reinstalling. `--restart` restarts only Caelestia; omit it to restart the desktop shell yourself later.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Use **Qt 6** `qmlformat` for syntax checks; an unversioned `qmlformat` command may select Qt 5 on some systems:

```sh
for qml_file in qml/*.qml; do
    /usr/lib/qt6/bin/qmlformat -n "$qml_file" >/dev/null || exit 1
done
```

The VM implementation was verified with live CPU/RAM/address reads from two KVM guests and SSH identity checks on both guests. `tests/smoke.qml` checks live delegate stability, CPU refresh and SSH gating. `tests/settings-smoke.qml` renders the native Nexus page and verifies that edits persist; run it only with an isolated `XDG_CONFIG_HOME`, since it writes test preferences.

Kubernetes tests cover health semantics, generation changes, partial permissions, stale-data recovery, context changes, read-only subprocess arguments, timeouts and process termination. A GUI check runs against deterministic fake kubectl responses in a temporary overlay with isolated configuration, cache and state:

```sh
python3 -B tests/run-kubernetes-smoke.py --preview-dir /tmp/caelestia-kubernetes-preview
```

Run it from a graphical session. It verifies both native pages, expanded-card stability, degraded/partial/unreachable states, saved settings and collector lifetime; no real cluster is contacted. Preview images and the QML log are saved in the requested directory. Live Kubernetes validation additionally requires a configured reachable cluster.

GUI checks were run against a temporary overlay under `/tmp`; state-transition checks used fixtures without stopping the real VMs. Settings tests also used temporary configuration files. No guest passwords are included in this repository.

The project can be committed and pushed to your own GitHub repository. It contains the extension and adapter rather than a vendored copy of Caelestia. License: GPL-3.0; see `LICENSE`.
