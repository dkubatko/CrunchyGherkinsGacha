import { useState, useEffect } from 'react';
import type { CardData } from '../types';

interface UseModalResult {
  showModal: boolean;
  modalCard: CardData | null;
  openModal: (card: CardData) => void;
  closeModal: () => void;
}

export const useModal = (): UseModalResult => {
  const [showModal, setShowModal] = useState(false);
  const [modalCard, setModalCard] = useState<CardData | null>(null);

  const openModal = (card: CardData) => {
    setModalCard(card);
    setShowModal(true);
  };

  const closeModal = () => {
    setShowModal(false);
    setModalCard(null);
  };

  // Handle Escape key to close modal
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && showModal) {
        closeModal();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [showModal]);

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (showModal) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }

    return () => {
      document.body.style.overflow = '';
    };
  }, [showModal]);

  return {
    showModal,
    modalCard,
    openModal,
    closeModal
  };
};