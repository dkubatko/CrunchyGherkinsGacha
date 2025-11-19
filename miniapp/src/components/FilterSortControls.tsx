import React, { memo, useState, useRef, useEffect } from 'react';
import './FilterSortControls.css';
import type { CardData } from '../types';
import { RARITY_SEQUENCE } from '../utils/rarityStyles';

export interface FilterOptions {
  owner: string;
  rarity: string;
  locked: '' | 'locked' | 'unlocked';
}

export interface SortOptions {
  field: 'rarity' | 'id' | 'name';
  direction: 'asc' | 'desc';
}

interface FilterSortControlsProps {
  cards: CardData[];
  filterOptions: FilterOptions;
  sortOptions: SortOptions;
  onFilterChange: (filters: FilterOptions) => void;
  onSortChange: (sort: SortOptions) => void;
  showOwnerFilter?: boolean; // Optional prop to show/hide owner filter
}

const FilterSortControls: React.FC<FilterSortControlsProps> = memo(({
  cards,
  filterOptions,
  sortOptions,
  onFilterChange,
  onSortChange,
  showOwnerFilter = true, // Default to true to maintain existing behavior
}) => {
  const [filterOpen, setFilterOpen] = useState(false);
  const [sortOpen, setSortOpen] = useState(false);
  const [expandedFilter, setExpandedFilter] = useState<'owner' | 'rarity' | 'locked' | null>(null);
  
  const filterRef = useRef<HTMLDivElement>(null);
  const sortRef = useRef<HTMLDivElement>(null);

  // Get unique owners from cards for the filter dropdown
  const uniqueOwners = Array.from(new Set(
    cards
      .map(card => card.owner)
      .filter((owner): owner is string => Boolean(owner))
  )).sort();

  // Get unique rarities from cards for the filter dropdown, sorted by rarity order
  const rarityArray = [...RARITY_SEQUENCE] as string[];
  const uniqueRarities = Array.from(new Set(
    cards.map(card => card.rarity)
  )).sort((a, b) => {
    const aIndex = rarityArray.indexOf(a);
    const bIndex = rarityArray.indexOf(b);
    // If rarity not found in order, put it at the end
    const aPos = aIndex === -1 ? rarityArray.length : aIndex;
    const bPos = bIndex === -1 ? rarityArray.length : bIndex;
    return aPos - bPos;
  });

  // Close dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (filterRef.current && !filterRef.current.contains(event.target as Node)) {
        setFilterOpen(false);
        setExpandedFilter(null);
      }
      if (sortRef.current && !sortRef.current.contains(event.target as Node)) {
        setSortOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const hasActiveFilters = (showOwnerFilter && filterOptions.owner) || filterOptions.rarity || filterOptions.locked;
  const isActiveSortField = (field: string) => sortOptions.field === field;

  const handleFilterToggle = () => {
    setFilterOpen(!filterOpen);
    setSortOpen(false);
    setExpandedFilter(null);
  };

  const handleSortToggle = () => {
    setSortOpen(!sortOpen);
    setFilterOpen(false);
    setExpandedFilter(null);
  };

  const handleFilterOptionClick = (type: 'owner' | 'rarity' | 'locked') => {
    if (expandedFilter === type) {
      setExpandedFilter(null);
    } else {
      setExpandedFilter(type);
    }
  };

  const handleOwnerSelect = (owner: string) => {
    onFilterChange({
      ...filterOptions,
      owner: owner
    });
    setFilterOpen(false);
    setExpandedFilter(null);
  };

  const handleRaritySelect = (rarity: string) => {
    onFilterChange({
      ...filterOptions,
      rarity: rarity
    });
    setFilterOpen(false);
    setExpandedFilter(null);
  };

  const handleLockedSelect = (locked: '' | 'locked' | 'unlocked') => {
    onFilterChange({
      ...filterOptions,
      locked
    });
    setFilterOpen(false);
    setExpandedFilter(null);
  };

  const handleClearFilters = () => {
    onFilterChange({
      owner: '',
      rarity: '',
      locked: ''
    });
    setFilterOpen(false);
    setExpandedFilter(null);
  };

  const handleSortSelect = (field: 'rarity' | 'id' | 'name', direction: 'asc' | 'desc') => {
    onSortChange({
      field,
      direction
    });
    setSortOpen(false);
  };

  return (
    <div className="filter-sort-controls">
      <div className="control-buttons">
        {/* Filter Button */}
        <div className="control-button-container" ref={filterRef}>
          <button 
            className={`control-button ${filterOpen ? 'active' : ''} ${hasActiveFilters ? 'has-active-filters' : ''}`}
            onClick={handleFilterToggle}
            aria-label="Filter cards"
          >
            <svg className="control-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M14,12V19.88C14.04,20.18 13.94,20.5 13.71,20.71C13.32,21.1 12.69,21.1 12.3,20.71L10.29,18.7C10.06,18.47 9.96,18.16 10,17.87V12H9.97L4.21,4.62C3.87,4.19 3.95,3.56 4.38,3.22C4.57,3.08 4.78,3 5,3V3H19V3C19.22,3 19.43,3.08 19.62,3.22C20.05,3.56 20.13,4.19 19.79,4.62L14.03,12H14Z" />
            </svg>
            <span>Filter</span>
            {hasActiveFilters && <div className="active-indicator" />}
          </button>
          
          {filterOpen && (
            <div className="dropdown filter-dropdown">
              <div className="dropdown-content">
                {showOwnerFilter && (
                  <div className={`dropdown-item ${expandedFilter === 'owner' ? 'expanded' : ''}`}>
                    <button 
                      className="dropdown-main-option"
                      onClick={() => handleFilterOptionClick('owner')}
                    >
                      <span>Owner</span>
                      {filterOptions.owner && <span className="current-value">({filterOptions.owner})</span>}
                      <svg className={`expand-icon ${expandedFilter === 'owner' ? 'rotated' : ''}`} viewBox="0 0 24 24">
                        <path d="M8.59,16.58L13.17,12L8.59,7.41L10,6L16,12L10,18L8.59,16.58Z"/>
                      </svg>
                    </button>
                    {expandedFilter === 'owner' && (
                      <div className="dropdown-submenu">
                        <button 
                          className={`dropdown-subitem ${!filterOptions.owner ? 'active' : ''}`}
                          onClick={() => handleOwnerSelect('')}
                        >
                          All owners
                        </button>
                        {uniqueOwners.map(owner => (
                          <button
                            key={owner}
                            className={`dropdown-subitem ${filterOptions.owner === owner ? 'active' : ''}`}
                            onClick={() => handleOwnerSelect(owner)}
                          >
                            {owner}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <div className={`dropdown-item ${expandedFilter === 'rarity' ? 'expanded' : ''}`}>
                  <button 
                    className="dropdown-main-option"
                    onClick={() => handleFilterOptionClick('rarity')}
                  >
                    <span>Rarity</span>
                    {filterOptions.rarity && <span className="current-value">({filterOptions.rarity})</span>}
                    <svg className={`expand-icon ${expandedFilter === 'rarity' ? 'rotated' : ''}`} viewBox="0 0 24 24">
                      <path d="M8.59,16.58L13.17,12L8.59,7.41L10,6L16,12L10,18L8.59,16.58Z"/>
                    </svg>
                  </button>
                  {expandedFilter === 'rarity' && (
                    <div className="dropdown-submenu">
                      <button 
                        className={`dropdown-subitem ${!filterOptions.rarity ? 'active' : ''}`}
                        onClick={() => handleRaritySelect('')}
                      >
                        All rarities
                      </button>
                      {uniqueRarities.map(rarity => (
                        <button
                          key={rarity}
                          className={`dropdown-subitem ${filterOptions.rarity === rarity ? 'active' : ''}`}
                          onClick={() => handleRaritySelect(rarity)}
                        >
                          {rarity}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <div className={`dropdown-item ${expandedFilter === 'locked' ? 'expanded' : ''}`}>
                  <button 
                    className="dropdown-main-option"
                    onClick={() => handleFilterOptionClick('locked')}
                  >
                    <span>Status</span>
                    {filterOptions.locked && (
                      <span className="current-value">({filterOptions.locked === 'locked' ? 'Locked' : 'Unlocked'})</span>
                    )}
                    <svg className={`expand-icon ${expandedFilter === 'locked' ? 'rotated' : ''}`} viewBox="0 0 24 24">
                      <path d="M8.59,16.58L13.17,12L8.59,7.41L10,6L16,12L10,18L8.59,16.58Z"/>
                    </svg>
                  </button>
                  {expandedFilter === 'locked' && (
                    <div className="dropdown-submenu">
                      <button 
                        className={`dropdown-subitem ${!filterOptions.locked ? 'active' : ''}`}
                        onClick={() => handleLockedSelect('')}
                      >
                        Any
                      </button>
                      <button
                        className={`dropdown-subitem ${filterOptions.locked === 'locked' ? 'active' : ''}`}
                        onClick={() => handleLockedSelect('locked')}
                      >
                        Locked
                      </button>
                      <button
                        className={`dropdown-subitem ${filterOptions.locked === 'unlocked' ? 'active' : ''}`}
                        onClick={() => handleLockedSelect('unlocked')}
                      >
                        Unlocked
                      </button>
                    </div>
                  )}
                </div>

                {hasActiveFilters && (
                  <div className="dropdown-item">
                    <button 
                      className="dropdown-main-option clear-option"
                      onClick={handleClearFilters}
                    >
                      Clear filters
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Sort Button */}
        <div className="control-button-container" ref={sortRef}>
          <button 
            className={`control-button ${sortOpen ? 'active' : ''}`}
            onClick={handleSortToggle}
            aria-label="Sort cards"
          >
            <svg className="control-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M18 21L14 17H17V7H14L18 3L22 7H19V17H22M2 19V17H12V19M2 13V11H9V13M2 7V5H6V7H2Z" />
            </svg>
            <span>Sort</span>
          </button>
          
          {sortOpen && (
            <div className="dropdown sort-dropdown">
              <div className="dropdown-content">
                <div className="dropdown-item">
                  <div className="sort-option">
                    <span className="sort-label">ID</span>
                    <div className="sort-directions">
                      <button 
                        className={`sort-direction ${isActiveSortField('id') && sortOptions.direction === 'asc' ? 'active' : ''}`}
                        onClick={() => handleSortSelect('id', 'asc')}
                        aria-label="Sort ID ascending"
                      >
                        ↑
                      </button>
                      <button 
                        className={`sort-direction ${isActiveSortField('id') && sortOptions.direction === 'desc' ? 'active' : ''}`}
                        onClick={() => handleSortSelect('id', 'desc')}
                        aria-label="Sort ID descending"
                      >
                        ↓
                      </button>
                    </div>
                  </div>
                </div>

                <div className="dropdown-item">
                  <div className="sort-option">
                    <span className="sort-label">Rarity</span>
                    <div className="sort-directions">
                      <button 
                        className={`sort-direction ${isActiveSortField('rarity') && sortOptions.direction === 'asc' ? 'active' : ''}`}
                        onClick={() => handleSortSelect('rarity', 'asc')}
                        aria-label="Sort rarity ascending"
                      >
                        ↑
                      </button>
                      <button 
                        className={`sort-direction ${isActiveSortField('rarity') && sortOptions.direction === 'desc' ? 'active' : ''}`}
                        onClick={() => handleSortSelect('rarity', 'desc')}
                        aria-label="Sort rarity descending"
                      >
                        ↓
                      </button>
                    </div>
                  </div>
                </div>

                <div className="dropdown-item">
                  <div className="sort-option">
                    <span className="sort-label">Name</span>
                    <div className="sort-directions">
                      <button 
                        className={`sort-direction ${isActiveSortField('name') && sortOptions.direction === 'asc' ? 'active' : ''}`}
                        onClick={() => handleSortSelect('name', 'asc')}
                        aria-label="Sort name ascending"
                      >
                        ↑
                      </button>
                      <button 
                        className={`sort-direction ${isActiveSortField('name') && sortOptions.direction === 'desc' ? 'active' : ''}`}
                        onClick={() => handleSortSelect('name', 'desc')}
                        aria-label="Sort name descending"
                      >
                        ↓
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

FilterSortControls.displayName = 'FilterSortControls';

export default FilterSortControls;