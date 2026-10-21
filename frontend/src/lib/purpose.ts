import type { TreeNode } from "../api/types";
import type { Key } from "../i18n/en";

/** Same edges as the gift-size bands: a project total of exactly NT$1,000,000 is in the top band. */
const BANDS: { key: Key; match: (amount: number) => boolean }[] = [
  { key: "size.5", match: (amount) => amount >= 1_000_000 },
  { key: "size.4", match: (amount) => amount > 500_000 },
  { key: "size.3", match: (amount) => amount > 100_000 },
  { key: "size.2", match: (amount) => amount > 50_000 },
  { key: "size.1", match: (amount) => amount > 10_000 },
  { key: "size.0", match: () => true },
];

export function amountBand(amount: number): Key {
  return BANDS.find((band) => band.match(amount))!.key;
}
export type PurposeProject = { name: string; value: number };
export type PurposeBand = { key: Key; projects: PurposeProject[] };
export type PurposeSection = { name: string; value: number; bands: PurposeBand[] };
export type PurposeBlock = { name: string; value: number; sections: PurposeSection[] };

function projectsOf(node: TreeNode): PurposeProject[] {
  const kids = node.children ?? [];
  if (!kids.length) return [{ name: node.name, value: node.value }];
  return kids.flatMap(projectsOf);
}

function section(name: string, value: number, projects: PurposeProject[]): PurposeSection {
  const bands = BANDS.map((band) => ({
    key: band.key,
    projects: projects.filter((project) => amountBand(project.value) === band.key).sort((a, b) => b.value - a.value),
  })).filter((band) => band.projects.length);
  return { name, value, bands };
}

/** Purpose groups, then amount bands, with every project kept. Larger groups and amounts come first. */
export function purposeBlocks(tree: TreeNode[]): PurposeBlock[] {
  return tree.map((node) => {
    const kids = node.children ?? [];
    const nested = kids.some((kid) => (kid.children?.length ?? 0) > 0);
    const sections = (nested
      ? kids.map((kid) => section(kid.name, kid.value, projectsOf(kid)))
      : [section(node.name, node.value, kids.map((kid) => ({ name: kid.name, value: kid.value })))]
    ).filter((item) => item.bands.length).sort((a, b) => b.value - a.value);
    return { name: node.name, value: node.value, sections };
  }).filter((block) => block.sections.length).sort((a, b) => b.value - a.value);
}
