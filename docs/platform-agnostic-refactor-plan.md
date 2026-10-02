# Platform-Agnostic Refactor Review and Plan

## Scope

This review covers commit `871ac15c2b576beac7901558ce7f96d13a879a30`, with particular attention to:

- platform checks and Windows-only imports;
- platform-specific features such as elevation, game termination, GPU checks,
  scheduling, notifications, overlays, and global hotkeys;
- the new Wayland/wlroots capture and input implementation;
- protocol generation, compatibility, packaging, and tests.

The intended product boundary should be stated precisely: this application can be
platform agnostic, but individual capabilities and backends do not have to be.
Linux should load only the features it can actually provide. Unsupported features
should be absent or visibly unavailable, not represented by inert classes, `None`
exports, false success, or functions that silently return.

## Executive assessment

The commit is not yet a platform-agnostic implementation. It adds a second set of
platform branches throughout code that was structured around Windows assumptions.
This produces three recurring failure modes:

1. The core application imports platform implementations directly and decides which
   one to use with `sys.platform` checks.
2. Unsupported operations are represented by no-ops, `None`, or misleading fallback
   values instead of being excluded through capability discovery.
3. The Wayland implementation exposes a complete-looking device even when only part
   of its required protocol set is available, and several protocol details are not
   handled correctly.

The first release priority should be correctness and honest feature availability,
not expanding Linux coverage. The current wlroots backend should be explicitly
experimental and gated until the connection, output, input, and frame lifecycle
issues below are fixed.

## Findings

### 1. Platform checks and import structure

#### 1.1 Module-level `ImportError` guards are the wrong boundary

Twelve implementation modules now begin by inspecting `sys.platform` and raising
`ImportError`. Examples include Windows capture implementations, Windows interaction
implementations, emulator helpers, and GPU settings.

This does not make the implementation safer. It makes every importer responsible
for knowing which imports can fail, encourages broad `try/except` blocks, and makes
the public import surface change type between platforms.

The correct rule is:

- platform-specific leaf modules may freely import their native dependencies;
- only a backend loader imports those leaf modules;
- the loader is the one permitted place that probes the host and dependencies;
- core modules depend on interfaces and capability records, never concrete Windows
  modules.

Once imports follow this rule, the leaf guards can simply be deleted. Linux never
imports a Windows backend, and Windows never imports a wlroots backend unless it is
explicitly requested for testing.

#### 1.2 Conditional exports and `None` sentinels create unstable APIs

The capture and interaction package initializers conditionally import classes and
assign unavailable symbols to `None`. Code such as `from ok import
PostMessageInteraction` can therefore succeed while returning something that is not
a class. The error is delayed until a distant call site and type checking cannot
describe the API accurately.

Do not export optional implementations from the core package. Export contracts,
identifiers, availability results, and registry APIs. A registry lookup should
either return a factory or a structured unavailable result.

#### 1.3 Platform decisions are scattered through orchestration and UI

The current tree contains about 116 direct platform checks across 42 application
files, excluding third-party/generated/resources code. Roughly 88 were added by this
commit. `DeviceManager` alone contains many branches mixing device family, operating
system, capture implementation, and interaction implementation.

This means adding macOS, X11, a portal backend, or even a second Wayland backend
requires editing unrelated orchestration and UI files. It also causes inconsistent
decisions: some code treats all non-Windows platforms as Linux, while other code
only special-cases the literal `linux` value and consequently treats macOS as
Windows.

Platform detection should occur inside backend probes. The rest of the application
should ask questions such as “is elevation available?”, “which capture providers are
available?”, or “can this target be terminated?”

#### 1.4 Broad exception handling hides broken installations and programming errors

Backend imports and device discovery often catch `Exception` and continue. A missing
optional dependency, an unsupported protocol version, a permission failure, and a
bug in application code are consequently reported in the same way: the feature
silently disappears or a later operation returns `None`.

