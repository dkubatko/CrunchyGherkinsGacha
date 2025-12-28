import React, { memo, useState, useRef, useEffect } from 'react';
import './FilterSortControls.css';
import type { CardData } from '../types';
import { RARITY_SEQUENCE } from '../utils/rarityStyles';

export interface FilterOptions {
  owner: string;
  rarity: string;
  locked: '' | 'locked' | 'unlocked';
  characterName: string;
  setName: string;
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
  const [expandedFilter, setExpandedFilter] = useState<'owner' | 'rarity' | 'locked' | 'characterName' | 'setName' | null>(null);
  
  const filterRef = useRef<HTMLDivElement>(null);
  const sortRef = useRef<HTMLDivElement>(null);
  const dropdownContentRef = useRef<HTMLDivElement>(null);
  const categoryItemRefs = useRef<{ [key: string]: HTMLDivElement | null }>({});

  // Get unique owners from cards for the filter dropdown
  const uniqueOwners = Array.from(new Set(
    cards
      .map(card => card.owner)
      .filter((owner): owner is string => Boolean(owner))
  )).sort();

  // Get unique character names from cards for the filter dropdown
  const uniqueCharacterNames = Array.from(new Set(
    cards.map(card => card.base_name)
  )).sort();

  // Get unique set names from cards for the filter dropdown
  const uniqueSetNames = Array.from(new Set(
    cards
      .map(card => card.set_name)
      .filter((setName): setName is string => Boolean(setName))
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

  // Calculate submenu offset to align with the selected category item's top edge
  const getSubmenuOffset = () => {
    if (expandedFilter && categoryItemRefs.current[expandedFilter] && dropdownContentRef.current) {
      const categoryItem = categoryItemRefs.current[expandedFilter];
      const dropdownContent = dropdownContentRef.current;
      
      if (categoryItem) {
        // Get the category item's position relative to the dropdown content
        const categoryRect = categoryItem.getBoundingClientRect();
        const contentRect = dropdownContent.getBoundingClientRect();
        
        // Align submenu top edge with category item top edge
        const offset = categoryRect.top - contentRect.top;
        
        return Math.max(0, offset);
      }
    }
    return 0;
  };

  // Callback ref to scroll to active item immediately when submenu mounts
  const submenuContentRef = (node: HTMLDivElement | null) => {
    if (node) {
      const activeItem = node.querySelector('.dropdown-subitem.active') as HTMLElement;
      if (activeItem) {
        // Set scroll position synchronously before paint
        const containerHeight = node.clientHeight;
        const itemOffsetTop = activeItem.offsetTop;
        const itemHeight = activeItem.offsetHeight;
        const scrollTop = itemOffsetTop - (containerHeight / 2) + (itemHeight / 2);
        node.scrollTop = Math.max(0, scrollTop);
      }
    }
  };

  const hasActiveFilters = (showOwnerFilter && filterOptions.owner) || filterOptions.rarity || filterOptions.locked || filterOptions.characterName || filterOptions.setName;
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

  const handleFilterOptionClick = (type: 'owner' | 'rarity' | 'locked' | 'characterName' | 'setName') => {
    if (expandedFilter === type) {
      setExpandedFilter(null);
    } else {
      setExpandedFilter(type);
    }
  };

  const handleFilterSelect = <K extends keyof FilterOptions>(key: K, value: FilterOptions[K]) => {
    onFilterChange({
      ...filterOptions,
      [key]: value
    });
  };

  const handleClearFilters = () => {
    onFilterChange({
      owner: '',
      rarity: '',
      locked: '',
      characterName: '',
      setName: ''
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
            <div className="filter-dropdown-wrapper">
              <div className="dropdown filter-dropdown">
                <div className="dropdown-content" ref={dropdownContentRef}>
                  {showOwnerFilter && (
                    <div className="dropdown-item" ref={el => { categoryItemRefs.current['owner'] = el; }}>
                      <button 
                        className={`dropdown-main-option ${expandedFilter === 'owner' ? 'selected' : ''} ${filterOptions.owner ? 'has-filter' : ''}`}
                        onClick={() => handleFilterOptionClick('owner')}
                      >
                        <span>Owner</span>
                        <svg className={`expand-icon ${expandedFilter === 'owner' ? 'rotated' : ''}`} viewBox="0 0 24 24">
                          <path d="M8.59,16.58L13.17,12L8.59,7.41L10,6L16,12L10,18L8.59,16.58Z"/>
                        </svg>
                      </button>
                    </div>
                  )}

                  <div className="dropdown-item" ref={el => { categoryItemRefs.current['rarity'] = el; }}>
                    <button 
                      className={`dropdown-main-option ${expandedFilter === 'rarity' ? 'selected' : ''} ${filterOptions.rarity ? 'has-filter' : ''}`}
                      onClick={() => handleFilterOptionClick('rarity')}
                    >
                      <span>Rarity</span>
                      <svg className={`expand-icon ${expandedFilter === 'rarity' ? 'rotated' : ''}`} viewBox="0 0 24 24">
                        <path d="M8.59,16.58L13.17,12L8.59,7.41L10,6L16,12L10,18L8.59,16.58Z"/>
                      </svg>
                    </button>
                  </div>

                  <div className="dropdown-item" ref={el => { categoryItemRefs.current['locked'] = el; }}>
                    <button 
                      className={`dropdown-main-option ${expandedFilter === 'locked' ? 'selected' : ''} ${filterOptions.locked ? 'has-filter' : ''}`}
                      onClick={() => handleFilterOptionClick('locked')}
                    >
                      <span>Status</span>
                      <svg className={`expand-icon ${expandedFilter === 'locked' ? 'rotated' : ''}`} viewBox="0 0 24 24">
                        <path d="M8.59,16.58L13.17,12L8.59,7.41L10,6L16,12L10,18L8.59,16.58Z"/>
                      </svg>
                    </button>
                  </div>

                  <div className="dropdown-item" ref={el => { categoryItemRefs.current['characterName'] = el; }}>
                    <button 
                      className={`dropdown-main-option ${expandedFilter === 'characterName' ? 'selected' : ''} ${filterOptions.characterName ? 'has-filter' : ''}`}
                      onClick={() => handleFilterOptionClick('characterName')}
                    >
                      <span>Character</span>
                      <svg className={`expand-icon ${expandedFilter === 'characterName' ? 'rotated' : ''}`} viewBox="0 0 24 24">
                        <path d="M8.59,16.58L13.17,12L8.59,7.41L10,6L16,12L10,18L8.59,16.58Z"/>
                      </svg>
                    </button>
                  </div>

                  {uniqueSetNames.length > 0 && (
                    <div className="dropdown-item" ref={el => { categoryItemRefs.current['setName'] = el; }}>
                      <button 
                        className={`dropdown-main-option ${expandedFilter === 'setName' ? 'selected' : ''} ${filterOptions.setName ? 'has-filter' : ''}`}
                        onClick={() => handleFilterOptionClick('setName')}
                      >
                        <span>Set</span>
                        <svg className={`expand-icon ${expandedFilter === 'setName' ? 'rotated' : ''}`} viewBox="0 0 24 24">
                          <path d="M8.59,16.58L13.17,12L8.59,7.41L10,6L16,12L10,18L8.59,16.58Z"/>
                        </svg>
                      </button>
                    </div>
                  )}

                  {hasActiveFilters && (
                    <div className="dropdown-item">
                      <button 
                        className="dropdown-main-option clear-option"
                        onClick={handleClearFilters}
                      >
                        Clear
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Submenu appears to the right */}
              {expandedFilter === 'owner' && (
                <div className="dropdown-submenu" style={{ '--submenu-offset': `${getSubmenuOffset()}px` } as React.CSSProperties}>
                  <div className="dropdown-submenu-content" ref={submenuContentRef}>
                    <button 
                      className={`dropdown-subitem ${!filterOptions.owner ? 'active' : ''}`}
                      onClick={() => handleFilterSelect('owner', '')}
                    >
                      All owners
                    </button>
                    {uniqueOwners.map(owner => (
                      <button
                        key={owner}
                        className={`dropdown-subitem ${filterOptions.owner === owner ? 'active' : ''}`}
                        onClick={() => handleFilterSelect('owner', owner)}
                      >
                        {owner}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {expandedFilter === 'rarity' && (
                <div className="dropdown-submenu" style={{ '--submenu-offset': `${getSubmenuOffset()}px` } as React.CSSProperties}>
                  <div className="dropdown-submenu-content" ref={submenuContentRef}>
                    <button 
                      className={`dropdown-subitem ${!filterOptions.rarity ? 'active' : ''}`}
                      onClick={() => handleFilterSelect('rarity', '')}
                    >
                      All rarities
                    </button>
                    {uniqueRarities.map(rarity => (
                      <button
                        key={rarity}
                        className={`dropdown-subitem ${filterOptions.rarity === rarity ? 'active' : ''}`}
                        onClick={() => handleFilterSelect('rarity', rarity)}
                      >
                        {rarity}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {expandedFilter === 'locked' && (
                <div className="dropdown-submenu" style={{ '--submenu-offset': `${getSubmenuOffset()}px` } as React.CSSProperties}>
                  <div className="dropdown-submenu-content" ref={submenuContentRef}>
                    <button 
                      className={`dropdown-subitem ${!filterOptions.locked ? 'active' : ''}`}
                      onClick={() => handleFilterSelect('locked', '')}
                    >
                      Any
                    </button>
                    <button
                      className={`dropdown-subitem ${filterOptions.locked === 'locked' ? 'active' : ''}`}
                      onClick={() => handleFilterSelect('locked', 'locked')}
                    >
                      Locked
                    </button>
                    <button
                      className={`dropdown-subitem ${filterOptions.locked === 'unlocked' ? 'active' : ''}`}
                      onClick={() => handleFilterSelect('locked', 'unlocked')}
                    >
                      Unlocked
                    </button>
                  </div>
                </div>
              )}

              {expandedFilter === 'characterName' && (
                <div className="dropdown-submenu" style={{ '--submenu-offset': `${getSubmenuOffset()}px` } as React.CSSProperties}>
                  <div className="dropdown-submenu-content" ref={submenuContentRef}>
                    <button 
                      className={`dropdown-subitem ${!filterOptions.characterName ? 'active' : ''}`}
                      onClick={() => handleFilterSelect('characterName', '')}
                    >
                      All characters
                    </button>
                    {uniqueCharacterNames.map(name => (
                      <button
                        key={name}
                        className={`dropdown-subitem ${filterOptions.characterName === name ? 'active' : ''}`}
                        onClick={() => handleFilterSelect('characterName', name)}
                      >
                        {name}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {expandedFilter === 'setName' && (
                <div className="dropdown-submenu" style={{ '--submenu-offset': `${getSubmenuOffset()}px` } as React.CSSProperties}>
                  <div className="dropdown-submenu-content" ref={submenuContentRef}>
                    <button 
                      className={`dropdown-subitem ${!filterOptions.setName ? 'active' : ''}`}
                      onClick={() => handleFilterSelect('setName', '')}
                    >
                      All sets
                    </button>
                    {uniqueSetNames.map(setName => (
                      <button
                        key={setName}
                        className={`dropdown-subitem ${filterOptions.setName === setName ? 'active' : ''}`}
                        onClick={() => handleFilterSelect('setName', setName)}
                      >
                        {setName}
                      </button>
                    ))}
                  </div>
                </div>
              )}
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