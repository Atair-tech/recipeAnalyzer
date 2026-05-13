import { useEffect, useState } from "react";

function isTauriRuntime() {
  return Boolean(
    typeof window !== "undefined" &&
      (window.__TAURI_INTERNALS__ ||
        window.location.protocol === "tauri:" ||
        window.location.hostname === "tauri.localhost")
  );
}

function formatUpdateNotes(notes) {
  if (!notes) {
    return "";
  }
  if (typeof notes === "string") {
    return notes;
  }
  return JSON.stringify(notes, null, 2);
}

const UPDATE_ENDPOINT = "https://github.com/Atair-tech/recipeAnalyzer/releases/latest/download/latest.json";

function formatUpdateError(fallbackCode, requestError) {
  if (!requestError) {
    return `错误代码：${fallbackCode}\n错误信息：未知错误`;
  }

  if (typeof requestError === "string") {
    return `错误代码：${fallbackCode}\n错误信息：${requestError}\n更新地址：${UPDATE_ENDPOINT}`;
  }

  const errorCode = requestError.code || requestError.name || fallbackCode;
  const details = [
    `错误代码：${errorCode}`,
    `错误信息：${requestError.message || String(requestError)}`,
    `更新地址：${UPDATE_ENDPOINT}`,
  ];

  if (requestError.status) {
    details.push(`HTTP 状态：${requestError.status}`);
  }
  if (requestError.cause) {
    details.push(`底层原因：${requestError.cause?.message || String(requestError.cause)}`);
  }
  if (requestError.stack) {
    details.push(`调试信息：${requestError.stack}`);
  }

  return details.join("\n");
}

export default function SystemSettings() {
  const [desktopRuntime, setDesktopRuntime] = useState(false);
  const [currentVersion, setCurrentVersion] = useState("");
  const [checking, setChecking] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [error, setError] = useState("");
  const [availableUpdate, setAvailableUpdate] = useState(null);

  useEffect(() => {
    let active = true;
    const isDesktop = isTauriRuntime();
    setDesktopRuntime(isDesktop);

    async function loadVersion() {
      if (!isDesktop) {
        return;
      }
      try {
        const { getVersion } = await import("@tauri-apps/api/app");
        const version = await getVersion();
        if (active) {
          setCurrentVersion(version);
        }
      } catch {
        if (active) {
          setCurrentVersion("");
        }
      }
    }

    loadVersion();
    return () => {
      active = false;
    };
  }, []);

  async function handleCheckUpdate() {
    setChecking(true);
    setError("");
    setStatusMessage("");
    setAvailableUpdate(null);

    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const update = await check();
      if (!update) {
        setStatusMessage("当前已经是最新版本。");
        return;
      }
      setAvailableUpdate(update);
      setStatusMessage(`发现新版本 ${update.version}。`);
    } catch (requestError) {
      setError(formatUpdateError("UPDATE_CHECK_FAILED", requestError));
    } finally {
      setChecking(false);
    }
  }

  async function handleInstallUpdate() {
    if (!availableUpdate) {
      return;
    }

    const confirmed = window.confirm(`将下载并安装 ${availableUpdate.version}，安装完成后程序会重启。是否继续？`);
    if (!confirmed) {
      return;
    }

    setInstalling(true);
    setError("");
    setStatusMessage("正在下载并安装更新...");

    try {
      await availableUpdate.downloadAndInstall();
      setStatusMessage("更新安装完成，正在重启...");
      const { relaunch } = await import("@tauri-apps/plugin-process");
      await relaunch();
    } catch (requestError) {
      setError(formatUpdateError("UPDATE_INSTALL_FAILED", requestError));
    } finally {
      setInstalling(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">System</p>
          <h2>系统设置</h2>
        </div>
      </div>

      {error ? <pre className="error-banner update-error-detail">{error}</pre> : null}
      {statusMessage ? <div className="success-banner">{statusMessage}</div> : null}

      <div className="settings-grid">
        <div className="settings-row">
          <div>
            <h3>软件更新</h3>
            <p>
              {desktopRuntime
                ? `当前版本：${currentVersion || "读取中"}`
                : "在线更新只在安装版 exe 中可用。"}
            </p>
          </div>
          <div className="action-row">
            <button
              type="button"
              className="action-button secondary"
              onClick={handleCheckUpdate}
              disabled={!desktopRuntime || checking || installing}
            >
              {checking ? "检查中..." : "检查更新"}
            </button>
            {availableUpdate ? (
              <button
                type="button"
                className="action-button"
                onClick={handleInstallUpdate}
                disabled={installing}
              >
                {installing ? "安装中..." : "下载并安装"}
              </button>
            ) : null}
          </div>
        </div>

        {availableUpdate ? (
          <div className="settings-update-detail">
            <div>
              <span>最新版本</span>
              <strong>{availableUpdate.version}</strong>
            </div>
            {availableUpdate.date ? (
              <div>
                <span>发布时间</span>
                <strong>{availableUpdate.date}</strong>
              </div>
            ) : null}
            {availableUpdate.body ? (
              <pre>{formatUpdateNotes(availableUpdate.body)}</pre>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