Use an availability result with a stable status and diagnostic detail:

```python
class AvailabilityStatus(Enum):
    AVAILABLE = "available"
    UNSUPPORTED_PLATFORM = "unsupported_platform"
    MISSING_DEPENDENCY = "missing_dependency"
    PERMISSION_DENIED = "permission_denied"
    PROTOCOL_MISMATCH = "protocol_mismatch"
    INITIALIZATION_FAILED = "initialization_failed"
```

Expected probe failures should be converted to one of these results. Unexpected
exceptions should retain a traceback and fail the relevant backend initialization.

### 2. Windows-only features

#### 2.1 Elevation currently lies about capability

`is_admin()` returns `True` on non-Windows. Other process helpers return without
doing anything. A successful boolean in this situation does not mean “not
applicable”; it means the caller is incorrectly told the requested capability is
available.

Introduce an optional `PrivilegeService`. Windows registers one with `is_elevated()`
and `restart_elevated()`. Linux registers nothing unless a real, intentionally
supported implementation is later added. The restart-as-admin action and setting
must be created only when that service exists.

#### 2.2 Automatic game termination is a target capability, not an OS branch

`stop_hwnd()` does nothing on Linux, but the exit-after-task flow can still call it,
wait, and quit the application as though the game were closed. Hiding one checkbox
does not make the underlying workflow correct, especially for CLI/config-driven
execution.

Move termination to the connected target/driver:

```python
class TargetSession(Protocol):
    capabilities: frozenset[Capability]

    def close_target(self) -> OperationResult: ...
```

Only expose “close game after task” when `CLOSE_TARGET` is present. A request from a
saved config or CLI on a session without that capability should fail validation with
a clear message. It must not sleep and report success.

#### 2.3 GPU post-processing checks belong in optional lifecycle hooks

`check_gpu_driver_post_processing()` is guarded both by its caller and internally.
The method should not exist in the platform-neutral start controller.

Define a lifecycle-hook collection, for example `post_start_checks`. The Windows
backend registers the NVIDIA/driver check; other backends register no such hook.
The start controller simply runs the registered checks. This removes the platform
condition from both the caller and the implementation.

#### 2.4 Sleep prevention, hotkeys, overlays, scheduling, and notifications use no-op objects

Several Windows implementations remain importable or constructible on Linux and
then silently do nothing:

- sleep prevention;
- global hotkeys;
- Win32 GDI overlay;
- Windows Task Scheduler integration;
- Windows system notifications;
- QQ/WeChat integration;
- Windows-only file/process helpers.

These should be optional services registered by a backend. UI sections and actions
should be contributed by the service or conditioned on its declared capability,
not on `sys.platform`.

An unavailable optional feature may be completely hidden, or displayed disabled
with the availability reason. It should never be an apparently enabled no-op.

#### 2.5 Windows abstractions leak into core types

`HwndWindow`, Win32 capture bases, `is_valid_hwnd`, resize logic, and handles are used
from otherwise generic orchestration. On non-Windows, `is_valid_hwnd` can accept any
non-zero integer, which gives a false meaning to a Windows-specific concept.

Replace these with neutral domain objects such as `CaptureTarget`, `TargetSession`,
and `TargetId`. Windows may attach an HWND in backend-owned metadata, but core code
must not use it to define target validity.

#### 2.6 Browser capture is duplicated and still Windows-shaped

The browser module conditionally defines an entire `BrowserWGC` class, and the new
`browser_wgc.py` contains a duplicate that is not imported. The nominal browser
backend still depends on Windows Graphics Capture availability.

Split browser automation/session discovery from capture transport. Register a
`browser-wgc` capture provider only from the Windows backend. If Linux browser
capture is wanted, implement and register a separate provider using a supported
cross-platform mechanism; do not make WGC appear portable through conditional class
definitions.

#### 2.7 Host-dependent configuration mutation can destroy settings

