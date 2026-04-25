import type { ButtonHTMLAttributes, ReactNode } from "react";

import "./GameUi.css";

type TelemetryLine = {
  label: string;
  value: string;
};

type GameScreenBackgroundProps = {
  imageSrc: string;
  watermark?: ReactNode;
};

export function GameScreenBackground({
  imageSrc,
  watermark,
}: GameScreenBackgroundProps) {
  return (
    <div className="game-bg" aria-hidden>
      <img alt="" className="game-bg-img" decoding="async" src={imageSrc} />
      <div className="game-bg-shade" />
      <div className="game-bg-watermark">{watermark}</div>
      <div className="game-bg-noise" />
      <div className="game-bg-scanline" />
    </div>
  );
}

type GameChromeProps = {
  onBack: () => void;
  kicker: string;
  title: string;
  telemetry: TelemetryLine[];
};

export function GameChrome({
  onBack,
  kicker,
  title,
  telemetry,
}: GameChromeProps) {
  return (
    <header className="game-chrome">
      <GameButton
        aria-label="もどる"
        className="game-back-button"
        icon="arrow_back"
        label="もどる"
        onClick={onBack}
        type="button"
        variant="ghost"
      />
      <div className="game-chrome-title">
        <p className="game-kicker">{kicker}</p>
        <h1>{title}</h1>
      </div>
      <div className="game-chrome-fill" aria-hidden />
      <div className="game-telemetry" aria-hidden>
        {telemetry.map((line) => (
          <div key={line.label}>
            <span>{line.label}</span> {line.value}
          </div>
        ))}
      </div>
    </header>
  );
}

type GameButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  icon?: string;
  label: string;
  sublabel?: string;
  variant?: "primary" | "ghost" | "frame";
};

export function GameButton({
  className = "",
  icon,
  label,
  sublabel,
  variant = "primary",
  ...props
}: GameButtonProps) {
  const classes = `game-button game-button--${variant} ${className}`.trim();
  return (
    <button className={classes} {...props}>
      {icon ? (
        <span className="game-button-icon material-symbols-outlined" aria-hidden>
          {icon}
        </span>
      ) : null}
      <span className="game-button-copy">
        <span className="game-button-label">{label}</span>
        {sublabel ? <span className="game-button-sublabel">{sublabel}</span> : null}
      </span>
    </button>
  );
}

type GameProtocolButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  sublabel?: string;
};

export function GameProtocolButton({
  className = "",
  label,
  sublabel,
  ...props
}: GameProtocolButtonProps) {
  return (
    <button className={`game-protocol-button ${className}`.trim()} {...props}>
      <span className="game-protocol-button-copy">
        <span className="game-protocol-button-label">{label}</span>
        {sublabel ? (
          <span className="game-protocol-button-sublabel">{sublabel}</span>
        ) : null}
      </span>
      <span className="game-protocol-button-divider" aria-hidden />
      <span className="game-protocol-button-arrow material-symbols-outlined" aria-hidden>
        arrow_forward
      </span>
    </button>
  );
}

type GameFrameButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  icon: string;
};

export function GameFrameButton({
  className = "",
  icon,
  ...props
}: GameFrameButtonProps) {
  return (
    <button className={`game-frame-button ${className}`.trim()} {...props}>
      <span className="material-symbols-outlined" aria-hidden>
        {icon}
      </span>
    </button>
  );
}

type GamePanelProps = {
  children: ReactNode;
  className?: string;
};

export function GamePanel({ children, className = "" }: GamePanelProps) {
  return <div className={`game-panel ${className}`.trim()}>{children}</div>;
}

type GameWorldBadgeProps = {
  imageSrc: string;
  protocolCode: string;
  subtitle: string;
  title: string;
};

export function GameWorldBadge({
  imageSrc,
  protocolCode,
  subtitle,
  title,
}: GameWorldBadgeProps) {
  return (
    <section className="game-world-badge" aria-label="選択中のワールド">
      <img alt="" className="game-world-badge-img" decoding="async" src={imageSrc} />
      <div className="game-world-badge-veil" />
      <div className="game-world-badge-copy">
        <p>{protocolCode}</p>
        <h2>{title}</h2>
        <span>{subtitle}</span>
      </div>
    </section>
  );
}
