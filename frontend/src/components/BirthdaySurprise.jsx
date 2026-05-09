import { useEffect, useRef, useState } from "react";

const VIDEO_SRC = "/resource/birthDayVid.mp4";
export default function BirthdaySurprise() {
  const [phase, setPhase] = useState("white");
  const [playBlocked, setPlayBlocked] = useState(false);
  const videoRef = useRef(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPhase("video");
    }, 2000);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (phase !== "video" || !videoRef.current) {
      return;
    }

    const playPromise = videoRef.current.play();
    if (playPromise && typeof playPromise.catch === "function") {
      playPromise.catch(() => {
        setPlayBlocked(true);
      });
    }
  }, [phase]);

  function openMainProgram() {
    try {
      window.sessionStorage.setItem("recipeAnalyzer.forceStartupGate", "1");
      window.localStorage.removeItem("recipeAnalyzer.startupGateDisabled");
    } catch {
      // Ignore storage failures; navigation still opens the main program.
    }
    window.location.hash = "";
  }

  function handleScreenClick() {
    if (phase === "done") {
      openMainProgram();
      return;
    }
    if (phase === "video" && playBlocked && videoRef.current) {
      setPlayBlocked(false);
      videoRef.current.play().catch(() => setPlayBlocked(true));
    }
  }

  return (
    <main className="birthday-page" onClick={handleScreenClick}>
      {phase === "white" ? <div className="birthday-white-screen" /> : null}

      {phase === "video" || phase === "done" ? (
        <div className="birthday-video-stage">
          <video
            ref={videoRef}
            className="birthday-video"
            src={VIDEO_SRC}
            muted
            autoPlay
            playsInline
            onEnded={openMainProgram}
          />
          {playBlocked ? (
            <button type="button" className="birthday-click-layer">
              点击继续
            </button>
          ) : null}
          {phase === "done" ? <div className="birthday-click-layer">点击继续</div> : null}
        </div>
      ) : null}

    </main>
  );
}