Linux removes Windows-only options from the default schema. The generic config
verification code then removes unknown persisted keys. Opening a configuration on
Linux can therefore erase Windows-specific settings that the same user needs later
on Windows.

Persist a superset schema or backend-namespaced settings. Capability filtering
controls presentation and validation for the current session; it must not delete
values owned by an unavailable backend. Add a round-trip test that opens and saves a
Windows-created configuration on Linux and verifies that Windows values survive.

### 3. Wayland/wlroots implementation

#### 3.1 The discovered Wayland device does not pass the connected-device path

`DeviceManager.device_connected()` recognizes Windows and browser paths but allows
the new Wayland device to fall into the ADB connection path. It may attempt
`adb_connect("wayland-N")`, so start validation fails even after Wayland discovery.

This is an immediate release blocker. A Wayland session must be represented by its
own device driver and connection state; it must never be inferred from string
prefixes or fall through to ADB behavior.

#### 3.2 Discovery validates capture but not advertised input capabilities

Availability currently requires screencopy, shared memory, a seat, and an output.
Virtual pointer and virtual keyboard globals are optional. Nevertheless, the UI
always advertises the wlroots interaction method, and `clickable()` always returns
`True`. Missing managers lead to silent no-ops while task operations report success.

Capture, pointer input, keyboard input, and text input must be separate capabilities.
Task validation must compute its requirements and reject a session that lacks any
required capability before starting. Operations must not report success when no
protocol request was emitted.

#### 3.3 Output and target selection are not modeled correctly

A device corresponds to a Wayland socket, while capture implicitly chooses
`outputs[0]`. It captures an entire compositor output, not a game window, even though
the surrounding UI and configuration describe a window target. On a normal desktop,
this can capture and control the wrong display.

The initial backend should require explicit output selection and display that output
identity to the user. For safety, consider limiting the experimental backend to a
dedicated or nested compositor/output until coordinate mapping is robust. Do not
present it as window capture.

#### 3.4 Absolute pointer coordinates are incorrect for multi-output layouts

The code creates a virtual pointer associated with a seat but not an explicit output,
while absolute coordinates are based on the first output's dimensions. It does not
account for output origin, scale, transform, rotation, or layout. Multi-monitor and
rotated/scaled arrangements can therefore click the wrong location.

Use the protocol request that binds the virtual pointer to the selected output where
available, and define a tested transformation from captured pixel coordinates to
the protocol's absolute coordinate space. Until then, disable absolute interaction
for layouts that cannot be proven safe.

#### 3.5 Screencopy frame flags and formats are incomplete

The implementation does not process the `y_invert` frame flag, so frames from some
compositors can be vertically inverted. It assumes a shared-memory buffer will be
announced and does not handle the DMA-BUF-only case. Reallocation checks dimensions
but not all format changes. Pixel-format handling is incomplete and partly relies on
magic numeric values.

Represent advertised buffer choices explicitly, select only a supported path, and
return a protocol/capture availability reason when no usable format exists. Handle
all supported wl_shm formats by named enum and apply frame transformation flags.

#### 3.6 Frame failure and timeout leak resources and add avoidable delay

The failure callback destroys the frame but does not set a terminal state, so the
capture loop waits for its timeout. Timeout and some error paths do not reliably
destroy the frame proxy. Repeated failures can leak resources and stall every frame
for approximately two seconds.

Use one frame-state object with exactly one terminal transition: ready, failed,
cancelled, or timed out. Every terminal path must release the frame and any temporary
buffer ownership in `finally`-style cleanup.

#### 3.7 Wayland dispatch and connection ownership are not serialized consistently

Capture dispatches the display directly while interaction uses a connection lock.
Disconnect and multiple consumers can race with both. The connection singleton also
has no clear reference ownership, so one consumer may tear down a connection another
is using.

