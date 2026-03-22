import { useState, useMemo, useCallback } from 'react';
import type { AspectData } from '@/types';
import { RARITY_SEQUENCE } from '@/utils/rarityStyles';

export interface AspectFilterOptions {
  rarity: string;
  locked: string;
  setName: string;
}

export interface AspectSortOptions {
  field: 'rarity' | 'name' | 'id';
  direction: 'asc' | 'desc';
}

export const DEFAULT_ASPECT_FILTER_OPTIONS: AspectFilterOptions = {
  rarity: '',
  locked: '',
  setName: ''
};

export const DEFAULT_ASPECT_SORT_OPTIONS: AspectSortOptions = {
  field: 'rarity',
  direction: 'desc'
};

const applyFilteringAndSorting = (
  aspects: AspectData[],
  filterOptions: AspectFilterOptions,
  sortOptions: AspectSortOptions,
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
  const [filterOptions, setFilterOptions] = useState<AspectFilterOptions>(DEFAULT_ASPECT_FILTER_OPTIONS);
  const [sortOptions, setSortOptions] = useState<AspectSortOptions>(DEFAULT_ASPECT_SORT_OPTIONS);

  const displayedAspects = useMemo(
    () => applyFilteringAndSorting(aspects, filterOptions, sortOptions),
    [aspects, filterOptions, sortOptions]
  );

  const onFilterChange = useCallback((newFilters: AspectFilterOptions) => {
    setFilterOptions(newFilters);
  }, []);

  const onSortChange = useCallback((newSort: AspectSortOptions) => {
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
    setFilterOptions,
    setSortOptions,
    onFilterChange,
    onSortChange,
    reset
  };
};
