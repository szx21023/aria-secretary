import { Icon } from "../lib/icons";
import { useTheme } from "../theme/ThemeProvider";
import { PRESETS, presetGradient } from "../theme/theme";

interface Props {
  onClose: () => void;
}

export function SettingsPanel({ onClose }: Props) {
  const { theme, setPreset, setGlow, reset } = useTheme();

  return (
    <div className="s-pop-back" onClick={onClose}>
      <div className="s-pop s-fadein" onClick={(e) => e.stopPropagation()}>
        <div className="s-pop-x" onClick={onClose}>
          <Icon name="x" />
        </div>

        <div className="s-eyebrow">外觀</div>
        <h3>主題設定</h3>

        <div className="s-set-sec">
          <div className="s-set-l">色彩主題</div>
          <div className="s-sw-row">
            {PRESETS.map((p) => (
              <button
                key={p.id}
                className={"s-sw" + (theme.preset === p.id ? " on" : "")}
                title={p.label}
                aria-label={p.label}
                onClick={() => setPreset(p.id)}
              >
                <span className="s-sw-dot" style={{ background: presetGradient(p) }} />
                <small>{p.label}</small>
              </button>
            ))}
          </div>
        </div>

        <div className="s-set-sec">
          <div className="s-set-l">
            光暈強度<span className="s-set-v">{Math.round(theme.glow * 100)}%</span>
          </div>
          <input
            className="s-range"
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={theme.glow}
            onChange={(e) => setGlow(Number(e.target.value))}
          />
        </div>

        <div className="s-pop-actions">
          <button className="s-btn" onClick={reset}>
            重設預設
          </button>
          <button className="s-btn primary" onClick={onClose}>
            完成
          </button>
        </div>
      </div>
    </div>
  );
}