Prefer one event-dispatch owner per connection, with requests queued onto that
owner. If a simpler synchronous implementation remains temporarily, all dispatch,
roundtrip, request, and disconnect operations must share the same lifecycle lock and
reference ownership rules.

#### 3.8 Scroll units are multiplied incorrectly

The interaction code multiplies scroll values by 256 before passing them to a
generated method whose fixed-point conversion is already handled by the protocol
binding. This produces an approximately 256-times scale error. It also omits axis
source, discrete steps, and stop events.

Normalize application scroll units once, then let the binding encode the fixed-point
value. Add an exact request-level test for positive and negative wheel input.

#### 3.9 Wayland event timestamps overflow

Monotonic milliseconds are sent to a protocol field represented as an unsigned
32-bit value without wrapping. Systems with sufficient uptime can overflow after
about 49.7 days.

Convert timestamps using `milliseconds & 0xFFFFFFFF` and test the rollover boundary.

#### 3.10 `_init_keymap` is hardcoded, incomplete, and semantically disconnected

The large embedded QWERTY keymap is difficult to audit and cannot correctly reflect
the user's layout. Task keys include punctuation, keypad aliases, and names such as
`command`, while the evdev conversion often constructs `KEY_<UPPERCASE>` and cannot
resolve those values. Modifier state is not sent, text input is not implemented, and
missing keyboard capability can still result in reported success.

Replace `_init_keymap` with a dedicated keymap provider:

- build a keymap with libxkbcommon from locale/layout settings, or obtain an
  explicitly selected layout;
- serialize the generated XKB keymap to a sealed temporary file/memfd for the
  virtual-keyboard request;
- centralize logical-key to evdev-keycode mappings, including keypad and punctuation;
- model modifiers and text input separately from physical key presses;
- validate every task-supported key in table-driven tests;
- track pressed keys/buttons and release them during cancellation and teardown.

If xkbcommon is not installed, keyboard input should be unavailable with a missing
dependency reason. It should not fall back to an unverified embedded map.

#### 3.11 Socket selection is heuristic and can select the wrong compositor

The scanner enumerates `wayland-*`, chooses the highest numeric suffix, and invents
`wayland-0` when no socket exists. It does not prioritize the active
`WAYLAND_DISPLAY` strongly enough. The highest suffix has no semantic relationship
to the user's session, and Linux may be running X11 or a non-wlroots compositor.

Probe in this order:

1. an explicitly configured socket/output;
2. `WAYLAND_DISPLAY` under the validated runtime directory;
3. other sockets, shown as explicit choices rather than silently selecting one.

Do not create a candidate for a nonexistent socket. Treat Wayland, wlroots, X11,
portal capture, and headless execution as distinct backend probes rather than
equating Linux with wlroots.

#### 3.12 Cleanup can leave input state stuck

Pressed keys and pointer buttons are not comprehensively tracked and released during
shutdown. Cleanup exceptions may also prevent later resources, including the keymap
file descriptor, from closing.

Make teardown idempotent, isolate cleanup errors per resource, release pressed input
state first, and verify file descriptors and proxies with repeated connect/cancel/
disconnect tests.

### 4. Protocol generation, versions, and packaging

#### 4.1 Generated bindings are committed without a reproducible source manifest

The commit adds a large generated protocol tree, including a duplicate generated
copy of core Wayland interfaces, but it does not add a generator command, pinned
scanner version, source URL/commit, checksum manifest, or CI regeneration check.
Reviewers cannot reliably determine whether the generated output matches its XML or
which upstream revision was used.

There are two defensible policies:

- source repository stores XML, source lock, and generator; wheel contains generated
  bindings; or
- source repository stores generated bindings as well, but CI regenerates and fails
  on a diff.

Runtime generation should not be used. It would impose scanner/compiler requirements
on end users and make installed behavior depend on the host toolchain.

#### 4.2 Core Wayland interfaces are duplicated and mixed

