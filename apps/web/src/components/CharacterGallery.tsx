import type { Character } from "../types";

interface CharacterGalleryProps {
  characters: Character[];
  onConfirm: (characterId: number) => void;
  onRegenerate: (imageId: number) => void;
}

function CharacterGallery({ characters, onConfirm, onRegenerate }: CharacterGalleryProps) {
  return (
    <div className="character-gallery">
      {characters.map((character) => (
        <article key={character.id} className="character-card">
          <div className="character-summary">
            <p className="section-kicker">CHARACTER</p>
            <h2>{character.name}</h2>
            <p>{character.biography}</p>
            <dl>
              <div><dt>中文提示词</dt><dd>{character.prompt_zh}</dd></div>
              <div><dt>英文提示词</dt><dd>{character.prompt_en}</dd></div>
              <div><dt>音色</dt><dd>{character.voice_prompt}</dd></div>
              <div><dt>外观锚点</dt><dd>{character.anchor_features.join(" · ")}</dd></div>
            </dl>
            {!character.anchor_confirmed && (
              <button type="button" onClick={() => onConfirm(character.id)}>
                确认锚点图
              </button>
            )}
          </div>
          <div className="character-images">
            {character.images.map((image) => (
              <figure key={image.id} className={image.status}>
                {image.path && (
                  <img src={`/api/v1/assets/${image.path}`} alt={`${character.name} ${image.label}`} />
                )}
                <figcaption>
                  <span>{image.label} · {image.status}</span>
                  {image.error && <small className="error-message">{image.error}</small>}
                  {image.status === "failed" && (
                    <button type="button" onClick={() => onRegenerate(image.id)}>
                      重新生成
                    </button>
                  )}
                  {!character.anchor_confirmed && image.label !== "front_full" && (
                    <small>确认锚点后解锁</small>
                  )}
                </figcaption>
              </figure>
            ))}
          </div>
        </article>
      ))}
    </div>
  );
}

export default CharacterGallery;
