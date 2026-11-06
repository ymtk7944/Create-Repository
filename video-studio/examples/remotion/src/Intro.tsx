import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

const TOOLS = ["Remotion", "HyperFrames", "GSAP", "three.js", "Blender", "FFmpeg"];

export const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const titleIn = spring({ frame, fps, config: { damping: 14 } });

  return (
    <AbsoluteFill
      style={{
        background: "radial-gradient(ellipse at 50% 30%, #23303d 0%, #10141a 70%)",
        color: "#f4efe6",
        fontFamily: "Helvetica Neue, Arial, sans-serif",
        alignItems: "center",
        justifyContent: "center",
        gap: 48,
      }}
    >
      <h1 style={{ fontSize: 96, margin: 0, transform: `translateY(${(1 - titleIn) * -80}px)`, opacity: titleIn }}>
        React で書いて、MP4 にする
      </h1>
      <div style={{ display: "flex", gap: 24 }}>
        {TOOLS.map((name, i) => {
          const s = spring({ frame: frame - 20 - i * 6, fps, config: { damping: 12 } });
          return (
            <div
              key={name}
              style={{
                fontSize: 40,
                fontWeight: 800,
                padding: "20px 32px",
                borderRadius: 16,
                background: "#2a2622",
                border: "4px solid #ffcf4a",
                transform: `scale(${s})`,
                opacity: interpolate(s, [0, 1], [0, 1]),
              }}
            >
              {name}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