The connection imports core interfaces from installed `pywayland`, while generated
extension bindings reference locally generated core interface classes. This creates
two sources of truth and exposes the backend to binding identity/version drift.

Generate only the extension protocols against one pinned pywayland core interface
set, or package a fully self-consistent binding set. Do not mix the two approaches.

#### 4.3 Version caps are hardcoded instead of derived from generated interfaces

The registry binding code manually caps screencopy, foreign-toplevel, virtual
pointer, virtual keyboard, seat, and output versions. This can drift from both the
XML and generated Python.

Bind with `min(server_version, generated_interface.version)` and define explicit
minimum versions per operation. Record the negotiated version in the connection's
capability report. Protocol interface version is the compatibility dimension here,
not a guessed wlroots/compositor software version.

#### 4.4 The dependency and package-data policy is inconsistent

`pywayland` is made a broad Linux dependency even though only the optional direct
wlroots backend needs it. XML inclusion is not clearly declared as package data, and
the build system is not configured to generate bindings from XML. Windows-only
dependencies such as the Direct3D capture package also need explicit environment
markers or backend extras.

Recommended package boundaries:

- `ok-script`: contracts, orchestration, UI, and portable features;
- Windows dependencies in a `windows` extra or platform markers;
- direct Wayland dependencies in a `wlroots` extra initially;
- preferably, a separately versioned `ok-script-wlroots` backend package discovered
  through an entry point.

The wlroots package should own its protocol XML manifest, generator, generated wheel
contents, dependency bounds, and compositor integration tests. Splitting the package
also prevents the base application's wheel from carrying a large protocol forest
that most installations never use.

#### 4.5 Legacy wlroots protocols should not define the permanent Linux architecture

Protocol availability depends on compositor-exposed globals. A backend registry can
support a direct wlroots implementation now while later adding standardized Wayland
capture/input paths as separate providers. The project should not call the direct
backend simply “Linux” or “Wayland.” Upstream wlr-protocols has moved toward
standardization in wayland-protocols, so the architecture must allow parallel or
replacement providers rather than embedding legacy protocol assumptions in core.

### 5. Tests, CI, and release quality

#### 5.1 Current tests exercise object mechanics but not backend correctness

The new tests cover some socket selection and object recreation, but not the
highest-risk behavior:

- Wayland device connection through `DeviceManager`;
- partial protocol availability;
- protocol versions 1/2/3;
- frame ready, failed, timeout, and cancellation lifecycle;
- `y_invert` and pixel formats;
- DMA-BUF-only advertisement;
- multiple outputs, scale, rotation, and coordinate mapping;
- pointer/scroll request values;
- the complete supported-key mapping and modifiers;
- pressed-input cleanup;
- concurrent dispatch/disconnect;
- real compositor integration.

#### 5.2 Linux test collection still includes unconditional Windows imports

Some tests import Windows notification and graphics-capture modules directly. In a
fully provisioned Linux environment this can fail during test collection. Platform
implementation tests should be marked and collected only in their platform job;
contract tests should run everywhere against fake backends.

#### 5.3 No cross-platform CI protects the new contract

Add at minimum:

- Linux: core/minimal dependency import and unit tests;
- Linux: wlroots extra unit tests and package-build inspection;
- Linux: headless/nested compositor integration test when feasible;
- Windows: existing capture/input behavior and Windows services;
- all: config round-trip, registry contract tests, static typing/linting, wheel and
  sdist content checks;
- generated protocol regeneration check in the wlroots package.

#### 5.4 The commit combines unrelated changes

The commit mixes the platform port with operation screenshot/logging, headless-exit
behavior, update/build changes, and other refactors. This makes review, regression
isolation, and rollback unnecessarily difficult. The unused duplicate
`browser_wgc.py` is a concrete symptom.

If history can still be changed, split the work into reviewable commits: contracts,
Windows extraction, capability-driven UI/config, wlroots package/generation,
wlroots capture, wlroots input, tests, and unrelated features. If history cannot be
changed, use that division for subsequent corrective commits.

