import { useCallback, useEffect, useMemo, useState } from "react";

import { AmbientMonitoringLayer } from "../ambient/AmbientMonitoringLayer";
import {
  GameButton,
  GameFrameButton,
  GameProtocolButton,
  GameScreenBackground,
} from "../ui/GameUi";
import { WORLDS } from "../worldSelect/worldSelectData";
import {
  getCharactersForWorld,
  PARTY_SLOT_COUNT,
  type SelectableCharacter,
} from "./characterSelectData";
import "./CharacterSelectScreen.css";

export type CharacterSelectScreenProps = {
  worldId: string;
  onBack: () => void;
  onTransfer?: (payload: { worldId: string; characterIds: string[] }) => void;
};

export function CharacterSelectScreen({
  worldId,
  onBack,
  onTransfer,
}: CharacterSelectScreenProps) {
  const world = useMemo(
    () => WORLDS.find((candidate) => candidate.id === worldId) ?? WORLDS[0],
    [worldId],
  );
  const characters = useMemo(() => getCharactersForWorld(world.id), [world.id]);
  const [index, setIndex] = useState(0);
  const [party, setParty] = useState<SelectableCharacter[]>([]);

  const selected = characters[index] ?? null;
  const canCycle = characters.length > 1;
  const isLinkable = selected?.statusLabel === "LINKABLE";
  const isSelected = selected ? party.some((member) => member.id === selected.id) : false;
  const worldTitleParts = world.title.split(" ―― ");

  useEffect(() => {
    setIndex(0);
    setParty([]);
  }, [world.id]);

  const goPrev = useCallback(() => {
    if (!canCycle) return;
    setIndex((current) => (current - 1 + characters.length) % characters.length);
  }, [canCycle, characters.length]);

  const goNext = useCallback(() => {
    if (!canCycle) return;
    setIndex((current) => (current + 1) % characters.length);
  }, [canCycle, characters.length]);

  const selectCharacter = useCallback(() => {
    if (!selected || !isLinkable || isSelected || party.length >= PARTY_SLOT_COUNT) return;
    setParty((current) => [...current, selected]);
  }, [isLinkable, isSelected, party.length, selected]);

  const transfer = useCallback(() => {
    if (!onTransfer || party.length === 0) return;
    onTransfer({
      worldId: world.id,
      characterIds: party.map((member) => member.id),
    });
  }, [onTransfer, party, world.id]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        goPrev();
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        goNext();
      } else if (event.key === "Enter") {
        event.preventDefault();
        if (party.length > 0) transfer();
        else selectCharacter();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goNext, goPrev, party.length, selectCharacter, transfer]);

  return (
    <div className="cs-root game-screen" lang="ja">
      <GameScreenBackground
        imageSrc={world.imageSrc}
        watermark={
          <>
            <span>{world.protocolCode}</span>
            <strong>{world.title}</strong>
          </>
        }
      />
      <AmbientMonitoringLayer variant="world" />

      <div className="cs-shell">
        <GameButton
          aria-label="もどる"
          className="cs-back-button"
          icon="arrow_back"
          label="もどる"
          onClick={onBack}
          type="button"
          variant="ghost"
        />

        <header className="cs-title-block">
          <h1>キャラクター選択</h1>
          <p>共に転送する存在を選んでください</p>
        </header>

        <div className="cs-telemetry" aria-hidden>
          <div>
            <span>PROTOCOL</span> CHARACTER_SELECT
          </div>
          <div>
            <span>WORLD</span> {world.id.toUpperCase()}
          </div>
          <div>
            <span>CHANNEL</span> DREAM_LAYER / STABLE
          </div>
        </div>

        <section className="cs-world-brief" aria-label="選択中のワールド">
          <p>WORLD</p>
          <h2>
            <span>{worldTitleParts[0]}</span>
            {worldTitleParts[1] ? <span>―― {worldTitleParts[1]}</span> : null}
          </h2>
          <span>{world.subtitle}</span>
        </section>

        <main className="cs-main" aria-label="キャラクター選択">
          {selected ? (
            <>
              <section className="cs-character-stage" aria-label="選択可能キャラクター">
                <GameFrameButton
                  aria-label="前のキャラクターへ"
                  className="cs-arrow cs-arrow--prev"
                  disabled={!canCycle}
                  icon="chevron_left"
                  onClick={goPrev}
                  type="button"
                />

                <div className="cs-portrait-wrap">
                  {selected.imageSrc ? (
                    <img
                      alt={selected.name}
                      className="cs-portrait"
                      decoding="async"
                      src={selected.imageSrc}
                    />
                  ) : (
                    <div className="cs-portrait-placeholder" aria-hidden>
                      <span>{String(index + 1).padStart(2, "0")}</span>
                    </div>
                  )}
                </div>

                <GameFrameButton
                  aria-label="次のキャラクターへ"
                  className="cs-arrow cs-arrow--next"
                  disabled={!canCycle}
                  icon="chevron_right"
                  onClick={goNext}
                  type="button"
                />
              </section>

              <section className="cs-character-dossier" aria-label="キャラクター詳細">
                <p className="cs-kicker">CHARACTER</p>
                <h2>{selected.name}</h2>
                <p className="cs-character-description">{selected.description}</p>
                <dl>
                  <div>
                    <dt>ORIGIN</dt>
                    <dd>{world.title.split(" ―― ")[0]}・門前</dd>
                  </div>
                  <div>
                    <dt>ROLE</dt>
                    <dd>{selected.roleLabel} / OBSERVER</dd>
                  </div>
                  <div>
                    <dt>AFFINITY</dt>
                    <dd>MEMORY / CHOICE</dd>
                  </div>
                  <div>
                    <dt>RISK</dt>
                    <dd>LOW</dd>
                  </div>
                </dl>
              </section>

              <div className="cs-select-row">
                <GameButton
                  disabled={!isLinkable || isSelected}
                  label={!isLinkable ? "信号なし" : isSelected ? "選択済み" : "選択する"}
                  onClick={selectCharacter}
                  sublabel={!isLinkable ? "NO SIGNAL" : isSelected ? "SUBJECT LOCKED" : "SELECT"}
                  type="button"
                />
              </div>
            </>
          ) : (
            <div className="cs-empty-state">
              <p className="cs-kicker">NO SUBJECT</p>
              <h2>接続可能なキャラクターがありません</h2>
            </div>
          )}

          <aside className="cs-party-panel" aria-label="パーティメンバー">
            <div className="cs-party-head">
              <p className="cs-kicker">PARTY BUFFER</p>
              <span>
                {String(party.length).padStart(2, "0")} /{" "}
                {String(PARTY_SLOT_COUNT).padStart(2, "0")}
              </span>
            </div>

            <div className="cs-slot-list">
              {Array.from({ length: PARTY_SLOT_COUNT }).map((_, slotIndex) => {
                const member = party[slotIndex] ?? null;
                return (
                  <div
                    className={member ? "cs-party-slot cs-party-slot--filled" : "cs-party-slot"}
                    key={slotIndex}
                  >
                    {member ? (
                      <>
                        <img
                          alt=""
                          className="cs-party-thumb"
                          decoding="async"
                          src={member.thumbnailSrc ?? member.imageSrc}
                        />
                        <div className="cs-party-copy">
                          <span className="cs-party-index">
                            {String(slotIndex + 1).padStart(2, "0")} / LINKED
                          </span>
                          <strong>{member.name}</strong>
                          <span className="cs-party-role">{member.roleLabel}</span>
                          <span className="cs-party-status">STATUS: LINKED</span>
                        </div>
                      </>
                    ) : (
                      <>
                        <span className="cs-empty-mark" aria-hidden>
                          {String(slotIndex + 1).padStart(2, "0")}
                        </span>
                        <div className="cs-party-copy">
                          <span className="cs-party-index">
                            {String(slotIndex + 1).padStart(2, "0")} / EMPTY
                          </span>
                          <strong>NO SIGNAL</strong>
                          <span className="cs-party-status">STATUS: VACANT</span>
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="cs-transfer-console">
              <div className="cs-transfer-status" aria-hidden>
                <p>TRANSFER PROTOCOL</p>
                <span>READY TO SYNCHRONIZE</span>
                <span>HANDSHAKE: {party.length > 0 ? "OK" : "WAITING"}</span>
              </div>
              <GameProtocolButton
                className="cs-transfer-btn"
                disabled={party.length === 0}
                label="転送する"
                onClick={transfer}
                sublabel="TRANSFER"
                type="button"
              />
            </div>
          </aside>
        </main>
      </div>
    </div>
  );
}
