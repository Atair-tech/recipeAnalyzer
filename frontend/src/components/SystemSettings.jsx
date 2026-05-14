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
const DEFAULT_UPDATE_PROXY = "http://127.0.0.1:7890";
const UPDATE_CHECK_TIMEOUT_MS = 30000;
const UPDATE_DOWNLOAD_TIMEOUT_MS = 180000;

function getUpdateAssetUrl(update) {
  const platforms = update?.rawJson?.platforms;
  const platform = platforms?.["windows-x86_64"] || platforms?.["windows-x86_64-msvc"];
  return typeof platform?.url === "string" ? platform.url : "";
}

function formatUpdateError(fallbackCode, requestError, extraDetails = []) {
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
    ...extraDetails.filter(Boolean),
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
  const [updateProxy, setUpdateProxy] = useState(() => {
    try {
      return window.localStorage.getItem("recipeAnalyzer.updateProxy") || DEFAULT_UPDATE_PROXY;
    } catch {
      return DEFAULT_UPDATE_PROXY;
    }
  });
  const [preflightMessage, setPreflightMessage] = useState("");
  const [downloadProgress, setDownloadProgress] = useState(null);

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

  function getUpdateOptions() {
    const proxy = updateProxy.trim();
    return {
      timeout: UPDATE_CHECK_TIMEOUT_MS,
      ...(proxy ? { proxy } : {})
    };
  }

  function getDownloadOptions() {
    const proxy = updateProxy.trim();
    return {
      timeout: UPDATE_DOWNLOAD_TIMEOUT_MS,
      ...(proxy ? { proxy } : {})
    };
  }

  async function runPreflight() {
    setPreflightMessage("正在预检 GitHub 更新清单...");
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), UPDATE_CHECK_TIMEOUT_MS);
    try {
      const response = await fetch(`${UPDATE_ENDPOINT}?t=${Date.now()}`, {
        cache: "no-store",
        signal: controller.signal
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status} ${response.statusText}`);
      }
      const payload = await response.json();
      setPreflightMessage(`GitHub 预检成功：latest.json 版本 ${payload.version || "未知"}`);
    } catch (requestError) {
      setPreflightMessage(
        `GitHub 预检失败：${requestError?.name === "AbortError" ? "请求超时" : requestError?.message || String(requestError)}`
      );
    } finally {
      window.clearTimeout(timeoutId);
    }
  }

  async function handleCheckUpdate() {
    setChecking(true);
    setError("");
    setStatusMessage("");
    setAvailableUpdate(null);
    setDownloadProgress(null);

    try {
      window.localStorage.setItem("recipeAnalyzer.updateProxy", updateProxy.trim());
    } catch {
      // Ignore storage failures; the current input still applies.
    }

    await runPreflight();

    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const update = await check(getUpdateOptions());
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
    setDownloadProgress(null);

    try {
      let totalBytes = null;
      let receivedBytes = 0;
      await availableUpdate.downloadAndInstall((event) => {
        if (event.event === "Started") {
          totalBytes = event.data.contentLength || null;
          receivedBytes = 0;
          setDownloadProgress({ totalBytes, receivedBytes, finished: false });
          setStatusMessage(
            totalBytes
              ? `开始下载更新包，大小 ${(totalBytes / 1024 / 1024).toFixed(1)} MB。`
              : "开始下载更新包。"
          );
        } else if (event.event === "Progress") {
          receivedBytes += event.data.chunkLength;
          setDownloadProgress({ totalBytes, receivedBytes, finished: false });
        } else if (event.event === "Finished") {
          setDownloadProgress({ totalBytes, receivedBytes, finished: true });
          setStatusMessage("更新包下载完成，正在安装...");
        }
      }, getDownloadOptions());
      setStatusMessage("更新安装完成，正在重启...");
      const { relaunch } = await import("@tauri-apps/plugin-process");
      await relaunch();
    } catch (requestError) {
      setStatusMessage("");
      setError(
        formatUpdateError("UPDATE_INSTALL_FAILED", requestError, [
          `安装包地址：${getUpdateAssetUrl(availableUpdate) || "未能从 latest.json 读取"}`,
          `代理地址：${updateProxy.trim() || "直连"}`,
          `下载超时：${Math.round(UPDATE_DOWNLOAD_TIMEOUT_MS / 1000)} 秒`
        ])
      );
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
            <label className="settings-proxy-field">
              <span>更新代理地址</span>
              <input
                type="text"
                value={updateProxy}
                onChange={(event) => setUpdateProxy(event.target.value)}
                placeholder="例如 http://127.0.0.1:7890；留空则直连"
                disabled={checking || installing}
              />
            </label>
            <p className="settings-update-help">
              Clash 常用 HTTP 代理为 http://127.0.0.1:7890；如果端口不同，请按 Clash 设置修改。
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

        {preflightMessage ? <div className="settings-update-detail">{preflightMessage}</div> : null}

        {downloadProgress ? (
          <div className="settings-update-detail">
            <div>
              <span>下载进度</span>
              <strong>
                {downloadProgress.totalBytes
                  ? `${((downloadProgress.receivedBytes / downloadProgress.totalBytes) * 100).toFixed(1)}%`
                  : `${(downloadProgress.receivedBytes / 1024 / 1024).toFixed(1)} MB`}
                {downloadProgress.finished ? "，已完成" : ""}
              </strong>
            </div>
          </div>
        ) : null}

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
