// Glowsky desktop shell. The web UI (Vite/React) is rendered in the system webview;
// the chemistry/agent backend is the FastAPI server the UI talks to over HTTP.

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .run(tauri::generate_context!())
        .expect("error while running Glowsky");
}
