import { useState } from "react";
import type { TreeNode } from "../api/types";
import { useI18n } from "../i18n";
import { purposeBlocks, type PurposeSection } from "../lib/purpose";

/** Purpose groups are tags. A group with categories, such as designated gifts, shows a second row of tags.
 *  The project chart appears only after a tag is chosen. */
export function PurposeBoard({ tree, label }: { tree: TreeNode[]; label: string }) {
  const { t, fmt } = useI18n();
  const blocks = purposeBlocks(tree);
  const [blockName, setBlockName] = useState<string | null>(null);
  const [sectionName, setSectionName] = useState<string | null>(null);
  const block = blocks.find((item) => item.name === blockName) ?? null;
  const nested = !!block && block.sections.some((section) => section.name !== block.name);
  const section = nested
    ? block?.sections.find((item) => item.name === sectionName) ?? null
    : block?.sections[0] ?? null;

  const chooseBlock = (name: string) => {
    setBlockName((current) => (current === name ? null : name));
    setSectionName(null);
  };

  return (
    <div className="purpose" aria-label={label}>
      <div className="purpose-tags" role="group" aria-label={t("purpose.groups")}>
        {blocks.map((item) => (
          <button type="button" key={item.name} className="purpose-tag" aria-pressed={item.name === blockName} onClick={() => chooseBlock(item.name)}>
            {item.name}<span className="num">{fmt.compact(item.value)}</span>
          </button>
        ))}
      </div>
      {block && nested && (
        <div className="purpose-tags sub" role="group" aria-label={t("purpose.sections")}>
          {block.sections.map((item) => (
            <button type="button" key={item.name} className="purpose-tag" aria-pressed={item.name === sectionName} onClick={() => setSectionName((current) => (current === item.name ? null : item.name))}>
              {item.name}<span className="num">{fmt.compact(item.value)}</span>
            </button>
          ))}
        </div>
      )}
      {section ? <PurposeChart section={section} /> : <p className="purpose-hint">{block && nested ? t("purpose.pick_section") : t("purpose.pick")}</p>}
    </div>
  );
}

function PurposeChart({ section }: { section: PurposeSection }) {
  const { t, fmt } = useI18n();
  const max = Math.max(...section.bands.flatMap((band) => band.projects.map((project) => project.value)), 1);
  return (
    <div className="purpose-chart" role="list" aria-label={section.name}>
      {section.bands.map((band) => (
        <div className="purpose-band" key={band.key}>
          <p>{t(band.key)}</p>
          {band.projects.map((project) => (
            <div className="purpose-row" role="listitem" key={project.name}>
              <span className="fill" style={{ width: `${Math.max(project.value / max * 100, 0.6)}%` }} />
              <span className="name">{project.name}</span>
              <span className="amt num">{fmt.compact(project.value)}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
