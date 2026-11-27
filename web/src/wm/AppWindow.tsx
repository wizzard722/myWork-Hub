import { useRef } from "react";
import { api, type AppStatus } from "../api";

/** Inhoud van een app-venster: de eigen gebruikersinterface van de app (iframe) of,
 *  als de app die niet heeft, een korte beschrijving. */
export function AppWindow({ app }: { app: AppStatus | undefined }) {
  const frame = useRef<HTMLIFrameElement>(null);
  if (!app?.manifest) return <p className="muted pad">Deze app is niet beschikbaar.</p>;
  const manifest = app.manifest;

  if (manifest.ui) {
    return (
      <iframe
        ref={frame}
        className="app-frame"
        title={manifest.name}
        src={`/api/apps/${app.id}${manifest.ui}`}
        sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads"
        onLoad={() => {
          // Het token van de gebruiker alleen naar een app op hetzelfde domein sturen.
          frame.current?.contentWindow?.postMessage(
            { type: "mywork:token", token: api.accessToken() },
            window.location.origin,
          );
        }}
      />
    );
  }
  return (
    <div className="pad">
      <h2>{manifest.name}</h2>
      <p className="muted">{manifest.description}</p>
      <p className="muted small">
        Deze app heeft (nog) geen eigen scherm. API-documentatie:{" "}
        <a href={`/api/apps/${app.id}/docs`} target="_blank" rel="noreferrer">
          /api/apps/{app.id}/docs
        </a>
      </p>
    </div>
  );
}
