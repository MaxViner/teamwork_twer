export default function FrameTexts({ texts }) {
  if (!texts.length) {
    return null;
  }

  return (
    <div className="keyframe-row">
      <span className="keyframe-label">Текст</span>

      <div className="keyframe-chips">
        {texts.slice(0, 3).map((text) => (
          <span className="keyframe-chip" key={text}>
            «{text}»
          </span>
        ))}

        {texts.length > 3 && (
          <span className="muted">
            +{texts.length - 3}
          </span>
        )}
      </div>
    </div>
  );
}