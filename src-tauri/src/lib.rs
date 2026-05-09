use std::sync::Mutex;

use tauri::Manager;
use tauri_plugin_shell::{process::CommandChild, ShellExt};

#[cfg(windows)]
use std::{os::windows::process::CommandExt, process::Command};

struct BackendProcess(Mutex<Option<CommandChild>>);

#[cfg(windows)]
fn cleanup_existing_backend_binaries() {
    if std::env::var("RECIPE_ANALYZER_PRESERVE_BACKEND").ok().as_deref() == Some("1") {
        return;
    }

    let Ok(current_exe) = std::env::current_exe() else {
        return;
    };
    let Some(exe_dir) = current_exe.parent() else {
        return;
    };
    let backend_exe = exe_dir.join("recipe-backend.exe");
    if !backend_exe.exists() {
        return;
    }

    let target = backend_exe
        .to_string_lossy()
        .replace('\'', "''");
    let script = format!(
        "$target = '{}'; Get-Process -Name 'recipe-backend' -ErrorAction SilentlyContinue | Where-Object {{ $_.Path -eq $target }} | Stop-Process -Force",
        target
    );

    let _ = Command::new("powershell")
        .args(["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", &script])
        .creation_flags(0x08000000)
        .status();
}

#[cfg(not(windows))]
fn cleanup_existing_backend_binaries() {}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            app.manage(BackendProcess(Mutex::new(None)));

            cleanup_existing_backend_binaries();

            match app.shell().sidecar("recipe-backend") {
                Ok(sidecar) => match sidecar.spawn() {
                    Ok((mut rx, child)) => {
                        {
                            let state = app.state::<BackendProcess>();
                            let mut guard = state.0.lock().expect("backend process lock poisoned");
                            *guard = Some(child);
                        }

                        tauri::async_runtime::spawn(async move {
                            while let Some(event) = rx.recv().await {
                                match event {
                                    tauri_plugin_shell::process::CommandEvent::Stdout(line) => {
                                        println!("[backend] {}", String::from_utf8_lossy(&line));
                                    }
                                    tauri_plugin_shell::process::CommandEvent::Stderr(line) => {
                                        eprintln!("[backend] {}", String::from_utf8_lossy(&line));
                                    }
                                    tauri_plugin_shell::process::CommandEvent::Terminated(payload) => {
                                        eprintln!("[backend] terminated: {:?}", payload);
                                        break;
                                    }
                                    _ => {}
                                }
                            }
                        });
                    }
                    Err(error) => {
                        eprintln!("[backend] failed to spawn sidecar: {error}");
                    }
                },
                Err(error) => {
                    eprintln!("[backend] failed to resolve sidecar: {error}");
                }
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Recipe Analyzer")
        .run(|_app_handle, _event| {});
}
