export const RARITY_SEQUENCE = ["Common", "Rare", "Epic", "Legendary"] as const;

export type RarityName = typeof RARITY_SEQUENCE[number];

const RARITY_COLOR_PALETTE: Record<RarityName, [string, string]> = {
  Common: ["#4A90E2", "#7BB3F0"],
  Rare: ["#4CAF50", "#81C784"],
  Epic: ["#9C27B0", "#BA68C8"],
  Legendary: ["#FFD700", "#FFF176"],
};

const RARITY_GRADIENTS: Record<RarityName, string> = {
  Common: `linear-gradient(45deg, ${RARITY_COLOR_PALETTE.Common[0]}, ${RARITY_COLOR_PALETTE.Common[1]})`,
  Rare: `linear-gradient(45deg, ${RARITY_COLOR_PALETTE.Rare[0]}, ${RARITY_COLOR_PALETTE.Rare[1]})`,
  Epic: `linear-gradient(45deg, ${RARITY_COLOR_PALETTE.Epic[0]}, ${RARITY_COLOR_PALETTE.Epic[1]})`,
  Legendary: `linear-gradient(45deg, ${RARITY_COLOR_PALETTE.Legendary[0]}, ${RARITY_COLOR_PALETTE.Legendary[1]})`,
};

export const normalizeRarityName = (rarity: string | null | undefined): RarityName | null => {
  if (!rarity) {
    return null;
  }

  const normalized = rarity.trim().toLowerCase();
  for (const name of RARITY_SEQUENCE) {
    if (name.toLowerCase() === normalized) {
      return name;
    }
  }

  return null;
};

export const getRarityGradient = (rarity: string | null | undefined): string => {
  const normalized = normalizeRarityName(rarity);
  if (normalized) {
    return RARITY_GRADIENTS[normalized];
  }

  return RARITY_GRADIENTS.Common;
};

export const getRarityColors = (rarity: string | null | undefined): [string, string] => {
  const normalized = normalizeRarityName(rarity);
  if (normalized) {
    return RARITY_COLOR_PALETTE[normalized];
  }

  return RARITY_COLOR_PALETTE.Common;
};

export const getRarityLabelClass = (rarity: string | null | undefined): string => {
  const normalized = normalizeRarityName(rarity);
  return normalized ? `rarity-${normalized.toLowerCase()}` : "rarity-common";
};
