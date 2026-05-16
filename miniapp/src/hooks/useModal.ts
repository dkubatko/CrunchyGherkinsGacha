import { useCallback, useEffect, useState } from 'react';

interface UseModalResult<T> {
  showModal: boolean;
  modalItem: T | null;
  openModal: (item: T) => void;
  closeModal: () => void;
  /** Toggle modal visibility without clearing the item — used by flows
   *  that temporarily hide the modal (e.g. overlay a sub-dialog) and
   *  later reopen it with the same item. */
  setOpen: (open: boolean) => void;
  updateModalItem: (updates: Partial<T>) => void;
}

export function useModal<T>(): UseModalResult<T> {
  const [showModal, setShowModal] = useState(false);
  const [modalItem, setModalItem] = useState<T | null>(null);

  const openModal = useCallback((item: T) => {
    setModalItem(item);
    setShowModal(true);
  }, []);

  const closeModal = useCallback(() => {
    setShowModal(false);
    setModalItem(null);
  }, []);

  const setOpen = useCallback((open: boolean) => {
    setShowModal(open);
  }, []);

  const updateModalItem = useCallback((updates: Partial<T>) => {
    setModalItem(prev => prev ? { ...prev, ...updates } : null);
  }, []);

  // Close on Escape
  useEffect(() => {
    if (!showModal) return;
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeModal();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [showModal, closeModal]);

  // Lock body scroll while open
  useEffect(() => {
    if (showModal) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [showModal]);

  return { showModal, modalItem, openModal, closeModal, setOpen, updateModalItem };
}