Operation capture logging should also receive a separate privacy/security review,
because screenshots may contain user-sensitive content even when the feature is
disabled by default.

### 6. Smaller correctness and maintainability issues

- Capture identifiers use inconsistent casing (`Wlroots` versus `wlroots`) and
  device type is inferred from string prefixes. Use stable enums/string IDs owned by
  registered providers.
- Capture creation catches errors and returns `None`, discarding actionable failure
  reasons. Return a typed result or raise a backend initialization error.
- Start behavior returns early for all Linux hosts rather than evaluating session
  capabilities. This skips readiness behavior unrelated to Windows.
- Font discovery checks broad directories but may miss recursively installed Linux
  fonts. Use fontconfig/Qt font discovery or a known bundled fallback.
- Default capture settings can remain Windows-oriented on Linux. Defaults should be
  selected from currently available providers without mutating persisted settings.
- DirectML, Windows Graphics Capture, and similar availability functions should
  always return a real boolean/result, not `None` in one branch.
- Public comments and UI copy call the new backend Wayland/window capture even though
  it is specifically wlroots output capture. Names should describe the real scope.

## Target architecture

### Core contracts

Suggested layout:

```text
ok/
  backends/
    contracts.py
    registry.py
    adb/
    browser/
    windows/
      backend.py
      capture.py
      interaction.py
      window.py
      process.py
      privilege.py
      gpu.py
      scheduler.py
      notifications.py
      overlay.py
```

The direct wlroots backend can start in-tree under `ok/backends/wlroots/` while the
contract stabilizes, then move to its own package without changing core consumers.

Each backend exports one lightweight descriptor/factory. A descriptor may expose:

```python
@dataclass(frozen=True)
class BackendDescriptor:
    id: str
    display_name: str
    capabilities: frozenset[Capability]
    availability: Availability
    device_driver_factory: Callable[[], DeviceDriver]
    optional_services: Mapping[ServiceId, ServiceFactory]
```

The core knows `DeviceDriver`, `TargetSession`, `CaptureProvider`,
`InteractionProvider`, lifecycle hooks, and optional service contracts. It does not
know HWNDs, wlroots globals, ADB serial parsing, or native dependency names.

### Registration and loading

Use built-in descriptors for core-shipped backends and Python entry points for
external backends, for example:

```toml
[project.entry-points."ok_script.backends"]
wlroots = "ok_script_wlroots:backend_descriptor"
```

The loader may use a small platform hint to avoid importing obviously incompatible
built-ins. That is the sole acceptable platform switch. The definitive answer still
comes from each backend's probe, because OS name alone cannot establish protocol,
permission, session, or dependency availability.

### Capability-driven UI and configuration

The UI asks the registry for available capture and interaction providers. It does
not maintain its own Windows/Linux lists. Optional services contribute actions or
settings only when present.

Keep persisted backend settings namespaced and lossless:

```yaml
backends:
  windows:
    capture: windows_graphics
    close_target_after_task: true
  wlroots:
    socket: wayland-1
    output: DP-1
```

Unavailable settings remain stored but are not active. A migration should translate
the current overloaded `windows` configuration without discarding it.

### Honest operation results

No platform adapter should implement an unsupported operation as `pass`, `return
True`, or a silent early return. Either the capability is absent and validation
prevents the call, or the operation returns a typed failure. Abstract defaults
should raise `NotImplementedError` during development so accidental calls are found
immediately.

## Implementation plan

### Phase 0 — Stabilize scope and capture current behavior

1. Mark direct wlroots support experimental in UI/config.
2. Separate unrelated changes into later commits where practical.
3. Add characterization tests for Windows device selection, capture choice,
   interaction choice, elevation visibility, exit-after-task, and config round-trip.
4. Add Linux tests that prove unsupported Windows services are absent rather than
   successful no-ops.

