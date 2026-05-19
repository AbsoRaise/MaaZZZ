# MaaFramework Win32 Controller Design

## Scope

Connect the desktop app to the PC version of Zenless Zone Zero through MaaFramework's Win32 controller. ADB and mobile/emulator support are out of scope for this pass.

## Architecture

The backend keeps `MaaScanner` as the integration boundary. `MaaFrameworkRuntime` owns the MaaFramework `Win32Controller`, `Resource`, and `Tasker` lifecycle. The desktop API exposes a lightweight connection test so the app can verify the game window and Maa runtime before running a scan task.

The scan profile remains the user-editable runtime configuration. It enables Maa, matches the game window title, selects Win32 screenshot and input methods, and names the Maa pipeline entry.

## Data Flow

1. The user opens the PC game window.
2. The backend loads `assets/resource/config/scan_profile.json`.
3. `MaaFrameworkRuntime` finds a window matching the configured title/class regex, or uses an explicit hwnd if provided.
4. The runtime creates a Win32 controller, posts the connection, loads `assets/resource`, and initializes a Tasker.
5. A scan task runs the configured pipeline and reads `assets/resource/output/latest_scan.json`.

## Error Handling

If the game window is not found, the backend returns a clear message that includes the expected title regex. If MaaFramework is not installed, the import error points at the missing runtime dependency. If Tasker initialization fails, the connection test reports the controller configuration used so screenshot/input methods can be adjusted.

## Testing

Use Python 3.13.13 for backend checks. Verify package imports, then run a connection test against the live `ZenlessZoneZero` window. Existing tests should continue to pass with Maa disabled or with injected runtimes.
