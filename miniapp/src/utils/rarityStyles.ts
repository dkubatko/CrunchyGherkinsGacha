export const RARITY_SEQUENCE = ["Common", "Rare", "Epic", "Legendary"] as const;

export type RarityName = typeof RARITY_SEQUENCE[number];

const RARITY_GRADIENTS: Record<RarityName, string> = {
  Common: "linear-gradient(45deg, #4A90E2, #7BB3F0)",
  Rare: "linear-gradient(45deg, #4CAF50, #81C784)",
  Epic: "linear-gradient(45deg, #9C27B0, #BA68C8)",
  Legendary: "linear-gradient(45deg, #FFD700, #FFF176)",
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

export const getRarityLabelClass = (rarity: string | null | undefined): string => {
  const normalized = normalizeRarityName(rarity);
  return normalized ? `rarity-${normalized.toLowerCase()}` : "rarity-common";
};