Exit criterion: existing Windows behavior is covered before structural movement.

### Phase 1 — Fix or gate immediate wlroots correctness defects

1. Give Wayland its own device/session connection branch; remove ADB fallthrough.
2. Require explicit socket and output selection for the experimental backend.
3. Report capture, pointer, and keyboard availability independently.
4. Disable task start when its input/capture requirements are not satisfied.
5. Fix frame failure/timeout cleanup, `y_invert`, pixel-format validation, scroll
   units, timestamp wrapping, and teardown input release.
6. Serialize display dispatch and define connection ownership.
7. Disable absolute pointer input on unsupported multi-output/transform layouts until
   coordinate conversion is implemented and tested.

Exit criterion: an exposed operation either works on a declared/tested compositor
configuration or is unavailable with an explicit reason.

### Phase 2 — Introduce contracts and the backend registry

1. Add capability, availability, device driver, target session, capture, interaction,
   and optional-service contracts.
2. Add typed backend identifiers and remove string-prefix inference.
3. Implement a registry that loads built-ins and optional entry-point backends.
4. Create adapters around current Windows, ADB, browser, and wlroots code before
   moving implementations.
5. Add fake-backend contract tests usable on every OS.

Exit criterion: new orchestration code selects providers exclusively through the
registry.

### Phase 3 — Extract Windows implementations

1. Move Win32 window/handle logic, capture, interaction, process/elevation, GPU,
   scheduler, notifications, hotkey, overlay, and sleep-prevention code under the
   Windows backend.
2. Delete module-level platform guards from those leaf modules.
3. Remove `None` exports and inert non-Windows implementations.
4. Split browser session logic from Windows WGC capture and delete the dead duplicate
   implementation.
5. Keep one minimal Windows backend probe responsible for importing native modules
   and explaining dependency failures.

Exit criterion: importing the core package on Linux never imports a Windows-native
module, and Windows leaf modules contain no defensive host checks.

### Phase 4 — Refactor orchestration around sessions and hooks

1. Replace `DeviceManager` platform branches with `DeviceDriver` and
   `TargetSession` operations.
2. Replace start-controller OS checks with backend lifecycle hooks.
3. Move resize, mute, launch, close-target, and readiness behavior to declared
   session capabilities.
4. Make task requirements explicit and validate them once before execution.
5. Remove silent operation fallbacks and preserve structured failure reasons through
   UI and logs.

Exit criterion: `DeviceManager`, `StartController`, and `TaskExecutor` contain no
`sys.platform`/`os.name` branches.

### Phase 5 — Make UI and configuration capability-driven

1. Generate capture and interaction choices from registry descriptors.
2. Register admin, auto-close, scheduler, notification, overlay, hotkey, and GPU
   options only when their services exist.
3. Migrate settings to backend namespaces while preserving unknown/unavailable
   backend data.
4. Replace OS-derived defaults with the first compatible provider or a required
   explicit choice.
5. Show disabled providers with useful reasons where discovery/troubleshooting value
   outweighs hiding them.

Exit criterion: UI/web/config code has no independent platform feature lists and a
cross-platform config round-trip is lossless.

### Phase 6 — Isolate and reproduce protocol bindings

1. Decide the exact XML set needed; remove duplicate core Wayland bindings.
2. Add an upstream source manifest containing repository, commit/tag, file path, and
   checksum for every XML.
3. Pin a compatible pywayland/scanner range and add a deterministic generation
   command.
4. Generate bindings for wheels, and add CI that regenerates and verifies no diff.
5. Move the backend, protocol inputs, and generated wheel outputs into
   `ok-script-wlroots` once the contract is stable.
6. Bind registry globals using generated interface maximums and operation-specific
   minimums; test lower negotiated versions.

Exit criterion: a clean checkout can reproduce the bindings byte-for-byte, the base
package does not ship duplicate protocols, and wheel contents are verified.

### Phase 7 — Harden direct Wayland support

