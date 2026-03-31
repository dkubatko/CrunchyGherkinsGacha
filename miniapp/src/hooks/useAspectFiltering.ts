import { useState, useMemo, useCallback } from 'react';
import type { AspectData } from '@/types';
import type { FilterOptions, SortOptions, FilterValues } from '@/components/cards';
import { RARITY_SEQUENCE } from '@/utils/rarityStyles';

export const DEFAULT_ASPECT_FILTER_OPTIONS: FilterOptions = {
  owner: '',
  rarity: '',
  locked: '',
  characterName: '',
  setName: '',
  aspectStatus: ''
};

export const DEFAULT_ASPECT_SORT_OPTIONS: SortOptions = {
  field: 'rarity',
  direction: 'desc'
};

const applyFilteringAndSorting = (
  aspects: AspectData[],
  filterOptions: FilterOptions,
  sortOptions: SortOptions,
): AspectData[] => {
  let filtered = aspects;

  if (filterOptions.rarity) {
    filtered = filtered.filter(a => a.rarity === filterOptions.rarity);
  }
  if (filterOptions.locked) {
    const shouldBeLocked = filterOptions.locked === 'locked';
    filtered = filtered.filter(a => Boolean(a.locked) === shouldBeLocked);
  }
  if (filterOptions.setName) {
    filtered = filtered.filter(a =>
      a.aspect_definition?.set_name === filterOptions.setName
    );
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
        aValue = a.display_name.toLowerCase();
        bValue = b.display_name.toLowerCase();
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

export const useAspectFiltering = (aspects: AspectData[]) => {
  const [filterOptions, setFilterOptions] = useState<FilterOptions>(DEFAULT_ASPECT_FILTER_OPTIONS);
  const [sortOptions, setSortOptions] = useState<SortOptions>(DEFAULT_ASPECT_SORT_OPTIONS);

  const displayedAspects = useMemo(
    () => applyFilteringAndSorting(aspects, filterOptions, sortOptions),
    [aspects, filterOptions, sortOptions]
  );

  const filterValues = useMemo<FilterValues>(() => {
    const rarityArray = [...RARITY_SEQUENCE] as string[];
    const sets = new Set<string>();
    const rarities = new Set<string>();
    aspects.forEach((a) => {
      rarities.add(a.rarity);
      if (a.aspect_definition?.set_name) sets.add(a.aspect_definition.set_name);
    });
    return {
      owners: [],
      characters: [],
      rarities: Array.from(rarities).sort((a, b) => {
        const aPos = rarityArray.indexOf(a);
        const bPos = rarityArray.indexOf(b);
        return (aPos === -1 ? rarityArray.length : aPos) - (bPos === -1 ? rarityArray.length : bPos);
      }),
      sets: Array.from(sets).sort(),
    };
  }, [aspects]);

  const onFilterChange = useCallback((newFilters: FilterOptions) => {
    setFilterOptions(newFilters);
  }, []);

  const onSortChange = useCallback((newSort: SortOptions) => {
    setSortOptions(newSort);
  }, []);

  const reset = useCallback(() => {
    setFilterOptions(DEFAULT_ASPECT_FILTER_OPTIONS);
    setSortOptions(DEFAULT_ASPECT_SORT_OPTIONS);
  }, []);

  return {
    filterOptions,
    sortOptions,
    displayedAspects,
    filterValues,
    setFilterOptions,
    setSortOptions,
    onFilterChange,
    onSortChange,
    reset
  };
};
