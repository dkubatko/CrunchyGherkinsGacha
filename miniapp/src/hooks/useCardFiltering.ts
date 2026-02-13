import { useState, useMemo, useCallback } from 'react';
import type { CardData } from '@/types';
import type { FilterOptions, SortOptions } from '@/components/cards';
import { RARITY_SEQUENCE } from '@/utils/rarityStyles';

export const DEFAULT_FILTER_OPTIONS: FilterOptions = {
  owner: '',
  rarity: '',
  locked: '',
  characterName: '',
  setName: ''
};

export const DEFAULT_SORT_OPTIONS: SortOptions = {
  field: 'rarity',
  direction: 'desc'
};

interface UseCardFilteringOptions {
  includeOwnerFilter?: boolean;
  initialFilterOptions?: FilterOptions;
  initialSortOptions?: SortOptions;
}

const applyFilteringAndSorting = (
  cards: CardData[],
  filterOptions: FilterOptions,
  sortOptions: SortOptions,
  includeOwnerFilter: boolean
): CardData[] => {
  let filtered = cards;

  if (includeOwnerFilter && filterOptions.owner) {
    filtered = filtered.filter(card => card.owner === filterOptions.owner);
  }
  if (filterOptions.rarity) {
    filtered = filtered.filter(card => card.rarity === filterOptions.rarity);
  }
  if (filterOptions.locked) {
    const shouldBeLocked = filterOptions.locked === 'locked';
    filtered = filtered.filter(card => Boolean(card.locked) === shouldBeLocked);
  }
  if (filterOptions.characterName) {
    filtered = filtered.filter(card => card.base_name === filterOptions.characterName);
  }
  if (filterOptions.setName) {
    filtered = filtered.filter(card => card.set_name === filterOptions.setName);
  }

  return [...filtered].sort((a, b) => {
    let aValue: string | number;
    let bValue: string | number;

    switch (sortOptions.field) {
      case 'rarity': {
        const rarityArray = [...RARITY_SEQUENCE] as string[];
        const aIndex = rarityArray.indexOf(a.rarity);
        const bIndex = rarityArray.indexOf(b.rarity);
        aValue = aIndex === -1 ? rarityArray.length : aIndex;
        bValue = bIndex === -1 ? rarityArray.length : bIndex;
        break;
      }
      case 'id':
        aValue = a.id;
        bValue = b.id;
        break;
      case 'name':
        aValue = `${a.modifier} ${a.base_name}`.toLowerCase();
        bValue = `${b.modifier} ${b.base_name}`.toLowerCase();
        break;
      default:
        aValue = a.id;
        bValue = b.id;
    }

    if (typeof aValue === 'string' && typeof bValue === 'string') {
      const comparison = aValue.localeCompare(bValue);
      return sortOptions.direction === 'asc' ? comparison : -comparison;
    }

    if (typeof aValue === 'number' && typeof bValue === 'number') {
      const comparison = aValue - bValue;
      return sortOptions.direction === 'asc' ? comparison : -comparison;
    }

    return 0;
  });
};

export const useCardFiltering = (
  cards: CardData[],
  {
    includeOwnerFilter = true,
    initialFilterOptions = DEFAULT_FILTER_OPTIONS,
    initialSortOptions = DEFAULT_SORT_OPTIONS
  }: UseCardFilteringOptions = {}
) => {
  const [filterOptions, setFilterOptions] = useState<FilterOptions>(initialFilterOptions);
  const [sortOptions, setSortOptions] = useState<SortOptions>(initialSortOptions);

  const displayedCards = useMemo(
    () => applyFilteringAndSorting(cards, filterOptions, sortOptions, includeOwnerFilter),
    [cards, filterOptions, sortOptions, includeOwnerFilter]
  );

  const onFilterChange = useCallback((newFilters: FilterOptions) => {
    setFilterOptions(newFilters);
  }, []);

  const onSortChange = useCallback((newSort: SortOptions) => {
    setSortOptions(newSort);
  }, []);

  const reset = useCallback(() => {
    setFilterOptions(DEFAULT_FILTER_OPTIONS);
    setSortOptions(DEFAULT_SORT_OPTIONS);
  }, []);

  return {
    filterOptions,
    sortOptions,
    displayedCards,
    setFilterOptions,
    setSortOptions,
    onFilterChange,
    onSortChange,
    reset
  };
};