1. Model each output as a selectable target with stable identity.
2. Implement scale/transform/layout-aware capture-to-input coordinates.
3. Add SHM format negotiation and a clearly scoped DMA-BUF path or explicit
   unsupported result.
4. Move Wayland dispatch to one event owner with queued requests and deterministic
   cancellation.
5. Implement the xkbcommon-based keymap provider, modifiers, comprehensive key
   mapping, and pressed-state cleanup.
6. Add nested-compositor integration tests for all declared protocol versions and
   lifecycle failures.

Exit criterion: output capture and input are correct for every configuration the UI
allows the user to select.

### Phase 8 — Expand Linux providers without weakening boundaries

Treat these as separate providers, not conditions inside the wlroots backend:

- direct wlroots output capture/input;
- standardized Wayland image-copy/toplevel protocols as they are available;
- desktop-portal/PipeWire capture;
- an appropriate permission-mediated input provider;
- X11 only if intentionally supported.

Provider composition should permit, for example, portal capture plus a distinct
input provider when both explicitly target the same coordinate space and session.

Exit criterion: “Linux support” is the union of discoverable providers, while every
provider retains an accurate name and capability statement.

### Phase 9 — Release gates and cleanup

1. Run Windows and Linux CI matrices, minimal-import tests, integration tests, and
   package inspection on every change.
2. Audit dependencies into platform markers/extras.
3. Delete obsolete platform helpers and count remaining platform checks.
4. Document the tested compositor/protocol/output matrix and expected permissions.
5. Remove the experimental label only after the integration matrix is green.

Final exit criteria:

- no platform checks outside backend loaders/adapters and narrowly scoped generic
  desktop integration;
- core imports with minimal dependencies on every supported OS;
- unavailable features are absent or carry an actionable reason;
- no unsupported operation reports success;
- Windows behavior has parity with the pre-refactor implementation;
- wlroots capture/input passes real compositor integration tests;
- protocol output is reproducible and packaged only with its backend;
- persisted settings survive moving between platforms.

## Recommended first pull requests

Keep the first changes small enough to review and backport:

1. **Correctness gate:** fix Wayland device connection, capability reporting, frame
   terminal cleanup, scroll units, timestamps, and hide unsafe input configurations.
2. **Contracts:** introduce availability/capability/session contracts plus fake
   contract tests, without moving implementations yet.
3. **Windows backend extraction:** move native modules and remove import guards and
   `None` exports.
4. **Orchestration migration:** convert `DeviceManager` and startup/task services to
   the registry and lifecycle hooks.
5. **Configuration/UI migration:** preserve inactive settings and derive controls
   from capabilities.
6. **Protocol package:** add the manifest/generator/check, remove duplicate core
   bindings, and split the wlroots backend package.
7. **Wayland hardening:** output identity/transforms, frame formats, event ownership,
   and xkbcommon input.

## Review validation performed

- `git diff --check 871ac15^` completed without whitespace errors.
- `python -m compileall -q ok tests` completed successfully.
- importing the top-level `ok` package completed successfully.
- Full tests could not be run in the available checkout because no repository
  `.venv` exists and the fallback interpreter does not have `pytest` installed.
- Runtime import smoke tests for optional modules were also limited by missing
  `PySide6`, `cv2`, and `pywayland`; this reinforces the need for minimal-core and
  per-extra CI environments.

## Protocol references

- PyWayland documents XML-to-Python generation through its scanner:
  <https://github.com/flacjacket/pywayland/blob/main/doc/scanner.rst>
- Wayland protocol versioning treats compatible additions as increasing interface
  versions, which supports negotiated `min(server, generated)` binding:
  <https://github.com/wayland-mirror/wayland-protocols>
- The wlr-protocols project states that protocol development has migrated toward
  freedesktop.org wayland-protocols:
  <https://github.com/swaywm/wlr-protocols/blob/master/README.md>
